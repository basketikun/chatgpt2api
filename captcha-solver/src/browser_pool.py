"""Patchright browser pool with per-profile persistent contexts.

Each "profile" is a directory under settings.data_dir/profiles/<name>/ that
Patchright treats as user-data-dir. Cookies, localStorage, IndexedDB and
extension state persist across restarts so a one-time manual Google login
(via the headful VNC flow) keeps working for headless automation later.

Robustness:
  • Detects dead contexts (Chrome killed via VNC, crash, OOM) and re-creates.
  • Tracks the headless mode each context was launched with so a
    /v1/session/manual-login call (headless=False) never re-uses a cached
    headless context — would cause noVNC to show an empty desktop because
    the live Chrome window is in another (headless) display.
  • Removes Chrome's SingletonLock / SingletonSocket / SingletonCookie
    leftover files in the user-data-dir before re-launching, otherwise
    the new Chrome refuses to start ("profile is already in use").
  • Subscribes to context.on("close") so user-driven window closes (clicking
    [X] in VNC) immediately drop the cache instead of waiting for the next
    call to detect it dead.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from patchright.async_api import (
    BrowserContext,
    Playwright,
    async_playwright,
)

from .settings import settings

logger = logging.getLogger(__name__)


_DEFAULT_VIEWPORT = {"width": 1366, "height": 768}
# Chrome single-instance lock files that linger after a crash and block
# the next launch with "Profile is already in use".
_CHROME_LOCK_FILES = ("SingletonLock", "SingletonSocket", "SingletonCookie")


@dataclass
class _PoolEntry:
    ctx: BrowserContext
    headless: bool


class BrowserPool:
    """Holds one Playwright runtime and lazily creates persistent contexts
    on demand. Contexts are reused for the lifetime of the process and only
    closed on shutdown so noVNC clients can keep seeing the same browser
    window after a login completes."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._contexts: dict[str, _PoolEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            logger.info("playwright started")

    async def stop(self) -> None:
        for name, entry in list(self._contexts.items()):
            try:
                await entry.ctx.close()
            except Exception:
                pass
        self._contexts.clear()
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    def _profile_dir(self, profile: str) -> Path:
        path = settings.data_dir / "profiles" / profile
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _clear_singleton_locks(self, profile: str) -> None:
        """Remove Chrome lock files left by a previous crash."""
        root = self._profile_dir(profile)
        for name in _CHROME_LOCK_FILES:
            try:
                p = root / name
                if p.exists() or p.is_symlink():
                    p.unlink()
                    logger.info("cleared stale chrome lock profile=%s file=%s", profile, name)
            except Exception as exc:
                logger.debug("could not unlink %s: %s", name, exc)

    async def _lock_for(self, profile: str) -> asyncio.Lock:
        async with self._global_lock:
            lock = self._locks.get(profile)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[profile] = lock
            return lock

    async def _is_alive(self, ctx: BrowserContext) -> bool:
        """Quick liveness probe — cookies() round-trips to the Chrome target,
        so a dead/disconnected context throws immediately."""
        try:
            await asyncio.wait_for(ctx.cookies(), timeout=2.5)
            return True
        except Exception as exc:
            logger.info("context liveness probe failed: %s", exc)
            return False

    def _attach_close_handler(self, profile: str, ctx: BrowserContext) -> None:
        """Drop cache entry the moment Chrome (or the user clicking [X] in
        VNC) closes the context. Saves us a liveness round-trip later."""
        def _on_close():
            entry = self._contexts.get(profile)
            if entry is not None and entry.ctx is ctx:
                self._contexts.pop(profile, None)
                logger.info("context closed (auto-drop) profile=%s", profile)
        try:
            ctx.on("close", _on_close)
        except Exception:
            pass

    async def _open_context(self, profile: str, headless: bool) -> BrowserContext:
        assert self._playwright is not None
        user_data_dir = self._profile_dir(profile)
        self._clear_singleton_locks(profile)
        # Patchright maintainers strongly recommend NOT passing args like
        # --disable-blink-features=AutomationControlled / --no-sandbox: the
        # stealth patches handle those internally and Cloudflare specifically
        # fingerprints those flags as bot indicators. We pass only DISPLAY
        # for headful mode and nothing else.
        env = None
        if not headless:
            env = {"DISPLAY": settings.display}
        context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            channel="chrome",  # real Google Chrome — best stealth profile
            headless=headless,
            no_viewport=False,
            viewport=_DEFAULT_VIEWPORT,
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
            env=env,
        )
        self._attach_close_handler(profile, context)
        logger.info("opened context profile=%s headless=%s", profile, headless)
        return context

    async def _evict(self, profile: str) -> None:
        """Drop + close a cached context (called when stale or mode-mismatched)."""
        entry = self._contexts.pop(profile, None)
        if entry is not None:
            try:
                await entry.ctx.close()
            except Exception:
                pass

    async def get(
        self,
        profile: str = "default",
        headless: bool = True,
        force_recreate: bool = False,
    ) -> BrowserContext:
        """Return a context for the given profile, creating one if needed.

        Contexts are NOT closed after a call so a manual-login session
        (headless=False) keeps the browser window alive for the user.

        If `force_recreate=True`, any cached context is closed and a fresh
        one is launched — useful when the UI offers a "restart browser"
        button or when the headless/headful mode changes.
        """
        await self.start()
        lock = await self._lock_for(profile)
        async with lock:
            entry = self._contexts.get(profile)
            if entry is not None and not force_recreate:
                # Reuse only when the mode matches AND the context is still alive.
                if entry.headless == headless and await self._is_alive(entry.ctx):
                    return entry.ctx
                logger.info(
                    "evicting stale context profile=%s reason=%s",
                    profile,
                    "mode_mismatch" if entry.headless != headless else "dead",
                )
                await self._evict(profile)
            elif force_recreate and entry is not None:
                logger.info("force-recreate profile=%s", profile)
                await self._evict(profile)

            ctx = await self._open_context(profile, headless=headless)
            self._contexts[profile] = _PoolEntry(ctx=ctx, headless=headless)
            return ctx

    async def close_profile(self, profile: str) -> bool:
        lock = await self._lock_for(profile)
        async with lock:
            entry = self._contexts.pop(profile, None)
            if entry is None:
                return False
            try:
                await entry.ctx.close()
            except Exception:
                pass
            return True

    def is_loaded(self, profile: str) -> bool:
        return profile in self._contexts

    def get_cached(self, profile: str) -> BrowserContext | None:
        entry = self._contexts.get(profile)
        return entry.ctx if entry else None

    @asynccontextmanager
    async def page(self, profile: str = "default", headless: bool = True) -> AsyncIterator:
        ctx = await self.get(profile=profile, headless=headless)
        page = await ctx.new_page()
        _attach_model_tracker(page, profile)
        try:
            yield page
        finally:
            try:
                await page.close()
            except Exception:
                pass


def _attach_model_tracker(page, profile: str) -> None:
    """Subscribe to network responses on `page` and pipe the bodies of
    Gemini Web / ChatGPT Web RPC frames through the passive model
    tracker. New model names ("Nano Banana 3", "Lyria 2", ...) get
    learned the first time the user's account actually uses them, so
    the /v1/models catalogue keeps up with upstream renames without
    code edits.

    Best-effort: any failure inside the handler is swallowed so a
    misbehaving response can't break the chat / image / music flows
    we're sharing the page with.
    """
    try:
        from .solvers.model_tracker import extract_gemini_models, record
    except Exception:
        return

    async def _handler(response):
        try:
            url = response.url
            if "BardChatUi" in url or "/_/BardChatUi" in url or "gemini.google.com" in url:
                provider = "gemini_web"
            elif "chatgpt.com" in url and "backend-api" in url:
                provider = "chatgpt_web"
            else:
                return
            # Only inspect text-like content — image binaries are noise.
            ct = (response.headers.get("content-type") or "").lower()
            if "json" not in ct and "javascript" not in ct and "text" not in ct:
                return
            try:
                body = await response.text()
            except Exception:
                return
            for name in extract_gemini_models(body):
                record(provider, profile, name)
        except Exception:
            pass

    try:
        page.on("response", _handler)
    except Exception as exc:
        logger.debug("model tracker hook failed: %s", exc)


pool = BrowserPool()
