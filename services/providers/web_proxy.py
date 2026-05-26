"""OpenAI-compatible adapter for captcha-solver Web providers.

Wraps the captcha-solver /v1/gemini-web/chat endpoints as
OpenAI chat completion calls so any OpenAI-compatible client (HA,
n8n, LiteLLM, etc) can route to gemini.google.com via chatgpt2api.

Usage from client:
    POST /v1/chat/completions
    {
      "model": "gmw/chat",
      "messages": [{"role": "user", "content": "Xin chào"}]
    }

Profile selection: configured per-provider in
  config.providers.gemini_web.profile  (default "gemini-web-default")

Captcha-solver connection reused from providers.flow:
  captcha_solver_url, captcha_solver_api_key
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Iterator

import httpx

from services.config import config
from services.log_service import LOG_TYPE_WEB_CHAT, LOG_TYPE_WEB_IMAGE, log_service
from utils.log import logger
from fastapi import HTTPException

class AccountBusyError(Exception):
    pass

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
) -> tuple[str, dict[str, Any]]:
    """POST to captcha-solver /v1/{provider}-web/chat.

    Returns (text, meta) where meta carries the per-stage timing
    breakdown (`stages`) plus the captcha-solver-side `elapsed_ms` so
    the caller can attribute slow calls to the right phase (page open,
    UI hydrate, prompt inject, send, model response).
    """
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
        if r.status_code == 429:
            raise AccountBusyError(f"ACCOUNT_BUSY:{profile}")
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"web chat HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except Exception as exc:
        raise RuntimeError(f"web chat call failed: {exc}") from exc
    data = r.json()
    text = str(data.get("text") or "")
    if not text:
        raise RuntimeError(f"web chat returned no text: {data}")
    meta: dict[str, Any] = {}
    if isinstance(data.get("stages"), dict):
        meta["stages"] = data["stages"]
    if data.get("elapsed_ms") is not None:
        meta["solver_elapsed_ms"] = data["elapsed_ms"]
    return text, meta


def _call_web_vision(
    provider_path: str,
    profile: str,
    image: str,
    prompt: str,
    timeout: int = 180,
) -> tuple[str, dict[str, Any]]:
    """POST to captcha-solver /v1/{provider}-web/analyze-image.

    Returns (text, meta) — meta carries `stages` + `solver_elapsed_ms`
    when the solver populates them, used by the slow-call diagnosis log.
    """
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
        if r.status_code == 429:
            raise AccountBusyError(f"ACCOUNT_BUSY:{profile}")
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"web vision HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except Exception as exc:
        raise RuntimeError(f"web vision call failed: {exc}") from exc
    data = r.json()
    text = str(data.get("text") or "")
    if not text:
        raise RuntimeError(f"web vision returned no text: {data}")
    meta: dict[str, Any] = {}
    if isinstance(data.get("stages"), dict):
        meta["stages"] = data["stages"]
    if data.get("elapsed_ms") is not None:
        meta["solver_elapsed_ms"] = data["elapsed_ms"]
    return text, meta


def _call_web_image_gen(
    provider_path: str,
    profile: str,
    prompt: str,
    count: int = 1,
    timeout: int = 240,
) -> tuple[list[str], dict[str, Any]]:
    """POST to captcha-solver /v1/{provider}-web/generate-image.
    Returns (image_urls, meta) where meta carries `stages` + `solver_elapsed_ms`
    for the slow-call diagnosis log."""
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
        if r.status_code == 429:
            raise AccountBusyError(f"ACCOUNT_BUSY:{profile}")
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"web image HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except Exception as exc:
        raise RuntimeError(f"web image call failed: {exc}") from exc
    data = r.json()
    images = data.get("images") or data.get("urls") or []
    if not isinstance(images, list) or not images:
        raise RuntimeError(f"web image returned no images: {data}")
    urls = [str(u) for u in images if u]
    meta: dict[str, Any] = {}
    if isinstance(data.get("stages"), dict):
        meta["stages"] = data["stages"]
    if data.get("elapsed_ms") is not None:
        meta["solver_elapsed_ms"] = data["elapsed_ms"]
    return urls, meta
    
    
def _expand_profiles(profile_str: str) -> list[str]:
    """Expand comma-separated profiles, resolving wildcards like 'chatgpt-*'
    by querying the captcha-solver for matching profile directories."""
    cfg = _captcha_solver_cfg()
    profiles = []
    for p in profile_str.split(","):
        p = p.strip()
        if not p:
            continue
        if p.endswith("*"):
            prefix = p[:-1]
            try:
                url = f"{cfg['url']}/v1/profiles?prefix={prefix}"
                headers = {}
                if cfg["api_key"]:
                    headers["Authorization"] = f"Bearer {cfg['api_key']}"
                r = httpx.get(url, headers=headers, timeout=5)
                r.raise_for_status()
                data = r.json()
                fetched = data.get("profiles", [])
                for f_p in fetched:
                    if "*" not in f_p:
                        profiles.append(f_p)
                if not fetched:
                    logger.warning("No profiles found matching prefix: %s", prefix)
            except Exception as exc:
                logger.warning("Failed to expand wildcard %s: %s", p, exc)
                # DO NOT append literal wildcard, it creates broken directories
        else:
            profiles.append(p)
    # Remove duplicates but preserve order
    seen = set()
    return [x for x in profiles if not (x in seen or seen.add(x))]


def _diagnose_slow_call(meta: dict[str, Any], total_ms: int) -> str:
    """Inspect the per-stage timing breakdown returned by captcha-solver
    and produce a one-line reason for why the call took total_ms.

    Categorises slow time by which phase ate the budget:
      - cold_browser   → page open + UI hydrate dominate (cold profile,
                          headful Chrome boot inside the container)
      - model_thinking → response stage dominates (Gemini/ChatGPT actually
                          generating; not our fault)
      - solver_overhead → captcha-solver elapsed_ms ≪ chatgpt2api total
                          (network round-trip, queue, browser_pool lock)
      - normal         → nothing stands out
    """
    stages = meta.get("stages") if isinstance(meta, dict) else None
    if not isinstance(stages, dict):
        return ""
    goto = int(stages.get("goto_ms") or 0)
    ready = int(stages.get("ready_ms") or 0)
    inject = int(stages.get("inject_ms") or 0)
    send = int(stages.get("send_ms") or 0)
    response = int(stages.get("response_ms") or 0)
    solver_total = int(meta.get("solver_elapsed_ms") or (goto + ready + inject + send + response))
    if total_ms <= 0:
        return ""
    if response > 0 and response >= 0.6 * solver_total and response >= 5_000:
        return f"model_thinking ({response}ms streaming)"
    if (goto + ready) >= 0.5 * solver_total and (goto + ready) >= 5_000:
        return f"cold_browser (goto={goto}ms, ready={ready}ms)"
    if solver_total > 0 and total_ms - solver_total >= max(2_000, 0.3 * total_ms):
        return f"solver_overhead (chatgpt2api={total_ms}ms vs solver={solver_total}ms)"
    return "normal"


def _log_web_call(
    log_type: str,
    *,
    provider: str,
    profile: str,
    op: str,
    started_at: float,
    prompt_len: int = 0,
    ok: bool = True,
    error: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Append a structured entry to logs.jsonl with provider + duration.

    Lets the Logs UI filter by surface (chat vs image) and provider
    (gemini_web / flow) and see how long each call took.
    """
    duration_ms = int((time.time() - started_at) * 1000)
    detail: dict[str, Any] = {
        "provider": provider,
        "profile": profile,
        "op": op,
        "duration_ms": duration_ms,
        "prompt_len": prompt_len,
        "ok": ok,
    }
    if error:
        detail["error"] = error[:300]
    if extra:
        detail.update(extra)
    # Add a one-line "why was this slow" reason when the call took >5s
    # AND the per-stage breakdown is available. Caller passes stages /
    # solver_elapsed_ms via `extra`.
    if ok and duration_ms >= 5_000:
        reason = _diagnose_slow_call(detail, duration_ms)
        if reason:
            detail["slow_reason"] = reason
    summary = f"{provider}/{op} {'OK' if ok else 'FAIL'} {duration_ms}ms"
    if detail.get("slow_reason"):
        summary += f" [{detail['slow_reason']}]"
    try:
        log_service.add(log_type, summary, detail)
    except Exception:
        # Logging must never break the actual call.
        pass


def handle_gemini_web_chat(
    model: str,
    messages: list[dict[str, Any]],
    stream: bool,
    body: dict[str, Any],
) -> dict[str, Any] | Iterator[dict[str, Any]]:
    """OpenAI chat completions handler routing to captcha-solver Gemini Web.
    Auto-detects multimodal image blocks → routes to vision endpoint."""
    cfg = _web_provider_cfg("gemini_web")
    profile_str = str(cfg.get("profile") or "gemini-web-default")
    profiles = _expand_profiles(profile_str)
    if not profiles:
        profiles = ["gemini-web-default"]
    timeout = int(cfg.get("timeout") or 120)
    image_url = _last_user_image(messages)
    prompt = _last_user_text(messages)
    started_at = time.time()
    
    last_exc = None
    for profile in profiles:
        try:
            if image_url:
                if not prompt:
                    prompt = "Phân tích chi tiết nội dung ảnh này."
                logger.info({"event": "gemini_web_vision_request", "profile": profile,
                             "prompt_len": len(prompt), "image_kind": image_url[:30]})
                text, meta = _call_web_vision("gemini-web", profile, image_url, prompt, timeout=max(timeout, 180))
                _log_web_call(LOG_TYPE_WEB_CHAT, provider="gemini_web", profile=profile,
                              op="vision", started_at=started_at, prompt_len=len(prompt),
                              extra={"text_len": len(text), **meta})
                full_model = "gmw/vision"
            else:
                if not prompt:
                    raise RuntimeError("Gemini Web chat requires a user message")
                logger.info({"event": "gemini_web_chat_request", "profile": profile, "prompt_len": len(prompt)})
                text, meta = _call_web_chat("gemini-web", profile, prompt, timeout=timeout)
                _log_web_call(LOG_TYPE_WEB_CHAT, provider="gemini_web", profile=profile,
                              op="chat", started_at=started_at, prompt_len=len(prompt),
                              extra={"text_len": len(text), "model": model, **meta})
                full_model = f"gmw/{model.split('/', 1)[-1] if '/' in model else 'chat'}"
            
            # Quota limit detection
            lower_text = text.lower()
            if any(k in lower_text for k in ("reached your limit", "giới hạn", "usage cap", "hết lượt")):
                raise AccountBusyError(f"Quota Hit: {text[:50]}")
                
            # Success, exit loop
            break
        except AccountBusyError as exc:
            last_exc = exc
            logger.info({"event": "gemini_web_failover", "profile": profile, "reason": "busy_or_quota"})
            continue
        except Exception as exc:
            last_exc = exc
            logger.warning({"event": "gemini_web_failover", "profile": profile, "reason": "error", "error": str(exc)[:100]})
            _log_web_call(LOG_TYPE_WEB_CHAT, provider="gemini_web", profile=profile,
                          op="vision" if image_url else "chat", started_at=started_at, prompt_len=len(prompt),
                          ok=False, error=str(exc))
            continue
    else:
        # All profiles failed (or busy)
        if last_exc:
            raise RuntimeError(f"All Gemini Web profiles busy or failed: {last_exc}")
    if stream:
        return _stream_chunks(text, full_model)
    return _build_openai_response(text, full_model)


def handle_gemini_web_image_gen(prompt: str, n: int = 1) -> dict[str, Any]:
    """OpenAI /v1/images/generations handler for Gemini Web (Imagen).
    Returns OpenAI-format {"created": ..., "data": [{"url": ...}]}."""
    cfg = _web_provider_cfg("gemini_web")
    profile = str(cfg.get("profile") or "gemini-web-default")
    timeout = int(cfg.get("timeout") or 240)
    started_at = time.time()
    logger.info({"event": "gemini_web_image_request", "profile": profile,
                 "prompt_len": len(prompt), "n": n})
    try:
        urls, meta = _call_web_image_gen("gemini-web", profile, prompt,
                                    count=max(1, n), timeout=timeout)
    except Exception as exc:
        _log_web_call(LOG_TYPE_WEB_IMAGE, provider="gemini_web", profile=profile,
                      op="image_gen", started_at=started_at, prompt_len=len(prompt),
                      ok=False, error=str(exc), extra={"n": n})
        raise
    _log_web_call(LOG_TYPE_WEB_IMAGE, provider="gemini_web", profile=profile,
                  op="image_gen", started_at=started_at, prompt_len=len(prompt),
                  extra={"n": n, "got": len(urls), **meta})
    return {"created": int(time.time()), "data": [{"url": u} for u in urls]}
