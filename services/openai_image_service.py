from __future__ import annotations

import json
import socket
import ssl
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Iterable

from services.config import config
from services.image_trace_logger import ImageTraceLogger
from services.image_service import ImageGenerationError

UPSTREAM_TIMEOUT_SECONDS = 600
READ_CHUNK_SIZE = 256 * 1024
DEFAULT_UPSTREAM_MAX_ATTEMPTS = 8
UPSTREAM_RETRY_DELAY_SECONDS = 2.0
RETRYABLE_HTTP_STATUS = {502, 503, 504}
GATEWAY_TIMEOUT_LOWER_SECONDS = 55
GATEWAY_TIMEOUT_UPPER_SECONDS = 75


class UpstreamInvalidJsonError(RuntimeError):
    pass


class UpstreamHttpStatusError(RuntimeError):
    def __init__(self, status_code: int, body: str):
        super().__init__(f"HTTP {status_code} {body}")
        self.status_code = status_code
        self.body = body


def is_openai_image_upstream_configured() -> bool:
    return bool(config.openai_image_base_url and config.openai_image_api_key)


def _upstream_url(path: str) -> str:
    return f"{config.openai_image_base_url.rstrip('/')}/{path.lstrip('/')}"


def _headers(content_type: str | None = "application/json") -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {config.openai_image_api_key}",
        "Accept": "application/json",
        "User-Agent": "chatgpt2api/1.0",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


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
    if isinstance(
        exc,
        (
            UpstreamInvalidJsonError,
            TimeoutError,
            ConnectionError,
            socket.timeout,
            ssl.SSLError,
            json.JSONDecodeError,
            urllib.error.URLError,
        ),
    ):
        return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "unexpected_eof",
            "eof occurred",
            "connection reset",
            "connection aborted",
            "connection closed abruptly",
            "remote end closed connection without response",
            "remote disconnected",
            "timed out",
        )
    )


def _read_json_response(response: object) -> object:
    chunks: list[bytes] = []
    while True:
        chunk = response.read(READ_CHUNK_SIZE)
        if not chunk:
            break
        chunks.append(chunk)
    raw_body = b"".join(chunks)
    try:
        return json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        preview = raw_body[:240].decode("utf-8", errors="replace")
        raise UpstreamInvalidJsonError(
            f"invalid or truncated JSON response: bytes={len(raw_body)} preview={preview!r}; {exc}"
        ) from exc


def _read_json_bytes(raw_body: bytes) -> object:
    try:
        return json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        preview = raw_body[:240].decode("utf-8", errors="replace")
        raise UpstreamInvalidJsonError(
            f"invalid or truncated JSON response: bytes={len(raw_body)} preview={preview!r}; {exc}"
        ) from exc


def _urlopen(request: urllib.request.Request):
    return urllib.request.urlopen(
        request,
        timeout=UPSTREAM_TIMEOUT_SECONDS,
        context=ssl.create_default_context(),
    )


def _looks_like_gateway_timeout(errors: list[str]) -> bool:
    timeout_markers = (
        "connection closed abruptly",
        "remote end closed connection without response",
        "remote disconnected",
        "unexpected_eof",
        "eof occurred",
    )
    if not errors:
        return False
    for item in errors:
        lowered = item.lower()
        if not any(marker in lowered for marker in timeout_markers):
            return False
        if "after " not in lowered or "s:" not in lowered:
            return False
    return True


def _final_error_message(attempt: int, errors: list[str]) -> str:
    detail = "; ".join(errors[-_max_attempts():])
    if _looks_like_gateway_timeout(errors):
        detail = (
            f"{detail}. likely upstream gateway timeout around "
            f"{GATEWAY_TIMEOUT_LOWER_SECONDS}-{GATEWAY_TIMEOUT_UPPER_SECONDS}s on the client-facing relay path"
        )
    return f"OpenAI image upstream failed after {attempt} attempt(s): {detail}"


def _max_attempts() -> int:
    return int(getattr(config, "openai_image_max_attempts", DEFAULT_UPSTREAM_MAX_ATTEMPTS) or DEFAULT_UPSTREAM_MAX_ATTEMPTS)


def _quote_multipart_header_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", "")


def _encode_multipart_form(
    fields: dict[str, object],
    files: Iterable[tuple[str, bytes, str, str]],
) -> tuple[bytes, str]:
    boundary = f"----chatgpt2api-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("ascii"),
                f'Content-Disposition: form-data; name="{_quote_multipart_header_value(name)}"\r\n'.encode("utf-8"),
                b"Content-Type: text/plain; charset=utf-8\r\n",
                b"\r\n",
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )

    for field_name, file_data, file_name, mime_type in files:
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("ascii"),
                (
                    'Content-Disposition: form-data; '
                    f'name="{_quote_multipart_header_value(field_name)}"; '
                    f'filename="{_quote_multipart_header_value(file_name or "image.png")}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {mime_type or 'application/octet-stream'}\r\n".encode("utf-8"),
                b"\r\n",
                file_data,
                b"\r\n",
            ]
        )

    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), boundary


def _post_json_once(path: str, body: dict[str, object], trace: ImageTraceLogger | None = None) -> dict[str, object]:
    trace and trace.event("upstream.request", method="POST", path=path, response_format=body.get("response_format"), client="urllib")
    request = urllib.request.Request(
        _upstream_url(path),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=_headers(),
        method="POST",
    )
    with _urlopen(request) as response:
        payload = _read_json_response(response)
        status_code = getattr(response, "status", 200)
        content_length = getattr(response, "length", None)
    trace and trace.event("upstream.response", path=path, status=status_code, bytes=content_length)
    return _normalize_image_response(payload)


def _post_with_retries(
    path: str,
    post_once: Callable[[], dict[str, object]],
    trace: ImageTraceLogger | None = None,
) -> dict[str, object]:
    errors: list[str] = []
    max_attempts = _max_attempts()
    for attempt in range(1, max_attempts + 1):
        started = time.time()
        trace and trace.event("upstream.attempt.start", path=path, attempt=attempt, max_attempts=max_attempts)
        try:
            result = post_once()
            trace and trace.event("upstream.attempt.success", path=path, attempt=attempt, duration_ms=int((time.time() - started) * 1000))
            if attempt > 1:
                print(f"[openai-image-upstream] success after retry attempt={attempt} path={path}")
            return result
        except urllib.error.HTTPError as exc:
            elapsed = time.time() - started
            error_body = exc.read().decode("utf-8", errors="replace")
            message = f"HTTP {exc.code} {error_body}"
            errors.append(f"attempt {attempt} after {elapsed:.1f}s: {message}")
            trace and trace.event("upstream.attempt.error", path=path, attempt=attempt, duration_ms=int(elapsed * 1000), error_type="HTTPError", status=exc.code, error=message)
            if exc.code not in RETRYABLE_HTTP_STATUS or attempt >= max_attempts:
                raise ImageGenerationError(
                    _final_error_message(attempt, errors)
                ) from exc
        except UpstreamHttpStatusError as exc:
            elapsed = time.time() - started
            message = str(exc)
            errors.append(f"attempt {attempt} after {elapsed:.1f}s: {message}")
            trace and trace.event("upstream.attempt.error", path=path, attempt=attempt, duration_ms=int(elapsed * 1000), error_type="HTTPError", status=exc.status_code, error=message)
            if exc.status_code not in RETRYABLE_HTTP_STATUS or attempt >= max_attempts:
                raise ImageGenerationError(_final_error_message(attempt, errors)) from exc
        except ImageGenerationError:
            raise
        except Exception as exc:
            elapsed = time.time() - started
            message = str(exc)
            errors.append(f"attempt {attempt} after {elapsed:.1f}s: {type(exc).__name__}: {message}")
            trace and trace.event("upstream.attempt.error", path=path, attempt=attempt, duration_ms=int(elapsed * 1000), error_type=type(exc).__name__, error=message)
            if not _is_retryable_exception(exc) or attempt >= max_attempts:
                raise ImageGenerationError(_final_error_message(attempt, errors)) from exc

        delay = UPSTREAM_RETRY_DELAY_SECONDS * attempt
        print(
            f"[openai-image-upstream] retry attempt={attempt + 1}/{max_attempts} "
            f"path={path} last_error={errors[-1]} wait={delay:.1f}s"
        )
        trace and trace.event("upstream.retry.sleep", path=path, next_attempt=attempt + 1, wait_seconds=delay, last_error=errors[-1])
        time.sleep(delay)

    raise ImageGenerationError("OpenAI image upstream failed")


def _post_json(path: str, body: dict[str, object], trace: ImageTraceLogger | None = None) -> dict[str, object]:
    return _post_with_retries(path, lambda: _post_json_once(path, body, trace), trace)


def _post_multipart_once(
    path: str,
    fields: dict[str, object],
    files: Iterable[tuple[str, bytes, str, str]],
    trace: ImageTraceLogger | None = None,
) -> dict[str, object]:
    body, boundary = _encode_multipart_form(fields, files)
    file_count = len(files) if isinstance(files, list) else None
    trace and trace.event(
        "upstream.request",
        method="POST",
        path=path,
        response_format=fields.get("response_format"),
        files=file_count,
        client="urllib",
    )
    request = urllib.request.Request(
        _upstream_url(path),
        data=body,
        headers=_headers(f"multipart/form-data; boundary={boundary}"),
        method="POST",
    )
    with _urlopen(request) as response:
        payload = _read_json_response(response)
        status_code = getattr(response, "status", 200)
        content_length = getattr(response, "length", None)
    trace and trace.event("upstream.response", path=path, status=status_code, bytes=content_length)
    return _normalize_image_response(payload)


def _post_multipart(
    path: str,
    fields: dict[str, object],
    files: Iterable[tuple[str, bytes, str, str]],
    trace: ImageTraceLogger | None = None,
) -> dict[str, object]:
    cached_files = list(files)
    return _post_with_retries(path, lambda: _post_multipart_once(path, fields, cached_files, trace), trace)


def generate_openai_image_result(prompt: str, model: str, n: int, response_format: str = "b64_json", trace: ImageTraceLogger | None = None) -> dict[str, object]:
    if not is_openai_image_upstream_configured():
        raise ImageGenerationError("OpenAI image upstream is not configured")

    body: dict[str, object] = {
        "model": model or "gpt-image-2",
        "prompt": prompt,
        "n": n,
        "response_format": response_format or "b64_json",
    }
    trace and trace.event("openai.generate.start", model=body["model"], n=n, response_format=body["response_format"])
    return _post_json("/images/generations", body, trace)


def edit_openai_image_result(
    prompt: str,
    images: Iterable[tuple[bytes, str, str]],
    model: str,
    n: int,
    response_format: str = "b64_json",
    trace: ImageTraceLogger | None = None,
) -> dict[str, object]:
    if not is_openai_image_upstream_configured():
        raise ImageGenerationError("OpenAI image upstream is not configured")

    image_list = list(images)
    if not image_list:
        raise ImageGenerationError("image is required")

    fields: dict[str, object] = {
        "model": model or "gpt-image-2",
        "prompt": prompt,
        "n": n,
        "response_format": response_format or "b64_json",
    }
    files = [
        ("image", image_data, file_name or "image.png", mime_type or "image/png")
        for image_data, file_name, mime_type in image_list
    ]
    trace and trace.event("openai.edit.start", model=fields["model"], n=n, response_format=fields["response_format"], input_images=len(files))
    return _post_multipart("/images/edits", fields, files, trace)
