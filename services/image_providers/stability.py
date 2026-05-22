"""
Stability AI Adapter — port from 9router stabilityAi.js.

Stability AI v2 API: https://api.stability.ai/v2beta/stable-image/generate/
Models: ultra, sd3, core
"""

from __future__ import annotations

import base64
from typing import Any

from curl_cffi import requests

from services.image_providers._base import BaseImageAdapter, now_sec
from utils.log import logger


class StabilityAIAdapter(BaseImageAdapter):
    """Stability AI v2 adapter.

    Model format: stability/sd3, stability/ultra, stability/core
    """

    BASE_URL = "https://api.stability.ai/v2beta/stable-image/generate"

    # Model name → API endpoint
    ENDPOINT_MAP = {
        "ultra": "ultra",
        "sd3": "sd3",
        "core": "core",
    }

    def build_url(self, model: str, credentials: dict[str, Any] | None) -> str:
        endpoint = self.ENDPOINT_MAP.get(model, "sd3")
        return f"{self.BASE_URL}/{endpoint}"

    def build_body(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        prompt = str(body.get("prompt") or "")
        size = str(body.get("size") or "1792x1024")

        aspect_ratio_map = {
            "1024x1024": "1:1",
            "1792x1024": "16:9",
            "1024x1792": "9:16",
            "1280x896": "4:3",
            "896x1280": "3:4",
        }

        return {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio_map.get(size, "16:9"),
            "output_format": "png",
        }

    def build_headers(
        self,
        credentials: dict[str, Any] | None,
        request_body: dict[str, Any],
        model: str,
        body: dict[str, Any],
    ) -> dict[str, str]:
        api_key = ""
        if credentials and isinstance(credentials, dict):
            api_key = str(credentials.get("apiKey") or credentials.get("accessToken") or "")
        return {
            "Authorization": f"Bearer {api_key}",
            "Accept": "image/*",
        }

    def parse_response(self, response: Any) -> dict[str, Any] | None:
        if hasattr(response, "content") and response.headers.get("content-type", "").startswith("image/"):
            return {"image_bytes": response.content}
        return None

    def normalize(self, parsed: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        image_bytes = parsed.get("image_bytes")
        if image_bytes and isinstance(image_bytes, bytes):
            b64 = base64.b64encode(image_bytes).decode("ascii")
            return {"created": now_sec(), "data": [{"b64_json": b64}]}
        return {"created": now_sec(), "data": []}

    def test_connection(self, credentials: dict[str, Any] | None = None) -> bool:
        try:
            resp = requests.get("https://api.stability.ai", timeout=10)
            return resp.status_code < 500
        except Exception:
            return False


stability_adapter = StabilityAIAdapter()
