from __future__ import annotations

from typing import Any, Iterator

from services.backend_router import backend_router
from services.image_providers import get_image_adapter
from services.protocol.conversation import (
    ConversationRequest,
    ImageGenerationError,
    collect_image_outputs,
    encode_images,
    format_image_result,
    stream_image_chunks,
    stream_image_outputs_with_pool,
)
from services.protocol.openai_v1_image_generations import _translate_prompt
from utils.log import logger


def handle(body: dict[str, Any]) -> dict[str, Any] | Iterator[dict[str, Any]]:
    prompt = str(body.get("prompt") or "")
    prompt = _translate_prompt(prompt)
    body = {**body, "prompt": prompt}
    images = body.get("images") or []
    model = str(body.get("model") or "gpt-image-2")
    n = int(body.get("n") or 1)
    size = body.get("size")
    response_format = str(body.get("response_format") or "b64_json")
    base_url = str(body.get("base_url") or "") or None

    # Check if this is an adapter model (gemini-image, nv-image, sdwebui, etc.)
    prov, resolved_model = backend_router.resolve_model(model)
    adapter = get_image_adapter(prov) if prov else None

    if adapter:
        # Build a simple route-like object (tuple unpacking)
        route = type('Route', (), {'provider': prov, 'model': resolved_model, 'is_image': True})()
        return _handle_adapter_edit(adapter, route, body, prompt, images, n, response_format, base_url)

    # Default: ChatGPT DALL-E pipeline
    encoded_images = encode_images(images)
    if not encoded_images:
        raise ImageGenerationError("image is required")
    outputs = stream_image_outputs_with_pool(ConversationRequest(
        prompt=prompt,
        model=model,
        n=n,
        size=size,
        response_format=response_format,
        base_url=base_url,
        images=encoded_images,
        message_as_error=True,
    ))
    if body.get("stream"):
        return stream_image_chunks(outputs)
    return collect_image_outputs(outputs)


def _handle_adapter_edit(adapter, route, body, prompt, images, n, response_format, base_url):
    """Handle image editing through an adapter (e.g., Gemini)."""
    import json
    from curl_cffi import requests as cffi_requests
    from services.config import config

    provider_key = route.provider
    providers_cfg = config.data.get("providers") or {}
    provider_config = providers_cfg.get(provider_key) or {}
    if not provider_config and provider_key == "gemini":
        provider_config = providers_cfg.get("gemini_free") or {}

    # For custom providers, get config from custom_providers
    if not provider_config and provider_key.startswith("custom:"):
        cp_id = provider_key[len("custom:"):]
        custom_cfg = (config.data.get("custom_providers") or {}).get(cp_id) or {}
        provider_config = custom_cfg

    credentials = {
        "apiKey": str(provider_config.get("api_key") or ""),
        "apiKeys": provider_config.get("api_keys") or [],
    }
    logger.info({
        "event": "image_edit_credentials",
        "provider_key": provider_key,
        "has_api_key": bool(credentials.get("apiKey")),
        "api_keys_count": len(credentials.get("apiKeys", [])),
    })

    max_keys = getattr(adapter, 'get_key_count', lambda c: 1)(credentials)
    all_data = []
    last_error = ""

    for idx in range(n):
        for key_try in range(max(max_keys, 1)):
            try:
                try:
                    url = adapter.build_url(route.model, credentials, key_try)
                except TypeError:
                    url = adapter.build_url(route.model, credentials)

                # Pass images in body for adapter
                edit_body = dict(body)
                edit_body["images"] = images  # raw bytes from upload
                req_body = adapter.build_body(route.model, edit_body)
                headers = adapter.build_headers(credentials, req_body, route.model, body)

                resp = cffi_requests.post(url, headers=headers, json=req_body, timeout=300)

                if resp.status_code >= 400:
                    error_text = ""
                    try:
                        error_text = resp.text[:500]
                    except Exception:
                        pass
                    if resp.status_code in (400, 429) and key_try < max_keys - 1:
                        last_error = error_text
                        continue
                    raise RuntimeError(f"Image edit failed: {route.provider} status={resp.status_code}")

                parsed = adapter.parse_response(resp) if hasattr(adapter, "parse_response") else None
                if parsed is None:
                    try:
                        parsed = resp.json()
                    except Exception:
                        parsed = {"image_bytes": resp.content}

                normalized = adapter.normalize(parsed, body)
                all_data.extend(normalized.get("data") or [])
                break

            except Exception as exc:
                logger.error({"event": "image_edit_adapter_error", "error": str(exc)})
                if key_try < max_keys - 1:
                    continue
                raise RuntimeError(f"Image edit failed: {exc}") from exc

    return format_image_result(all_data, prompt, response_format, base_url)
