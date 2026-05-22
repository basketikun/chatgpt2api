"""
NVIDIA NIM Image Generation Adapter.

Endpoint: https://ai.api.nvidia.com/v1/genai/{model}
Auth: Bearer token from build.nvidia.com
Format: Custom request/response — needs conversion to/from OpenAI format.

Supported aspect ratios (from NVIDIA docs):
  1:1, 16:9, 9:16, 5:4, 4:5, 3:2, 2:3

Example model: black-forest-labs/flux.2-klein-4b
"""

from __future__ import annotations

import base64
from typing import Any

from curl_cffi import requests

from services.image_providers._base import (
    BaseImageAdapter,
    now_sec,
    size_to_width_height,
)
from services.config import config
from utils.log import logger


# NVIDIA-supported resolutions per aspect ratio
# klein model max ~1M pixels; standard model max ~2M pixels
_NVIDIA_SIZE_MAP: dict[str, tuple[int, int]] = {
    "1024x1024": (1024, 1024),    # 1:1
    "1152x768":  (1152, 768),     # 3:2
    "768x1152":  (768, 1152),     # 2:3
    "1280x1024": (1280, 1024),    # 5:4
    "1024x1280": (1024, 1280),    # 4:5
    "1344x768":  (1344, 768),     # 16:9
    "768x1344":  (768, 1344),     # 9:16
}
_NVIDIA_DEFAULT_SIZE = "1344x768"  # 16:9


def _nvidia_size(size: str | None) -> tuple[int, int]:
    """Map OpenAI size → NVIDIA-compatible resolution."""
    if not size:
        return _NVIDIA_SIZE_MAP[_NVIDIA_DEFAULT_SIZE]
    if size in _NVIDIA_SIZE_MAP:
        return _NVIDIA_SIZE_MAP[size]
    # Try parsing WxH from existing SIZE_MAP, then map to closest nvidia size
    w, h = size_to_width_height(size)
    # Find best match by aspect ratio
    target_ratio = w / h if h else 1.0
    best = _NVIDIA_SIZE_MAP[_NVIDIA_DEFAULT_SIZE]
    best_diff = float("inf")
    for nw, nh in _NVIDIA_SIZE_MAP.values():
        n_ratio = nw / nh if nh else 1.0
        diff = abs(target_ratio - n_ratio)
        if diff < best_diff:
            best_diff = diff
            best = (nw, nh)
    return best


class NvidiaNimImageAdapter(BaseImageAdapter):
    """NVIDIA NIM Image Generation adapter.

    Uses NVIDIA's image generation endpoint (different from chat endpoint).
    """

    BASE_URL = "https://ai.api.nvidia.com/v1/genai"

    def _get_keys(self) -> list[str]:
        cfg = config.data.get("providers") or {}
        nv_cfg = cfg.get("nvidia_nim") or {}
        single = str(nv_cfg.get("api_key") or "").strip()
        multi = nv_cfg.get("api_keys") or []
        if not isinstance(multi, list):
            multi = []
        keys = [k.strip() for k in multi if k.strip()]
        if single and single not in keys:
            keys.insert(0, single)
        return keys

    def build_url(self, model: str, credentials: dict[str, Any] | None) -> str:
        return f"{self.BASE_URL}/{model}"

    def build_body(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        prompt = str(body.get("prompt") or "")
        size = str(body.get("size") or "")
        w, h = _nvidia_size(size if size else None)

        return {
            "prompt": prompt,
            "width": w,
            "height": h,
            "seed": int(body.get("seed", 0)),
            "steps": max(5, int(body.get("steps", 28))),
        }

    def build_headers(
        self,
        credentials: dict[str, Any] | None,
        request_body: dict[str, Any],
        model: str,
        body: dict[str, Any],
    ) -> dict[str, str]:
        # Use API key from provider config
        keys = self._get_keys()
        api_key = keys[0] if keys else ""
        if credentials and isinstance(credentials, dict):
            api_key = str(credentials.get("apiKey") or credentials.get("accessToken") or api_key)
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def parse_response(self, response: Any) -> dict[str, Any] | None:
        """Parse NVIDIA image gen response → OpenAI image format."""
        if not hasattr(response, "json"):
            return None

        try:
            data = response.json()
        except Exception as exc:
            logger.error({"event": "nvidia_image_parse_error", "error": str(exc)})
            return None

        # Response format: {"artifacts":[{"base64":"..."}]} or {"image":"..."}
        image_b64 = ""

        # NVIDIA returns artifacts array with base64
        artifacts = data.get("artifacts") or []
        if isinstance(artifacts, list) and artifacts:
            first = artifacts[0]
            if isinstance(first, dict):
                image_b64 = first.get("base64") or first.get("image") or ""
            elif isinstance(first, str):
                image_b64 = first

        if not image_b64:
            # Try direct image field
            image_b64 = data.get("image") or ""

        if not image_b64:
            images = data.get("images") or data.get("data") or []
            if isinstance(images, list) and images:
                first = images[0]
                if isinstance(first, dict):
                    image_b64 = first.get("image") or first.get("b64_json") or first.get("url") or first.get("base64") or ""
                elif isinstance(first, str):
                    image_b64 = first

        if not image_b64:
            logger.error({"event": "nvidia_image_no_data", "keys": list(data.keys())[:5]})
            return None

        # If it's a URL, convert to base64
        if image_b64.startswith("http"):
            from services.image_providers._base import url_to_base64
            image_b64 = url_to_base64(image_b64)

        return {"data": [{"b64_json": image_b64}]}

    def normalize(self, parsed: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        """Convert parsed result → OpenAI image response format."""
        data = parsed.get("data") or []
        normalized_data = []
        for item in data:
            b64 = item.get("b64_json") or ""
            if b64:
                if not b64.startswith("data:"):
                    b64 = f"data:image/png;base64,{b64}"
                normalized_data.append({"b64_json": b64, "revised_prompt": str(body.get("prompt") or "")})

        if not normalized_data:
            return {"created": now_sec(), "data": []}

        return {"created": now_sec(), "data": normalized_data}

    def test_connection(self, credentials: dict[str, Any] | None = None) -> bool:
        """Test connectivity to NVIDIA image gen endpoint."""
        try:
            keys = self._get_keys()
            api_key = keys[0] if keys else ""
            resp = requests.get(
                "https://integrate.api.nvidia.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False


nvidia_nim_image_adapter = NvidiaNimImageAdapter()
