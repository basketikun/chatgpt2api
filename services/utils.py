from __future__ import annotations

import base64
import binascii
import struct
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote_to_bytes, urlparse
from urllib.request import Request, urlopen

from fastapi import HTTPException


IMAGE_MODELS = {"gpt-image-1", "gpt-image-2"}
SUPPORTED_IMAGE_MIME_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


@dataclass(frozen=True)
class InputImage:
    name: str
    mime_type: str
    data: bytes
    width: int
    height: int
    source: str = "local"

    @property
    def size_bytes(self) -> int:
        return len(self.data)


def is_image_chat_request(body: dict[str, object]) -> bool:
    model = str(body.get("model") or "").strip()
    modalities = body.get("modalities")
    if model in IMAGE_MODELS:
        return True
    if isinstance(modalities, list):
        normalized = {str(item or "").strip().lower() for item in modalities}
        return "image" in normalized
    if has_chat_image_inputs(body):
        return True
    return False


def has_response_image_generation_tool(body: dict[str, object]) -> bool:
    tools = body.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, dict) and str(tool.get("type") or "").strip() == "image_generation":
                return True

    tool_choice = body.get("tool_choice")
    if isinstance(tool_choice, dict) and str(tool_choice.get("type") or "").strip() == "image_generation":
        return True
    return False


def _invalid_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"error": message})


def _normalize_image_reference(value: object) -> tuple[str, str | None]:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized, None
        raise _invalid_request("image value is empty")

    if not isinstance(value, dict):
        raise _invalid_request("image must be a string, object, or list")

    if value.get("file_id"):
        raise _invalid_request("file_id image inputs are not supported")

    name = str(value.get("name") or value.get("filename") or "").strip() or None

    direct_value = value.get("data_url") or value.get("url") or value.get("image") or value.get("image_url")
    if isinstance(direct_value, dict):
        direct_value = direct_value.get("url") or direct_value.get("image_url")

    normalized = str(direct_value or "").strip()
    if not normalized:
        raise _invalid_request("image url is required")
    return normalized, name


def _decode_data_url(value: str) -> tuple[str, bytes]:
    header, separator, payload = value.partition(",")
    if separator == "":
        raise _invalid_request("invalid data url image")

    media_type = "text/plain;charset=US-ASCII"
    if header.startswith("data:"):
        media_type = header[5:] or media_type

    parts = [item.strip() for item in media_type.split(";") if item.strip()]
    mime_type = parts[0] if parts else "text/plain"

    try:
        if any(part.lower() == "base64" for part in parts[1:]):
            data = base64.b64decode(payload, validate=True)
        else:
            data = unquote_to_bytes(payload)
    except (ValueError, binascii.Error) as exc:
        raise _invalid_request("invalid base64 image data") from exc

    return mime_type, data


def _fetch_remote_image_bytes(url: str) -> tuple[str, bytes]:
    request = Request(
        url,
        headers={
            "Accept": "image/*",
            "User-Agent": "chatgpt2api/1.0",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get_content_type() or "application/octet-stream"
            return content_type, response.read()
    except HTTPError as exc:
        raise _invalid_request(f"failed to download image: HTTP {exc.code}") from exc
    except URLError as exc:
        raise _invalid_request("failed to download image") from exc


def _detect_image_type(image_bytes: bytes) -> tuple[str, str]:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", ".gif"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp", ".webp"
    raise _invalid_request("unsupported image format")


def _read_jpeg_size(image_bytes: bytes) -> tuple[int, int]:
    index = 2
    size = len(image_bytes)
    while index < size:
        if image_bytes[index] != 0xFF:
            index += 1
            continue
        while index < size and image_bytes[index] == 0xFF:
            index += 1
        if index >= size:
            break
        marker = image_bytes[index]
        index += 1
        if marker in {0xD8, 0xD9, 0x01} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > size:
            break
        segment_length = struct.unpack(">H", image_bytes[index : index + 2])[0]
        if segment_length < 2 or index + segment_length > size:
            break
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if index + 7 > size:
                break
            height, width = struct.unpack(">HH", image_bytes[index + 3 : index + 7])
            return width, height
        index += segment_length
    raise _invalid_request("failed to read jpeg size")


def _read_webp_size(image_bytes: bytes) -> tuple[int, int]:
    chunk_type = image_bytes[12:16]
    if chunk_type == b"VP8 ":
        if len(image_bytes) < 30:
            raise _invalid_request("failed to read webp size")
        width, height = struct.unpack("<HH", image_bytes[26:30])
        return width & 0x3FFF, height & 0x3FFF
    if chunk_type == b"VP8L":
        if len(image_bytes) < 25:
            raise _invalid_request("failed to read webp size")
        bits = struct.unpack("<I", image_bytes[21:25])[0]
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    if chunk_type == b"VP8X":
        if len(image_bytes) < 30:
            raise _invalid_request("failed to read webp size")
        width = 1 + int.from_bytes(image_bytes[24:27], "little")
        height = 1 + int.from_bytes(image_bytes[27:30], "little")
        return width, height
    raise _invalid_request("failed to read webp size")


def _read_image_size(image_bytes: bytes, mime_type: str) -> tuple[int, int]:
    if mime_type == "image/png":
        if len(image_bytes) < 24:
            raise _invalid_request("failed to read png size")
        return struct.unpack(">II", image_bytes[16:24])
    if mime_type == "image/gif":
        if len(image_bytes) < 10:
            raise _invalid_request("failed to read gif size")
        return struct.unpack("<HH", image_bytes[6:10])
    if mime_type == "image/jpeg":
        return _read_jpeg_size(image_bytes)
    if mime_type == "image/webp":
        return _read_webp_size(image_bytes)
    raise _invalid_request("unsupported image format")


def _normalize_image_name(name: str | None, fallback_url: str | None, mime_type: str, extension: str) -> str:
    candidate = str(name or "").strip()
    if not candidate and fallback_url:
        candidate = Path(urlparse(fallback_url).path).name
    if not candidate:
        candidate = f"input_image{extension}"

    suffix = Path(candidate).suffix.lower()
    if suffix and suffix in SUPPORTED_IMAGE_MIME_TYPES.values():
        return candidate
    if mime_type in SUPPORTED_IMAGE_MIME_TYPES:
        return f"{candidate}{extension}" if not suffix else f"{Path(candidate).stem}{extension}"
    return candidate


def _build_input_image(reference: str, name: str | None) -> InputImage:
    if reference.startswith("data:"):
        declared_mime_type, image_bytes = _decode_data_url(reference)
        source = "local"
        fallback_url = None
    else:
        declared_mime_type, image_bytes = _fetch_remote_image_bytes(reference)
        source = "remote"
        fallback_url = reference

    if not image_bytes:
        raise _invalid_request("image data is empty")

    detected_mime_type, extension = _detect_image_type(image_bytes)
    if declared_mime_type.startswith("image/") and declared_mime_type != detected_mime_type:
        mime_type = detected_mime_type
    else:
        mime_type = detected_mime_type

    if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
        raise _invalid_request("unsupported image mime type")

    width, height = _read_image_size(image_bytes, mime_type)
    return InputImage(
        name=_normalize_image_name(name, fallback_url, mime_type, extension),
        mime_type=mime_type,
        data=image_bytes,
        width=width,
        height=height,
        source=source,
    )


def _collect_image_inputs(value: object) -> list[InputImage]:
    if value is None:
        return []
    if isinstance(value, list):
        images: list[InputImage] = []
        for item in value:
            images.extend(_collect_image_inputs(item))
        return images

    reference, name = _normalize_image_reference(value)
    return [_build_input_image(reference, name)]


def extract_generation_images(body: dict[str, object], *, require_image: bool = False) -> list[InputImage]:
    images: list[InputImage] = []
    if "image" in body:
        images.extend(_collect_image_inputs(body.get("image")))
    if "images" in body:
        images.extend(_collect_image_inputs(body.get("images")))
    if require_image and not images:
        raise _invalid_request("image is required")
    return images


def _extract_prompt_and_images_from_message_content(content: object) -> tuple[list[str], list[InputImage]]:
    if isinstance(content, str):
        text = content.strip()
        return ([text] if text else []), []
    if not isinstance(content, list):
        return [], []

    prompt_parts: list[str] = []
    images: list[InputImage] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type in {"text", "input_text"}:
            text = str(item.get("text") or item.get("input_text") or "").strip()
            if text:
                prompt_parts.append(text)
            continue
        if item_type in {"image_url", "input_image"}:
            image_value = item.get("image_url") or item.get("input_image") or item.get("image")
            images.extend(_collect_image_inputs(image_value))
    return prompt_parts, images


def _message_content_has_image_inputs(content: object) -> bool:
    if not isinstance(content, list):
        return False
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type in {"image_url", "input_image"}:
            return True
    return False


def has_chat_image_inputs(body: dict[str, object]) -> bool:
    if body.get("image") is not None or body.get("images") is not None:
        return True

    messages = body.get("messages")
    if not isinstance(messages, list):
        return False

    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip().lower()
        if role != "user":
            continue
        if _message_content_has_image_inputs(message.get("content")):
            return True
    return False


def extract_prompt_from_message_content(content: object) -> str:
    prompt_parts, _ = _extract_prompt_and_images_from_message_content(content)
    return "\n".join(prompt_parts).strip()


def extract_chat_prompt_and_images(body: dict[str, object]) -> tuple[str, list[InputImage]]:
    direct_prompt = str(body.get("prompt") or "").strip()
    direct_images = extract_generation_images(body)
    if direct_prompt:
        return direct_prompt, direct_images

    messages = body.get("messages")
    if not isinstance(messages, list):
        return "", direct_images

    prompt_parts: list[str] = []
    images = list(direct_images)
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip().lower()
        if role != "user":
            continue
        content_prompts, content_images = _extract_prompt_and_images_from_message_content(message.get("content"))
        prompt_parts.extend(content_prompts)
        images.extend(content_images)

    return "\n".join(prompt_parts).strip(), images


def extract_chat_prompt(body: dict[str, object]) -> str:
    prompt, _ = extract_chat_prompt_and_images(body)
    return prompt


def extract_response_prompt_and_images(input_value: object) -> tuple[str, list[InputImage]]:
    if isinstance(input_value, str):
        return input_value.strip(), []

    if isinstance(input_value, dict):
        role = str(input_value.get("role") or "").strip().lower()
        if role and role != "user":
            return "", []
        prompt_parts, images = _extract_prompt_and_images_from_message_content(input_value.get("content"))
        return "\n".join(prompt_parts).strip(), images

    if not isinstance(input_value, list):
        return "", []

    prompt_parts: list[str] = []
    images: list[InputImage] = []
    for item in input_value:
        if isinstance(item, dict) and str(item.get("type") or "").strip() == "input_text":
            text = str(item.get("text") or "").strip()
            if text:
                prompt_parts.append(text)
            continue
        if isinstance(item, dict) and str(item.get("type") or "").strip() == "input_image":
            images.extend(_collect_image_inputs(item.get("image_url") or item.get("input_image") or item.get("image")))
            continue
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role and role != "user":
            continue
        content_prompts, content_images = _extract_prompt_and_images_from_message_content(item.get("content"))
        prompt_parts.extend(content_prompts)
        images.extend(content_images)
    return "\n".join(prompt_parts).strip(), images


def extract_response_prompt(input_value: object) -> str:
    prompt, _ = extract_response_prompt_and_images(input_value)
    return prompt


def parse_image_count(raw_value: object) -> int:
    try:
        value = int(raw_value or 1)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"error": "n must be an integer"}) from exc
    if value < 1 or value > 4:
        raise HTTPException(status_code=400, detail={"error": "n must be between 1 and 4"})
    return value


def build_chat_image_completion(
    model: str,
    prompt: str,
    image_result: dict[str, object],
) -> dict[str, object]:
    created = int(image_result.get("created") or time.time())
    image_items = image_result.get("data") if isinstance(image_result.get("data"), list) else []

    markdown_images = []
    output_images = []

    for index, item in enumerate(image_items, start=1):
        if not isinstance(item, dict):
            continue
        b64_json = str(item.get("b64_json") or "").strip()
        if not b64_json:
            continue
        image_data_url = f"data:image/png;base64,{b64_json}"
        markdown_images.append(f"![image_{index}]({image_data_url})")
        output_images.append(
            {
                "b64_json": b64_json,
                "revised_prompt": str(item.get("revised_prompt") or prompt).strip(),
            }
        )

    text_content = "\n\n".join(markdown_images) if markdown_images else "Image generation completed."

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text_content,
                    "images": output_images,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }
