"""Cloudflare Turnstile token extractor.

Strategy (in order):
  1. Open URL with the persistent profile so cf_clearance cookies are reused.
  2. Wait for the widget to publish a token to the hidden input. Many sites
     auto-pass once cookies are warm — this is the fast path (~1-3 s).
  3. If no token after a few seconds, locate the Turnstile iframe and click
     the visible checkbox (handles "managed" challenges where one click is
     enough to satisfy the challenge).
  4. If still no token within the soft-timeout, fall back to 2captcha/
     CapSolver (only when CAPTCHA_SOLVER_2CAPTCHA_KEY is set).
"""

from __future__ import annotations

import asyncio
import logging
import time

from ..browser_pool import pool
from ..settings import settings
from . import twocaptcha

logger = logging.getLogger(__name__)


async def _try_click_checkbox(page) -> bool:
    """If the Turnstile widget shows a visible checkbox, click it.

    The widget renders inside an iframe hosted on challenges.cloudflare.com.
    We use Playwright's frame_locator to reach the checkbox and click via
    its accessibility label — works for both English and Vietnamese pages.
    """
    try:
        iframe = page.frame_locator("iframe[src*='challenges.cloudflare.com']")
        # The checkbox has role=checkbox; label varies by locale.
        checkbox = iframe.locator("input[type='checkbox']")
        await checkbox.wait_for(state="visible", timeout=3000)
        await checkbox.click(timeout=3000)
        logger.info("turnstile checkbox auto-clicked")
        return True
    except Exception as exc:
        logger.debug("checkbox auto-click skipped: %s", exc)
        return False


async def _read_token(page) -> str | None:
    return await page.evaluate(
        """() => {
            const inp = document.querySelector("input[name='cf-turnstile-response']");
            if (inp && inp.value && inp.value.length > 20) return inp.value;
            if (window.turnstile && typeof window.turnstile.getResponse === 'function') {
                try { return window.turnstile.getResponse() || null; } catch(e) {}
            }
            return null;
        }"""
    )


async def solve_turnstile(
    url: str,
    sitekey: str | None = None,
    profile: str = "default",
    headless: bool = True,
    timeout: int | None = None,
    allow_paid_fallback: bool = True,
) -> dict:
    """Open `url`, wait for the Turnstile widget to emit a token, return it.

    Args:
        url: Page that hosts the Turnstile challenge.
        sitekey: Optional — sanity check the rendered widget matches.
        profile: Persistent profile (reuses cf_clearance cookies).
        headless: When False the browser shows on Xvfb display → noVNC.
        timeout: Override default solve timeout.
        allow_paid_fallback: If solver fails and 2captcha is configured,
            try it before giving up.
    """
    soft_deadline = time.time() + (timeout or settings.solve_timeout)

    async with pool.page(profile=profile, headless=headless) as page:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        # Wait for the widget container to mount.
        try:
            await page.wait_for_selector(
                "div.cf-turnstile, iframe[src*='challenges.cloudflare.com']",
                timeout=15_000,
            )
        except Exception as exc:
            raise RuntimeError(f"turnstile widget not present on {url}: {exc}") from exc

        if sitekey:
            actual = await page.evaluate(
                "() => document.querySelector('.cf-turnstile')?.dataset?.sitekey"
            )
            if actual and actual != sitekey:
                logger.warning("turnstile sitekey mismatch: page=%s arg=%s", actual, sitekey)
        # If sitekey not provided, grab it for fallback path
        resolved_sitekey = sitekey or await page.evaluate(
            "() => document.querySelector('.cf-turnstile')?.dataset?.sitekey || null"
        )

        # Fast path — poll for ~6 s waiting for cookie-based auto-pass.
        fast_deadline = time.time() + 6
        while time.time() < fast_deadline:
            token = await _read_token(page)
            if token:
                logger.info("turnstile token via cookie-pass len=%d", len(token))
                return {
                    "token": token,
                    "expires_at": time.time() + 110,
                    "profile": profile,
                    "method": "cookie",
                }
            await asyncio.sleep(0.4)

        # Auto-click attempt — handles "managed" widgets that show a visible checkbox.
        if await _try_click_checkbox(page):
            click_deadline = min(soft_deadline, time.time() + 25)
            while time.time() < click_deadline:
                token = await _read_token(page)
                if token:
                    logger.info("turnstile token after auto-click len=%d", len(token))
                    return {
                        "token": token,
                        "expires_at": time.time() + 110,
                        "profile": profile,
                        "method": "auto_click",
                    }
                await asyncio.sleep(0.5)

        # Keep polling until the soft deadline in case Cloudflare validates
        # silently after the checkbox click or after additional fingerprint
        # checks complete.
        while time.time() < soft_deadline:
            token = await _read_token(page)
            if token:
                logger.info("turnstile token via slow-poll len=%d", len(token))
                return {
                    "token": token,
                    "expires_at": time.time() + 110,
                    "profile": profile,
                    "method": "slow",
                }
            await asyncio.sleep(0.5)

    # 2captcha fallback — paid, slow (~30-60 s), but ~95 % success rate.
    if allow_paid_fallback and twocaptcha.is_enabled() and resolved_sitekey:
        logger.info("falling back to 2captcha for %s", url)
        result = await twocaptcha.solve_turnstile_2captcha(url=url, sitekey=resolved_sitekey)
        result["profile"] = profile
        result["method"] = "2captcha"
        return result

    raise TimeoutError(f"turnstile solve timed out after {settings.solve_timeout}s")
