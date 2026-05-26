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
    click_google_oauth_consent,
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
    """Check if Gemini Web is actually logged in.

    Gemini renders the chat editor even for anonymous users (preview
    mode), so contenteditable presence alone is a false positive.
    Reliable signal: absence of a top-bar 'Đăng nhập' / 'Sign in' button.
    """
    try:
        result = await page.evaluate(
            """() => {
                // Has prompt editor visible?
                const ces = Array.from(document.querySelectorAll('[contenteditable=true]'));
                const has_editor = ces.some(e => e.offsetWidth > 200 && e.offsetHeight > 0);
                if (!has_editor) return {ready: false, reason: 'no_editor'};

                // Find any visible 'Đăng nhập' / 'Sign in' / 'Log in' button.
                // If present, user is NOT logged in (preview mode).
                const buttons = Array.from(document.querySelectorAll('button, a'));
                const login_btn = buttons.find(b => {
                    if (b.offsetWidth === 0) return false;
                    const t = (b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase();
                    return t === 'đăng nhập' || t === 'sign in' || t === 'log in';
                });
                if (login_btn) return {ready: false, reason: 'login_button_visible'};

                // Look for a logged-in indicator: user avatar (usually
                // <img alt="Google Account"> or a button with class
                // gb_d / gb_g / similar Google account chip).
                const account_btn = document.querySelector(
                    'a[aria-label*="Google Account"], a[href*="accounts.google.com/SignOutOptions"], '
                    + 'img[alt*="Google Account"], a[aria-label*="Tài khoản Google"]'
                );
                return {ready: !!account_btn, reason: account_btn ? 'account_chip' : 'no_account_chip'};
            }"""
        )
        if isinstance(result, dict):
            logger.info("gemini_session_ready: %s", result)
            return bool(result.get("ready"))
        return False
    except Exception as exc:
        logger.warning("gemini_session_ready check failed: %s", exc)
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
        await asyncio.sleep(3.0)

        # If already authenticated (has account chip + no login button),
        # short-circuit to success.
        if await _gemini_session_ready(page):
            session.state = "success"
            session.message = "Profile đã có Gemini session — không cần đăng nhập"
            session.completed_at = time.time()
            return

        # Gemini renders preview mode for anonymous users — no auto-redirect
        # to login. Click the 'Đăng nhập' button to trigger the OAuth flow.
        session.message = "Click 'Đăng nhập' trên Gemini Web..."
        clicked = await page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button, a'));
                const btn = buttons.find(b => {
                    if (b.offsetWidth === 0) return false;
                    const t = (b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase();
                    return t === 'đăng nhập' || t === 'sign in' || t === 'log in';
                });
                if (!btn) return false;
                btn.click();
                return true;
            }
        """)
        if not clicked:
            session.state = "failed"
            session.error = "Không tìm thấy nút 'Đăng nhập' trên gemini.google.com"
            session.completed_at = time.time()
            return

        # Wait for redirect to accounts.google.com.
        try:
            await page.wait_for_url("**/accounts.google.com/**", timeout=20_000)
            logger.info("gemini_login: at google login page %s", page.url)
        except Exception:
            logger.warning("gemini_login: no accounts.google.com redirect after login click")

        try:
            on_google = "accounts.google.com" in page.url
        except Exception:
            on_google = False

        # Pre-consent: when Google has a session cookie for the profile,
        # it skips the email/password form and shows a one-button confirm
        # page. Click it first so do_google_login_steps doesn't fail on
        # the missing email input.
        try:
            pre_consent = await click_google_oauth_consent(page, timeout=6.0)
            if pre_consent:
                session.message = "Đã bấm OAuth consent..."
                await asyncio.sleep(2.0)
        except Exception:
            pre_consent = False

        if on_google and not pre_consent:
            ok = await do_google_login_steps(session, page, ctx, password)
            if not ok:
                return

            # Post-login consent — appears after fresh email/password too.
            try:
                if await click_google_oauth_consent(page, timeout=8.0):
                    session.message = "Đã bấm OAuth consent..."
                    await asyncio.sleep(2.0)
            except Exception as exc:
                logger.debug("gemini_login: consent click skipped: %s", str(exc)[:120])

            # After Google login, wait for redirect back to gemini.google.com.
            try:
                await page.wait_for_url("**/gemini.google.com/**", timeout=30_000)
            except Exception:
                logger.warning("gemini_login: no return to gemini (url=%s)",
                                getattr(page, "url", "?"))
            await asyncio.sleep(3.0)
        elif pre_consent:
            # Consent path: wait for redirect back to gemini.google.com.
            try:
                await page.wait_for_url("**/gemini.google.com/**", timeout=30_000)
            except Exception:
                logger.warning("gemini_login: consent path no return (url=%s)",
                                getattr(page, "url", "?"))
            await asyncio.sleep(3.0)

        # Verify Gemini is now actually logged in (account chip visible).
        for _ in range(20):
            if await _gemini_session_ready(page):
                session.state = "success"
                session.message = "Đăng nhập Gemini Web thành công"
                session.completed_at = time.time()
                return
            await asyncio.sleep(1.0)

        # Fall back — if Google login cookies present, treat as soft-success.
        if await _already_logged_in(ctx):
            session.state = "success"
            session.message = "Google OK nhưng Gemini chưa hydrate đủ — chat thử có thể work"
            session.completed_at = time.time()
            return

        session.state = "failed"
        session.error = f"Không thấy Gemini logged-in (url={getattr(page, 'url', '?')})"
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
