"""
SD WebUI Adapter — port from 9router sdwebui.js.

AUTOMATIC1111 Stable Diffusion Web UI at localhost:7860.
NoAuth — completely free, runs on local GPU.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from curl_cffi import requests

from services.image_providers._base import BaseImageAdapter, now_sec, size_to_width_height
from utils.log import logger


class SDWebUIAdapter(BaseImageAdapter):
    """Stable Diffusion Web UI (AUTOMATIC1111) adapter.

    NoAuth — runs locally at http://localhost:7860.
    """

    no_auth = True

    def __init__(self, base_url: str = "http://localhost:7860"):
        self.base_url = base_url.rstrip("/")

    def build_url(self, model: str, credentials: dict[str, Any] | None) -> str:
        return f"{self.base_url}/sdapi/v1/txt2img"

    def build_body(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        prompt = str(body.get("prompt") or "")
        n = max(1, min(4, int(body.get("n") or 1)))
        size = str(body.get("size") or "1792x1024")
        w, h = size_to_width_height(size)

        return {
            "prompt": prompt,
            "negative_prompt": "",
            "width": w,
            "height": h,
            "steps": 20,
            "batch_size": n,
            "cfg_scale": 7,
            "sampler_name": "Euler a",
        }

    def build_headers(
        self,
        credentials: dict[str, Any] | None,
        request_body: dict[str, Any],
        model: str,
        body: dict[str, Any],
    ) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def normalize(self, parsed: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        # SD WebUI returns {"images": ["base64...", ...]}
        images = parsed.get("images") or []
        data = [
            {"b64_json": img}
            for img in images
            if isinstance(img, str)
        ]
        return {"created": now_sec(), "data": data}

    def test_connection(self, credentials: dict[str, Any] | None = None) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/sdapi/v1/sd-models", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


sdwebui_adapter = SDWebUIAdapter()
