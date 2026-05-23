"""2captcha / CapSolver fallback for Cloudflare Turnstile.

Used when the headless Patchright path fails (Cloudflare flagged us, cookies
expired, etc.). Activated only if env CAPTCHA_SOLVER_2CAPTCHA_KEY is set.
The 2captcha API is the de-facto standard so both 2captcha.com and most
clones (capsolver, anti-captcha) speak it with minor URL differences.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)


def _get_key() -> str | None:
    key = os.environ.get("CAPTCHA_SOLVER_2CAPTCHA_KEY") or ""
    return key.strip() or None


def is_enabled() -> bool:
    return _get_key() is not None


async def solve_turnstile_2captcha(
    url: str,
    sitekey: str,
    action: str | None = None,
    cdata: str | None = None,
    timeout: int = 180,
) -> dict:
    """Submit a Turnstile job to 2captcha and poll until solved.

    Returns {"token": "...", "expires_at": float, "provider": "2captcha"}.
    Raises on failure.
    """
    key = _get_key()
    if not key:
        raise RuntimeError("2captcha key not configured (CAPTCHA_SOLVER_2CAPTCHA_KEY)")

    in_url = "https://2captcha.com/in.php"
    res_url = "https://2captcha.com/res.php"

    submit_payload = {
        "key": key,
        "method": "turnstile",
        "sitekey": sitekey,
        "pageurl": url,
        "json": 1,
    }
    if action:
        submit_payload["action"] = action
    if cdata:
        submit_payload["data"] = cdata

    deadline = time.time() + timeout
    async with httpx.AsyncClient(timeout=30) as client:
        # 1) Submit job
        r = await client.post(in_url, data=submit_payload)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != 1:
            raise RuntimeError(f"2captcha submit failed: {data}")
        task_id = str(data.get("request"))
        logger.info("2captcha job submitted id=%s sitekey=%s", task_id, sitekey)

        # 2) Poll for result (every 5 s; first wait 15 s)
        await asyncio.sleep(15)
        while time.time() < deadline:
            r = await client.get(res_url, params={"key": key, "action": "get", "id": task_id, "json": 1})
            r.raise_for_status()
            data = r.json()
            if data.get("status") == 1:
                token = str(data.get("request") or "")
                if not token:
                    raise RuntimeError(f"2captcha returned empty token: {data}")
                logger.info("2captcha solved id=%s len=%d", task_id, len(token))
                return {
                    "token": token,
                    "expires_at": time.time() + 110,
                    "provider": "2captcha",
                    "task_id": task_id,
                }
            err = str(data.get("request") or "")
            if err == "CAPCHA_NOT_READY":
                await asyncio.sleep(5)
                continue
            # Any other status code is a hard error
            raise RuntimeError(f"2captcha error id={task_id}: {data}")

    raise TimeoutError(f"2captcha solve timed out id={task_id} after {timeout}s")
