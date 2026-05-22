"""
Custom OpenAI-compatible Provider — generic proxy for any OpenAI-compatible API.

Users can add custom APIs via UI (Settings → Custom Providers) without writing code.
Each provider gets a unique prefix. Models are auto-fetched from {base_url}/v1/models.

Config stored in config.data["custom_providers"]:
{
  "deepseek": {
    "name": "DeepSeek",
    "base_url": "https://api.deepseek.com",
    "api_key": "sk-...",
    "prefix": "deepseek",
    "enabled": true
  }
}
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Iterator

from curl_cffi import requests

from services.config import config
from utils.log import logger


def get_custom_providers() -> dict[str, dict[str, Any]]:
    """Get all enabled custom providers from config."""
    providers = config.data.get("custom_providers") or {}
    if not isinstance(providers, dict):
        return {}
    return {
        k: v for k, v in providers.items()
        if isinstance(v, dict) and v.get("enabled", True)
    }


def resolve_custom_provider(model: str) -> tuple[dict[str, Any] | None, str]:
    """Check if model matches any custom provider prefix.
    Returns (provider_config, stripped_model) or (None, original_model).
    """
    for provider_id, cfg in get_custom_providers().items():
        prefix = str(cfg.get("prefix") or provider_id).strip()
        if not prefix:
            continue
        full_prefix = f"{prefix}/"
        if model.startswith(full_prefix):
            return (cfg, model[len(full_prefix):])
    return (None, model)


class CustomOpenAIProvider:
    """Generic OpenAI-compatible provider — proxies to any OpenAI-compatible endpoint."""

    def __init__(self, provider_config: dict[str, Any]):
        self.cfg = provider_config
        self.base_url = str(provider_config.get("base_url") or "").rstrip("/")
        self.name = str(provider_config.get("name") or "Custom")
        self._key_index = 0
        self._rate_limited: dict[str, float] = {}

        # Detect API style: some providers don't use /v1 prefix
        api_style = str(provider_config.get("api_style") or "").strip().lower()
        if not api_style:
            if "deepseek.com" in self.base_url:
                api_style = "deepseek"
            elif "perplexity.ai" in self.base_url:
                api_style = "deepseek"  # Perplexity also uses no /v1
            else:
                api_style = "openai"

        # Determine paths: avoid double /v1 when base_url already includes it
        base_has_v1 = self.base_url.rstrip("/").endswith("/v1")

        if api_style == "deepseek":
            self._models_path = "/models"
            self._chat_path = "/chat/completions"
        elif base_has_v1:
            # Base URL already includes /v1 (e.g. https://api.groq.com/openai/v1)
            self._models_path = "/models"
            self._chat_path = "/chat/completions"
        else:
            # Standard OpenAI format: base_url has no /v1 suffix
            self._models_path = "/v1/models"
            self._chat_path = "/v1/chat/completions"

    def _get_keys(self) -> list[str]:
        """Get all configured API keys (supports multi-key).
        Auto-injects JWT token from account pool if API key is a placeholder.
        """
        single = str(self.cfg.get("api_key") or "").strip()
        multi = self.cfg.get("api_keys") or []
        if not isinstance(multi, list):
            multi = []
        keys = [k.strip() for k in multi if k.strip()]
        if single and single not in keys:
            keys.insert(0, single)

        # Auto-use JWT tokens from account pool if only placeholder key is configured
        if keys == ["sk-auto-created"] or keys == ["sk-placeholder"]:
            try:
                from services.account_service import account_service
                jwt_keys = []
                for acc in account_service.list_accounts():
                    token = (acc.get("access_token") or "").strip()
                    if token.startswith("eyJ") and acc.get("status") == "active":
                        jwt_keys.append(token)
                if jwt_keys:
                    from utils.log import logger
                    logger.info({"event": "openai_auto_key", "key_count": len(jwt_keys),
                                  "emails": [a.get("email") for a in account_service.list_accounts()
                                            if a.get("status") == "active" and (a.get("access_token") or "").startswith("eyJ")]})
                    keys = jwt_keys
            except Exception:
                pass

        return keys

    @property
    def api_key(self) -> str:
        keys = self._get_keys()
        if not keys:
            return ""
        now = time.time()
        for _ in range(len(keys)):
            key = keys[self._key_index % len(keys)]
            self._key_index += 1
            if self._rate_limited.get(key, 0) < now:
                return key
        return min(keys, key=lambda k: self._rate_limited.get(k, 0))

    @property
    def is_available(self) -> bool:
        if not self.base_url or not self.api_key:
            return False
        try:
            resp = requests.get(
                f"{self.base_url}{self._models_path}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def chat_completions(
        self,
        messages: list[dict[str, Any]],
        model: str = "",
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        **kwargs,
    ) -> dict[str, Any] | Iterator[dict[str, Any]]:
        """Forward chat request to custom API endpoint."""
        if not self.base_url:
            raise RuntimeError(f"Custom provider '{self.name}' has no base URL configured")
        if not self.api_key:
            raise RuntimeError(f"Custom provider '{self.name}' has no API key configured")

        body: dict[str, Any] = {
            "model": model,
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

        # Pass through common extra params
        for key in ("top_p", "frequency_penalty", "presence_penalty", "seed", "response_format"):
            if key in kwargs and kwargs[key] is not None:
                body[key] = kwargs[key]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if stream:
            headers["Accept"] = "text/event-stream"

        logger.info({
            "event": "custom_provider_request",
            "provider": self.name,
            "base_url": self.base_url,
            "model": model,
            "stream": stream,
        })

        try:
            resp = requests.post(
                f"{self.base_url}{self._chat_path}",
                headers=headers,
                json=body,
                timeout=300,
                stream=stream,
            )

            if resp.status_code == 429:
                # Rate limited — mark key and retry with next
                current_key = self.api_key
                self._rate_limited[current_key] = time.time() + 60
                attempted = getattr(self, "_attempted_keys", set())
                attempted.add(current_key)
                self._attempted_keys = attempted
                if len(attempted) < len(self._get_keys()):
                    return self.chat_completions(
                        messages=messages, model=model, stream=stream,
                        temperature=temperature, max_tokens=max_tokens,
                        tools=tools, tool_choice=tool_choice, **kwargs,
                    )
                raise RuntimeError(f"[{self.name}] All API keys rate limited")

            if resp.status_code >= 400:
                error_text = ""
                try:
                    # Try to read error body — may fail for streaming responses
                    if not stream:
                        error_text = (resp.text or "")[:500]
                    else:
                        raw = b""
                        for chunk in resp.iter_content(chunk_size=8192):
                            if chunk:
                                raw += chunk if isinstance(chunk, bytes) else chunk.encode()
                                if len(raw) > 5000:
                                    break
                        error_text = raw.decode("utf-8", errors="ignore")[:500] if raw else ""
                except Exception:
                    pass
                # Also log response headers for debugging
                resp_headers = dict(resp.headers) if hasattr(resp, 'headers') else {}
                logger.error({
                    "event": "custom_provider_error",
                    "provider": self.name,
                    "status": resp.status_code,
                    "error": error_text,
                    "model_sent": body.get("model"),
                    "msg_count": len(body.get("messages", [])),
                    "key_preview": (self.api_key or "")[:15] + "...",
                    "headers": {k: str(v)[:200] for k, v in resp_headers.items()},
                })
                raise RuntimeError(f"[{self.name}] Error {resp.status_code}: {error_text[:200]}")

            if stream:
                return self._stream_response(resp, model)
            else:
                return self._non_stream_response(resp, model)

        except requests.RequestsError as exc:
            raise RuntimeError(f"[{self.name}] Connection failed: {exc}") from exc

    def _stream_response(self, response, model: str) -> Iterator[dict[str, Any]]:
        """Parse SSE stream → OpenAI chunks (passthrough — already OpenAI format)."""
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())
        sent_role = False

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

                # Pass through OpenAI-format chunks as-is (they're already correct)
                choices = chunk.get("choices") or []
                for choice in choices:
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if content:
                        if not sent_role:
                            sent_role = True
                            yield {
                                "id": completion_id, "object": "chat.completion.chunk",
                                "created": created, "model": model,
                                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                            }
                    # Yield the chunk as-is with our IDs
                    yield {
                        "id": completion_id, "object": "chat.completion.chunk",
                        "created": created, "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": delta,
                            "finish_reason": choice.get("finish_reason"),
                        }],
                    }

        except Exception as exc:
            logger.error({"event": "custom_provider_stream_error", "provider": self.name, "error": str(exc)})

        yield {
            "id": completion_id, "object": "chat.completion.chunk",
            "created": created, "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }

    def _non_stream_response(self, response, model: str) -> dict[str, Any]:
        """Handle non-streaming response (passthrough)."""
        data = response.json()
        # Return as-is — already OpenAI format
        return data

    def list_models(self) -> list[dict[str, Any]]:
        """Fetch available models from custom API, prefixed with provider prefix.

        If /v1/models returns empty, falls back to probing /v1/chat/completions
        with a fake model name and parsing the error message for available models.
        """
        if not self.base_url or not self.api_key:
            return []

        prefix = str(self.cfg.get("prefix") or "").strip()
        if not prefix:
            return []

        models: list[dict[str, Any]] = []

        # Try standard models endpoint first
        try:
            resp = requests.get(
                f"{self.base_url}{self._models_path}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if isinstance(data, list) and data:
                    for item in data:
                        slug = str(item.get("id") or "").strip()
                        if slug:
                            if slug.startswith(f"{prefix}/"):
                                display_id = slug
                            else:
                                display_id = f"{prefix}/{slug}"
                            models.append({
                                "id": display_id,
                                "object": "model",
                                "created": item.get("created", 0),
                                "owned_by": str(item.get("owned_by") or self.name),
                            })
        except Exception:
            pass

        # Fallback: if models list is empty, probe chat endpoint to discover models
        if not models:
            try:
                import re
                resp = requests.post(
                    f"{self.base_url}{self._chat_path}",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "__discover_models__",
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 1,
                    },
                    timeout=15,
                )
                detail = ""
                try:
                    detail = resp.json().get("detail", "")
                except Exception:
                    detail = resp.text[:500] if resp.text else ""

                # Parse: "Available models: model1, model2, model3"
                if isinstance(detail, str) and "Available models:" in detail:
                    parts = detail.split("Available models:", 1)[1].strip().rstrip(".")
                    found_models = [m.strip() for m in parts.split(",") if m.strip()]
                    for slug in found_models:
                        if slug and slug != "unspecified":
                            display_id = f"{prefix}/{slug}"
                            models.append({
                                "id": display_id,
                                "object": "model",
                                "created": 0,
                                "owned_by": self.name,
                            })
                    if models:
                        logger.info({
                            "event": "custom_provider_models_fallback",
                            "provider": self.name,
                            "count": len(models),
                        })
            except Exception:
                pass

        return models
