"""Google reCAPTCHA v2/v3 solver via playwright-recaptcha (audio-challenge
fallback) plus a passive token harvester for v3-invisible widgets.

For v3 (invisible) we just open the page, let the JS execute the
"grecaptcha.execute(sitekey, {action})" promise, and read the returned token
from grecaptcha.getResponse(). For v2 (checkbox) we delegate to the audio
challenge solver from playwright-recaptcha — Patchright passes Google's
suspicion checks well enough that the audio path usually succeeds.
"""

from __future__ import annotations

import asyncio
import logging
import time

from ..browser_pool import pool
from ..settings import settings

logger = logging.getLogger(__name__)


async def solve_recaptcha_v3(
    url: str,
    sitekey: str,
    action: str = "submit",
    profile: str = "default",
    headless: bool = True,
    timeout: int | None = None,
) -> dict:
    """Trigger grecaptcha.execute on `url` and return the resulting token.

    The page does not need to have a visible reCAPTCHA widget — only the
    grecaptcha runtime must be loaded.
    """
    deadline = time.time() + (timeout or settings.solve_timeout)
    async with pool.page(profile=profile, headless=headless) as page:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        # Wait for the grecaptcha runtime, then call execute(sitekey, {action})
        await page.wait_for_function(
            "() => window.grecaptcha && grecaptcha.execute",
            timeout=20_000,
        )

        token = await page.evaluate(
            """async ({sitekey, action}) => {
                try {
                    return await grecaptcha.execute(sitekey, { action });
                } catch (e) {
                    return { __error: String(e) };
                }
            }""",
            {"sitekey": sitekey, "action": action},
        )

        if isinstance(token, dict) and token.get("__error"):
            raise RuntimeError(f"grecaptcha.execute failed: {token['__error']}")

        if not token or not isinstance(token, str):
            raise RuntimeError("grecaptcha.execute returned empty token")

        logger.info("recaptcha v3 token obtained len=%d action=%s", len(token), action)
        return {
            "token": token,
            "expires_at": time.time() + 110,
            "action": action,
            "profile": profile,
        }


async def solve_recaptcha_v2(
    url: str,
    profile: str = "default",
    headless: bool = True,
    timeout: int | None = None,
) -> dict:
    """Solve a v2 checkbox/audio reCAPTCHA on the given page.

    Uses playwright-recaptcha's audio-challenge solver under the hood.
    """
    from playwright_recaptcha import recaptchav2

    deadline = time.time() + (timeout or settings.solve_timeout)
    async with pool.page(profile=profile, headless=headless) as page:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        async with recaptchav2.AsyncSolver(page) as solver:
            token = await solver.solve_recaptcha(wait=True)
        if not token:
            raise RuntimeError("recaptcha v2 solver returned empty token")
        return {
            "token": token,
            "expires_at": time.time() + 110,
            "profile": profile,
        }
