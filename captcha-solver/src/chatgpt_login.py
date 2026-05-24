"""ChatGPT login via Google account (chat.openai.com → "Continue with Google").

Reuses the Google email/password/2FA dance from auto_login.do_google_login_steps
so a single Google auto-login mechanism powers both Google Labs Flow and ChatGPT.

End-to-end:
  1. Force-create a Chrome context on the requested profile.
  2. Navigate to https://chatgpt.com (redirects to login page).
  3. Click "Log in" → "Continue with Google".
  4. The OAuth redirect lands on accounts.google.com → run the shared
     Google login steps (email, password, 2FA).
  5. After Google success, browser redirects back through auth.openai.com
     and lands on chatgpt.com authenticated.
  6. GET https://chatgpt.com/api/auth/session → parse JSON → extract
     `accessToken`, `expires`, `user.email`. Save to session state.

Caller (HTTP endpoint or CLI) then takes the returned access_token and
adds it to chatgpt2api's account pool. The accessToken is a JWT with
audience "chatgpt.com" so chatgpt2api routes it as a ChatGPT-free
account automatically.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .auto_login import (
    LoginSession,
    _already_logged_in,
    _safe_click,
    do_google_login_steps,
    submit_2fa_code as _submit_2fa_code,
)
from .browser_pool import pool

logger = logging.getLogger(__name__)


# ChatGPT entry points — we navigate to chatgpt.com first, which redirects
# unauthenticated users to the login picker.
_CHATGPT_HOME = "https://chatgpt.com/"
_CHATGPT_AUTH_SESSION = "https://chatgpt.com/api/auth/session"

# Selectors for the chat.openai.com / auth.openai.com login UI.
# Order matters — try most specific first.
_LOGIN_BUTTON_SELECTORS = (
    'a[data-testid="login-button"]',
    'button[data-testid="login-button"]',
    'a:has-text("Log in")',
    'button:has-text("Log in")',
    'a:has-text("Đăng nhập")',
)
_CONTINUE_WITH_GOOGLE_SELECTORS = (
    'button[data-provider="google"]',
    'button:has-text("Continue with Google")',
    'a:has-text("Continue with Google")',
    'button:has-text("Tiếp tục với Google")',
)


@dataclass
class ChatGPTLoginSession(LoginSession):
    """Extends LoginSession with the captured access_token + expiry."""
    access_token: Optional[str] = None
    expires: Optional[str] = None
    captured_email: Optional[str] = None  # email Google returned (may differ from input)

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "access_token": self.access_token,
            "expires": self.expires,
            "captured_email": self.captured_email,
            # Truncated preview for log/UI readability
            "access_token_preview": (
                f"{self.access_token[:18]}...{self.access_token[-6:]}"
                if self.access_token else None
            ),
        })
        return base


_sessions: dict[str, ChatGPTLoginSession] = {}
_tasks: dict[str, asyncio.Task] = {}


def get_session(profile: str) -> Optional[ChatGPTLoginSession]:
    return _sessions.get(profile)


def submit_2fa_code(profile: str, code: str) -> bool:
    session = _sessions.get(profile)
    if not session or session.state != "need_code":
        return False
    session.pending_code = code.strip()
    session.message = "Đã nhận mã, đang submit..."
    return True


async def start_chatgpt_login(profile: str, email: str, password: str) -> ChatGPTLoginSession:
    """Kick off background ChatGPT-via-Google login. Returns the session
    object immediately; callers poll get_session(profile) for progress."""
    old_task = _tasks.pop(profile, None)
    if old_task and not old_task.done():
        old_task.cancel()

    session = ChatGPTLoginSession(
        profile=profile,
        email=email,
        state="starting",
        message="Khởi tạo Chrome",
    )
    _sessions[profile] = session

    task = asyncio.create_task(_run(session, password))
    _tasks[profile] = task
    return session


async def _click_one(page, selectors, *, timeout: int = 5000) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


async def _scrape_session(page) -> dict | None:
    """GET chatgpt.com/api/auth/session — returns the parsed JSON or None.

    Uses page.evaluate(fetch) instead of page.goto because the response
    is application/json, and goto would render it as text and lose
    cookies after navigation. fetch() within the page context keeps the
    SameSite=strict session cookies intact.
    """
    try:
        result = await page.evaluate(
            """
            async (url) => {
                const r = await fetch(url, { credentials: 'include' });
                const text = await r.text();
                try { return {status: r.status, json: JSON.parse(text)}; }
                catch { return {status: r.status, text: text.slice(0, 500)}; }
            }
            """,
            _CHATGPT_AUTH_SESSION,
        )
        if isinstance(result, dict) and result.get("status") == 200:
            return result.get("json")
        logger.warning("chatgpt /api/auth/session HTTP %s: %s",
                        result.get("status"), result.get("text") or result.get("json"))
        return None
    except Exception as exc:
        logger.warning("chatgpt /api/auth/session fetch failed: %s", exc)
        return None


async def _run(session: ChatGPTLoginSession, password: str) -> None:
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
        session.message = "Mở chatgpt.com..."
        await page.goto(_CHATGPT_HOME, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(2.0)  # let any client-side redirect settle

        # If already authenticated, just scrape session and finish.
        scraped = await _scrape_session(page)
        if scraped and scraped.get("accessToken"):
            user_email = (scraped.get("user") or {}).get("email")
            session.access_token = scraped["accessToken"]
            session.expires = str(scraped.get("expires") or "")
            session.captured_email = user_email
            session.state = "success"
            session.message = f"Đã có session ChatGPT — captured (email={user_email})"
            session.completed_at = time.time()
            return

        # Not authenticated — click "Log in" then "Continue with Google".
        session.message = "Click 'Log in'..."
        if not await _click_one(page, _LOGIN_BUTTON_SELECTORS, timeout=8000):
            # On the login picker page directly, no "Log in" button
            # — try "Continue with Google" right away.
            logger.info("no Log in button visible — assuming on picker page")

        await asyncio.sleep(1.5)

        session.message = "Click 'Continue with Google'..."
        if not await _click_one(page, _CONTINUE_WITH_GOOGLE_SELECTORS, timeout=10_000):
            session.state = "failed"
            session.error = "Không tìm thấy nút 'Continue with Google' trên trang login ChatGPT"
            session.completed_at = time.time()
            return

        # Wait for Google's OAuth screen to take over.
        try:
            await page.wait_for_url("**/accounts.google.com/**", timeout=20_000)
        except Exception:
            # Some routes go directly to a session-picker; if user has only one
            # Google account already in the browser, Google auto-redirects back.
            # Keep going — _scrape_session will tell us if we ended up logged in.
            pass

        # If we landed on Google's account chooser (multi-account), click the
        # matching email if visible. Otherwise let the email-step handle it.
        try:
            chooser = page.locator(f'div[data-email="{session.email}"], '
                                    f'div[data-identifier="{session.email}"], '
                                    f'li:has-text("{session.email}")').first
            if await chooser.count() > 0:
                await chooser.click(timeout=3000)
                logger.info("chatgpt_login: clicked account chooser entry")
                await asyncio.sleep(2.0)
        except Exception:
            pass

        # If still on Google's email step (no existing session), drive it.
        try:
            on_google = "accounts.google.com" in page.url
        except Exception:
            on_google = False
        if on_google:
            ok = await do_google_login_steps(session, page, ctx, password)
            if not ok:
                return  # state/error already set

        # Wait for redirect back to chatgpt.com.
        try:
            await page.wait_for_url("**/chatgpt.com/**", timeout=45_000)
        except Exception:
            try:
                cur = page.url
            except Exception:
                cur = "?"
            logger.warning("chatgpt_login: did not return to chatgpt.com (url=%s)", cur)

        await asyncio.sleep(2.0)

        # Final scrape — should now have accessToken.
        scraped = await _scrape_session(page)
        if not scraped or not scraped.get("accessToken"):
            session.state = "failed"
            session.error = "Không lấy được accessToken từ /api/auth/session"
            session.completed_at = time.time()
            return

        user_email = (scraped.get("user") or {}).get("email")
        session.access_token = scraped["accessToken"]
        session.expires = str(scraped.get("expires") or "")
        session.captured_email = user_email
        session.state = "success"
        session.message = f"Đăng nhập ChatGPT OK (email={user_email})"
        session.completed_at = time.time()

    except asyncio.CancelledError:
        session.state = "failed"
        session.error = "Bị huỷ (có yêu cầu login mới)"
        session.completed_at = time.time()
        raise
    except Exception as exc:
        logger.exception("chatgpt_login crashed profile=%s", session.profile)
        session.state = "failed"
        session.error = str(exc)
        session.completed_at = time.time()
