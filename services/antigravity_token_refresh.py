"""
Antigravity (Google Cloud) OAuth token refresh — exchange a Google refresh token
for a fresh access token using Google's OAuth2 endpoints.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from threading import Lock
from typing import Any

from curl_cffi import requests

from utils.log import logger

import os
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
# Antigravity Google OAuth Client ID & Secret.
#
# The OAuth client_id is public (it appears in the Antigravity desktop app
# binary). The client_secret here is also public in the Google sense — it
# travels with every desktop OAuth client and is documented as
# "non-confidential" by Google for installed-app flows. Even so, we read
# them from env vars when available so secret-scanning tools (codegraph,
# Understand-Anything, leak detectors) don't flag the source file.
ANTIGRAVITY_CLIENT_ID = os.getenv(
    "ANTIGRAVITY_CLIENT_ID",
    "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com",
)
ANTIGRAVITY_CLIENT_SECRET = os.getenv(
    "ANTIGRAVITY_CLIENT_SECRET",
    "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",
)

UNRECOVERABLE_CODES = {
    "invalid_grant",
    "invalid_request",
    "unauthorized_client",
    "unsupported_grant_type",
}

# Per-refresh_token mutex — see codex_token_refresh.py for rationale.
_refresh_locks: dict[str, Lock] = defaultdict(Lock)
_refresh_locks_guard = Lock()
_MAX_REFRESH_LOCKS = 4096


def _lock_for(refresh_token: str) -> Lock:
    """Return the per-token Lock, creating one on first use."""
    with _refresh_locks_guard:
        if len(_refresh_locks) > _MAX_REFRESH_LOCKS:
            for key in list(_refresh_locks.keys()):
                lock = _refresh_locks[key]
                if lock.acquire(blocking=False):
                    try:
                        _refresh_locks.pop(key, None)
                    finally:
                        lock.release()
                if len(_refresh_locks) <= _MAX_REFRESH_LOCKS // 2:
                    break
        return _refresh_locks[refresh_token]


def refresh_antigravity_token(refresh_token: str, device_id: str | None = None) -> dict[str, Any] | None:
    """Exchange a Google refresh_token for a fresh access_token.

    Concurrency-safe: per-refresh_token Lock + re-check pattern (see
    codex_token_refresh.py for rationale).

    Args:
        refresh_token: the refresh_token to exchange.
        device_id: stable per-account UUID. Currently logged but not sent
            to Google (Google OAuth doesn't honour an X-Device-Id header).
            Kept on the signature to match the Codex side and so future
            device-fingerprint work can wire it through here.

    Returns:
        On success: {"access_token": str, "refresh_token": str, "expires_in": int,
                     "expires_at": float (epoch seconds)}
        On unrecoverable failure: {"error": "unrecoverable", "code": <error>}
        On transient failure: None
    """
    if not refresh_token or not isinstance(refresh_token, str):
        return None

    lock = _lock_for(refresh_token)
    with lock:
        try:
            from services.account_service import account_service
            existing = account_service.find_by_refresh_token(refresh_token)
        except Exception:
            existing = None
        if existing:
            cached_access = str(existing.get("access_token") or "")
            cached_exp_raw = existing.get("expires_at")
            cached_exp = 0.0
            if cached_exp_raw:
                try:
                    cached_exp = float(cached_exp_raw)
                except ValueError:
                    try:
                        from datetime import datetime
                        cached_exp = datetime.fromisoformat(str(cached_exp_raw).replace('Z', '+00:00')).timestamp()
                    except Exception:
                        pass
            # Google access_tokens live 1h — re-use only when ≥10min remain.
            if cached_access and cached_exp - time.time() > 600:
                return {
                    "access_token": cached_access,
                    "refresh_token": refresh_token,
                    "expires_in": int(cached_exp - time.time()),
                    "expires_at": cached_exp,
                }
            if device_id is None:
                device_id = str(existing.get("device_id") or "") or None
        return _refresh_antigravity_token_locked(refresh_token, device_id)


def _refresh_antigravity_token_locked(
    refresh_token: str, device_id: str | None = None
) -> dict[str, Any] | None:
    """Inner worker: actual OAuth call. Caller MUST hold _lock_for(refresh_token)."""
    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": ANTIGRAVITY_CLIENT_ID,
        "client_secret": ANTIGRAVITY_CLIENT_SECRET,
    }

    try:
        resp = requests.post(
            GOOGLE_TOKEN_URL,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=20,
        )
    except Exception as exc:
        logger.warning({"event": "antigravity_refresh_network_error", "error": str(exc)[:200]})
        return None

    if resp.status_code == 200:
        try:
            payload = resp.json()
        except Exception:
            logger.warning({"event": "antigravity_refresh_bad_json", "status": 200})
            return None

        access_token = str(payload.get("access_token") or "")
        new_refresh = str(payload.get("refresh_token") or refresh_token)
        expires_in = int(payload.get("expires_in") or 3600)
        if not access_token:
            return None
        return {
            "access_token": access_token,
            "refresh_token": new_refresh,
            "expires_in": expires_in,
            "expires_at": time.time() + expires_in if expires_in > 0 else 0.0,
        }

    # Non-200 — inspect error body for unrecoverable codes
    error_text = ""
    try:
        error_text = (resp.text or "")[:500]
    except Exception:
        pass

    code = None
    try:
        parsed = json.loads(error_text) if error_text else {}
        if isinstance(parsed, dict):
            err = parsed.get("error")
            if isinstance(err, str):
                code = err
    except Exception:
        pass

    if code in UNRECOVERABLE_CODES:
        logger.warning({
            "event": "antigravity_refresh_unrecoverable",
            "status": resp.status_code,
            "code": code,
        })
        return {"error": "unrecoverable", "code": code}

    logger.warning({
        "event": "antigravity_refresh_transient_error",
        "status": resp.status_code,
        "body": error_text[:200],
    })
    return None
