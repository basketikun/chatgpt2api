from __future__ import annotations

from typing import Any, Iterator

from services.protocol.conversation import (
    ConversationRequest,
    collect_image_outputs,
    count_text_tokens,
    stream_image_chunks,
    stream_image_outputs_with_pool,
)
from utils.image_tokens import count_image_output_items_tokens, image_usage


def handle(body: dict[str, Any]) -> dict[str, Any] | Iterator[dict[str, Any]]:
    prompt = str(body.get("prompt") or "")
    model = str(body.get("model") or "gpt-image-2")
    n = int(body.get("n") or 1)
    size = body.get("size")
    quality = str(body.get("quality") or "auto")
    response_format = str(body.get("response_format") or "b64_json")
    base_url = str(body.get("base_url") or "") or None
    progress_callback = body.get("progress_callback")
    outputs = stream_image_outputs_with_pool(ConversationRequest(
        prompt=prompt,
        model=model,
        n=n,
        size=size,
        quality=quality,
        response_format=response_format,
        base_url=base_url,
        message_as_error=True,
        progress_callback=progress_callback,
        provider_binding_id=str(body.get("provider_binding_id") or ""),
        conversation_id=str(body.get("conversation_id") or ""),
        parent_message_id=str(body.get("parent_message_id") or ""),
        retain_conversation=bool(body.get("retain_conversation")),
    ))
    if body.get("stream"):
        return stream_image_chunks(outputs)
    result = collect_image_outputs(outputs)
    result["usage"] = image_usage(
        input_text_tokens=count_text_tokens(prompt, model),
        output_tokens=count_image_output_items_tokens(result.get("data"), size, quality),
    )
    return result
