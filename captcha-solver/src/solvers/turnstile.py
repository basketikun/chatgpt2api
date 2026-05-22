"""Cloudflare Turnstile token extractor.

Strategy: open the target URL in Patchright, wait for the Turnstile widget
to publish its response token to the hidden form input, and read it. This
works for the "managed" and "non-interactive" variants because Cloudflare
fingerprints the runtime — Patchright passes those checks. For "interactive"
variants the user needs to click the checkbox via the noVNC view.

The returned token is short-lived (~120 s). Callers must use it immediately.
"""

from __future__ import annotations

import asyncio
import logging
import time

from ..browser_pool import pool
from ..settings import settings

logger = logging.getLogger(__name__)


async def solve_turnstile(
    url: str,
    sitekey: str | None = None,
    profile: str = "default",
    headless: bool = True,
    timeout: int | None = None,
) -> dict:
    """Open `url`, wait for the Turnstile widget to emit a token, return it.

    Args:
        url: Page that hosts the Turnstile challenge.
        sitekey: Optional — if provided we also verify the rendered widget
            matches, helps catch misconfigurations early.
        profile: Persistent profile to use (cookies survive across calls).
        headless: When False the browser shows up on the Xvfb display so
            users can solve "interactive" challenges via noVNC.
        timeout: Override default solve timeout.
    """
    deadline = time.time() + (timeout or settings.solve_timeout)
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

        # The widget posts the token into a hidden input named cf-turnstile-response
        # (sometimes inside a shadow root inside the iframe — but the hidden input
        # on the host page is the source of truth for form submission).
        while time.time() < deadline:
            token = await page.evaluate(
                """() => {
                    const inp = document.querySelector("input[name='cf-turnstile-response']");
                    if (inp && inp.value && inp.value.length > 20) return inp.value;
                    // Some sites read the token via window.turnstile.getResponse()
                    if (window.turnstile && typeof window.turnstile.getResponse === 'function') {
                        try { return window.turnstile.getResponse() || null; } catch(e) {}
                    }
                    return null;
                }"""
            )
            if token:
                logger.info("turnstile token obtained len=%d profile=%s", len(token), profile)
                return {
                    "token": token,
                    "expires_at": time.time() + 110,  # CF tokens last ~2 min
                    "profile": profile,
                }
            await asyncio.sleep(0.5)

        raise TimeoutError(f"turnstile solve timed out after {settings.solve_timeout}s")
