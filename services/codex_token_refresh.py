"""
Codex OAuth token refresh — keep ChatGPT JWTs alive without manual re-login.

Mirrors the flow in 9router/open-sse/services/tokenRefresh.js#refreshCodexToken.

Flow:
    POST https://auth.openai.com/oauth/token
        Content-Type: application/x-www-form-urlencoded
        grant_type=refresh_token
        refresh_token=<refresh_token>
        client_id=<codex_client_id>
        scope=openid profile email offline_access

Response (success):
    {
        "access_token": "eyJ...",
        "refresh_token": "v1.M...",
        "expires_in": 28800,
        "id_token": "eyJ...",
        "token_type": "Bearer"
    }

Response (unrecoverable):
    {"error": "invalid_grant" | "refresh_token_reused" | "token_expired" | ...}
    -> caller must mark the account disabled and stop retrying.
"""

from __future__ import annotations

import json
import time
from typing import Any

from curl_cffi import requests

from utils.log import logger

OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
# Public Codex CLI client_id (matches 9router PROVIDERS.codex.clientId)
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
SCOPE = "openid profile email offline_access"

UNRECOVERABLE_CODES = {
    "invalid_grant",
    "refresh_token_reused",
    "token_expired",
    "invalid_token",
    "invalid_request",
}


def refresh_codex_token(refresh_token: str) -> dict[str, Any] | None:
    """Exchange a Codex refresh_token for a fresh access_token.

    Returns:
        On success: {"access_token": str, "refresh_token": str, "expires_in": int,
                     "expires_at": float (epoch seconds)}
        On unrecoverable failure: {"error": "unrecoverable", "code": <auth0_code>}
        On transient failure: None
    """
    if not refresh_token or not isinstance(refresh_token, str):
        return None

    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CODEX_CLIENT_ID,
        "scope": SCOPE,
    }

    try:
        resp = requests.post(
            OAUTH_TOKEN_URL,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=20,
            impersonate="chrome110",
        )
    except Exception as exc:
        logger.warning({"event": "codex_refresh_network_error", "error": str(exc)[:200]})
        return None

    if resp.status_code == 200:
        try:
            payload = resp.json()
        except Exception:
            logger.warning({"event": "codex_refresh_bad_json", "status": 200})
            return None

        access_token = str(payload.get("access_token") or "")
        new_refresh = str(payload.get("refresh_token") or refresh_token)
        expires_in = int(payload.get("expires_in") or 0)
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
            elif isinstance(err, dict):
                code = err.get("code") or err.get("error")
    except Exception:
        pass

    if code in UNRECOVERABLE_CODES:
        logger.warning({
            "event": "codex_refresh_unrecoverable",
            "status": resp.status_code,
            "code": code,
        })
        return {"error": "unrecoverable", "code": code}

    logger.warning({
        "event": "codex_refresh_transient_error",
        "status": resp.status_code,
        "body": error_text[:200],
    })
    return None
