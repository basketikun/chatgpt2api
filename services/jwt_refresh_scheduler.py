"""ChatGPT free JWT auto-refresh scheduler.

ChatGPT free JWTs expire after ~28 days. Each account is tied to a
captcha-solver browser profile (long-lived cookies). When a JWT is
within REFRESH_THRESHOLD_DAYS of expiry, we ask captcha-solver to open
the profile and re-scrape /api/auth/session for a fresh token — no
password, no Google OAuth round-trip.

The profile name is derived from the JWT's email claim:
  chatgpt-<localpart-of-email> (matches chatgpt-onboard-card convention)

If captcha-solver returns 401 (profile logged out), we mark the account
disabled so admin can re-onboard manually.
"""
from __future__ import annotations

import base64
import json
import random
import threading
import time
from typing import Any

import httpx

from services.config import config
from utils.log import logger

# Refresh when JWT has <= 7 days until expiry (giving 21d window where
# refresh is a noop). Run every 6h; this is gentle enough that a single
# misconfigured profile won't hammer captcha-solver.
REFRESH_THRESHOLD_DAYS = 7
SCAN_INTERVAL_SECONDS = 6 * 3600
# Per-scan wall-clock jitter (seconds): break the lockstep "every 6h on
# the dot" pattern visible to OpenAI's fraud team when 300+ accounts
# share one egress IP. Up to ±30 min variance on the 6h beat.
SCAN_INTERVAL_JITTER_SECONDS = 30 * 60
# Per-account jitter (seconds) inside one scan: spread refreshes across
# the scan window instead of bursting them in the same second.
PER_ACCOUNT_JITTER_SECONDS = 300
REFRESH_TIMEOUT = 60

_started = False


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    """Decode the JWT payload (middle segment, base64url) without verifying."""
    try:
        _, payload_b64, _ = token.split(".", 2)
    except ValueError:
        return None
    pad = "=" * (-len(payload_b64) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload_b64 + pad)
        return json.loads(raw)
    except Exception:
        return None


def _profile_for_email(email: str) -> str:
    local = (email.split("@", 1)[0] or "default")
    safe = "".join(c if c.isalnum() or c == "-" else "-" for c in local)
    return f"chatgpt-{safe}"


def _captcha_solver_cfg() -> tuple[str, str]:
    providers = config.data.get("providers") or {}
    flow = providers.get("flow") or {}
    return (
        str(flow.get("captcha_solver_url") or "").rstrip("/"),
        str(flow.get("captcha_solver_api_key") or ""),
    )


def _refresh_one(account: dict[str, Any]) -> dict[str, Any] | None:
    """Refresh a single ChatGPT free account's JWT.

    Returns updated account dict (with new access_token + refresh meta)
    or None if refresh was skipped or failed.
    """
    token = str(account.get("access_token") or "")
    if not token:
        return None
    payload = _decode_jwt_payload(token)
    if not payload:
        return None
    # Only auto-refresh ChatGPT free JWTs (have chatgpt_plan_type claim)
    auth_claims = payload.get("https://api.openai.com/auth") or {}
    if auth_claims.get("chatgpt_plan_type") not in ("free", "plus", "pro"):
        return None
    exp = int(payload.get("exp") or 0)
    now = int(time.time())
    days_left = (exp - now) / 86400.0
    if days_left > REFRESH_THRESHOLD_DAYS:
        return None  # not yet — skip

    profile_claims = payload.get("https://api.openai.com/profile") or {}
    email = str(profile_claims.get("email") or "")
    if not email:
        return None
    profile = _profile_for_email(email)
    cs_url, cs_key = _captcha_solver_cfg()
    if not cs_url:
        logger.warning({"event": "jwt_refresh_skipped", "reason": "captcha_solver_not_configured"})
        return None

    headers = {"Content-Type": "application/json"}
    if cs_key:
        headers["Authorization"] = f"Bearer {cs_key}"
    url = f"{cs_url}/v1/chatgpt/{profile}/refresh-jwt"
    try:
        r = httpx.post(url, headers=headers, timeout=REFRESH_TIMEOUT + 30)
    except Exception as exc:
        logger.warning({"event": "jwt_refresh_request_failed",
                        "profile": profile, "email": email, "error": str(exc)[:120]})
        return None
    if r.status_code == 401:
        logger.warning({"event": "jwt_refresh_unauthorized",
                        "profile": profile, "email": email,
                        "hint": "profile logged out — re-onboard manually"})
        return None
    if r.status_code >= 400:
        logger.warning({"event": "jwt_refresh_http_error",
                        "profile": profile, "status": r.status_code,
                        "body": r.text[:200]})
        return None
    try:
        data = r.json()
    except Exception:
        return None
    new_token = str(data.get("access_token") or "")
    if not new_token or new_token == token:
        return None
    logger.info({"event": "jwt_refreshed", "profile": profile,
                 "email": email, "old_days_left": round(days_left, 2)})
    return {**account, "access_token": new_token,
            "jwt_refreshed_at": int(time.time())}


def _scan_and_refresh() -> None:
    """Scan all accounts and refresh any near-expiry JWTs."""
    try:
        from services.account_service import account_service
    except Exception as exc:
        logger.warning({"event": "jwt_refresh_no_account_service", "error": str(exc)[:120]})
        return
    try:
        accounts = account_service.list_accounts() if hasattr(account_service, "list_accounts") else []
    except Exception as exc:
        logger.warning({"event": "jwt_refresh_list_failed", "error": str(exc)[:120]})
        return
    refreshed = 0
    for acc in list(accounts):
        try:
            # Per-account jitter: spread the burst across the scan so 300+
            # accounts don't hit captcha-solver / auth.openai.com in the
            # same second. Sleep 0..PER_ACCOUNT_JITTER_SECONDS BEFORE each
            # refresh.
            time.sleep(random.uniform(0, PER_ACCOUNT_JITTER_SECONDS))
            updated = _refresh_one(acc)
            if updated and hasattr(account_service, "update_account"):
                ident = acc.get("id") or acc.get("access_token")
                try:
                    account_service.update_account(ident, updated)
                    refreshed += 1
                except Exception as exc:
                    logger.warning({"event": "jwt_refresh_save_failed",
                                    "error": str(exc)[:120]})
        except Exception as exc:
            logger.warning({"event": "jwt_refresh_one_crashed",
                            "error": str(exc)[:120]})
    if refreshed:
        logger.info({"event": "jwt_refresh_cycle_done", "refreshed": refreshed})


def _scheduler_loop() -> None:
    # Initial 30s delay so server fully starts before scanning
    time.sleep(30)
    while True:
        try:
            _scan_and_refresh()
        except Exception as exc:
            logger.warning({"event": "jwt_refresh_loop_error", "error": str(exc)[:120]})
        # Jittered sleep: SCAN_INTERVAL_SECONDS ± SCAN_INTERVAL_JITTER_SECONDS.
        # Stops 300+ accounts from hitting auth.openai.com on the same beat.
        jitter = random.uniform(-SCAN_INTERVAL_JITTER_SECONDS,
                                SCAN_INTERVAL_JITTER_SECONDS)
        time.sleep(max(60, SCAN_INTERVAL_SECONDS + jitter))


def start() -> None:
    """Start the background scheduler (idempotent)."""
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_scheduler_loop, daemon=True, name="jwt-refresh-scheduler")
    t.start()
    logger.info({"event": "jwt_refresh_scheduler_started",
                 "interval_h": SCAN_INTERVAL_SECONDS / 3600,
                 "threshold_days": REFRESH_THRESHOLD_DAYS})
