"""
9Router Proxy Provider — forward chat requests to 9router.

9router handles OAuth for Claude, Codex, Copilot, Gemini CLI, Cursor...
So chatgpt2api just proxies to 9router which has all the tokens.
This is the best approach: 9router for chat, chatgpt2api for image + web UI.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from curl_cffi import requests

from services.config import config
from utils.log import logger


class NinerouterProxy:
    """Proxy chat requests to 9router's OpenAI-compatible endpoint."""

    def __init__(self):
        self._base_url: str = ""
        self._api_key: str = ""

    @property
    def base_url(self) -> str:
        if not self._base_url:
            cfg = config.data.get("ninerouter") or {}
            self._base_url = str(cfg.get("base_url") or "http://localhost:20128").rstrip("/")
        return self._base_url

    @property
    def api_key(self) -> str:
        if not self._api_key:
            cfg = config.data.get("ninerouter") or {}
            self._api_key = str(cfg.get("api_key") or "")
        return self._api_key

    @property
    def chat_url(self) -> str:
        return f"{self.base_url}/v1/chat/completions"

    @property
    def models_url(self) -> str:
        return f"{self.base_url}/v1/models"

    @property
    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/version", timeout=5)
            return resp.status_code < 500
        except Exception:
            return False

    def list_models(self) -> list[dict[str, Any]]:
        """Fetch available models from 9router."""
        try:
            headers = {"Accept": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            resp = requests.get(self.models_url, headers=headers, timeout=15)
            if resp.status_code != 200:
                return []

            data = resp.json()
            models = data.get("data") if isinstance(data, dict) else data
            if not isinstance(models, list):
                return []

            # Prefix 9router models with 9r/
            return [
                {
                    "id": f"9r/{m.get('id', '')}",
                    "object": "model",
                    "created": m.get("created", 0),
                    "owned_by": f"9router/{m.get('owned_by', '')}",
                }
                for m in models
                if isinstance(m, dict)
            ]

        except Exception as exc:
            logger.warning({"event": "9router_models_error", "error": str(exc)})
            return []

    def chat_completions(
        self,
        messages: list[dict[str, Any]],
        model: str = "auto",
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        **kwargs,
    ) -> dict[str, Any] | Iterator[str]:
        """Forward chat request to 9router.

        9router handles:
        - OAuth token management (Claude, Codex, Copilot, ...)
        - Multi-provider routing & fallback
        - Format translation (OpenAI ↔ Claude ↔ Gemini)
        - No 24KB payload limit

        Args:
            messages: Chat messages
            model: Model name (WITHOUT 9r/ prefix — we strip it)
            stream: Whether to stream
            temperature: Sampling temperature
            max_tokens: Max tokens

        Returns:
            Dict for non-streaming, Iterator[str] for streaming SSE
        """
        # Strip 9r/ prefix
        if model.startswith("9r/"):
            model = model[3:]
        if not model or model == "auto":
            model = "auto"

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if tools:
            body["tools"] = tools
        if tool_choice:
            body["tool_choice"] = tool_choice
        body.update(kwargs)

        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        logger.info({
            "event": "9router_proxy_request",
            "model": model,
            "stream": stream,
            "message_count": len(messages),
            "url": self.chat_url,
        })

        try:
            resp = requests.post(
                self.chat_url,
                headers=headers,
                json=body,
                timeout=300,
                stream=stream,
            )

            if resp.status_code >= 400:
                error_text = ""
                try:
                    error_text = resp.text[:1000]
                except Exception:
                    pass
                logger.error({
                    "event": "9router_proxy_error",
                    "status": resp.status_code,
                    "error": error_text,
                })
                raise RuntimeError(
                    f"9router error: status={resp.status_code}, body={error_text[:200]}"
                )

            if stream:
                return self._stream_response(resp)
            else:
                return resp.json()

        except requests.RequestsError as exc:
            logger.error({"event": "9router_connection_error", "error": str(exc)})
            raise RuntimeError(f"9router connection failed: {exc}") from exc

    def _stream_response(self, response) -> Iterator[str]:
        """Pass through SSE stream from 9router."""
        try:
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="ignore") if isinstance(raw_line, bytes) else str(raw_line)
                yield line + "\n"
        except Exception as exc:
            logger.error({"event": "9router_stream_error", "error": str(exc)})
            error_chunk = json.dumps({
                "error": {
                    "message": f"9router stream error: {exc}",
                    "type": "proxy_error",
                }
            }, ensure_ascii=False)
            yield f"data: {error_chunk}\n\n"
            yield "data: [DONE]\n\n"


# Singleton
ninerouter_proxy = NinerouterProxy()
