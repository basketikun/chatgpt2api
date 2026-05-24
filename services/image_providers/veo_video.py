"""
Veo Video Adapter — Google Veo 3.1 video generation.

Endpoint: :predictLongRunning (async operation with polling)
Model: veo-3.1-generate-preview
Supports: text→video, image→video, video extension, reference images
"""

from __future__ import annotations

import base64
import time
from typing import Any

from curl_cffi import requests

from utils.log import logger

VEO_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
VEO_MODEL = "veo-3.1-generate-preview"
VEO_POLL_INTERVAL = 10  # seconds


def _veo_base() -> str:
    """Honor providers.gemini_free.base_url for VN-block proxy."""
    try:
        from services.config import config
        cfg = (config.data.get("providers") or {}).get("gemini_free") or {}
        override = str(cfg.get("base_url") or "").rstrip("/")
        if override:
            if not override.endswith("/v1beta"):
                override = override + "/v1beta"
            return override
    except Exception:
        pass
    return "https://generativelanguage.googleapis.com/v1beta"
VEO_MAX_WAIT = 600  # 10 minutes max


class VeoVideoAdapter:
    """Google Veo 3.1 video generation adapter.

    Model format: veo/veo-3.1-generate-preview
    Uses Veo predictLongRunning API with operation polling.
    """

    def __init__(self):
        self._key_index = 0

    def _get_api_keys(self, credentials: dict[str, Any] | None) -> list[str]:
        if not credentials or not isinstance(credentials, dict):
            return []
        keys = credentials.get("apiKeys") or credentials.get("api_keys") or []
        if isinstance(keys, list) and keys:
            return [str(k) for k in keys if k]
        single = str(credentials.get("apiKey") or credentials.get("api_key") or "")
        return [single] if single else []

    def get_key_count(self, credentials: dict[str, Any] | None) -> int:
        return len(self._get_api_keys(credentials))

    def _build_url(self, credentials: dict[str, Any] | None, key_index: int = 0) -> str:
        keys = self._get_api_keys(credentials)
        api_key = keys[key_index % len(keys)] if keys else ""
        return f"{VEO_BASE}/{VEO_MODEL}:predictLongRunning?key={api_key}"

    def _build_body(self, body: dict[str, Any]) -> dict[str, Any]:
        """Build Veo API request body."""
        prompt = str(body.get("prompt") or "")
        instance: dict[str, Any] = {"prompt": prompt}

        # Optional: input image for image→video
        image_b64 = body.get("image")
        if image_b64:
            instance["image"] = {
                "inlineData": {"mimeType": "image/png", "data": image_b64}
            }

        # Optional: last frame for interpolation
        last_frame = body.get("last_frame")
        if last_frame:
            instance["lastFrame"] = {
                "inlineData": {"mimeType": "image/png", "data": last_frame}
            }

        request: dict[str, Any] = {"instances": [instance]}

        # Parameters
        params: dict[str, Any] = {}
        aspect_ratio = body.get("aspect_ratio") or "16:9"
        if aspect_ratio:
            params["aspectRatio"] = aspect_ratio

        duration = body.get("duration")
        if duration:
            params["durationSeconds"] = duration

        resolution = body.get("resolution")
        if resolution:
            params["resolution"] = resolution

        if params:
            request["parameters"] = params

        return request

    def generate(
        self,
        body: dict[str, Any],
        credentials: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Generate video — submit, poll, download.

        Returns:
            {"data": [{"b64_json": "<base64 video>"}]}
        """
        max_keys = self.get_key_count(credentials)
        last_error = ""

        for key_try in range(max(max_keys, 1)):
            try:
                url = self._build_url(credentials, key_try)
                req_body = self._build_body(body)

                logger.info({
                    "event": "veo_request",
                    "url": url[:120],
                    "key_try": key_try,
                })

                # Step 1: Submit
                resp = requests.post(url, json=req_body, timeout=60)
                if resp.status_code >= 400:
                    error_text = ""
                    try:
                        error_text = resp.text[:500]
                    except Exception:
                        pass
                    if resp.status_code in (400, 429) and key_try < max_keys - 1:
                        last_error = error_text
                        continue
                    raise RuntimeError(f"Veo submit error {resp.status_code}: {error_text[:200]}")

                data = resp.json()
                operation_name = data.get("name", "")
                if not operation_name:
                    raise RuntimeError(f"Veo did not return operation name: {data}")

                logger.info({"event": "veo_submitted", "operation": operation_name[:80]})

                # Step 2: Poll until done
                base_url = f"{_veo_base()}/{operation_name}"
                keys = self._get_api_keys(credentials)
                api_key = keys[key_index % len(keys)] if keys else ""

                start_time = time.time()
                while time.time() - start_time < VEO_MAX_WAIT:
                    time.sleep(VEO_POLL_INTERVAL)
                    poll_resp = requests.get(f"{base_url}?key={api_key}", timeout=30)
                    if poll_resp.status_code >= 400:
                        continue  # keep polling
                    poll_data = poll_resp.json()
                    if poll_data.get("done"):
                        # Step 3: Extract video URI and download
                        video_uri = (
                            poll_data.get("response", {})
                            .get("generateVideoResponse", {})
                            .get("generatedSamples", [{}])[0]
                            .get("video", {})
                            .get("uri", "")
                        )
                        if not video_uri:
                            raise RuntimeError("Veo completed but no video URI")

                        logger.info({"event": "veo_downloading", "uri": video_uri[:120]})

                        dl_resp = requests.get(
                            f"{video_uri}?key={api_key}",
                            timeout=120,
                        )
                        if dl_resp.status_code == 200:
                            video_b64 = base64.b64encode(dl_resp.content).decode()
                            return {
                                "created": int(time.time()),
                                "data": [{"b64_json": video_b64}],
                            }

                        raise RuntimeError(f"Veo download error {dl_resp.status_code}")

                    logger.info({
                        "event": "veo_polling",
                        "operation": operation_name[:40],
                        "elapsed": int(time.time() - start_time),
                    })

                raise RuntimeError(f"Veo timed out after {VEO_MAX_WAIT}s")

            except RuntimeError:
                raise
            except Exception as exc:
                logger.error({"event": "veo_error", "error": str(exc)})
                if key_try < max_keys - 1:
                    continue
                raise RuntimeError(f"Veo generation failed: {exc}") from exc

        raise RuntimeError(f"Veo generation failed: {last_error}")


veo_adapter = VeoVideoAdapter()
