"""
NVIDIA NIM Provider — OpenAI-compatible API for chat + vision.

Base URL: https://integrate.api.nvidia.com/v1
Auth: Bearer token from https://build.nvidia.com
Format: OpenAI-compatible — forward nguyên bản, không cần convert.

Supports: Chat, Vision (base64 images), streaming SSE.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Iterator

from curl_cffi import requests

from services.config import config
from utils.log import logger

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaNimProvider:
    """NVIDIA NIM — OpenAI-compatible proxy for chat + vision."""

    def __init__(self):
        self._key_index = 0
        self._rate_limited: dict[str, float] = {}

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

    @property
    def api_key(self) -> str:
        keys = self._get_keys()
        if not keys:
            return ""
        # Skip rate-limited keys
        now = time.time()
        for _ in range(len(keys)):
            key = keys[self._key_index % len(keys)]
            self._key_index += 1
            if self._rate_limited.get(key, 0) < now:
                return key
        # All keys rate limited, return least recently limited
        return min(keys, key=lambda k: self._rate_limited.get(k, 0))

    @property
    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            resp = requests.get(
                f"{NVIDIA_BASE_URL}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def chat_completions(
        self,
        messages: list[dict[str, Any]],
        model: str = "openai/gpt-oss-120b",
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        **kwargs,
    ) -> dict[str, Any] | Iterator[dict[str, Any]]:
        """Forward chat request to NVIDIA NIM API."""
        if not self.api_key:
            raise RuntimeError("NVIDIA NIM API key not configured")

        # Strip nv/ prefix if present
        pure_model = model
        for prefix in ("nv/",):
            if model.startswith(prefix):
                pure_model = model[len(prefix):]
                break

        body: dict[str, Any] = {
            "model": pure_model,
            "messages": messages,
            "stream": stream,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens:
            body["max_tokens"] = max_tokens
        if tools:
            body["tools"] = tools
        if tool_choice:
            body["tool_choice"] = tool_choice

        # Pass through extra params
        for key in ("top_p", "frequency_penalty", "presence_penalty", "seed"):
            if key in kwargs and kwargs[key] is not None:
                body[key] = kwargs[key]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if stream:
            headers["Accept"] = "text/event-stream"

        logger.info({"event": "nvidia_nim_request", "model": pure_model, "stream": stream})

        try:
            resp = requests.post(
                f"{NVIDIA_BASE_URL}/chat/completions",
                headers=headers,
                json=body,
                timeout=300,
                stream=stream,
            )

            if resp.status_code == 429:
                self._rate_limited[self.api_key] = time.time() + 60
                # Try next key
                attempted = getattr(self, "_attempted_keys", set())
                attempted.add(self.api_key)
                self._attempted_keys = attempted
                if len(attempted) < len(self._get_keys()):
                    return self.chat_completions(
                        messages=messages, model=model, stream=stream,
                        temperature=temperature, max_tokens=max_tokens,
                        tools=tools, tool_choice=tool_choice, **kwargs,
                    )
                raise RuntimeError("All NVIDIA NIM API keys rate limited")

            if resp.status_code >= 400:
                error_text = ""
                try:
                    error_text = resp.text[:500]
                except Exception:
                    pass
                logger.error({
                    "event": "nvidia_nim_error",
                    "status": resp.status_code,
                    "error": error_text,
                })
                raise RuntimeError(f"NVIDIA NIM error {resp.status_code}: {error_text[:200]}")

            if stream:
                return self._stream_response(resp, model)
            else:
                return self._non_stream_response(resp, model)

        except requests.RequestsError as exc:
            raise RuntimeError(f"NVIDIA NIM connection failed: {exc}") from exc

    def _stream_response(self, response, model: str) -> Iterator[dict[str, Any]]:
        """Parse NVIDIA SSE stream → OpenAI chunks."""
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())
        sent_role = False
        accumulated = ""

        try:
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="ignore") if isinstance(raw_line, bytes) else str(raw_line)
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices") or []
                for choice in choices:
                    delta = choice.get("delta") or {}
                    finish_reason = choice.get("finish_reason")

                    # Handle reasoning_content (for deepseek, qwen models)
                    reasoning = delta.get("reasoning_content")
                    if reasoning:
                        accumulated += reasoning

                    content = delta.get("content")
                    if content:
                        accumulated += content
                        if not sent_role:
                            sent_role = True
                            yield {
                                "id": completion_id, "object": "chat.completion.chunk",
                                "created": created, "model": model,
                                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                            }
                        yield {
                            "id": completion_id, "object": "chat.completion.chunk",
                            "created": created, "model": model,
                            "choices": [{"index": 0, "delta": {"content": content, "reasoning_content": reasoning or None}, "finish_reason": finish_reason}],
                        }

                    # Tool calls
                    tool_calls_delta = delta.get("tool_calls")
                    if tool_calls_delta:
                        yield {
                            "id": completion_id, "object": "chat.completion.chunk",
                            "created": created, "model": model,
                            "choices": [{"index": 0, "delta": {"tool_calls": tool_calls_delta}, "finish_reason": None}],
                        }

        except Exception as exc:
            logger.error({"event": "nvidia_nim_stream_error", "error": str(exc)})

        if not sent_role:
            yield {
                "id": completion_id, "object": "chat.completion.chunk",
                "created": created, "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
            }
        yield {
            "id": completion_id, "object": "chat.completion.chunk",
            "created": created, "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }

    def _non_stream_response(self, response, model: str) -> dict[str, Any]:
        """Handle non-streaming NVIDIA response."""
        data = response.json()
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())

        choices = data.get("choices") or []
        message = {}
        for choice in choices:
            msg = choice.get("message") or {}
            message = {
                "role": msg.get("role", "assistant"),
                "content": msg.get("content", ""),
            }
            if msg.get("tool_calls"):
                message["tool_calls"] = msg["tool_calls"]

        usage = data.get("usage") or {}
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "message": message, "finish_reason": choices[0].get("finish_reason", "stop") if choices else "stop"}],
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        }

    def list_models(self) -> list[dict[str, Any]]:
        """Fetch available models from NVIDIA API, prefixed with nv/."""
        if not self.api_key:
            return []
        try:
            resp = requests.get(
                f"{NVIDIA_BASE_URL}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=15,
            )
            if resp.status_code != 200:
                return []
            models = []
            for item in resp.json().get("data", []):
                slug = str(item.get("id") or "").strip()
                if slug:
                    models.append({
                        "id": f"nv/{slug}",
                        "object": "model",
                        "created": item.get("created", 0),
                        "owned_by": str(item.get("owned_by") or "nvidia"),
                    })
            return models
        except Exception as exc:
            logger.warning({"event": "nvidia_nim_list_models_error", "error": str(exc)})
            return []


# Singleton
nvidia_nim_provider = NvidiaNimProvider()
