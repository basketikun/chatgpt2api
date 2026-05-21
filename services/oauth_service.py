"""
OAuth Service — PKCE login flow for Codex (chat) and Google (image).
Port from 9router oauth/ directory.

Codex OAuth:
- Client ID: app_EMoamEEZ73f0CkXaXp7hrann
- Auth: https://auth.openai.com/oauth/authorize
- Token: https://auth.openai.com/oauth/token

Google OAuth (chatgpt.com):
- Direct session token from chatgpt.com/api/auth/session
- User logs in via browser, copy token
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import urllib.parse
from typing import Any

from curl_cffi import requests

from services.account_service import account_service
from utils.log import logger

# Codex OAuth config (from 9router)
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_AUTH_URL = "https://auth.openai.com/oauth/authorize"
CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_REDIRECT_URI = "http://localhost:3030/api/oauth/codex/callback"
CODEX_SCOPE = "openid profile email offline_access model.request model.read"


def _curl_post(url: str, **kwargs) -> requests.Response:
    """POST with impersonate fallback on TLS errors (LXC compatibility)."""
    try:
        return requests.post(url, impersonate="chrome110", **kwargs)
    except Exception as e:
        msg = str(e).lower()
        if any(k in msg for k in ("openssl", "tls", "invalid library")):
            logger.warning({"event": "oauth_tls_fallback", "url": url[:60]})
            return requests.post(url, **kwargs)
        raise


def generate_pkce() -> dict[str, str]:
    """Generate PKCE code verifier and challenge."""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    state = secrets.token_hex(16)
    return {
        "code_verifier": code_verifier,
        "code_challenge": code_challenge,
        "state": state,
    }


def get_codex_auth_url(base_url: str = "") -> dict[str, str]:
    """Generate Codex OAuth authorization URL with PKCE.

    IMPORTANT: redirect_uri MUST be localhost for Codex CLI OAuth.
    OpenAI only trusts localhost redirects — remote IPs require phone verification.
    If chatgpt2api is not on your local machine, use the manual exchange flow:
    1. Open auth_url in browser
    2. Authorize
    3. Copy the full redirect URL (localhost:3030/auth/callback?code=...)
    4. POST that URL to /api/oauth/codex/exchange
    """
    pkce = generate_pkce()
    redirect_uri = "http://localhost:3030/auth/callback" if not base_url else f"{base_url.rstrip('/')}/auth/callback"

    params = {
        "response_type": "code",
        "client_id": CODEX_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email offline_access",
        "code_challenge": pkce["code_challenge"],
        "code_challenge_method": "S256",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "originator": "codex_cli_rs",
        "state": pkce["state"],
    }

    # Build query string manually to use %20 instead of + (like 9router does)
    query_parts = []
    for k, v in params.items():
        encoded_key = urllib.parse.quote(str(k), safe="")
        encoded_val = urllib.parse.quote(str(v), safe="")
        query_parts.append(f"{encoded_key}={encoded_val}")
    query_string = "&".join(query_parts)

    auth_url = f"{CODEX_AUTH_URL}?{query_string}"

    # Store PKCE data temporarily (in-memory, short-lived)
    _pending_auths[pkce["state"]] = {
        "code_verifier": pkce["code_verifier"],
        "redirect_uri": redirect_uri,
    }

    return {
        "auth_url": auth_url,
        "state": pkce["state"],
    }


# In-memory store for pending OAuth flows (state → {code_verifier, redirect_uri})
_pending_auths: dict[str, dict[str, str]] = {}


def exchange_codex_code(code: str, state: str) -> dict[str, Any]:
    """Exchange authorization code for Codex OAuth token."""
    pending = _pending_auths.pop(state, None)
    if not pending:
        raise ValueError("Invalid or expired OAuth state. Please try again.")

    body = {
        "client_id": CODEX_CLIENT_ID,
        "code": code,
        "redirect_uri": pending["redirect_uri"],
        "code_verifier": pending["code_verifier"],
        "grant_type": "authorization_code",
    }

    resp = _curl_post(
        CODEX_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=body,
        timeout=30,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Token exchange failed: {resp.status_code} {resp.text[:200]}")

    token_data = resp.json()
    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")

    if access_token:
        # Add to account pool as codex type (for cx/ models)
        account_service.add_accounts_with_type([access_token], "codex")
        account_service.update_account(access_token, {
            "image_quota_unknown": True,
            "quota": 10,
            "status": "active",
        })

    return {
        "ok": True,
        "message": "Đăng nhập Codex OAuth thành công! Token đã được thêm.",
        "access_token_prefix": access_token[:20] + "..." if access_token else "",
        "has_refresh_token": bool(refresh_token),
    }


def get_chatgpt_session_url() -> str:
    """Return URL for getting chatgpt.com session token."""
    return "https://chatgpt.com/api/auth/session"


# ===== Token từ backup 9router =====

def detect_token_type(access_token: str) -> str:
    """Detect token type from JWT claims.

    Returns: "codex" | "google" | "unknown"
    """
    try:
        parts = access_token.split(".")
        if len(parts) < 2:
            return "unknown"
        payload = parts[1]
        payload += "=" * (4 - len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload))

        client_id = decoded.get("client_id", "")
        sub = decoded.get("sub", "")

        if client_id == CODEX_CLIENT_ID:
            return "codex"
        if sub.startswith("google-oauth2"):
            return "google"
        if "chatgpt_account_id" in str(decoded.get("https://api.openai.com/auth", {})):
            return "codex"
        return "unknown"
    except Exception:
        return "unknown"


# ===== Antigravity Google OAuth Flow =====

_pending_antigravity_auths: dict[str, dict[str, str]] = {}

ANTIGRAVITY_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
ANTIGRAVITY_CLIENT_SECRET = "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"
ANTIGRAVITY_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
ANTIGRAVITY_TOKEN_URL = "https://oauth2.googleapis.com/token"
ANTIGRAVITY_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
]

def get_antigravity_auth_url(base_url: str = "") -> dict[str, str]:
    """Generate Antigravity Google OAuth authorization URL.

    IMPORTANT: Google Client ID for Cloud Code strictly registers specific redirect URIs.
    We will use 'http://localhost:8080/callback' as the default loopback, which works
    for manual callback paste from user browsers.
    """
    state = secrets.token_hex(16)
    redirect_uri = "http://localhost:8080/callback"

    params = {
        "client_id": ANTIGRAVITY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(ANTIGRAVITY_SCOPES),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }

    query_parts = []
    for k, v in params.items():
        encoded_key = urllib.parse.quote(str(k), safe="")
        encoded_val = urllib.parse.quote(str(v), safe="")
        query_parts.append(f"{encoded_key}={encoded_val}")
    query_string = "&".join(query_parts)

    auth_url = f"{ANTIGRAVITY_AUTH_URL}?{query_string}"

    _pending_antigravity_auths[state] = {
        "redirect_uri": redirect_uri,
    }

    return {
        "auth_url": auth_url,
        "state": state,
    }


def exchange_antigravity_code(code: str, state: str) -> dict[str, Any]:
    """Exchange authorization code for Antigravity Google OAuth token."""
    pending = _pending_antigravity_auths.pop(state, None)
    redirect_uri = pending["redirect_uri"] if pending else "http://localhost:8080/callback"

    body = {
        "grant_type": "authorization_code",
        "client_id": ANTIGRAVITY_CLIENT_ID,
        "client_secret": ANTIGRAVITY_CLIENT_SECRET,
        "code": code,
        "redirect_uri": redirect_uri,
    }

    resp = _curl_post(
        ANTIGRAVITY_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=body,
        timeout=30,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Google Token exchange failed: {resp.status_code} {resp.text[:200]}")

    token_data = resp.json()
    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")

    if not access_token:
        raise RuntimeError("No access_token returned from Google")

    # 1. Fetch Google user info (email)
    email = None
    try:
        user_resp = requests.get(
            "https://www.googleapis.com/oauth2/v1/userinfo?alt=json",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if user_resp.status_code == 200:
            email = user_resp.json().get("email")
    except Exception as e:
        logger.warning(f"Failed to fetch Google userinfo during OAuth: {e}")

    # 2. Fetch project ID
    project_id = None
    try:
        load_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "google-api-nodejs-client/9.15.1",
            "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
            "Client-Metadata": json.dumps({ "ideType": "IDE_UNSPECIFIED", "platform": "PLATFORM_UNSPECIFIED", "pluginType": "GEMINI" }),
            "x-request-source": "local",
        }
        load_resp = requests.post(
            "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
            headers=load_headers,
            json={"metadata": { "ideType": "IDE_UNSPECIFIED", "platform": "PLATFORM_UNSPECIFIED", "pluginType": "GEMINI" }},
            timeout=15,
        )
        if load_resp.status_code == 200:
            data = load_resp.json()
            project_id = data.get("cloudaicompanionProject", {}).get("id") or data.get("cloudaicompanionProject")
    except Exception as e:
        logger.warning(f"Failed to fetch Antigravity project_id during OAuth: {e}")

    import time
    expires_at = int(time.time()) + int(token_data.get("expires_in", 3599))

    creds = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
    }
    if email:
        creds["email"] = email
    if project_id:
        creds["project_id"] = project_id

    # Add to account pool with type "antigravity"
    account_service.add_accounts_with_credentials([creds], "antigravity")

    return {
        "ok": True,
        "message": "Đăng nhập Antigravity Google OAuth thành công! Token đã được thêm.",
        "email": email,
        "project_id": project_id,
        "has_refresh_token": bool(refresh_token),
    }

