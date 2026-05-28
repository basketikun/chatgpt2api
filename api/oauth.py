"""
OAuth token import endpoints — compatible with Codex Account Studio + 9router format.

Codex Account Studio pushes tokens via:
  POST /api/oauth/codex/import-token
  Body: { accessToken: string, name?: string }

Also accepts 9router backup-style imports:
  POST /api/oauth/codex/import-tokens (batch)
  Body: { tokens: [{ accessToken, refreshToken?, expiresAt?, name? }] }
"""

from __future__ import annotations

import base64
import json

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.account_service import account_service
from utils.log import logger


class ImportTokenRequest(BaseModel):
    accessToken: str = ""
    name: str | None = None


class ImportTokenBatchRequest(BaseModel):
    tokens: list[dict] = Field(default_factory=list)


def _decode_jwt(token: str) -> dict:
    """Decode JWT payload without verification (for extracting email/plan)."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1].replace("-", "+").replace("_", "/")
        missing = (4 - (len(payload_b64) % 4)) % 4
        payload_b64 += "=" * missing
        return json.loads(base64.b64decode(payload_b64).decode("utf-8"))
    except Exception:
        return {}


def _extract_account_info(token: str) -> dict:
    """Extract account metadata from JWT (email, workspace, plan) — 9router-compatible."""
    payload = _decode_jwt(token)
    if not payload:
        return {}

    auth = payload.get("https://api.openai.com/auth") or {}
    profile = payload.get("https://api.openai.com/profile") or {}

    info: dict = {}

    email = profile.get("email") or payload.get("email") or payload.get("preferred_username")
    if email:
        info["email"] = email

    if auth.get("chatgpt_account_id"):
        info["chatgpt_account_id"] = auth["chatgpt_account_id"]
    if auth.get("chatgpt_plan_type"):
        info["chatgpt_plan_type"] = auth["chatgpt_plan_type"]
    if payload.get("exp"):
        info["jwt_exp"] = payload["exp"]

    return info


def create_router() -> APIRouter:
    router = APIRouter()

    @router.post("/api/oauth/codex/import-token")
    @router.post("/dashboard/providers/codex")
    async def import_token(body: ImportTokenRequest):
        """Import a single ChatGPT access token — Codex Account Studio compatible.

        Accepts the same format as 9router's /api/oauth/codex/import-token:
          { accessToken: "eyJ...", name?: "optional label" }

        The token is added to the codex account pool and available immediately
        for cx/auto, cx/gpt-5.5, and all other cx/* models.
        """
        token = str(body.accessToken or "").strip()
        if not token:
            return {"success": False, "error": "Access token is required"}

        # Decode JWT to extract metadata
        info = _extract_account_info(token)
        email = info.get("email")
        name = body.name or email or "ChatGPT Access Token"

        # Store provider-specific metadata
        provider_data = {"authMethod": "access_token"}
        if info.get("chatgpt_account_id"):
            provider_data["chatgptAccountId"] = info["chatgpt_account_id"]
        if info.get("chatgpt_plan_type"):
            provider_data["chatgptPlanType"] = info["chatgpt_plan_type"]
        if info.get("jwt_exp"):
            provider_data["jwtExp"] = info["jwt_exp"]

        # Check if token already exists
        existing = account_service.get_account(token)
        is_new = existing is None

        # Add to codex pool with full credential support
        creds = [{
            "access_token": token,
            "refresh_token": None,  # Codex Account Studio tokens may not have refresh
            "expires_at": None,
            "email": email,
        }]
        result = account_service.add_accounts_with_credentials(creds, "codex")

        # Set image capability for codex accounts (DALL-E via chatgpt.com backend)
        account_service.update_account(token, {
            "image_quota_unknown": True,
            "quota": 10,
            "status": "active",
        })

        logger.info({
            "event": "codex_token_imported",
            "source": "codex_account_studio",
            "email": email or "(none)",
            "plan": info.get("chatgpt_plan_type", "unknown"),
            "is_new": is_new,
        })

        return {
            "success": True,
            "connection": {
                "provider": "codex",
                "email": email,
                "name": name,
                "workspace": info.get("chatgpt_account_id"),
                "plan": info.get("chatgpt_plan_type"),
                "is_new": is_new,
            },
        }

    @router.post("/api/oauth/codex/import-tokens")
    async def import_tokens_batch(body: ImportTokenBatchRequest):
        """Batch import multiple tokens — 9router backup compatible.

        Accepts: { tokens: [{ accessToken, refreshToken?, expiresAt?, name? }] }

        Each token is decoded and added to the codex pool with image support.
        """
        if not body.tokens:
            return {"success": False, "error": "tokens array is required"}

        creds = []
        imported = 0
        skipped = 0
        results = []

        for t in body.tokens:
            if not isinstance(t, dict):
                continue
            access_token = str(t.get("accessToken") or "").strip()
            if not access_token:
                continue

            existing = account_service.get_account(access_token)
            if existing:
                skipped += 1
                continue

            info = _extract_account_info(access_token)
            email = info.get("email")
            name = t.get("name") or email or "ChatGPT Access Token"

            creds.append({
                "access_token": access_token,
                "refresh_token": str(t.get("refreshToken") or "").strip() or None,
                "expires_at": t.get("expiresAt"),
                "email": email,
            })

            account_service.update_account(access_token, {
                "image_quota_unknown": True,
                "quota": 10,
                "status": "active",
            })

            imported += 1
            results.append({
                "email": email,
                "name": name,
                "plan": info.get("chatgpt_plan_type"),
                "is_new": True,
            })

        if creds:
            add_result = account_service.add_accounts_with_credentials(creds, "codex")
            imported = add_result.get("added", 0) + add_result.get("updated", 0)

        logger.info({
            "event": "codex_tokens_batch_imported",
            "count": imported,
            "skipped": skipped,
        })

        return {
            "success": True,
            "imported": imported,
            "skipped": skipped,
            "connections": results,
        }

    return router
