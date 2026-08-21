from __future__ import annotations

from io import BytesIO
from typing import Any, Iterator

from PIL import Image

from services.protocol.conversation import (
    ConversationRequest,
    ImageGenerationError,
    collect_image_outputs,
    count_text_tokens,
    encode_images,
    stream_image_chunks,
    stream_image_outputs_with_pool,
)
from utils.image_tokens import count_image_inputs_tokens, count_image_output_items_tokens, image_usage


def _composite_mask(
    images: list[tuple[bytes, str, str]],
    masks: list[tuple[bytes, str, str]],
) -> list[tuple[bytes, str, str]]:
    """将 mask 的 alpha 通道合成到图片中，标识需要编辑的区域。
    
    mask 的透明区域（低 alpha）= 需要编辑的区域，
    mask 的不透明区域（高 alpha）= 保留的区域。
    如果无 mask 则返回原图。
    """
    if not masks:
        return images
    result: list[tuple[bytes, str, str]] = []
    for i, (data, filename, mime_type) in enumerate(images):
        mask_data = masks[i][0] if i < len(masks) else masks[-1][0]
        img = Image.open(BytesIO(data)).convert("RGBA")
        mask_img = Image.open(BytesIO(mask_data))
        if mask_img.mode == "RGBA":
            alpha = mask_img.split()[3]
        elif mask_img.mode == "L":
            alpha = mask_img
        else:
            alpha = mask_img.convert("L")
        alpha = alpha.resize(img.size, Image.LANCZOS)
        img.putalpha(alpha)
        buf = BytesIO()
        img.save(buf, format="PNG")
        result.append((buf.getvalue(), filename, "image/png"))
    return result


def handle(body: dict[str, Any]) -> dict[str, Any] | Iterator[dict[str, Any]]:
    prompt = str(body.get("prompt") or "")
    images = body.get("images") or []
    masks = body.get("mask") or []
    images = _composite_mask(images, masks)
    model = str(body.get("model") or "gpt-image-2")
    n = int(body.get("n") or 1)
    size = body.get("size")
    quality = str(body.get("quality") or "auto")
    response_format = str(body.get("response_format") or "b64_json")
    base_url = str(body.get("base_url") or "") or None
    progress_callback = body.get("progress_callback")
    encoded_images = encode_images(images)
    if not encoded_images:
        raise ImageGenerationError("image is required")
    outputs = stream_image_outputs_with_pool(ConversationRequest(
        prompt=prompt,
        model=model,
        n=n,
        size=size,
        quality=quality,
        response_format=response_format,
        base_url=base_url,
        images=encoded_images,
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
        input_image_tokens=count_image_inputs_tokens(images, model),
        output_tokens=count_image_output_items_tokens(result.get("data"), size, quality),
    )
    return result
