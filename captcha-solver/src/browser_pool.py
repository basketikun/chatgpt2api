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
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Any

from patchright.async_api import BrowserContext
try:
    from cloakbrowser import launch_persistent_context_async as _cloak_launch
    _CLOAK_AVAILABLE = True
except ImportError:
    _CLOAK_AVAILABLE = False
    from patchright.async_api import (
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
    page: Any
    headless: bool
    last_used: float = 0.0


class BrowserPool:
    """Holds one Playwright runtime and lazily creates persistent contexts
    on demand. Contexts are reused for the lifetime of the process and only
    closed on shutdown so noVNC clients can keep seeing the same browser
    window after a login completes."""

    def __init__(self) -> None:
        self._playwright = None
        self._contexts: dict[str, _PoolEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._evict_task: asyncio.Task | None = None

    async def start(self) -> None:
        if _CLOAK_AVAILABLE:
            # CloakBrowser doesn't need a playwright runtime — it manages its own binary
            if self._evict_task is None:
                self._evict_task = asyncio.create_task(self._eviction_loop())
            logger.info("cloakbrowser ready (stealth mode, Cloudflare bypass enabled)")
            return
        if self._playwright is None:
            from patchright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._evict_task = asyncio.create_task(self._eviction_loop())
            logger.info("playwright started (fallback mode)")

    async def stop(self) -> None:
        if self._evict_task:
            self._evict_task.cancel()
        for name, entry in list(self._contexts.items()):
            try:
                await entry.ctx.close()
            except Exception:
                pass
        self._contexts.clear()
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def _eviction_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(60)
                now = time.time()
                to_evict = []
                async with self._global_lock:
                    for profile, entry in list(self._contexts.items()):
                        # Warm-pool: keep tabs alive 30 min idle (was 10 min).
                        # The prewarmer re-warms every 25 min so a healthy
                        # warmed profile never sees this branch.
                        if now - entry.last_used > 1800:
                            lock = self._locks.get(profile)
                            if lock and not lock.locked():
                                to_evict.append(profile)
                for profile in to_evict:
                    lock = await self._lock_for(profile)
                    if not lock.locked():
                        async with lock:
                            entry = self._contexts.get(profile)
                            if entry and now - entry.last_used > 1800:
                                logger.info("auto-evicting idle profile=%s", profile)
                                await self._evict(profile)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("eviction loop error: %s", e)

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

    def _clear_crash_flag(self, profile: str) -> None:
        """Patch Default/Preferences to set exit_type=Normal so Chrome/Chromium
        does NOT show the 'Restore pages?' dialog on next launch.
        This is the most reliable way — the --disable-session-crashed-bubble flag
        only works on real Chrome, not on Chromium-based builds like CloakBrowser.
        """
        import json as _json
        prefs_file = self._profile_dir(profile) / "Default" / "Preferences"
        if not prefs_file.exists():
            return
        try:
            data = _json.loads(prefs_file.read_text(encoding="utf-8"))
            profile_data = data.get("profile", {})
            if profile_data.get("exit_type") not in ("Normal", "SessionEnded"):
                profile_data["exit_type"] = "Normal"
                profile_data["exited_cleanly"] = True
                data["profile"] = profile_data
                prefs_file.write_text(_json.dumps(data), encoding="utf-8")
                logger.info("cleared crash flag profile=%s", profile)
        except Exception as exc:
            logger.debug("could not clear crash flag %s: %s", profile, exc)

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

    async def _open_context(self, profile: str, headless: bool) -> tuple[BrowserContext, Any]:
        user_data_dir = self._profile_dir(profile)
        self._clear_singleton_locks(profile)
        self._clear_crash_flag(profile)  # Prevent "Restore pages?" dialog
        env = None
        if not headless:
            env = {"DISPLAY": settings.display}
        
        if _CLOAK_AVAILABLE:
            # CloakBrowser: source-level Chromium patches, passes Cloudflare Turnstile automatically
            # Set DISPLAY before launch (env= param not supported by cloakbrowser API)
            if env:
                import os as _os
                for k, v in env.items():
                    _os.environ[k] = v
            context = await _cloak_launch(
                user_data_dir=str(user_data_dir),
                headless=headless,
                viewport=_DEFAULT_VIEWPORT,
                locale="vi-VN",
                timezone="Asia/Ho_Chi_Minh",
                # backend='patchright' suppresses CDP signals → better Turnstile score
                backend='patchright',
                humanize=True,  # human-like mouse/keyboard behavior → passes 24/24 behavioral signals
                human_preset='careful',  # extra-careful preset for max stealth
                args=[
                    "--no-first-run",
                    "--disable-session-crashed-bubble",
                    "--disable-infobars",
                    "--no-default-browser-check",
                ],
            )
        else:
            # Fallback to patchright (Google Chrome channel)
            assert self._playwright is not None
            context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                channel="chrome",
                headless=headless,
                no_viewport=False,
                viewport=_DEFAULT_VIEWPORT,
                locale="vi-VN",
                timezone_id="Asia/Ho_Chi_Minh",
                env=env,
                args=[
                    "--no-first-run",
                    "--disable-session-crashed-bubble",
                    "--disable-infobars",
                    "--no-default-browser-check",
                ],
                ignore_default_args=["--enable-automation"],
            )
        
        self._attach_close_handler(profile, context)
        pages = context.pages
        page = pages[0] if pages else await context.new_page()
        mode = "cloakbrowser" if _CLOAK_AVAILABLE else "patchright"
        logger.info("opened context profile=%s headless=%s engine=%s", profile, headless, mode)
        return context, page

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
                    entry.last_used = time.time()
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

            ctx, page = await self._open_context(profile, headless=headless)
            self._contexts[profile] = _PoolEntry(ctx=ctx, page=page, headless=headless, last_used=time.time())
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
        await self.start()
        lock = await self._lock_for(profile)
        # Fast Failover: if the profile is already busy, refuse immediately
        # with HTTP 429 so the upstream chatgpt2api router rotates to the
        # next account (web_proxy.AccountBusyError → next profile in loop).
        # Queuing on a single account just stacks latency.
        if lock.locked():
            from fastapi import HTTPException
            logger.info("fast-failover profile=%s already busy → 429", profile)
            raise HTTPException(status_code=429, detail="Account Busy")
        await lock.acquire()
        try:
            entry = self._contexts.get(profile)
            if entry is not None:
                if entry.headless != headless or not await self._is_alive(entry.ctx):
                    await self._evict(profile)
                    entry = None
            if entry is None:
                ctx, p = await self._open_context(profile, headless=headless)
                _attach_model_tracker(p, profile)
                entry = _PoolEntry(ctx=ctx, page=p, headless=headless, last_used=time.time())
                self._contexts[profile] = entry
                
            entry.last_used = time.time()
            try:
                yield entry.page
            finally:
                entry.last_used = time.time()
        finally:
            lock.release()


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
