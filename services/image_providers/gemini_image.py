"""
Gemini Image Adapter — port from 9router gemini.js.

Google Gemini image generation via Imagen.
Uses Gemini API: https://generativelanguage.googleapis.com/v1beta/models/
"""

from __future__ import annotations

import base64
from typing import Any

from curl_cffi import requests

from services.image_providers._base import BaseImageAdapter, now_sec
from utils.log import logger


class GeminiImageAdapter(BaseImageAdapter):
    """Gemini Imagen image generation adapter.

    Model format: gemini-image/imagen-3.0-generate-001
    Uses Gemini generateContent API with image generation config.
    Supports API key rotation from api_keys array.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    _key_index: int = 0

    def _resolve_base(self) -> str:
        """Honor providers.gemini_free.base_url override (Cloudflare Worker)."""
        try:
            from services.config import config
            cfg = (config.data.get("providers") or {}).get("gemini_free") or {}
            override = str(cfg.get("base_url") or "").rstrip("/")
            if override:
                if not override.endswith("/v1beta"):
                    override = override + "/v1beta"
                return override + "/models"
        except Exception:
            pass
        return self.BASE_URL

    def _get_api_keys(self, credentials: dict[str, Any] | None) -> list[str]:
        """Get all available API keys from credentials."""
        if not credentials or not isinstance(credentials, dict):
            return []
        keys = credentials.get("apiKeys") or credentials.get("api_keys") or []
        if isinstance(keys, list) and keys:
            return [str(k) for k in keys if k]
        single = str(credentials.get("apiKey") or credentials.get("api_key") or "")
        return [single] if single else []

    def build_url(self, model: str, credentials: dict[str, Any] | None, key_index: int = 0) -> str:
        api_key = ""
        if credentials and isinstance(credentials, dict):
            keys = self._get_api_keys(credentials)
            if keys:
                api_key = keys[key_index % len(keys)]
        return f"{self._resolve_base()}/{model}:generateContent?key={api_key}"

    def get_key_count(self, credentials: dict[str, Any] | None) -> int:
        return len(self._get_api_keys(credentials))

    # Size → aspect ratio mapping (OpenAI format → Gemini format)
    _SIZE_TO_RATIO = {
        # 16:9
        "1792x1024": "16:9", "1344x768": "16:9",
        # 9:16
        "1024x1792": "9:16", "768x1344": "9:16",
        # 1:1
        "1024x1024": "1:1", "768x768": "1:1", "512x512": "1:1", "256x256": "1:1",
        # 4:3
        "1792x1344": "4:3", "1200x896": "4:3", "1024x768": "4:3",
        # 3:2
        "1536x1024": "3:2", "1264x848": "3:2",
        # 3:4
        "768x1024": "3:4", "896x1200": "3:4",
    }

    def build_body(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        prompt = str(body.get("prompt") or "")
        images = body.get("images") or []
        n = max(1, min(4, int(body.get("n") or 1)))
        size = str(body.get("size") or "")

        parts = [{"text": prompt}]
        for img in images:
            if isinstance(img, bytes):
                import base64 as b64
                parts.append({"inlineData": {"mimeType": "image/png", "data": b64.b64encode(img).decode()}})
            elif isinstance(img, str) and img.startswith("data:"):
                header, data = img.split(",", 1)
                mime = header.split(";")[0].replace("data:", "")
                parts.append({"inlineData": {"mimeType": mime, "data": data}})

        gen_config: dict[str, Any] = {
            "responseModalities": ["TEXT", "IMAGE"],
        }

        # Note: generateContent does NOT support responseFormat.
        # Aspect ratio and image size are controlled via model-specific parameters
        # that vary by model version. Default is model-dependent.

        return {
            "contents": [{"parts": parts}],
            "generationConfig": gen_config,
        }

    def build_headers(
        self,
        credentials: dict[str, Any] | None,
        request_body: dict[str, Any],
        model: str,
        body: dict[str, Any],
    ) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def parse_response(self, response: Any) -> dict[str, Any] | None:
        """Extract inline image data from Gemini response."""
        if not hasattr(response, "json"):
            return None

        data = response.json()

        # Check for error
        if "error" in data:
            err = data["error"]
            raise RuntimeError(f"Gemini API error {err.get('status','')}: {err.get('message','')[:200]}")

        images = []

        candidates = data.get("candidates") or []
        for candidate in candidates:
            content = candidate.get("content") or {}
            parts = content.get("parts") or []
            for part in parts:
                if "inlineData" in part:
                    inline = part["inlineData"]
                    b64 = inline.get("data") or ""
                    if b64:
                        images.append({"b64_json": b64})

        return {"data": images} if images else None

    def normalize(self, parsed: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        data = parsed.get("data") or []
        return {"created": now_sec(), "data": data}

    def test_connection(self, credentials: dict[str, Any] | None = None) -> bool:
        try:
            resp = requests.get("https://generativelanguage.googleapis.com", timeout=10)
            return resp.status_code < 500
        except Exception:
            return False


gemini_image_adapter = GeminiImageAdapter()
