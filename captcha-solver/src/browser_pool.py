"""Patchright browser pool with per-profile persistent contexts.

Each "profile" is a directory under settings.data_dir/profiles/<name>/ that
Patchright treats as user-data-dir. Cookies, localStorage, IndexedDB and
extension state persist across restarts so a one-time manual Google login
(via the headful VNC flow) keeps working for headless automation later.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from patchright.async_api import (
    BrowserContext,
    Playwright,
    async_playwright,
)

from .settings import settings

logger = logging.getLogger(__name__)


# Reasonable defaults to look like a real Chrome user. Patchright already
# strips automation flags and patches navigator properties; we just add a
# stable viewport so screenshots are consistent.
_DEFAULT_VIEWPORT = {"width": 1366, "height": 768}


class BrowserPool:
    """Holds one Playwright runtime and lazily creates persistent contexts
    on demand. Contexts are reused for the lifetime of the process and only
    closed on shutdown so noVNC clients can keep seeing the same browser
    window after a login completes."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._contexts: dict[str, BrowserContext] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            logger.info("playwright started")

    async def stop(self) -> None:
        for name, ctx in list(self._contexts.items()):
            try:
                await ctx.close()
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

    async def _lock_for(self, profile: str) -> asyncio.Lock:
        async with self._global_lock:
            lock = self._locks.get(profile)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[profile] = lock
            return lock

    async def _open_context(self, profile: str, headless: bool) -> BrowserContext:
        assert self._playwright is not None
        user_data_dir = self._profile_dir(profile)
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
        logger.info("opened context profile=%s headless=%s", profile, headless)
        return context

    async def get(self, profile: str = "default", headless: bool = True) -> BrowserContext:
        """Return a context for the given profile, creating one if needed.

        Contexts are NOT closed after a call so a manual-login session
        (headless=False) keeps the browser window alive for the user.
        """
        await self.start()
        lock = await self._lock_for(profile)
        async with lock:
            ctx = self._contexts.get(profile)
            if ctx is not None:
                return ctx
            ctx = await self._open_context(profile, headless=headless)
            self._contexts[profile] = ctx
            return ctx

    async def close_profile(self, profile: str) -> bool:
        lock = await self._lock_for(profile)
        async with lock:
            ctx = self._contexts.pop(profile, None)
            if ctx is None:
                return False
            try:
                await ctx.close()
            except Exception:
                pass
            return True

    @asynccontextmanager
    async def page(self, profile: str = "default", headless: bool = True) -> AsyncIterator:
        ctx = await self.get(profile=profile, headless=headless)
        page = await ctx.new_page()
        try:
            yield page
        finally:
            try:
                await page.close()
            except Exception:
                pass


pool = BrowserPool()
