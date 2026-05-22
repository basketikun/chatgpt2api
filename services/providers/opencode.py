"""
OpenCode Free Provider — port from 9router open-sse/executors/opencode.js.

OpenCode provides free LLM access via https://opencode.ai/zen/v1/chat/completions.
No authentication required — uses virtual "public" token.
This bypasses ChatGPT's 24KB free-account payload limit entirely.
"""

from __future__ import annotations

import json
import time
from typing import Any, Iterator

from curl_cffi import requests

from utils.helper import sse_json_stream
from utils.log import logger

OPENCODE_BASE_URL = "https://opencode.ai"
OPENCODE_CHAT_URL = f"{OPENCODE_BASE_URL}/zen/v1/chat/completions"
OPENCODE_MODELS_URL = f"{OPENCODE_BASE_URL}/zen/v1/models"
OPENCODE_MESSAGES_URL = f"{OPENCODE_BASE_URL}/zen/v1/messages"

# Models that use Claude format (messages endpoint)
CLAUDE_FORMAT_MODELS = {"big-pickle"}

# Default headers — ported from 9router OpenCodeExecutor
DEFAULT_HEADERS = {
    "Authorization": "Bearer public",
    "x-opencode-client": "desktop",
    "Content-Type": "application/json",
    "Accept": "text/event-stream, application/json",
}


class OpenCodeProvider:
    """Free LLM provider via OpenCode.ai — no API key needed."""

    def __init__(self):
        self._models_cache: list[dict[str, Any]] | None = None
        self._models_cache_time: float = 0
        self._models_cache_ttl: float = 300  # 5 minutes

    @property
    def is_available(self) -> bool:
        """Quick availability check."""
        try:
            resp = requests.get(
                f"{OPENCODE_BASE_URL}/zen/v1/models",
                headers=DEFAULT_HEADERS,
                timeout=10,
            )
            return resp.status_code < 500
        except Exception:
            return False

    def list_models(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Fetch available free models from OpenCode.

        Filters to models ending in '-free' (port from 9router opencode-free filter).
        """
        now = time.time()
        if (
            not force_refresh
            and self._models_cache is not None
            and (now - self._models_cache_time) < self._models_cache_ttl
        ):
            return self._models_cache

        try:
            resp = requests.get(OPENCODE_MODELS_URL, headers=DEFAULT_HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning({"event": "opencode_models_fetch_failed", "status": resp.status_code})
                return self._models_cache or []

            data = resp.json()
            all_models = data.get("data") if isinstance(data, dict) else data
            if not isinstance(all_models, list):
                all_models = []

            # Filter to free models (port from 9router opencode-free filter)
            free_models = [
                {
                    "id": f"oc/{m.get('id', '')}",
                    "object": "model",
                    "created": int(now),
                    "owned_by": "opencode",
                }
                for m in all_models
                if isinstance(m, dict) and str(m.get("id", "")).endswith("-free")
            ]

            self._models_cache = free_models
            self._models_cache_time = now
            return free_models

        except Exception as exc:
            logger.warning({"event": "opencode_models_fetch_error", "error": str(exc)})
            return self._models_cache or []

    def chat_completions(
        self,
        messages: list[dict[str, Any]],
        model: str = "auto",
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs,
    ) -> dict[str, Any] | Iterator[str]:
        """Send chat request to OpenCode API.

        Args:
            messages: Normalized chat messages
            model: Model name (without oc/ prefix)
            stream: Whether to stream the response
            temperature: Sampling temperature
            max_tokens: Max tokens to generate

        Returns:
            Dict for non-streaming, Iterator[str] for streaming SSE chunks
        """
        body: dict[str, Any] = {
            "messages": messages,
            "model": model,
            "stream": stream,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        body.update(kwargs)

        # Some models use Claude format (messages endpoint)
        if model in CLAUDE_FORMAT_MODELS:
            url = OPENCODE_MESSAGES_URL
        else:
            url = OPENCODE_CHAT_URL

        logger.info({
            "event": "opencode_request",
            "model": model,
            "stream": stream,
            "message_count": len(messages),
        })

        try:
            resp = requests.post(
                url,
                headers=DEFAULT_HEADERS,
                json=body,
                timeout=300,
                stream=stream,
            )

            if resp.status_code != 200:
                error_text = ""
                try:
                    error_text = resp.text[:500]
                except Exception:
                    pass
                logger.error({
                    "event": "opencode_error",
                    "status": resp.status_code,
                    "error": error_text,
                })
                raise RuntimeError(
                    f"OpenCode API error: status={resp.status_code}, body={error_text}"
                )

            if stream:
                return self._stream_response(resp)
            else:
                return resp.json()

        except requests.RequestsError as exc:
            logger.error({"event": "opencode_connection_error", "error": str(exc)})
            raise RuntimeError(f"OpenCode connection failed: {exc}") from exc

    def _stream_response(self, response) -> Iterator[str]:
        """Stream SSE response from OpenCode, yielding OpenAI-compatible chunks."""
        try:
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="ignore") if isinstance(raw_line, bytes) else str(raw_line)
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        yield "data: [DONE]\n\n"
                        break
                    yield f"data: {payload}\n\n"
        except Exception as exc:
            logger.error({"event": "opencode_stream_error", "error": str(exc)})
            error_chunk = json.dumps({
                "error": {
                    "message": str(exc),
                    "type": "opencode_stream_error",
                }
            }, ensure_ascii=False)
            yield f"data: {error_chunk}\n\n"
            yield "data: [DONE]\n\n"


# Singleton
opencode_provider = OpenCodeProvider()
