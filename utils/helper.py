import base64
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

from curl_cffi import requests
from fastapi import HTTPException
from utils.log import logger

IMAGE_MODELS = {"gpt-image-2", "codex-gpt-image-2"}
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

SUPPORTED_JSON_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}
MAX_JSON_IMAGE_BYTES = 10 * 1024 * 1024
MAX_JSON_EDIT_IMAGES = 10
DATA_URL_IMAGE_RE = re.compile(r"^data:(?P<mime>[-+./\w]+);base64,(?P<data>.*)$", re.DOTALL)


def _image_extension(mime_type: str) -> str:
    image_type = mime_type.split("/", 1)[1].split(";", 1)[0].lower() if "/" in mime_type else "png"
    return "jpg" if image_type == "jpeg" else image_type or "png"


def _decode_json_image_string(value: str, index: int, filename: str | None = None, mime_type: str | None = None) -> tuple[bytes, str, str]:
    text = value.strip()
    if not text:
        raise HTTPException(status_code=400, detail={"error": "image file is empty"})
    match = DATA_URL_IMAGE_RE.match(text)
    if match:
        resolved_mime = (match.group("mime") or "image/png").lower()
        encoded = match.group("data")
    else:
        if text.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail={"error": "remote image URLs are not supported"})
        resolved_mime = (mime_type or "image/png").lower()
        encoded = text
    if resolved_mime == "image/jpg":
        resolved_mime = "image/jpeg"
    if resolved_mime not in SUPPORTED_JSON_IMAGE_MIME_TYPES:
        raise HTTPException(status_code=400, detail={"error": "unsupported image mime type"})
    try:
        image_data = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid base64 image data"}) from exc
    if not image_data:
        raise HTTPException(status_code=400, detail={"error": "image file is empty"})
    if len(image_data) > MAX_JSON_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail={"error": "image file is too large"})
    return image_data, filename or f"image_{index}.{_image_extension(resolved_mime)}", resolved_mime


def _extract_json_image_value(item: object) -> tuple[str, str | None, str | None]:
    if isinstance(item, str):
        return item, None, None
    if not isinstance(item, dict):
        raise HTTPException(status_code=400, detail={"error": "image entry must be a base64 string or object"})
    filename = str(item.get("filename") or item.get("file_name") or "").strip() or None
    mime_type = str(item.get("mime_type") or item.get("mimeType") or "").strip() or None
    value = item.get("b64_json") or item.get("base64")
    if not value:
        image_url = item.get("image_url") or item.get("url")
        if isinstance(image_url, dict):
            filename = filename or str(image_url.get("filename") or image_url.get("file_name") or "").strip() or None
            mime_type = mime_type or str(image_url.get("mime_type") or image_url.get("mimeType") or "").strip() or None
            value = image_url.get("url") or image_url.get("image_url")
        else:
            value = image_url
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail={"error": "image entry must include image data"})
    return value, filename, mime_type


def normalize_json_edit_images(image: object = None, images: object = None) -> list[tuple[bytes, str, str]]:
    raw_images = images if images is not None else image
    if raw_images is None:
        raise HTTPException(status_code=400, detail={"error": "image file is required"})
    entries = raw_images if isinstance(raw_images, list) else [raw_images]
    if not entries:
        raise HTTPException(status_code=400, detail={"error": "image file is required"})
    if len(entries) > MAX_JSON_EDIT_IMAGES:
        raise HTTPException(status_code=400, detail={"error": f"images supports up to {MAX_JSON_EDIT_IMAGES} items"})
    normalized = []
    for index, item in enumerate(entries, start=1):
        value, filename, mime_type = _extract_json_image_value(item)
        normalized.append(_decode_json_image_string(value, index, filename, mime_type))
    return normalized


def new_uuid() -> str:
    return str(uuid.uuid4())


def is_image_chat_request(body: dict[str, object]) -> bool:
    model = str(body.get("model") or "").strip()
    modalities = body.get("modalities")
    if model in IMAGE_MODELS:
        return True
    return isinstance(modalities, list) and "image" in {str(item or "").strip().lower() for item in modalities}


def ensure_ok(response: requests.Response, context: str) -> None:
    if 200 <= response.status_code < 300:
        return
    body: Any = response.text
    try:
        body = response.json()
    except Exception:
        pass
    raise RuntimeError(f"{context} failed: status={response.status_code}, body={body}")


def sse_json_stream(items) -> Iterator[str]:
    yield ": stream-open\n\n"
    try:
        for item in items:
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
    except Exception as exc:
        logger.warning({
            "event": "sse_stream_error",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        })
        error = exc.to_openai_error() if hasattr(exc, "to_openai_error") else {
            "error": {"message": str(exc), "type": exc.__class__.__name__}
        }
        yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def anthropic_sse_stream(items) -> Iterator[str]:
    try:
        for item in items:
            event = str(item.get("type") or "message_delta") if isinstance(item, dict) else "message_delta"
            yield f"event: {event}\n"
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
    except Exception as exc:
        logger.warning({
            "event": "anthropic_sse_stream_error",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        })
        error = {"type": "error", "error": {"type": exc.__class__.__name__, "message": str(exc)}}
        yield "event: error\n"
        yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"


def iter_sse_payloads(response: requests.Response) -> Iterator[str]:
    for raw_line in response.iter_lines():
        if not raw_line:
            continue
        line = raw_line.decode("utf-8", errors="ignore") if isinstance(raw_line, bytes) else str(raw_line)
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload:
            yield payload


def save_images_from_text(text: str, prefix: str) -> list[Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    matches = re.findall(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", text or "")
    saved_paths: list[Path] = []
    timestamp = int(time.time() * 1000)
    for index, data_url in enumerate(matches, start=1):
        header, encoded = data_url.split(",", 1)
        image_type = header.split(";")[0].removeprefix("data:image/").strip() or "png"
        extension = "jpg" if image_type == "jpeg" else image_type
        output_path = OUTPUT_DIR / f"{prefix}_{timestamp}_{index}.{extension}"
        output_path.write_bytes(base64.b64decode(encoded))
        saved_paths.append(output_path)
    return saved_paths


def anonymize_token(token: object) -> str:
    value = str(token or "").strip()
    if not value:
        return "token:empty"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"token:{digest}"


def extract_response_prompt(input_value: object) -> str:
    if isinstance(input_value, str):
        return input_value.strip()
    if isinstance(input_value, dict):
        role = str(input_value.get("role") or "").strip().lower()
        if role and role != "user":
            return ""
        return extract_prompt_from_message_content(input_value.get("content"))
    if not isinstance(input_value, list):
        return ""
    prompt_parts: list[str] = []
    for item in input_value:
        if isinstance(item, dict) and str(item.get("type") or "").strip() == "input_text":
            text = str(item.get("text") or "").strip()
            if text:
                prompt_parts.append(text)
            continue
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role and role != "user":
            continue
        prompt = extract_prompt_from_message_content(item.get("content"))
        if prompt:
            prompt_parts.append(prompt)
    return "\n".join(prompt_parts).strip()


def has_response_image_generation_tool(body: dict[str, object]) -> bool:
    tools = body.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, dict) and str(tool.get("type") or "").strip() == "image_generation":
                return True
    tool_choice = body.get("tool_choice")
    return isinstance(tool_choice, dict) and str(tool_choice.get("type") or "").strip() == "image_generation"


def extract_prompt_from_message_content(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type == "text":
            text = str(item.get("text") or "").strip()
            if text:
                parts.append(text)
        elif item_type == "input_text":
            text = str(item.get("text") or item.get("input_text") or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def extract_image_from_message_content(content: object) -> list[tuple[bytes, str]]:
    if not isinstance(content, list):
        return []
    images = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type == "image_url":
            url_obj = item.get("image_url") or item
            url = str(url_obj.get("url") or "") if isinstance(url_obj, dict) else str(url_obj)
            if url.startswith("data:"):
                header, _, data = url.partition(",")
                mime = header.split(";")[0].removeprefix("data:")
                images.append((base64.b64decode(data), mime or "image/png"))
        elif item_type == "input_image":
            image_url = str(item.get("image_url") or "")
            if image_url.startswith("data:"):
                header, _, data = image_url.partition(",")
                mime = header.split(";")[0].removeprefix("data:")
                images.append((base64.b64decode(data), mime or "image/png"))
    return images


def extract_chat_image(body: dict[str, object]) -> list[tuple[bytes, str]]:
    messages = body.get("messages")
    if not isinstance(messages, list):
        return []
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        if str(message.get("role") or "").strip().lower() != "user":
            continue
        images = extract_image_from_message_content(message.get("content"))
        if images:
            return images
    return []


def extract_chat_prompt(body: dict[str, object]) -> str:
    direct_prompt = str(body.get("prompt") or "").strip()
    if direct_prompt:
        return direct_prompt
    messages = body.get("messages")
    if not isinstance(messages, list):
        return ""
    prompt_parts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        if str(message.get("role") or "").strip().lower() != "user":
            continue
        prompt = extract_prompt_from_message_content(message.get("content"))
        if prompt:
            prompt_parts.append(prompt)
    return "\n".join(prompt_parts).strip()


def parse_image_count(raw_value: object) -> int:
    try:
        value = int(raw_value or 1)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"error": "n must be an integer"}) from exc
    if value < 1 or value > 4:
        raise HTTPException(status_code=400, detail={"error": "n must be between 1 and 4"})
    return value


def build_chat_image_markdown_content(image_result: dict[str, object]) -> str:
    image_items = image_result.get("data") if isinstance(image_result.get("data"), list) else []
    markdown_images: list[str] = []
    for index, item in enumerate(image_items, start=1):
        if not isinstance(item, dict):
            continue
        b64_json = str(item.get("b64_json") or "").strip()
        if b64_json:
            markdown_images.append(f"![image_{index}](data:image/png;base64,{b64_json})")
    return "\n\n".join(markdown_images) if markdown_images else "Image generation completed."
