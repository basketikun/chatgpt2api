from __future__ import annotations

import asyncio
import unittest

from services.request_limits import (
    MAX_JSON_REQUEST_BYTES,
    MAX_MULTIPART_REQUEST_BYTES,
    RequestBodyLimitMiddleware,
)


class _Receive:
    def __init__(self, messages):
        self.messages = iter(messages)

    async def __call__(self):
        return next(self.messages)


class RequestBodyLimitTests(unittest.TestCase):
    def _run(self, scope, messages, app):
        sent = []

        async def send(message):
            sent.append(message)

        asyncio.run(RequestBodyLimitMiddleware(app)(scope, _Receive(messages), send))
        return sent

    def test_declared_json_body_is_rejected_before_app(self):
        called = False

        async def app(scope, receive, send):
            nonlocal called
            called = True

        sent = self._run(
            {
                "type": "http",
                "method": "POST",
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(MAX_JSON_REQUEST_BYTES + 1).encode()),
                ],
            },
            [],
            app,
        )

        self.assertFalse(called)
        self.assertEqual(sent[0]["status"], 413)

    def test_duplicate_content_length_is_rejected(self):
        called = False

        async def app(scope, receive, send):
            nonlocal called
            called = True

        sent = self._run(
            {
                "type": "http",
                "method": "POST",
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", b"1"),
                    (b"content-length", b"1"),
                ],
            },
            [],
            app,
        )

        self.assertFalse(called)
        self.assertEqual(sent[0]["status"], 400)

    def test_negative_content_length_is_rejected(self):
        sent = self._run(
            {
                "type": "http",
                "method": "POST",
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", b"-1"),
                ],
            },
            [],
            lambda scope, receive, send: None,
        )
        self.assertEqual(sent[0]["status"], 400)

    def test_unknown_content_type_is_rejected_while_reading(self):
        async def app(scope, receive, send):
            while True:
                message = await receive()
                if not message.get("more_body"):
                    break

        sent = self._run(
            {"type": "http", "method": "POST", "headers": [(b"content-type", b"text/plain")]},
            [
                {"type": "http.request", "body": b"x" * MAX_JSON_REQUEST_BYTES, "more_body": True},
                {"type": "http.request", "body": b"x", "more_body": False},
            ],
            app,
        )

        self.assertEqual(sent[0]["status"], 413)

    def test_chunked_json_body_is_rejected_while_reading(self):
        async def app(scope, receive, send):
            while True:
                message = await receive()
                if not message.get("more_body"):
                    break

        sent = self._run(
            {"type": "http", "method": "POST", "headers": [(b"content-type", b"application/json")]},
            [
                {"type": "http.request", "body": b"x" * MAX_JSON_REQUEST_BYTES, "more_body": True},
                {"type": "http.request", "body": b"x", "more_body": False},
            ],
            app,
        )

        self.assertEqual(sent[0]["status"], 413)

    def test_multipart_limit_is_larger_than_image_file_aggregate_limit(self):
        self.assertGreater(MAX_MULTIPART_REQUEST_BYTES, 40 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
