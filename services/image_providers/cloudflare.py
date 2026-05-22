"""
Cloudflare Workers AI Adapter — port from 9router cloudflareAi.js.

Free tier available with Cloudflare account.
Models: @cf/black-forest-labs/flux-1-schnell, @cf/bytedance/stable-diffusion-xl-lightning
"""

from __future__ import annotations

import base64
from typing import Any

from curl_cffi import requests

from services.image_providers._base import BaseImageAdapter, now_sec
from utils.log import logger


class CloudflareAIAdapter(BaseImageAdapter):
    """Cloudflare Workers AI adapter.

    Requires Cloudflare Account ID + API Token (free tier available).
    Model format: cloudflare/@cf/black-forest-labs/flux-1-schnell
    """

    BASE_URL = "https://api.cloudflare.com/client/v4/accounts"

    def build_url(self, model: str, credentials: dict[str, Any] | None) -> str:
        account_id = ""
        if credentials and isinstance(credentials, dict):
            account_id = str(credentials.get("accountId") or credentials.get("account_id") or "")
        return f"{self.BASE_URL}/{account_id}/ai/run/{model}"

    def build_body(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        prompt = str(body.get("prompt") or "")
        n = max(1, min(4, int(body.get("n") or 1)))
        return {
            "prompt": prompt,
            "num_steps": 4 if "schnell" in model else 8,
        }

    def build_headers(
        self,
        credentials: dict[str, Any] | None,
        request_body: dict[str, Any],
        model: str,
        body: dict[str, Any],
    ) -> dict[str, str]:
        api_token = ""
        if credentials and isinstance(credentials, dict):
            api_token = str(credentials.get("apiToken") or credentials.get("api_token") or credentials.get("accessToken") or "")
        return {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    def parse_response(self, response: Any) -> dict[str, Any] | None:
        # Cloudflare returns {"result": {"image": "base64..."}}
        if hasattr(response, "json"):
            data = response.json()
            result = data.get("result", {})
            if isinstance(result, dict) and result.get("image"):
                return {"image_base64": result["image"]}
        return None

    def normalize(self, parsed: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        b64 = parsed.get("image_base64")
        if b64 and isinstance(b64, str):
            return {"created": now_sec(), "data": [{"b64_json": b64}]}
        return {"created": now_sec(), "data": []}

    def test_connection(self, credentials: dict[str, Any] | None = None) -> bool:
        try:
            resp = requests.get("https://api.cloudflare.com/client/v4/user/tokens/verify", timeout=10)
            return resp.status_code < 500
        except Exception:
            return False


cloudflare_adapter = CloudflareAIAdapter()
