from __future__ import annotations

import base64
import json
import re
from typing import Any, Iterator

from curl_cffi import requests as cffi_requests

from services.protocol.conversation import (
    ConversationRequest,
    ImageOutput,
    collect_image_outputs,
    format_image_result,
    stream_image_chunks,
    stream_image_outputs_with_pool,
)
from services.backend_router import backend_router
from services.config import config
from services.image_providers import get_image_adapter, is_noauth_image_provider
from services.image_providers._base import now_sec
from utils.log import logger

_NON_EN = re.compile(r'[^\x00-\x7F]')

# Translation cache: {original: english}
_translation_cache: dict[str, str] = {}


def _needs_translation(text: str) -> bool:
    return bool(_NON_EN.search(text))


def _translate_prompt(prompt: str) -> str:
    """Translate non-English prompt → English using ChatGPT (Codex OAuth)."""
    if not _needs_translation(prompt):
        return prompt
    if prompt in _translation_cache:
        return _translation_cache[prompt]

    translate_prompt = (
        "Translate the following image generation prompt to English. "
        "Output ONLY the English translation. Be faithful and detailed, "
        "preserve all visual descriptions, lighting, style, composition, "
        "camera angles, mood. Output ONLY the translated prompt, nothing else:\n\n"
        + prompt
    )

    # Try ChatGPT via Codex OAuth
    try:
        from services.providers.openai_oauth import codex_oauth

        token = codex_oauth.get_token_for_request()
        result = codex_oauth.chat_completions(
            access_token=token,
            messages=[{"role": "user", "content": translate_prompt}],
            model="auto",
            stream=False,
        )
        if isinstance(result, dict):
            choices = result.get("choices") or []
            if choices:
                translated = str(choices[0].get("message", {}).get("content", "")).strip()
                if translated:
                    logger.info({"event": "prompt_translated", "source": "chatgpt",
                                  "original": prompt[:120], "english": translated[:250]})
                    _translation_cache[prompt] = translated
                    return translated
    except Exception as exc:
        logger.warning({"event": "translation_chatgpt_failed", "error": str(exc)[:100]})

    # Fallback: Gemini Free
    cfg = config.data.get("providers") or {}
    gemini_cfg = cfg.get("gemini_free") or {}
    api_key = str(gemini_cfg.get("api_key") or "").strip()
    if not api_key:
        keys = gemini_cfg.get("api_keys") or []
        if isinstance(keys, list) and keys:
            api_key = str(keys[0]).strip()
    if api_key:
        try:
            resp = cffi_requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": translate_prompt}]}],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 512},
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates") or []
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    translated = "".join(p.get("text", "") for p in parts).strip()
                    if translated:
                        logger.info({"event": "prompt_translated", "source": "gemini",
                                      "original": prompt[:120], "english": translated[:250]})
                        _translation_cache[prompt] = translated
                        return translated
        except Exception as exc:
            logger.warning({"event": "translation_gemini_failed", "error": str(exc)[:100]})

    return prompt


def _handle_adapter_image(route, body: dict[str, Any]) -> dict[str, Any] | Iterator[dict[str, Any]]:
    """Handle image generation through an adapter (sdwebui, huggingface, etc.)."""
    adapter = get_image_adapter(route.provider)
    if not adapter:
        # Custom providers don't have image adapters — raise to trigger combo fallback
        raise RuntimeError(f"Provider '{route.provider}' does not support image generation")

    prompt = str(body.get("prompt") or "")
    prompt = _translate_prompt(prompt)
    body = {**body, "prompt": prompt}
    n = max(1, min(4, int(body.get("n") or 1)))
    response_format = str(body.get("response_format") or "b64_json")
    base_url_str = str(body.get("base_url") or "") or None
    stream = bool(body.get("stream"))

    # Build credentials from config
    provider_key = route.provider
    providers_cfg = config.data.get("providers") or {}
    provider_config = providers_cfg.get(provider_key) or {}
    # Map image adapter key → chat provider key for credentials
    if not provider_config and provider_key == "gemini":
        provider_config = providers_cfg.get("gemini_free") or {}
    elif not provider_config and provider_key == "nvidia_nim_image":
        provider_config = providers_cfg.get("nvidia_nim") or {}

    credentials = {}
    if route.no_auth:
        credentials = {"accessToken": "public"}
    else:
        credentials = {
            "apiKey": str(provider_config.get("api_key") or ""),
            "apiKeys": provider_config.get("api_keys") or [],
            "accessToken": str(provider_config.get("api_key") or ""),
        }

    # For sdwebui, use configured base_url
    if route.provider == "sdwebui":
        adapter.base_url = str(provider_config.get("base_url") or "http://localhost:7860").rstrip("/")

    # Generate n images
    all_data: list[dict[str, Any]] = []
    stream_outputs: list[ImageOutput] = []
    # Get key count for retry
    max_keys = getattr(adapter, 'get_key_count', lambda c: 1)(credentials)

    for idx in range(n):
        last_error = ""
        for key_try in range(max(max_keys, 1)):
            try:
                # Try with key_index for adapters that support key rotation
                try:
                    url = adapter.build_url(route.model, credentials, key_try)
                except TypeError:
                    url = adapter.build_url(route.model, credentials)
                req_body = adapter.build_body(route.model, body)
                headers = adapter.build_headers(credentials, req_body, route.model, body)

                logger.info({
                    "event": "image_adapter_request",
                    "provider": route.provider,
                    "model": route.model,
                    "url": url[:120],
                    "key_try": key_try,
                })

                resp = cffi_requests.post(
                    url,
                    headers=headers,
                    json=req_body,
                    timeout=300,
                )

                if resp.status_code >= 400:
                    error_text = ""
                    try:
                        error_text = resp.text[:500]
                    except Exception:
                        pass
                    if resp.status_code in (400, 429) and key_try < max_keys - 1:
                        logger.warning({
                            "event": "image_adapter_retry",
                            "provider": route.provider,
                            "status": resp.status_code,
                            "key_try": key_try,
                            "error": error_text[:200],
                        })
                        last_error = error_text
                        continue  # try next key
                    logger.error({
                        "event": "image_adapter_error",
                        "provider": route.provider,
                        "status": resp.status_code,
                        "error": error_text,
                    })
                    raise RuntimeError(f"Image generation failed: {route.provider} status={resp.status_code} detail={error_text[:300]}")

                # Try custom parse_response first (async adapters)
                parsed = adapter.parse_response(resp) if hasattr(adapter, "parse_response") else None

                if parsed is None:
                    # Default: parse JSON + normalize
                    try:
                        raw_json = resp.json()
                    except Exception:
                        # Binary response (image bytes)
                        raw_json = {"image_bytes": resp.content}
                    parsed = raw_json

                normalized = adapter.normalize(parsed, body)
                data_items = normalized.get("data") or []
                all_data.extend(data_items)

                if stream:
                    stream_outputs.append(ImageOutput(
                        kind="result",
                        model=body.get("model", "unknown"),
                        index=idx + 1,
                        total=n,
                        data=data_items,
                    ))
                break  # success — stop trying keys

            except Exception as exc:
                logger.error({"event": "image_adapter_fatal", "provider": route.provider, "error": str(exc)})
                if key_try < max_keys - 1:
                    continue  # try next key
                raise RuntimeError(f"Image generation failed: {exc}") from exc

    if stream and stream_outputs:
        # Yield stream chunks
        def _stream():
            for output in stream_outputs:
                yield output.to_chunk()
        return _stream()

    # Non-streaming response
    result = format_image_result(
        all_data,
        prompt,
        response_format,
        base_url_str,
    )
    if not result.get("data"):
        result["message"] = "Image generation completed but no images returned."
    return result


def handle(body: dict[str, Any]) -> dict[str, Any] | Iterator[dict[str, Any]]:
    prompt = str(body.get("prompt") or "")
    model = str(body.get("model") or "gpt-image-2")
    n = int(body.get("n") or 1)
    size = body.get("size") or config.default_image_size  # configurable default (16:9)
    response_format = str(body.get("response_format") or "b64_json")
    base_url_str = str(body.get("base_url") or "") or None
    stream = bool(body.get("stream"))

    # Combo model support — try each model in the combo until one succeeds
    if backend_router.is_combo(model):
        routes = backend_router.route_combo(model)
        last_error = ""
        for route in routes:
            try:
                # Try all models in combo: image models + custom providers (may support image gen)
                if route.is_image or route.provider == "chatgpt" or route.provider.startswith("custom:"):
                    return _handle_single_image(route, body)
            except Exception as exc:
                last_error = str(exc)
                logger.warning({
                    "event": "image_combo_fallback",
                    "model": route.model,
                    "error": last_error,
                })
                continue
        raise RuntimeError(f"All image models in combo '{model}' failed: {last_error}")

    # Single model routing
    route = backend_router.route(model)
    return _handle_single_image(route, body)


def _handle_single_image(route, body: dict[str, Any]) -> dict[str, Any] | Iterator[dict[str, Any]]:
    """Handle image generation for a single model (adapter or ChatGPT DALL-E)."""
    prompt = str(body.get("prompt") or "")
    model = str(body.get("model") or "gpt-image-2")
    n = int(body.get("n") or 1)
    size = body.get("size") or config.default_image_size  # configurable default (16:9)
    response_format = str(body.get("response_format") or "b64_json")
    base_url_str = str(body.get("base_url") or "") or None
    stream = bool(body.get("stream"))

    # If routed to a non-ChatGPT image provider, use adapter
    if route.provider != "chatgpt" and (route.is_image or route.provider.startswith("custom:")):
        logger.info({
            "event": "image_routed_to_adapter",
            "provider": route.provider,
            "model": route.model,
        })
        try:
            return _handle_adapter_image(route, body)
        except Exception as exc:
            logger.warning({
                "event": "image_adapter_fallback",
                "provider": route.provider,
                "error": str(exc),
            })
            raise  # Re-raise to trigger combo fallback

    # For chatgpt/ DALL-E: use original chatgpt.com backend flow (same as upstream)
    # Let combo fallback handle failures if token can't access chatgpt.com
    # Default: use existing ChatGPT DALL-E flow (unchanged)
    outputs = stream_image_outputs_with_pool(ConversationRequest(
        prompt=prompt,
        model=route.model if route.model != "auto" else model,
        n=n,
        size=size,
        response_format=response_format,
        base_url=base_url_str,
        message_as_error=True,
    ))
    if stream:
        return stream_image_chunks(outputs)
    return collect_image_outputs(outputs)
