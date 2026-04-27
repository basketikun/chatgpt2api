from __future__ import annotations

import base64
import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from typing import Iterable

from services.config import config
from services.image_service import ImageGenerationError

UPSTREAM_TIMEOUT_SECONDS = 600
READ_CHUNK_SIZE = 256 * 1024
UPSTREAM_MAX_ATTEMPTS = 3
UPSTREAM_RETRY_DELAY_SECONDS = 2.0
RETRYABLE_HTTP_STATUS = {502, 503, 504}


def is_openai_image_upstream_configured() -> bool:
    return bool(config.openai_image_base_url and config.openai_image_api_key)


def _upstream_url(path: str) -> str:
    return f"{config.openai_image_base_url.rstrip('/')}/{path.lstrip('/')}"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.openai_image_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _normalize_image_response(payload: object, *, created: int | None = None) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ImageGenerationError("OpenAI image upstream returned invalid payload")

    data = payload.get("data")
    if not isinstance(data, list):
        raise ImageGenerationError("OpenAI image upstream response missing data")

    items: list[dict[str, object]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        b64_json = str(item.get("b64_json") or "").strip()
        url = str(item.get("url") or "").strip()
        if not b64_json and not url:
            continue
        next_item: dict[str, object] = {}
        if b64_json:
            next_item["b64_json"] = b64_json
        if url:
            next_item["url"] = url
        revised_prompt = str(item.get("revised_prompt") or "").strip()
        if revised_prompt:
            next_item["revised_prompt"] = revised_prompt
        items.append(next_item)

    if not items:
        raise ImageGenerationError("OpenAI image upstream did not return images")

    return {
        "created": int(payload.get("created") or created or time.time()),
        "data": items,
    }


def _is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError, socket.timeout, ssl.SSLError)):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, (TimeoutError, ConnectionError, socket.timeout, ssl.SSLError)):
            return True
        reason_text = str(reason).lower()
        return any(
            marker in reason_text
            for marker in (
                "unexpected_eof",
                "eof occurred",
                "connection reset",
                "connection aborted",
                "timed out",
            )
        )
    return False


def _read_json_response(response: object) -> object:
    chunks: list[bytes] = []
    while True:
        chunk = response.read(READ_CHUNK_SIZE)
        if not chunk:
            break
        chunks.append(chunk)
    return json.loads(b"".join(chunks).decode("utf-8"))


def _post_json_once(path: str, body: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        _upstream_url(path),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=_headers(),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=UPSTREAM_TIMEOUT_SECONDS) as response:
        payload = _read_json_response(response)
    return _normalize_image_response(payload)


def _post_json(path: str, body: dict[str, object]) -> dict[str, object]:
    errors: list[str] = []
    for attempt in range(1, UPSTREAM_MAX_ATTEMPTS + 1):
        try:
            result = _post_json_once(path, body)
            if attempt > 1:
                print(f"[openai-image-upstream] success after retry attempt={attempt} path={path}")
            return result
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            message = f"HTTP {exc.code} {error_body}"
            errors.append(f"attempt {attempt}: {message}")
            if exc.code not in RETRYABLE_HTTP_STATUS or attempt >= UPSTREAM_MAX_ATTEMPTS:
                raise ImageGenerationError(
                    f"OpenAI image upstream failed after {attempt} attempt(s): {message}"
                ) from exc
        except ImageGenerationError:
            raise
        except Exception as exc:
            message = str(exc)
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {message}")
            if not _is_retryable_exception(exc) or attempt >= UPSTREAM_MAX_ATTEMPTS:
                detail = "; ".join(errors[-UPSTREAM_MAX_ATTEMPTS:])
                raise ImageGenerationError(
                    f"OpenAI image upstream failed after {attempt} attempt(s): {detail}"
                ) from exc

        delay = UPSTREAM_RETRY_DELAY_SECONDS * attempt
        print(
            f"[openai-image-upstream] retry attempt={attempt + 1}/{UPSTREAM_MAX_ATTEMPTS} "
            f"path={path} last_error={errors[-1]} wait={delay:.1f}s"
        )
        time.sleep(delay)

    raise ImageGenerationError("OpenAI image upstream failed")


def generate_openai_image_result(prompt: str, model: str, n: int, response_format: str = "b64_json") -> dict[str, object]:
    if not is_openai_image_upstream_configured():
        raise ImageGenerationError("OpenAI image upstream is not configured")

    body: dict[str, object] = {
        "model": model or "gpt-image-2",
        "prompt": prompt,
        "n": n,
        "response_format": response_format or "b64_json",
    }
    return _post_json("/images/generations", body)


def edit_openai_image_result(
    prompt: str,
    images: Iterable[tuple[bytes, str, str]],
    model: str,
    n: int,
    response_format: str = "b64_json",
) -> dict[str, object]:
    if not is_openai_image_upstream_configured():
        raise ImageGenerationError("OpenAI image upstream is not configured")

    encoded_images: list[dict[str, str]] = []
    for image_data, _file_name, mime_type in images:
        encoded = base64.b64encode(image_data).decode("ascii")
        encoded_images.append(
            {
                "type": "input_image",
                "image_url": f"data:{mime_type or 'image/png'};base64,{encoded}",
            }
        )

    if not encoded_images:
        raise ImageGenerationError("image is required")

    body: dict[str, object] = {
        "model": model or "gpt-image-2",
        "prompt": prompt,
        "image": encoded_images,
        "n": n,
        "response_format": response_format or "b64_json",
    }
    return _post_json("/images/edits", body)
