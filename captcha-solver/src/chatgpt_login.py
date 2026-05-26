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
    click_google_oauth_consent,
    do_google_login_steps,
    submit_2fa_code as _submit_2fa_code,
)
from .browser_pool import pool

logger = logging.getLogger(__name__)


# ChatGPT entry points — we navigate to chatgpt.com first, which redirects
# unauthenticated users to the login picker.
_CHATGPT_HOME = "https://chatgpt.com/"
_CHATGPT_AUTH_SESSION = "https://chatgpt.com/api/auth/session"

# Selectors for the chatgpt.com / auth.openai.com / Auth0 login UI.
# After click on chatgpt.com header "Đăng nhập" / "Log in" button, the
# page redirects to auth.openai.com which then redirects to Auth0's
# Universal Login. The flow CAN take 5-10s of full page loads.
_LOGIN_BUTTON_SELECTORS = (
    'button[data-testid="login-button"]',
    'a[data-testid="login-button"]',
    'button:has-text("Log in")',
    'button:has-text("Đăng nhập")',
    'a:has-text("Log in")',
    'a:has-text("Đăng nhập")',
)
_CONTINUE_WITH_GOOGLE_SELECTORS = (
    'button[data-provider="google"]',
    'button[name="provider"][value="google"]',
    'button:has-text("Continue with Google")',
    'a:has-text("Continue with Google")',
    'button:has-text("Tiếp tục với Google")',
    'button:has-text("Đăng nhập bằng Google")',
    # Auth0 Universal Login uses these selectors:
    'button.auth0-lock-social-button[data-provider="google-oauth2"]',
    'a[href*="google-oauth2"]',
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


async def refresh_jwt(profile: str, timeout: int = 30) -> dict:
    """Refresh ChatGPT JWT for an already logged-in profile.

    Opens the persistent profile (no login flow), visits chatgpt.com,
    scrapes /api/auth/session and returns the freshest accessToken.
    Reuses the same browser pool as the login flow but does NOT trigger
    Google OAuth — relies on existing cookies.

    Returns: {"access_token": str, "expires": str|None, "email": str|None}
    Raises: RuntimeError if profile is logged out or scrape fails.
    """
    ctx = await pool.get(profile=profile, headless=True, force_recreate=False)
    pages = ctx.pages
    page = pages[0] if pages else await ctx.new_page()
    try:
        await page.goto(_CHATGPT_HOME, wait_until="domcontentloaded", timeout=timeout * 1000)
        await asyncio.sleep(1.5)
        scraped = await _scrape_session(page)
        if not scraped or not scraped.get("accessToken"):
            raise RuntimeError("Profile not logged in or session expired")
        user_obj = scraped.get("user") or {}
        account_obj = scraped.get("account") or {}
        # Plan tier — chatgpt.com's `/api/auth/session` currently puts the
        # active subscription at `account.planType`. Older schemas used
        # root `plan` or `user.subscription_plan`; check all three so we
        # don't have to chase another schema change next year.
        plan = (
            account_obj.get("planType")
            or account_obj.get("plan")
            or scraped.get("plan")
            or user_obj.get("subscription_plan")
            or user_obj.get("plan")
        )
        return {
            "access_token": scraped["accessToken"],
            "expires": str(scraped.get("expires") or ""),
            "email": user_obj.get("email"),
            "plan": plan,
        }
    finally:
        # Don't close the page — pool keeps the context alive for reuse
        pass


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
    """Click the first matching selector. Tries Playwright click, falls back to JS click."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            # Wait for it to exist in DOM first (avoid failing immediately)
            await loc.wait_for(state="attached", timeout=timeout)
            try:
                await loc.click(timeout=2000)
                logger.info("chatgpt_login: clicked selector=%s", sel)
                return True
            except Exception as exc:
                logger.debug("chatgpt_login: Playwright click failed %s: %s", sel, str(exc)[:80])
                # Fallback to JS click for obstructed or un-actionable elements
                await loc.evaluate("el => el.click()")
                logger.info("chatgpt_login: JS clicked selector=%s", sel)
                return True
        except Exception as exc:
            logger.debug("chatgpt_login: selector miss %s: %s", sel, str(exc)[:80])
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
        await asyncio.sleep(4.0)  # let any client-side redirect settle

        # ── Cloudflare challenge wait ──
        session.message = "Chờ Cloudflare verify..."
        cf_deadline = time.time() + 60
        while time.time() < cf_deadline:
            try:
                cur = page.url
            except Exception:
                cur = ""
            if "__cf_chl_rt_tk" not in cur and "/cdn-cgi/challenge" not in cur:
                break
            await asyncio.sleep(2.0)
        else:
            logger.info("chatgpt_login: cloudflare challenge did not clear in 60s (url=%s)", page.url)

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
        session.message = "Click 'Đăng nhập'..."
        
        # We might need to try clicking Log in multiple times if React is hydrating
        for _ in range(3):
            if await _click_one(page, _LOGIN_BUTTON_SELECTORS, timeout=5000):
                # Check if Google button appears
                try:
                    google_loc = page.locator('button[data-provider="google"], button:has-text("Continue with Google")').first
                    await google_loc.wait_for(state="visible", timeout=8000)
                    logger.info("chatgpt_login: Google button became visible!")
                    break
                except Exception:
                    logger.info("chatgpt_login: Google button not visible yet, clicking Log in again...")
            await asyncio.sleep(2.0)
        else:
            logger.info("chatgpt_login: Failed to open login modal after multiple tries.")
        session.message = "Click 'Continue with Google'..."
        if not await _click_one(page, _CONTINUE_WITH_GOOGLE_SELECTORS, timeout=8000):
            session.state = "failed"
            session.error = (
                f"Không tìm thấy nút 'Continue with Google' (cur_url={page.url})"
            )
            session.completed_at = time.time()
            return

        # Wait for Google's OAuth screen to take over.
        try:
            await page.wait_for_url("**/accounts.google.com/**", timeout=20_000)
            logger.info("chatgpt_login: at google login page %s", page.url)
        except Exception:
            # Google may skip the login form if a session cookie exists
            # → bounces straight back to chatgpt.com. _scrape_session
            # tells us if we ended up authenticated.
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

        # OAuth consent / "Continue as <email>" — when Google already has
        # a session cookie for this profile, it skips the email/password
        # form and goes straight to a one-button confirm page. Try this
        # FIRST so we don't fail the email step looking for an input that
        # isn't there.
        try:
            consent_clicked = await click_google_oauth_consent(page, timeout=6.0)
            if consent_clicked:
                session.message = "Đã bấm OAuth consent..."
                await asyncio.sleep(2.0)
        except Exception as exc:
            consent_clicked = False
            logger.debug("chatgpt_login: pre-consent skipped: %s", str(exc)[:120])

        # If still on Google's email step (no existing session), drive it.
        try:
            on_google = "accounts.google.com" in page.url
        except Exception:
            on_google = False
        if on_google and not consent_clicked:
            ok = await do_google_login_steps(session, page, ctx, password)
            if not ok:
                return  # state/error already set

        # Post-login consent — appears after fresh email/password too.
        try:
            await click_google_oauth_consent(page, timeout=8.0)
        except Exception as exc:
            logger.debug("chatgpt_login: post-consent skipped: %s", str(exc)[:120])

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
