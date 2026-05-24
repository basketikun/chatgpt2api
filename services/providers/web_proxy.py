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


def _last_user_image(messages: list[dict[str, Any]]) -> str | None:
    """Return the most recent image_url URL from user messages (OpenAI
    multimodal format). Supports both data: URLs and https:// URLs.
    Returns None if no image is present."""
    for m in reversed(messages):
        if m.get("role") != "user":
            continue
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for p in reversed(content):
            if not isinstance(p, dict):
                continue
            if p.get("type") == "image_url":
                iu = p.get("image_url")
                if isinstance(iu, dict):
                    url = iu.get("url")
                elif isinstance(iu, str):
                    url = iu
                else:
                    url = None
                if url and isinstance(url, str):
                    return url
            elif p.get("type") == "input_image":
                url = p.get("image_url") or p.get("url")
                if url and isinstance(url, str):
                    return url
    return None


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


def _call_web_vision(
    provider_path: str,
    profile: str,
    image: str,
    prompt: str,
    timeout: int = 180,
) -> str:
    """POST to captcha-solver /v1/{provider}-web/analyze-image."""
    cfg = _captcha_solver_cfg()
    if not cfg["url"]:
        raise RuntimeError("captcha-solver URL chưa cấu hình")
    url = f"{cfg['url']}/v1/{provider_path}/analyze-image"
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    body = {
        "profile": profile, "image": image, "prompt": prompt,
        "timeout": timeout, "headless": False,
    }
    try:
        r = httpx.post(url, headers=headers, json=body, timeout=timeout + 30)
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"web vision HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except Exception as exc:
        raise RuntimeError(f"web vision call failed: {exc}") from exc
    data = r.json()
    text = str(data.get("text") or "")
    if not text:
        raise RuntimeError(f"web vision returned no text: {data}")
    return text


def _call_web_image_gen(
    provider_path: str,
    profile: str,
    prompt: str,
    count: int = 1,
    timeout: int = 240,
) -> list[str]:
    """POST to captcha-solver /v1/{provider}-web/generate-image.
    Returns a list of image URLs (or data URLs)."""
    cfg = _captcha_solver_cfg()
    if not cfg["url"]:
        raise RuntimeError("captcha-solver URL chưa cấu hình")
    url = f"{cfg['url']}/v1/{provider_path}/generate-image"
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    body: dict[str, Any] = {
        "profile": profile, "prompt": prompt,
        "timeout": timeout, "headless": False,
    }
    if provider_path == "gemini-web":
        body["count"] = count
    try:
        r = httpx.post(url, headers=headers, json=body, timeout=timeout + 30)
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"web image HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except Exception as exc:
        raise RuntimeError(f"web image call failed: {exc}") from exc
    data = r.json()
    images = data.get("images") or data.get("urls") or []
    if not isinstance(images, list) or not images:
        raise RuntimeError(f"web image returned no images: {data}")
    return [str(u) for u in images if u]


def handle_gemini_web_chat(
    model: str,
    messages: list[dict[str, Any]],
    stream: bool,
    body: dict[str, Any],
) -> dict[str, Any] | Iterator[dict[str, Any]]:
    """OpenAI chat completions handler routing to captcha-solver Gemini Web.
    Auto-detects multimodal image blocks → routes to vision endpoint."""
    cfg = _web_provider_cfg("gemini_web")
    profile = str(cfg.get("profile") or "gemini-web-default")
    timeout = int(cfg.get("timeout") or 120)
    image_url = _last_user_image(messages)
    prompt = _last_user_text(messages)
    if image_url:
        if not prompt:
            prompt = "Phân tích chi tiết nội dung ảnh này."
        logger.info({"event": "gemini_web_vision_request", "profile": profile,
                     "prompt_len": len(prompt), "image_kind": image_url[:30]})
        text = _call_web_vision("gemini-web", profile, image_url, prompt, timeout=max(timeout, 180))
        full_model = "gmw/vision"
    else:
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
    """OpenAI chat completions handler routing to captcha-solver ChatGPT Web.
    Auto-detects multimodal image blocks → routes to vision endpoint."""
    cfg = _web_provider_cfg("chatgpt_web")
    profile = str(cfg.get("profile") or "chatgpt-default")
    timeout = int(cfg.get("timeout") or 120)
    image_url = _last_user_image(messages)
    prompt = _last_user_text(messages)
    if image_url:
        if not prompt:
            prompt = "Phân tích chi tiết nội dung ảnh này."
        logger.info({"event": "chatgpt_web_vision_request", "profile": profile,
                     "prompt_len": len(prompt), "image_kind": image_url[:30]})
        text = _call_web_vision("chatgpt-web", profile, image_url, prompt, timeout=max(timeout, 180))
        full_model = "cgw/vision"
    else:
        if not prompt:
            raise RuntimeError("ChatGPT Web chat requires a user message")
        logger.info({"event": "chatgpt_web_chat_request", "profile": profile, "prompt_len": len(prompt)})
        text = _call_web_chat("chatgpt-web", profile, prompt, timeout=timeout)
        full_model = f"cgw/{model.split('/', 1)[-1] if '/' in model else 'chat'}"
    if stream:
        return _stream_chunks(text, full_model)
    return _build_openai_response(text, full_model)


def handle_gemini_web_image_gen(prompt: str, n: int = 1) -> dict[str, Any]:
    """OpenAI /v1/images/generations handler for Gemini Web (Imagen).
    Returns OpenAI-format {"created": ..., "data": [{"url": ...}]}."""
    cfg = _web_provider_cfg("gemini_web")
    profile = str(cfg.get("profile") or "gemini-web-default")
    timeout = int(cfg.get("timeout") or 240)
    logger.info({"event": "gemini_web_image_request", "profile": profile,
                 "prompt_len": len(prompt), "n": n})
    urls = _call_web_image_gen("gemini-web", profile, prompt,
                                count=max(1, n), timeout=timeout)
    return {"created": int(time.time()), "data": [{"url": u} for u in urls]}


def handle_chatgpt_web_image_gen(prompt: str, n: int = 1) -> dict[str, Any]:
    """OpenAI /v1/images/generations handler for ChatGPT Web (DALL-E).
    Free tier returns 1 image per call; n>1 calls the endpoint multiple times."""
    cfg = _web_provider_cfg("chatgpt_web")
    profile = str(cfg.get("profile") or "chatgpt-default")
    timeout = int(cfg.get("timeout") or 240)
    logger.info({"event": "chatgpt_web_image_request", "profile": profile,
                 "prompt_len": len(prompt), "n": n})
    all_urls: list[str] = []
    for i in range(max(1, n)):
        try:
            urls = _call_web_image_gen("chatgpt-web", profile, prompt,
                                        count=1, timeout=timeout)
            all_urls.extend(urls)
        except Exception as exc:
            if i == 0:
                raise
            logger.warning({"event": "chatgpt_web_image_partial",
                            "got": len(all_urls), "error": str(exc)[:120]})
            break
    return {"created": int(time.time()), "data": [{"url": u} for u in all_urls]}
