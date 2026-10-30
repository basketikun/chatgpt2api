"""Small ASGI request-body limits used before framework body parsing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


MAX_JSON_REQUEST_BYTES = 8 * 1024 * 1024
# Image-edit handlers enforce a 40 MiB aggregate file limit. Leave room for
# multipart boundaries and field headers while still bounding parser memory.
MAX_MULTIPART_REQUEST_BYTES = 48 * 1024 * 1024


class RequestBodyTooLarge(Exception):
    """Raised while an application is reading a request over its limit."""


def _headers(scope: dict[str, Any], name: bytes) -> list[bytes]:
    return [value for key, value in scope.get("headers", []) if key.lower() == name]


def _header(scope: dict[str, Any], name: bytes) -> bytes:
    values = _headers(scope, name)
    return values[0] if values else b""


def request_body_limit(scope: dict[str, Any]) -> int | None:
    """Return a limit for request bodies that would otherwise be unbounded.

    FastAPI reads a request body even when its media type is missing or not a
    JSON media type, then lets Pydantic reject the resulting value. Treat
    every non-multipart request as a bounded JSON-sized body so callers cannot
    bypass the pre-parser limit by changing ``Content-Type``.
    """
    if scope.get("type") != "http" or scope.get("method", "GET").upper() in {"GET", "HEAD", "OPTIONS"}:
        return None
    content_type = _header(scope, b"content-type").split(b";", 1)[0].strip().lower()
    if content_type == b"multipart/form-data":
        return MAX_MULTIPART_REQUEST_BYTES
    return MAX_JSON_REQUEST_BYTES


class RequestBodyLimitMiddleware:
    """Reject oversized bodies before Starlette/FastAPI parses them.

    The Content-Length check handles the common case without reading any body.
    The wrapped receive function also enforces the limit for chunked requests or
    clients that omit Content-Length.
    """

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:
        limit = request_body_limit(scope)
        if limit is None:
            await self.app(scope, receive, send)
            return

        content_lengths = _headers(scope, b"content-length")
        if len(content_lengths) > 1:
            await self._send_error(send, 400, "duplicate content-length")
            return
        content_length = content_lengths[0] if content_lengths else b""
        try:
            declared_length = int(content_length) if content_length else None
        except ValueError:
            await self._send_error(send, 400, "invalid content-length")
            return
        if declared_length is not None and declared_length < 0:
            await self._send_error(send, 400, "invalid content-length")
            return
        if declared_length is not None and declared_length > limit:
            await self._send_error(send, 413, "request body too large")
            return

        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestBodyTooLarge
            return message

        async def tracked_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyTooLarge:
            if not response_started:
                await self._send_error(send, 413, "request body too large")
            else:
                raise

    @staticmethod
    async def _send_error(send, status: int, detail: str) -> None:
        body = ("{\"detail\":\"" + detail + "\"}").encode("ascii")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"connection", b"close"),
            ],
        })
        await send({"type": "http.response.body", "body": body})
