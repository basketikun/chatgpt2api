"""
HuggingFace Inference API Adapter — port from 9router huggingface.js.

Free tier available for many models (e.g., black-forest-labs/FLUX.1-schnell).
"""

from __future__ import annotations

import base64
from typing import Any

from curl_cffi import requests

from services.image_providers._base import BaseImageAdapter, now_sec
from utils.log import logger


class HuggingFaceAdapter(BaseImageAdapter):
    """HuggingFace Inference API adapter.

    Supports free-tier models with optional API token.
    Model format: huggingface/owner/model-name
    """

    BASE_URL = "https://api-inference.huggingface.co/models"

    def build_url(self, model: str, credentials: dict[str, Any] | None) -> str:
        return f"{self.BASE_URL}/{model}"

    def build_body(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        prompt = str(body.get("prompt") or "")
        return {"inputs": prompt}

    def build_headers(
        self,
        credentials: dict[str, Any] | None,
        request_body: dict[str, Any],
        model: str,
        body: dict[str, Any],
    ) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = ""
        if credentials and isinstance(credentials, dict):
            api_key = str(credentials.get("apiKey") or credentials.get("accessToken") or "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def parse_response(self, response: Any) -> dict[str, Any] | None:
        # HuggingFace returns raw image bytes
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
            resp = requests.get(f"{self.BASE_URL}/black-forest-labs/FLUX.1-schnell", timeout=10)
            return resp.status_code < 500
        except Exception:
            return False


huggingface_adapter = HuggingFaceAdapter()
