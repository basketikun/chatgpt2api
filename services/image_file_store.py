from __future__ import annotations

import base64
import binascii
import time
import uuid
from pathlib import Path
from typing import Any

from services.config import config
from services.image_trace_logger import ImageTraceLogger
from services.image_service import ImageGenerationError


def _decode_b64_image(value: str) -> bytes:
    cleaned = value.strip()
    if cleaned.startswith("data:") and "," in cleaned:
        cleaned = cleaned.split(",", 1)[1]
    return base64.b64decode(cleaned, validate=False)


def _image_extension(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        return ".gif"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def _save_image_bytes(image_bytes: bytes, index: int, timestamp: str) -> dict[str, str | int]:
    config.images_dir.mkdir(parents=True, exist_ok=True)
    extension = _image_extension(image_bytes)
    file_name = f"{timestamp}-{uuid.uuid4().hex[:8]}-{index}{extension}"
    file_path = config.images_dir / file_name
    file_path.write_bytes(image_bytes)
    return {
        "file_name": file_name,
        "file_path": str(file_path),
        "file_size": len(image_bytes),
    }


def save_image_result_files(result: dict[str, Any], trace: ImageTraceLogger | None = None) -> dict[str, Any]:
    data = result.get("data")
    if not isinstance(data, list):
        trace and trace.event("image.save.skip", reason="response data is not a list")
        return result

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    trace and trace.event("image.save.start", item_count=len(data), images_dir=config.images_dir)
    try:
        for index, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                trace and trace.event("image.save.skip", index=index, reason="item is not an object")
                continue
            b64_json = item.get("b64_json")
            if not isinstance(b64_json, str) or not b64_json.strip():
                trace and trace.event("image.save.skip", index=index, reason="item has no b64_json")
                continue
            saved = _save_image_bytes(_decode_b64_image(b64_json), index, timestamp)
            item.update(saved)
            trace and trace.event("image.save.file", index=index, **saved)
    except (binascii.Error, OSError, ValueError) as exc:
        trace and trace.event("image.save.error", error_type=type(exc).__name__, error=str(exc))
        raise ImageGenerationError(f"failed to save generated image: {exc}") from exc

    trace and trace.event("image.save.complete")
    return result
