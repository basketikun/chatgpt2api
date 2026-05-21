"""
Antigravity (Google Cloud) OAuth token refresh — exchange a Google refresh token
for a fresh access token using Google's OAuth2 endpoints.
"""

from __future__ import annotations

import json
import time
from typing import Any

from curl_cffi import requests

from utils.log import logger

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
# Antigravity Google OAuth Client ID & Secret
ANTIGRAVITY_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
ANTIGRAVITY_CLIENT_SECRET = "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"

UNRECOVERABLE_CODES = {
    "invalid_grant",
    "invalid_request",
    "unauthorized_client",
    "unsupported_grant_type",
}


def refresh_antigravity_token(refresh_token: str) -> dict[str, Any] | None:
    """Exchange a Google refresh_token for a fresh access_token.

    Returns:
        On success: {"access_token": str, "refresh_token": str, "expires_in": int,
                     "expires_at": float (epoch seconds)}
        On unrecoverable failure: {"error": "unrecoverable", "code": <error>}
        On transient failure: None
    """
    if not refresh_token or not isinstance(refresh_token, str):
        return None

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
