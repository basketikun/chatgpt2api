"""Google account auto-login orchestration with 2FA support.

Three states the user cares about:
  • running  — Playwright is busy on Chrome (typing email/password,
               waiting for Google's UI). UI shows "Đang chạy: <step>".
  • need_code — Google asked for an SMS/authenticator code. UI shows
                a code-entry input that POSTs to /2fa-code.
  • need_tap — Google sent a "tap this number" notification to the
               user's phone. UI shows the number to tap.
  • success / failed — terminal.

Anti-bot reality: Google often blocks headless-detected Chrome in a
container, especially from a VPS IP without a real device history.
If auto-login stalls, the noVNC window is still open and the user can
finish manually — the saved cookies still persist in user-data-dir.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .browser_pool import pool

logger = logging.getLogger(__name__)


_GOOGLE_SIGNIN_URL = (
    "https://accounts.google.com/signin/v2/identifier"
    "?hl=vi&service=accountsettings"
)

# Cookies that prove a Google login completed.
_GOOGLE_LOGIN_COOKIES = ("__Secure-1PSID", "__Secure-3PSID", "SID")

# Selectors Google uses for the 2FA code input (varies by challenge type).
_2FA_CODE_SELECTORS = (
    'input[type="tel"][autocomplete="one-time-code"]',
    'input[name="totpPin"]',
    'input[id="totpPin"]',
    'input[autocomplete="one-time-code"]',
    'input[type="tel"]:not([disabled])',
)

# Selectors for the tap-match number Google displays. They change often;
# we look for any short numeric digit in a heading-like element. Best-
# effort — if we can't extract it, we still report state="need_tap" so
# the user knows to look at noVNC.
_TAP_MATCH_SELECTORS = (
    'samp',
    'div[role="heading"] >> visible=true',
    '.eFajbf',
    '.NQ5OL',
)

# Selectors for the "Choose how you'll sign in" page. When Google shows
# a list of 2FA methods (tap-on-device / Authenticator / SMS / recovery
# email), this page sits between password and the actual challenge.
# `_detect_state` would otherwise treat it as "working" and the 4-minute
# deadline expires before any code field shows up. We pick the TOTP /
# Authenticator option automatically because it's the fastest fully-
# automatable path — user only has to read the 6-digit Authenticator
# code and POST it to /v1/session/{profile}/auto-login-2fa-code.
_AUTHENTICATOR_OPTION_SELECTORS = (
    'li[data-challengetype="9"]',          # 9 = TOTP in Google's taxonomy
    'div[data-challengetype="9"]',
    'div[role="link"]:has-text("Google Authenticator")',
    'div[role="link"]:has-text("authenticator")',
    'li:has-text("Google Authenticator")',
    'li:has-text("Nhận mã xác minh")',
    'li:has-text("ứng dụng xác thực")',
    'div:has-text("Google Authenticator"):not(:has(div))',
)

_METHOD_SELECTOR_HINTS = (
    "choose how you", "chọn cách",
    "try another way", "thử cách khác",
    "google authenticator",
    "nhận mã xác minh", "ứng dụng xác thực",
)


async def _pick_authenticator_method(page) -> bool:
    """When Google shows the method picker, click the Authenticator entry.

    Returns True if a click was made (page likely advanced to the code
    input step). False if the picker isn't visible or no Authenticator
    option could be found — caller should fall through to need_tap.
    """
    try:
        body_text = (await page.locator("body").inner_text(timeout=600)).lower()
    except Exception:
        return False
    if not any(h in body_text for h in _METHOD_SELECTOR_HINTS):
        return False
    if not any(k in body_text for k in (
        "google authenticator", "ứng dụng xác thực", "nhận mã xác minh",
    )):
        return False
    for sel in _AUTHENTICATOR_OPTION_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            await loc.click(timeout=2500)
            logger.info("auto_login: picked Authenticator method via selector=%s", sel)
            return True
        except Exception:
            continue
    logger.info("auto_login: method-picker visible but no Authenticator selector matched")
    return False


@dataclass
class LoginSession:
    profile: str
    email: str
    state: str = "pending"
    message: str = ""
    tap_number: Optional[str] = None
    pending_code: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None
    # Selects how to satisfy a 2FA challenge when Google offers a picker.
    # "auth" → click Authenticator → state=need_code, user POSTs 6-digit.
    # "tap"  → skip picker, fall through to tap-on-phone (state=need_tap).
    prefer_method: str = "auth"

    def to_dict(self) -> dict:
        return {
            "profile": self.profile,
            "email": self.email,
            "state": self.state,
            "message": self.message,
            "tap_number": self.tap_number,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_sec": int((self.completed_at or time.time()) - self.started_at),
            "error": self.error,
        }


_sessions: dict[str, LoginSession] = {}
_tasks: dict[str, asyncio.Task] = {}


def get_session(profile: str) -> Optional[LoginSession]:
    return _sessions.get(profile)


def list_sessions() -> list[dict]:
    return [s.to_dict() for s in _sessions.values()]


def submit_2fa_code(profile: str, code: str) -> bool:
    """Feed an SMS / TOTP / backup code to a waiting auto-login.
    Returns False if there's no session waiting for a code."""
    session = _sessions.get(profile)
    if not session or session.state != "need_code":
        return False
    session.pending_code = code.strip()
    session.message = "Đã nhận mã, đang submit..."
    return True


async def start_auto_login(
    profile: str,
    email: str,
    password: str,
    prefer_method: str = "auth",
) -> LoginSession:
    """Kick off background auto-login. Returns the LoginSession immediately
    so the UI can start polling /auto-login-status.

    `prefer_method` selects the 2FA path when Google offers a picker:
    "auth" = click Authenticator (need_code), "tap" = wait for the
    tap-on-device prompt (need_tap).
    """
    old_task = _tasks.pop(profile, None)
    if old_task and not old_task.done():
        old_task.cancel()

    session = LoginSession(
        profile=profile,
        email=email,
        state="starting",
        message="Khởi tạo Chrome",
        prefer_method=prefer_method if prefer_method in ("auth", "tap") else "auth",
    )
    _sessions[profile] = session

    task = asyncio.create_task(_run(session, password))
    _tasks[profile] = task
    return session


async def _already_logged_in(ctx) -> bool:
    try:
        cookies = await ctx.cookies()
        return any(c["name"] in _GOOGLE_LOGIN_COOKIES for c in cookies)
    except Exception:
        return False


async def _detect_state(page) -> tuple[str, Optional[str]]:
    """Inspect the current Google sign-in page and classify it.

    Returns (state, extra_info) where state is one of:
      success, need_code, need_tap, error, working
    extra_info is the tap number when state=="need_tap"."""
    try:
        url = page.url
    except Exception:
        return "working", None

    # Success heuristic — Google redirects away from accounts.google.com
    # after sign-in, typically to myaccount.google.com or service URL.
    if "myaccount.google.com" in url or "google.com/accounts/Logout" in url:
        return "success", None
    if "accounts.google.com" not in url and "ServiceLogin" not in url:
        return "success", None

    # Generic error banner
    try:
        err_count = await page.locator(
            'div[jsname="B34EJ"], .Ekjuhf, .dEOOab'
        ).first.count()
        if err_count > 0:
            try:
                err_text = await page.locator(
                    'div[jsname="B34EJ"], .Ekjuhf, .dEOOab'
                ).first.inner_text(timeout=600)
                if err_text and len(err_text) < 220:
                    return "error", err_text.strip()
            except Exception:
                pass
    except Exception:
        pass

    # Code input visible?
    for sel in _2FA_CODE_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible(timeout=400):
                return "need_code", None
        except Exception:
            continue

    # Tap-match: page typically says "Check your phone" or has a samp
    # element with a number 0-99.
    try:
        body_text = (await page.locator("body").inner_text(timeout=600)).lower()
    except Exception:
        body_text = ""
    if any(k in body_text for k in (
        "check your phone", "kiểm tra điện thoại",
        "tap yes", "nhấn có", "trên thiết bị của bạn",
    )):
        # Try extracting the number
        for sel in _TAP_MATCH_SELECTORS:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    txt = (await loc.inner_text(timeout=400)).strip()
                    if txt.isdigit() and 1 <= len(txt) <= 3:
                        return "need_tap", txt
            except Exception:
                continue
        return "need_tap", None

    return "working", None


async def _safe_click(page, *selectors, timeout: int = 2500) -> bool:
    for sel in selectors:
        try:
            await page.locator(sel).first.click(timeout=timeout)
            return True
        except Exception:
            continue
    return False


async def do_google_login_steps(
    session: LoginSession,
    page,
    ctx,
    password: str,
    prefer_method: str = "auth",
) -> bool:
    """Shared Google login email/password/2FA dance.

    Assumes `page` is already navigated to an accounts.google.com page
    (signin form OR an OAuth redirect target). Drives the form forward
    and handles 2FA prompts.

    `prefer_method` selects how to satisfy a 2FA challenge when Google
    offers a method picker:
      "auth" — click the Authenticator option; flow advances to need_code
               and the user POSTs the 6-digit code via the existing
               /auto-login-2fa-code endpoint.
      "tap"  — skip the picker; let Google fall through to the
               tap-on-device prompt (need_tap). The user opens Gmail/
               Google app on their phone and taps "Yes, it's me".

    Updates `session.state` / `.message` / `.error` in-place. Returns
    True on success, False on failure. Caller decides what to do next
    (e.g. scrape session cookies, navigate elsewhere, etc).
    """
    # ── Email step ──
    session.message = "Điền email..."
    try:
        email_input = page.locator('input[type="email"]').first
        await email_input.wait_for(state="visible", timeout=15_000)
        await email_input.fill(session.email)
        await asyncio.sleep(0.8)
        await _safe_click(page, '#identifierNext button', 'button[jsname="LgbsSe"]:visible')
    except Exception as exc:
        session.state = "failed"
        session.error = f"Không tìm thấy ô email: {exc}"
        session.completed_at = time.time()
        return False

    await asyncio.sleep(2.0)

    # ── Password step ──
    session.message = "Điền mật khẩu..."
    try:
        pwd_input = page.locator('input[type="password"]').first
        await pwd_input.wait_for(state="visible", timeout=15_000)
        await asyncio.sleep(0.8)
        await pwd_input.fill(password)
        await asyncio.sleep(0.6)
        await _safe_click(page, '#passwordNext button', 'button[jsname="LgbsSe"]:visible')
    except Exception as exc:
        session.state = "failed"
        session.error = f"Không điền được mật khẩu (Google có thể đã chặn): {exc}"
        session.completed_at = time.time()
        return False

    # ── 2FA poll loop ──
    deadline = time.time() + 240
    picker_clicked = False
    while time.time() < deadline:
        await asyncio.sleep(2.0)

        # If Google shows the method picker (tap-on-device / Authenticator /
        # SMS / recovery email), pick Authenticator automatically when the
        # caller asked for the auth path. With prefer_method="tap" we skip
        # the picker entirely and let _detect_state fall through to
        # need_tap, so the user's existing on-device prompt drives the
        # confirmation instead of getting overridden by an Authenticator
        # click.
        if session.prefer_method == "auth" and not picker_clicked:
            try:
                if await _pick_authenticator_method(page):
                    picker_clicked = True
                    session.message = "Đã chọn Google Authenticator, đang chờ code..."
                    await asyncio.sleep(1.5)
                    continue
            except Exception:
                pass

        state, info = await _detect_state(page)

        if state == "success":
            if await _already_logged_in(ctx):
                session.message = "Google login OK"
                return True
            continue

        if state == "error":
            session.state = "failed"
            session.error = info or "Google báo lỗi"
            session.completed_at = time.time()
            return False

        if state == "need_tap":
            session.state = "need_tap"
            session.tap_number = info
            session.message = (
                f"Bấm số {info} trên điện thoại"
                if info else
                "Mở app Gmail/Google trên điện thoại và bấm 'Có' để xác minh"
            )
            continue

        if state == "need_code":
            session.state = "need_code"
            session.message = "Cần mã 2FA — nhập vào ô bên dưới"
            code_deadline = time.time() + 180
            while time.time() < code_deadline and not session.pending_code:
                await asyncio.sleep(0.5)
            if not session.pending_code:
                session.state = "failed"
                session.error = "Không nhận được mã 2FA trong 3 phút"
                session.completed_at = time.time()
                return False
            code = session.pending_code
            session.pending_code = None
            for sel in _2FA_CODE_SELECTORS:
                try:
                    await page.locator(sel).first.fill(code, timeout=2000)
                    break
                except Exception:
                    continue
            await asyncio.sleep(0.5)
            await _safe_click(
                page,
                'button:has-text("Next")', 'button:has-text("Tiếp theo")',
                '#totpNext button', '#submit',
                'button[jsname="LgbsSe"]:visible',
            )
            session.state = "running"
            session.message = "Đã gửi mã, đang xác minh..."
            continue

    session.state = "failed"
    session.error = "Hết 4 phút mà chưa hoàn tất 2FA"
    session.completed_at = time.time()
    return False


async def _run(session: LoginSession, password: str) -> None:
    """Playwright orchestration for accounts.google.com direct login.
    Updates session.state in-place; UI polls /v1/session/{profile}/
    auto-login-status to see progress."""
    try:
        session.state = "starting"
        session.message = "Đang mở Chrome (headful → noVNC)"
        ctx = await pool.get(profile=session.profile, headless=False, force_recreate=True)

        if await _already_logged_in(ctx):
            session.state = "success"
            session.message = "Profile đã có session Google — không cần đăng nhập lại"
            session.completed_at = time.time()
            return

        pages = ctx.pages
        page = pages[0] if pages else await ctx.new_page()
        try:
            await page.bring_to_front()
        except Exception:
            pass

        session.state = "running"
        session.message = "Mở trang accounts.google.com..."
        await page.goto(_GOOGLE_SIGNIN_URL, wait_until="domcontentloaded", timeout=30_000)

        ok = await do_google_login_steps(session, page, ctx, password)
        if ok:
            session.state = "success"
            session.message = "Đăng nhập thành công"
            session.completed_at = time.time()

    except asyncio.CancelledError:
        session.state = "failed"
        session.error = "Bị huỷ (có yêu cầu auto-login mới)"
        session.completed_at = time.time()
        raise
    except Exception as exc:
        logger.exception("auto-login crashed profile=%s", session.profile)
        session.state = "failed"
        session.error = str(exc)
        session.completed_at = time.time()
