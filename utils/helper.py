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
from utils.remote_image import download_public_image

BASE_IMAGE_MODELS = {"gpt-image-2", "codex-gpt-image-2"}
IMAGE_MODEL_PLAN_TYPES = ("plus", "team", "pro")
CODEX_IMAGE_MODEL = "codex-gpt-image-2"
PREFIXED_CODEX_IMAGE_MODELS = {
    f"{plan_type}-{CODEX_IMAGE_MODEL}"
    for plan_type in IMAGE_MODEL_PLAN_TYPES
}
IMAGE_MODELS = BASE_IMAGE_MODELS | PREFIXED_CODEX_IMAGE_MODELS
PUBLIC_IMAGE_MODELS = BASE_IMAGE_MODELS | PREFIXED_CODEX_IMAGE_MODELS
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

SUPPORTED_JSON_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}
MAX_JSON_IMAGE_BYTES = 10 * 1024 * 1024
MAX_JSON_EDIT_IMAGES = 10
DATA_URL_IMAGE_RE = re.compile(r"^data:(?P<mime>[-+./\w]+);base64,(?P<data>.*)$", re.DOTALL)
REMOTE_IMAGE_TIMEOUT_SECONDS = 20


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


def split_image_model(model: object) -> tuple[str | None, str | None]:
    normalized = str(model or "").strip().lower()
    if not normalized:
        return None, None
    if normalized in BASE_IMAGE_MODELS:
        return None, normalized
    for plan_type in IMAGE_MODEL_PLAN_TYPES:
        prefix = f"{plan_type}-"
        if normalized.startswith(prefix):
            base_model = normalized[len(prefix):]
            if base_model == CODEX_IMAGE_MODEL:
                return plan_type, base_model
    return None, None


def is_supported_image_model(model: object) -> bool:
    _, base_model = split_image_model(model)
    return base_model is not None


def is_codex_image_model(model: object) -> bool:
    _, base_model = split_image_model(model)
    return base_model == CODEX_IMAGE_MODEL


def is_image_chat_request(body: dict[str, object]) -> bool:
    model = str(body.get("model") or "").strip()
    modalities = body.get("modalities")
    if is_supported_image_model(model):
        return True
    return isinstance(modalities, list) and "image" in {str(item or "").strip().lower() for item in modalities}


_UPSTREAM_BODY_LOG_LIMIT = 500


class UpstreamHTTPError(RuntimeError):
    """Raised when an upstream HTTP call returns a non-2xx status.

    Carries structured fields (status_code, body, retry_after) so callers can
    branch on status code instead of string-matching on str(exc). The full
    body is preserved on the instance; the formatted message truncates it
    to keep log lines reasonable.
    """

    def __init__(
        self,
        context: str,
        status_code: int,
        body: Any,
        retry_after: int | None = None,
    ) -> None:
        self.context = context
        self.status_code = status_code
        self.body = body
        self.retry_after = retry_after
        if isinstance(body, (dict, list)):
            try:
                body_str = json.dumps(body, ensure_ascii=False)
            except (TypeError, ValueError):
                body_str = repr(body)
        else:
            body_str = str(body)
        if len(body_str) > _UPSTREAM_BODY_LOG_LIMIT:
            body_str = body_str[:_UPSTREAM_BODY_LOG_LIMIT] + "…[truncated]"
        super().__init__(f"{context} failed: status={status_code}, body={body_str}")


def ensure_ok(response: requests.Response, context: str) -> None:
    if 200 <= response.status_code < 300:
        return
    body: Any = response.text
    try:
        body = response.json()
    except Exception:
        pass
    retry_after_header = response.headers.get("Retry-After") if hasattr(response, "headers") else None
    retry_after: int | None = None
    if retry_after_header is not None:
        ra_str = str(retry_after_header).strip()
        if ra_str.isdigit():
            retry_after = int(ra_str)
    raise UpstreamHTTPError(context, response.status_code, body, retry_after=retry_after)


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


def _message_image_url(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("url") or value.get("image_url") or "").strip()
    return str(value or "").strip()


def _decode_message_image_url(value: object) -> tuple[bytes, str] | None:
    source = _message_image_url(value)
    if source.startswith("data:"):
        header, _, data = source.partition(",")
        mime = header.split(";")[0].removeprefix("data:") or "image/png"
        return base64.b64decode(data), mime
    if not source.startswith(("http://", "https://")):
        return None
    image_data, _parsed_path, mime = download_public_image(
        source,
        max_bytes=MAX_JSON_IMAGE_BYTES,
        timeout_seconds=REMOTE_IMAGE_TIMEOUT_SECONDS,
        user_agent="chatgpt2api vision fetcher",
    )
    return image_data, mime


def _decode_message_image_object(item: dict[str, object]) -> tuple[bytes, str] | None:
    data = item.get("data")
    if isinstance(data, (bytes, bytearray)):
        return bytes(data), str(item.get("mime") or item.get("mime_type") or "image/png")
    for key in ("image_url", "url"):
        image = _decode_message_image_url(item.get(key))
        if image:
            return image
    value = item.get("b64_json") or item.get("base64")
    if isinstance(value, str) and value.strip():
        image_data, _, mime = _decode_json_image_string(
            value,
            1,
            mime_type=str(item.get("mime") or item.get("mime_type") or item.get("mimeType") or "image/png"),
        )
        return image_data, mime
    source = item.get("source")
    if isinstance(source, dict) and str(source.get("type") or "") == "base64":
        encoded = str(source.get("data") or "")
        mime = str(source.get("media_type") or source.get("mime_type") or "image/png")
        image_data, _, resolved_mime = _decode_json_image_string(encoded, 1, mime_type=mime)
        return image_data, resolved_mime
    return None


def extract_image_from_message_content(content: object) -> list[tuple[bytes, str]]:
    if not isinstance(content, list):
        return []
    images = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type == "image_url":
            image = _decode_message_image_url(item.get("image_url") or item.get("url") or item)
            if image:
                images.append(image)
        elif item_type in {"input_image", "image"}:
            image = _decode_message_image_object(item)
            if image:
                images.append(image)
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
