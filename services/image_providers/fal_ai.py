"""
Fal.ai Adapter — port from 9router falAi.js.

Async (polling-based) adapter for Fal.ai queue API.
Model format: fal_ai/fal-ai/flux/schnell
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


class FalAIAdapter(BaseImageAdapter):
    """Fal.ai async queue adapter.

    Submits to queue API, polls status_url until completion.
    """

    BASE_URL = "https://queue.fal.run"

    def build_url(self, model: str, credentials: dict[str, Any] | None) -> str:
        return f"{self.BASE_URL}/{model}"

    def build_body(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        prompt = str(body.get("prompt") or "")
        size = str(body.get("size") or "1792x1024")

        # Map OpenAI size to fal.ai image_size
        size_map = {
            "1024x1024": "square_hd",
            "1792x1024": "landscape_16_9",
            "1024x1792": "portrait_16_9",
            "1280x896": "landscape_4_3",
            "896x1280": "portrait_4_3",
        }

        return {
            "prompt": prompt,
            "image_size": size_map.get(size, "landscape_16_9"),
            "num_images": max(1, min(4, int(body.get("n") or 1))),
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
            "Authorization": f"Key {api_key}",
            "Content-Type": "application/json",
        }

    def parse_response(self, response: Any) -> dict[str, Any] | None:
        """Submit to queue, poll for result."""
        if not hasattr(response, "json"):
            return None

        data = response.json()
        status_url = data.get("status_url")
        if not status_url:
            logger.error({"event": "fal_ai_no_status_url", "response": str(data)[:200]})
            return None

        # Poll for completion
        elapsed = 0.0
        while elapsed < POLL_TIMEOUT_S:
            sleep_s(POLL_INTERVAL_S)
            elapsed += POLL_INTERVAL_S

            try:
                poll_resp = requests.get(status_url, timeout=30)
                poll_data = poll_resp.json()
            except Exception as exc:
                logger.warning({"event": "fal_ai_poll_error", "error": str(exc)})
                continue

            status = poll_data.get("status", "")
            if status == "COMPLETED":
                result = poll_data.get("result") or poll_data
                images = (
                    result.get("images") or
                    [result.get("image")] if result.get("image") else
                    []
                )
                if images:
                    b64_list = []
                    for img in images:
                        if isinstance(img, dict) and img.get("url"):
                            from services.image_providers._base import url_to_base64
                            b64_list.append({"b64_json": url_to_base64(img["url"])})
                    return {"data": b64_list}

                logger.error({"event": "fal_ai_no_images", "result": str(result)[:200]})
                return None

            elif status in ("FAILED", "CANCELLED"):
                error_msg = str(poll_data.get("error") or "unknown")
                logger.error({"event": "fal_ai_failed", "status": status, "error": error_msg})
                return None

        logger.error({"event": "fal_ai_timeout", "elapsed": elapsed})
        return None

    def normalize(self, parsed: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        data = parsed.get("data") or []
        return {"created": now_sec(), "data": data}

    def test_connection(self, credentials: dict[str, Any] | None = None) -> bool:
        try:
            resp = requests.get("https://queue.fal.run", timeout=10)
            return resp.status_code < 500
        except Exception:
            return False


fal_ai_adapter = FalAIAdapter()
