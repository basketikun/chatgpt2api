"""
Image Provider Adapters — port from 9router open-sse/handlers/imageProviders/.

Base utilities shared across all image adapters:
- POLL_INTERVAL_MS / POLL_TIMEOUT_MS for async adapters
- size_to_aspect_ratio: convert OpenAI size string to width/height
- url_to_base64: download image URL and convert to base64
- Size constants and default (16:9)
"""

from __future__ import annotations

import base64
import time
from typing import Any

from curl_cffi import requests

# Polling config (port from 9router _base.js)
POLL_INTERVAL_S = 1.5
POLL_TIMEOUT_S = 120

# OpenAI size → width x height (16:9 mặc định)
SIZE_MAP: dict[str, tuple[int, int]] = {
    "1024x1024": (1024, 1024),    # 1:1
    "1792x1024": (1792, 1024),    # 16:9 ← DEFAULT
    "1024x1792": (1024, 1792),    # 9:16
    "1280x896":  (1280, 896),     # ~4:3 landscape
    "896x1280":  (896, 1280),     # ~4:3 portrait
}

DEFAULT_SIZE = "1792x1024"


def size_to_width_height(size: str | None) -> tuple[int, int]:
    """Convert OpenAI size string → (width, height). Default 16:9."""
    if not size:
        return SIZE_MAP[DEFAULT_SIZE]
    if size in SIZE_MAP:
        return SIZE_MAP[size]
    # Try parsing "WxH" format
    try:
        parts = size.split("x")
        if len(parts) == 2:
            return (int(parts[0]), int(parts[1]))
    except (ValueError, TypeError):
        pass
    return SIZE_MAP[DEFAULT_SIZE]


def size_to_aspect_ratio(size: str | None) -> str:
    """Convert OpenAI size → aspect ratio string (e.g. '16:9')."""
    w, h = size_to_width_height(size)
    if w == h:
        return "1:1"
    if w > h:
        if w / h > 1.6:
            return "16:9"
        return "4:3"
    else:
        if h / w > 1.6:
            return "9:16"
        return "3:4"


def url_to_base64(url: str, timeout: int = 30) -> str:
    """Download image from URL and return as base64 string."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return base64.b64encode(resp.content).decode("ascii")


def now_sec() -> int:
    """Current time in seconds (Unix timestamp)."""
    return int(time.time())


def sleep_s(seconds: float) -> None:
    """Sleep for seconds."""
    time.sleep(seconds)


class BaseImageAdapter:
    """Base class for image generation adapters.

    Ported from 9router imageProviders adapters.
    Each adapter implements:
    - build_url(model, credentials) -> str
    - build_body(model, body) -> dict
    - build_headers(credentials, request_body, model, body) -> dict
    - normalize(parsed) -> dict  (OpenAI-compatible format)
    - parse_response(response) -> dict | None  (optional, for async/polling)
    """

    no_auth: bool = False

    def build_url(self, model: str, credentials: dict[str, Any] | None) -> str:
        raise NotImplementedError

    def build_body(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def build_headers(
        self,
        credentials: dict[str, Any] | None,
        request_body: dict[str, Any],
        model: str,
        body: dict[str, Any],
    ) -> dict[str, str]:
        raise NotImplementedError

    def parse_response(self, response: Any) -> dict[str, Any] | None:
        """Optional: custom response parsing (async polling, SSE, etc.)."""
        return None

    def normalize(self, parsed: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        """Convert provider response to OpenAI format: {created, data: [{b64_json}]}."""
        raise NotImplementedError

    def test_connection(self, credentials: dict[str, Any] | None = None) -> bool:
        """Quick connection test."""
        return True
