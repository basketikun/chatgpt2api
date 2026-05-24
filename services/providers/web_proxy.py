"""OpenAI-compatible adapter for captcha-solver Web providers.

Wraps the captcha-solver /v1/{gemini|chatgpt}-web/chat endpoints as
OpenAI chat completion calls so any OpenAI-compatible client (HA,
n8n, LiteLLM, etc) can route to gemini.google.com or chatgpt.com
via chatgpt2api.

Usage from client:
    POST /v1/chat/completions
    {
      "model": "gmw/chat" | "cgw/chat",
      "messages": [{"role": "user", "content": "Xin chào"}]
    }

Profile selection: configured per-provider in
  config.providers.gemini_web.profile  (default "gemini-web-default")
  config.providers.chatgpt_web.profile (default "chatgpt-default")

Captcha-solver connection reused from providers.flow:
  captcha_solver_url, captcha_solver_api_key
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Iterator

import httpx

from services.config import config
from utils.log import logger


def _captcha_solver_cfg() -> dict[str, str]:
    """Reuse the captcha-solver connection settings from providers.flow."""
    providers = config.data.get("providers") or {}
    flow = providers.get("flow") or {}
    return {
        "url": str(flow.get("captcha_solver_url") or "").rstrip("/"),
        "api_key": str(flow.get("captcha_solver_api_key") or ""),
    }


def _web_provider_cfg(provider: str) -> dict[str, Any]:
    providers = config.data.get("providers") or {}
    return providers.get(provider) or {}


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    """Concatenate all user message text content into a single prompt
    suitable for a fresh chat (Gemini/ChatGPT Web don't reuse session
    history across our calls)."""
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "user")
        if role not in ("user", "system"):
            continue
        content = m.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for p in content:
                if isinstance(p, dict) and p.get("type") == "text":
                    parts.append(str(p.get("text", "")))
    return "\n\n".join(p for p in parts if p.strip())


def _build_openai_response(text: str, model: str) -> dict[str, Any]:
    """Wrap a plain text response in OpenAI chat.completion format."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 0,  # we don't have real tokenization
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


def _stream_chunks(text: str, model: str) -> Iterator[dict[str, Any]]:
    """OpenAI-style streaming — chunk the captured text by ~50-char
    boundaries so clients with streaming UIs still feel responsive."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    # First chunk: role
    yield {
        "id": chunk_id, "object": "chat.completion.chunk", "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }
    # Content chunks
    chunk_size = 80
    for i in range(0, len(text), chunk_size):
        yield {
            "id": chunk_id, "object": "chat.completion.chunk", "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": text[i:i + chunk_size]}, "finish_reason": None}],
        }
    # Final
    yield {
        "id": chunk_id, "object": "chat.completion.chunk", "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }


def _call_web_chat(
    provider_path: str,
    profile: str,
    prompt: str,
    timeout: int = 120,
) -> str:
    """POST to captcha-solver /v1/{provider}-web/chat and return text."""
    cfg = _captcha_solver_cfg()
    if not cfg["url"]:
        raise RuntimeError(
            "captcha-solver URL chưa cấu hình — vào Settings → Google Labs Flow → điền URL+key"
        )
    url = f"{cfg['url']}/v1/{provider_path}/chat"
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    body = {"profile": profile, "prompt": prompt, "timeout": timeout, "headless": False}
    try:
        r = httpx.post(url, headers=headers, json=body, timeout=timeout + 30)
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"web chat HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except Exception as exc:
        raise RuntimeError(f"web chat call failed: {exc}") from exc
    data = r.json()
    text = str(data.get("text") or "")
    if not text:
        raise RuntimeError(f"web chat returned no text: {data}")
    return text


def handle_gemini_web_chat(
    model: str,
    messages: list[dict[str, Any]],
    stream: bool,
    body: dict[str, Any],
) -> dict[str, Any] | Iterator[dict[str, Any]]:
    """OpenAI chat completions handler routing to captcha-solver Gemini Web."""
    cfg = _web_provider_cfg("gemini_web")
    profile = str(cfg.get("profile") or "gemini-web-default")
    timeout = int(cfg.get("timeout") or 120)
    prompt = _last_user_text(messages)
    if not prompt:
        raise RuntimeError("Gemini Web chat requires a user message")
    logger.info({"event": "gemini_web_chat_request", "profile": profile, "prompt_len": len(prompt)})
    text = _call_web_chat("gemini-web", profile, prompt, timeout=timeout)
    full_model = f"gmw/{model.split('/', 1)[-1] if '/' in model else 'chat'}"
    if stream:
        return _stream_chunks(text, full_model)
    return _build_openai_response(text, full_model)


def handle_chatgpt_web_chat(
    model: str,
    messages: list[dict[str, Any]],
    stream: bool,
    body: dict[str, Any],
) -> dict[str, Any] | Iterator[dict[str, Any]]:
    """OpenAI chat completions handler routing to captcha-solver ChatGPT Web."""
    cfg = _web_provider_cfg("chatgpt_web")
    profile = str(cfg.get("profile") or "chatgpt-default")
    timeout = int(cfg.get("timeout") or 120)
    prompt = _last_user_text(messages)
    if not prompt:
        raise RuntimeError("ChatGPT Web chat requires a user message")
    logger.info({"event": "chatgpt_web_chat_request", "profile": profile, "prompt_len": len(prompt)})
    text = _call_web_chat("chatgpt-web", profile, prompt, timeout=timeout)
    full_model = f"cgw/{model.split('/', 1)[-1] if '/' in model else 'chat'}"
    if stream:
        return _stream_chunks(text, full_model)
    return _build_openai_response(text, full_model)
