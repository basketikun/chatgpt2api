from __future__ import annotations

import time
import uuid
from typing import Any, Iterable, Iterator

from fastapi import HTTPException

from services.protocol.chat_completion_cache import cache_key, chat_completion_cache, normalize_text_messages
from services.protocol.conversation import (
    ConversationRequest,
    ImageOutput,
    collect_image_outputs,
    collect_text,
    count_message_image_tokens,
    count_message_text_tokens,
    count_text_tokens,
    encode_images,
    normalize_messages,
    stream_image_outputs_with_pool,
    stream_text_deltas,
    text_backend,
)
from services.protocol.web_search_tool import (
    WEB_SEARCH_TOOL_TYPES,
    has_unsupported_tools,
    is_web_search_chat_request,
    run_web_search,
    search_query_from_messages,
    text_with_url_citations,
)
from utils.helper import build_chat_image_markdown_content, extract_chat_image, extract_chat_prompt, is_image_chat_request, parse_image_count
from utils.image_tokens import (
    chat_usage_from_image_usage,
    count_image_inputs_tokens,
    count_image_output_items_tokens,
    image_usage,
)

TOOL_UNAVAILABLE_SYSTEM_MESSAGE = (
    "This compatibility backend cannot execute local tools, shell commands, non-search tools, "
    "or file operations. Do not claim to have run tools or inspected external resources. "
    "If a user asks you to use a tool, say that tool execution is unavailable through this backend."
)


def normalize_thinking_effort(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "none"}:
        return ""
    if normalized in {"low", "medium", "high"}:
        return normalized
    if normalized in {"xhigh", "extended"}:
        return "extended"
    return ""


def thinking_effort_from_body(body: dict[str, Any]) -> str:
    if "thinking_effort" in body:
        return normalize_thinking_effort(body.get("thinking_effort"))
    if "reasoning_effort" in body:
        return normalize_thinking_effort(body.get("reasoning_effort"))
    reasoning = body.get("reasoning")
    if isinstance(reasoning, dict):
        return normalize_thinking_effort(reasoning.get("effort"))
    return ""


def completion_chunk(model: str, delta: dict[str, Any], finish_reason: str | None = None, completion_id: str = "", created: int | None = None) -> dict[str, Any]:
    return {
        "id": completion_id or f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": created or int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def completion_response(
    model: str,
    content: str,
    created: int | None = None,
    messages: list[dict[str, Any]] | None = None,
    annotations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    prompt_text_tokens = count_message_text_tokens(messages, model) if messages else 0
    prompt_image_tokens = count_message_image_tokens(messages, model) if messages else 0
    prompt_tokens = prompt_text_tokens + prompt_image_tokens
    completion_tokens = count_text_tokens(content, model) if messages else 0
    message = {"role": "assistant", "content": content}
    if annotations:
        message["annotations"] = annotations
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": created or int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "prompt_tokens_details": {
                "text_tokens": prompt_text_tokens,
                "image_tokens": prompt_image_tokens,
                "cached_tokens": 0,
            },
            "completion_tokens_details": {
                "text_tokens": completion_tokens,
                "image_tokens": 0,
                "reasoning_tokens": 0,
            },
        },
    }


def stream_text_chat_completion(
    backend,
    messages: list[dict[str, Any]],
    model: str,
    thinking_effort: str = "",
) -> Iterator[dict[str, Any]]:
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    sent_role = False
    request = ConversationRequest(model=model, messages=messages, thinking_effort=thinking_effort)
    for delta_text in stream_text_deltas(backend, request):
        if not sent_role:
            sent_role = True
            yield completion_chunk(model, {"role": "assistant", "content": delta_text}, None, completion_id, created)
        else:
            yield completion_chunk(model, {"content": delta_text}, None, completion_id, created)
    if not sent_role:
        yield completion_chunk(model, {"role": "assistant", "content": ""}, None, completion_id, created)
    yield completion_chunk(model, {}, "stop", completion_id, created)


def collect_chat_content(chunks: Iterable[dict[str, Any]]) -> str:
    parts: list[str] = []
    for chunk in chunks:
        choices = chunk.get("choices")
        first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        delta = first.get("delta") if isinstance(first.get("delta"), dict) else {}
        content = str(delta.get("content") or "")
        if content:
            parts.append(content)
    return "".join(parts)


def chat_messages_from_body(body: dict[str, Any]) -> list[dict[str, Any]]:
    messages = body.get("messages")
    if isinstance(messages, list) and messages:
        return [message for message in messages if isinstance(message, dict)]
    prompt = str(body.get("prompt") or "").strip()
    if prompt:
        return [{"role": "user", "content": prompt}]
    raise HTTPException(status_code=400, detail={"error": "messages or prompt is required"})


def chat_image_args(body: dict[str, Any]) -> tuple[str, str, int, list[tuple[bytes, str, str]]]:
    model = str(body.get("model") or "gpt-image-2").strip() or "gpt-image-2"
    prompt = extract_chat_prompt(body)
    if not prompt:
        raise HTTPException(status_code=400, detail={"error": "prompt is required"})
    images = [
        (data, f"image_{idx}.png", mime)
        for idx, (data, mime) in enumerate(extract_chat_image(body), start=1)
    ]
    return model, prompt, parse_image_count(body.get("n")), images


def text_chat_parts(body: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    model = str(body.get("model") or "auto").strip() or "auto"
    messages = normalize_text_messages(normalize_messages(chat_messages_from_body(body)))
    if has_unsupported_tools(body, WEB_SEARCH_TOOL_TYPES):
        messages.insert(0, {"role": "system", "content": TOOL_UNAVAILABLE_SYSTEM_MESSAGE})
    return model, messages


def chat_completion_annotations(annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for item in annotations:
        if item.get("type") != "url_citation":
            continue
        output.append({
            "type": "url_citation",
            "url_citation": {
                "start_index": item.get("start_index", 0),
                "end_index": item.get("end_index", 0),
                "url": item.get("url", ""),
                "title": item.get("title", ""),
            },
        })
    return output


def web_search_chat_response(messages: list[dict[str, Any]], model: str) -> dict[str, Any]:
    query = search_query_from_messages(messages)
    if not query:
        raise HTTPException(status_code=400, detail={"error": "messages or prompt is required for web search"})
    text, annotations = text_with_url_citations(run_web_search(query))
    return completion_response(
        model,
        text,
        messages=messages,
        annotations=chat_completion_annotations(annotations),
    )


def stream_web_search_chat_completion(messages: list[dict[str, Any]], model: str) -> Iterator[dict[str, Any]]:
    query = search_query_from_messages(messages)
    if not query:
        raise HTTPException(status_code=400, detail={"error": "messages or prompt is required for web search"})
    text, _annotations = text_with_url_citations(run_web_search(query))
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    yield completion_chunk(model, {"role": "assistant", "content": text}, None, completion_id, created)
    yield completion_chunk(model, {}, "stop", completion_id, created)


def image_result_content(result: dict[str, Any]) -> str:
    data = result.get("data")
    if isinstance(data, list) and data:
        return build_chat_image_markdown_content(result)
    return str(result.get("message") or "Image generation completed.")


def image_chat_response(body: dict[str, Any]) -> dict[str, Any]:
    model, prompt, n, images = chat_image_args(body)
    result = collect_image_outputs(stream_image_outputs_with_pool(ConversationRequest(
        prompt=prompt,
        model=model,
        n=n,
        response_format="b64_json",
        images=encode_images(images) or None,
    )))
    response = completion_response(model, image_result_content(result), int(result.get("created") or 0) or None)
    usage = image_usage(
        input_text_tokens=count_text_tokens(prompt, model),
        input_image_tokens=count_image_inputs_tokens(images, model),
        output_tokens=count_image_output_items_tokens(result.get("data")),
    )
    response["usage"] = chat_usage_from_image_usage(usage)
    return response


def image_chat_events(body: dict[str, Any]) -> Iterator[dict[str, Any]]:
    model, prompt, n, images = chat_image_args(body)
    image_outputs = stream_image_outputs_with_pool(ConversationRequest(
        prompt=prompt,
        model=model,
        n=n,
        response_format="b64_json",
        images=encode_images(images) or None,
    ))
    yield from stream_image_chat_completion(image_outputs, model)


def stream_image_chat_completion(image_outputs: Iterable[ImageOutput], model: str) -> Iterator[dict[str, Any]]:
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    sent_role = False
    sent_text = ""
    for output in image_outputs:
        content = ""
        if output.kind == "progress":
            content = output.text
            sent_text += content
        elif output.kind == "result":
            content = build_chat_image_markdown_content({"data": output.data})
        elif output.kind == "message":
            content = output.text[len(sent_text):] if output.text.startswith(sent_text) else output.text
        if not content:
            continue
        if not sent_role:
            sent_role = True
            yield completion_chunk(model, {"role": "assistant", "content": content}, None, completion_id, created)
        else:
            yield completion_chunk(model, {"content": content}, None, completion_id, created)
    if not sent_role:
        yield completion_chunk(model, {"role": "assistant", "content": ""}, None, completion_id, created)
    yield completion_chunk(model, {}, "stop", completion_id, created)


def handle(body: dict[str, Any]) -> dict[str, Any] | Iterator[dict[str, Any]]:
    if body.get("stream"):
        if is_image_chat_request(body):
            return image_chat_events(body)
        model, messages = text_chat_parts(body)
        if is_web_search_chat_request(body) and not has_unsupported_tools(body, WEB_SEARCH_TOOL_TYPES):
            return stream_web_search_chat_completion(messages, model)
        thinking_effort = thinking_effort_from_body(body)
        key = cache_key(body, messages, stream=True)
        return chat_completion_cache.get_or_compute_stream(
            key,
            lambda: stream_text_chat_completion(text_backend(), messages, model, thinking_effort),
        )
    if is_image_chat_request(body):
        return image_chat_response(body)
    model, messages = text_chat_parts(body)
    if is_web_search_chat_request(body) and not has_unsupported_tools(body, WEB_SEARCH_TOOL_TYPES):
        return web_search_chat_response(messages, model)
    thinking_effort = thinking_effort_from_body(body)
    key = cache_key(body, messages, stream=False)
    return chat_completion_cache.get_or_compute_response(
        key,
        lambda: completion_response(
            model,
            collect_text(text_backend(), ConversationRequest(model=model, messages=messages, thinking_effort=thinking_effort)),
            messages=messages,
        ),
    )
