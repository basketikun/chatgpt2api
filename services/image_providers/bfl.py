"""
Black Forest Labs Adapter — port from 9router blackForestLabs.js.

BFL/FLUX API: https://api.bfl.ai/v1
Async polling-based adapter.
"""

from __future__ import annotations

import base64
from typing import Any

from curl_cffi import requests

from services.image_providers._base import (
    BaseImageAdapter,
    POLL_INTERVAL_S,
    POLL_TIMEOUT_S,
    now_sec,
    sleep_s,
)
from utils.log import logger


class BFLAdapter(BaseImageAdapter):
    """Black Forest Labs (FLUX) adapter — async polling.

    Model format: bfl/flux-pro-1.1, bfl/flux-dev, bfl/flux-schnell
    """

    BASE_URL = "https://api.bfl.ai/v1"

    def build_url(self, model: str, credentials: dict[str, Any] | None) -> str:
        # Map model to endpoint
        if "pro" in model:
            return f"{self.BASE_URL}/flux-pro-1.1"
        elif "dev" in model:
            return f"{self.BASE_URL}/flux-dev"
        else:
            return f"{self.BASE_URL}/{model}"

    def build_body(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        prompt = str(body.get("prompt") or "")
        size = str(body.get("size") or "1792x1024")

        # BFL uses width/height
        from services.image_providers._base import size_to_width_height
        w, h = size_to_width_height(size)

        return {
            "prompt": prompt,
            "width": w,
            "height": h,
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
            "X-Key": api_key,
            "Content-Type": "application/json",
        }

    def parse_response(self, response: Any) -> dict[str, Any] | None:
        """Submit and poll for result."""
        if not hasattr(response, "json"):
            return None

        data = response.json()
        task_id = data.get("id")
        if not task_id:
            return None

        # Poll for result
        elapsed = 0.0
        while elapsed < POLL_TIMEOUT_S:
            sleep_s(POLL_INTERVAL_S)
            elapsed += POLL_INTERVAL_S

            try:
                poll_resp = requests.get(
                    f"{self.BASE_URL}/get_result",
                    params={"id": task_id},
                    timeout=30,
                )
                poll_data = poll_resp.json()
            except Exception as exc:
                logger.warning({"event": "bfl_poll_error", "error": str(exc)})
                continue

            status = poll_data.get("status", "")
            if status == "Ready":
                result = poll_data.get("result", {})
                sample_url = result.get("sample")
                if sample_url:
                    from services.image_providers._base import url_to_base64
                    return {"data": [{"b64_json": url_to_base64(sample_url)}]}

            elif status in ("Error", "Failed"):
                logger.error({"event": "bfl_failed", "status": status})
                return None

        logger.error({"event": "bfl_timeout", "elapsed": elapsed})
        return None

    def normalize(self, parsed: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        data = parsed.get("data") or []
        return {"created": now_sec(), "data": data}

    def test_connection(self, credentials: dict[str, Any] | None = None) -> bool:
        try:
            resp = requests.get("https://api.bfl.ai/v1", timeout=10)
            return resp.status_code < 500
        except Exception:
            return False


bfl_adapter = BFLAdapter()
