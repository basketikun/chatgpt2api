"""Gemini Web login (gemini.google.com via Google account).

Reuses auto_login.do_google_login_steps for the email/password/2FA dance.

Unlike ChatGPT Web (which scrapes /api/auth/session for a JWT), Gemini
Web doesn't expose a standalone bearer token — everything goes through
the logged-in browser session. So instead of returning an access_token,
this module just confirms the profile has a valid Gemini session and
the chat / image / music capabilities can read/write the page.

The actual chat / image / music handlers live in solvers/gemini_web.py
and operate on the persistent browser context.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

from .auto_login import (
    LoginSession,
    _already_logged_in,
    do_google_login_steps,
)
from .browser_pool import pool

logger = logging.getLogger(__name__)


_GEMINI_HOME = "https://gemini.google.com/"
# Cookies that prove a logged-in Gemini session (subset of Google's).
_GEMINI_LOGIN_COOKIES = ("__Secure-1PSID", "__Secure-3PSID", "SID")


@dataclass
class GeminiWebLoginSession(LoginSession):
    """No access_token — Gemini Web only confirms the session is alive."""
    pass


_sessions: dict[str, GeminiWebLoginSession] = {}
_tasks: dict[str, asyncio.Task] = {}


def get_session(profile: str) -> Optional[GeminiWebLoginSession]:
    return _sessions.get(profile)


def submit_2fa_code(profile: str, code: str) -> bool:
    session = _sessions.get(profile)
    if not session or session.state != "need_code":
        return False
    session.pending_code = code.strip()
    session.message = "Đã nhận mã, đang submit..."
    return True


async def start_gemini_web_login(profile: str, email: str, password: str) -> GeminiWebLoginSession:
    """Kick off background Gemini Web login.

    If the profile already has a valid Google session (from Flow or
    ChatGPT onboard), this short-circuits to success without re-running
    the email/password flow — Gemini just uses Google's SSO cookie.
    """
    old_task = _tasks.pop(profile, None)
    if old_task and not old_task.done():
        old_task.cancel()

    session = GeminiWebLoginSession(
        profile=profile,
        email=email,
        state="starting",
        message="Khởi tạo Chrome",
    )
    _sessions[profile] = session

    task = asyncio.create_task(_run(session, password))
    _tasks[profile] = task
    return session


async def _gemini_session_ready(page) -> bool:
    """Check if gemini.google.com is loaded + the user prompt input is
    visible (= logged in + Gemini app hydrated)."""
    try:
        # Gemini's prompt input is a contenteditable with class rich-textarea
        # OR a textarea with placeholder. Selectors change between A/B tests
        # so we match the largest visible contenteditable.
        ready = await page.evaluate(
            """() => {
                const ces = Array.from(document.querySelectorAll('[contenteditable=true]'));
                return ces.some(e => e.offsetWidth > 200 && e.offsetHeight > 0);
            }"""
        )
        return bool(ready)
    except Exception:
        return False


async def _run(session: GeminiWebLoginSession, password: str) -> None:
    try:
        session.state = "starting"
        session.message = "Đang mở Chrome (headful → noVNC)"
        ctx = await pool.get(profile=session.profile, headless=False, force_recreate=True)

        pages = ctx.pages
        page = pages[0] if pages else await ctx.new_page()
        try:
            await page.bring_to_front()
        except Exception:
            pass

        session.state = "running"
        session.message = "Mở gemini.google.com..."
        await page.goto(_GEMINI_HOME, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(3.0)  # let any client-side redirects settle

        # If we land on gemini.google.com and the chat input is ready,
        # we're logged in (Google SSO via persistent cookies).
        if await _gemini_session_ready(page):
            session.state = "success"
            session.message = "Profile đã có Gemini session — không cần đăng nhập"
            session.completed_at = time.time()
            return

        # Otherwise we got redirected to accounts.google.com for login.
        try:
            on_google = "accounts.google.com" in page.url
        except Exception:
            on_google = False

        if on_google:
            ok = await do_google_login_steps(session, page, ctx, password)
            if not ok:
                return  # state/error set by helper

            # After Google login, wait for redirect back to gemini.google.com.
            try:
                await page.wait_for_url("**/gemini.google.com/**", timeout=30_000)
            except Exception:
                logger.warning("gemini_login: no return to gemini.google.com (url=%s)",
                                getattr(page, "url", "?"))
            await asyncio.sleep(2.0)

        # Verify Gemini is ready.
        for _ in range(20):  # up to 20s of polling for hydration
            if await _gemini_session_ready(page):
                session.state = "success"
                session.message = "Đăng nhập Gemini Web thành công"
                session.completed_at = time.time()
                return
            await asyncio.sleep(1.0)

        # Fall back — if any Google login cookies are present, treat as
        # success and let the chat handler retry hydration on its own call.
        if await _already_logged_in(ctx):
            session.state = "success"
            session.message = "Login OK nhưng Gemini chưa hydrate — sẽ retry khi chat"
            session.completed_at = time.time()
            return

        session.state = "failed"
        session.error = f"Không thấy Gemini app sẵn sàng (url={getattr(page, 'url', '?')})"
        session.completed_at = time.time()

    except asyncio.CancelledError:
        session.state = "failed"
        session.error = "Bị huỷ (có yêu cầu login mới)"
        session.completed_at = time.time()
        raise
    except Exception as exc:
        logger.exception("gemini_web_login crashed profile=%s", session.profile)
        session.state = "failed"
        session.error = str(exc)
        session.completed_at = time.time()
