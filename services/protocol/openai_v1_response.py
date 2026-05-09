from __future__ import annotations

import base64
import time
import uuid
from typing import Any, Iterable, Iterator

from fastapi import HTTPException

from services.protocol.conversation import (
    ConversationRequest,
    ImageOutput,
    encode_images,
    stream_image_outputs_with_pool,
    stream_text_deltas,
    text_backend,
)
from utils.helper import extract_image_from_message_content, extract_response_prompt, has_response_image_generation_tool


def is_text_response_request(body: dict[str, Any]) -> bool:
    return not has_response_image_generation_tool(body)


def extract_response_image(input_value: object) -> tuple[bytes, str] | None:
    if isinstance(input_value, dict):
        images = extract_image_from_message_content(input_value.get("content"))
        return images[0] if images else None
    if not isinstance(input_value, list):
        return None
    for item in reversed(input_value):
        if isinstance(item, dict) and str(item.get("type") or "").strip() == "input_image":
            image_url = str(item.get("image_url") or "")
            if image_url.startswith("data:"):
                header, _, data = image_url.partition(",")
                mime = header.split(";")[0].removeprefix("data:")
                return base64.b64decode(data), mime or "image/png"
        if isinstance(item, dict):
            images = extract_image_from_message_content(item.get("content"))
            if images:
                return images[0]
    return None


def messages_from_input(input_value: object, instructions: object = None) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    system_text = str(instructions or "").strip()
    if system_text:
        messages.append({"role": "system", "content": system_text})
    if isinstance(input_value, str):
        if input_value.strip():
            messages.append({"role": "user", "content": input_value.strip()})
        return messages
    if isinstance(input_value, dict):
        messages.append({
            "role": str(input_value.get("role") or "user"),
            "content": extract_response_prompt([input_value]) or input_value.get("content") or "",
        })
        return messages
    if isinstance(input_value, list):
        if all(isinstance(item, dict) and item.get("type") for item in input_value):
            text = extract_response_prompt(input_value)
            if text:
                messages.append({"role": "user", "content": text})
            return messages
        for item in input_value:
            if isinstance(item, dict):
                messages.append({
                    "role": str(item.get("role") or "user"),
                    "content": extract_response_prompt([item]) or item.get("content") or "",
                })
    return messages


def text_output_item(text: str, item_id: str | None = None, status: str = "completed") -> dict[str, Any]:
    return {
        "id": item_id or f"msg_{uuid.uuid4().hex}",
        "type": "message",
        "status": status,
        "role": "assistant",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def image_output_items(prompt: str, data: list[dict[str, Any]], item_id: str | None = None) -> list[dict[str, Any]]:
    output = []
    for item in data:
        b64_json = str(item.get("b64_json") or "").strip()
        if b64_json:
            output.append({
                "id": item_id or f"ig_{len(output) + 1}",
                "type": "image_generation_call",
                "status": "completed",
                "result": b64_json,
                "revised_prompt": str(item.get("revised_prompt") or prompt).strip() or prompt,
            })
    return output


def response_created(response_id: str, model: str, created: int) -> dict[str, Any]:
    return {
        "type": "response.created",
        "response": {
            "id": response_id,
            "object": "response",
            "created_at": created,
            "status": "in_progress",
            "error": None,
            "incomplete_details": None,
            "model": model,
            "output": [],
            "parallel_tool_calls": False,
        },
    }


def response_completed(response_id: str, model: str, created: int, output: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "response.completed",
        "response": {
            "id": response_id,
            "object": "response",
            "created_at": created,
            "status": "completed",
            "error": None,
            "incomplete_details": None,
            "model": model,
            "output": output,
            "parallel_tool_calls": False,
        },
    }


def stream_text_response(backend, body: dict[str, Any]) -> Iterator[dict[str, Any]]:
    model = str(body.get("model") or "auto").strip() or "auto"
    messages = messages_from_input(body.get("input"), body.get("instructions"))
    tools = body.get("tools")
    if isinstance(tools, list) and tools:
        tools = [t for t in tools if isinstance(t, dict)]
    else:
        tools = None
    tool_choice = body.get("tool_choice")
    response_id = f"resp_{uuid.uuid4().hex}"
    item_id = f"msg_{uuid.uuid4().hex}"
    created = int(time.time())
    full_text = ""
    yield response_created(response_id, model, created)
    yield {"type": "response.output_item.added", "output_index": 0, "item": text_output_item("", item_id, "in_progress")}
    request = ConversationRequest(model=model, messages=messages, tools=tools, tool_choice=tool_choice)
    for delta in stream_text_deltas(backend, request):
        full_text += delta
        yield {"type": "response.output_text.delta", "item_id": item_id, "output_index": 0, "content_index": 0, "delta": delta}
    yield {"type": "response.output_text.done", "item_id": item_id, "output_index": 0, "content_index": 0, "text": full_text}
    item = text_output_item(full_text, item_id, "completed")
    yield {"type": "response.output_item.done", "output_index": 0, "item": item}
    yield response_completed(response_id, model, created, [item])


def stream_image_response(image_outputs: Iterable[ImageOutput], prompt: str, model: str) -> Iterator[dict[str, Any]]:
    response_id = f"resp_{uuid.uuid4().hex}"
    created = int(time.time())
    yield response_created(response_id, model, created)
    for output in image_outputs:
        if output.kind == "message":
            text = output.text
            item = text_output_item(text)
            yield {"type": "response.output_text.delta", "item_id": item["id"], "output_index": 0, "content_index": 0, "delta": text}
            yield {"type": "response.output_text.done", "item_id": item["id"], "output_index": 0, "content_index": 0, "text": text}
            yield {"type": "response.output_item.done", "output_index": 0, "item": item}
            yield response_completed(response_id, model, created, [item])
            return
        if output.kind != "result":
            continue
        items = image_output_items(prompt, output.data)
        if items:
            item = items[0]
            yield {"type": "response.output_item.done", "output_index": 0, "item": item}
            yield response_completed(response_id, model, created, [item])
            return
    raise RuntimeError("image generation failed")


def collect_response(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    completed = {}
    for event in events:
        if event.get("type") == "response.completed":
            completed = event.get("response") if isinstance(event.get("response"), dict) else {}
    if not completed:
        raise RuntimeError("response generation failed")
    return completed


def response_events(body: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if is_text_response_request(body):
        yield from stream_text_response(text_backend(), body)
        return

    prompt = extract_response_prompt(body.get("input"))
    if not prompt:
        raise HTTPException(status_code=400, detail={"error": "input text is required"})
    model = str(body.get("model") or "gpt-image-2").strip() or "gpt-image-2"
    size = body.get("size")
    image_info = extract_response_image(body.get("input"))
    if image_info:
        image_data, mime_type = image_info
        images = encode_images([(image_data, "image.png", mime_type)])
    else:
        images = None
    image_outputs = stream_image_outputs_with_pool(ConversationRequest(
        prompt=prompt,
        model=model,
        size=size,
        response_format="b64_json",
        images=images,
    ))
    yield from stream_image_response(image_outputs, prompt, model)


def handle(body: dict[str, Any]) -> dict[str, Any] | Iterator[dict[str, Any]]:
    events = response_events(body)
    if body.get("stream"):
        return events
    return collect_response(events)
