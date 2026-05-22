"""Generic helper: open a URL inside a profile, wait, evaluate JS, return data.

Useful for SPAs that gate content behind a Cloudflare interstitial or render
client-side — caller fetches the post-JS DOM instead of raw HTTP.
"""

from __future__ import annotations

import logging
from typing import Any

from ..browser_pool import pool

logger = logging.getLogger(__name__)


async def browser_run(
    url: str,
    script: str | None = None,
    wait_for: str | None = None,
    profile: str = "default",
    headless: bool = True,
    timeout: int = 30,
) -> dict[str, Any]:
    async with pool.page(profile=profile, headless=headless) as page:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        if wait_for:
            try:
                await page.wait_for_selector(wait_for, timeout=timeout * 1000)
            except Exception as exc:
                logger.warning("wait_for selector failed: %s", exc)
        result: Any = None
        if script:
            result = await page.evaluate(script)
        html = await page.content()
        title = await page.title()
        return {
            "title": title,
            "url": page.url,
            "result": result,
            "html_len": len(html),
            "html": html[:200_000],  # cap so the response stays bounded
        }
