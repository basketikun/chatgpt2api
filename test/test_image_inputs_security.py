from __future__ import annotations

import socket
import unittest
from unittest import mock

from fastapi import HTTPException

from api import image_inputs
from utils import helper
from utils import remote_image


PUBLIC_DNS_RESULT = [
    (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443)),
]


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        chunks: list[bytes] | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {"content-type": "image/png"}
        self._chunks = chunks or []
        self.content = b"".join(self._chunks)
        self.read_count = 0
        self.closed = False

    def iter_content(self, chunk_size: int):
        self.chunk_size = chunk_size
        for chunk in self._chunks:
            self.read_count += 1
            yield chunk

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict]] = []
        self.closed = False

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return self.response

    def close(self) -> None:
        self.closed = True


class ImageInputSecurityTests(unittest.TestCase):
    def test_message_image_urls_use_the_shared_secure_downloader(self) -> None:
        with mock.patch.object(
            helper,
            "download_public_image",
            return_value=(b"image", "/image.png", "image/png"),
        ) as download:
            result = helper._decode_message_image_url("https://public.example/image.png")

        self.assertEqual(result, (b"image", "image/png"))
        download.assert_called_once_with(
            "https://public.example/image.png",
            max_bytes=helper.MAX_JSON_IMAGE_BYTES,
            timeout_seconds=helper.REMOTE_IMAGE_TIMEOUT_SECONDS,
            user_agent="chatgpt2api vision fetcher",
        )

    def test_loopback_literal_is_rejected_before_network_access(self) -> None:
        with mock.patch.object(remote_image.requests, "get") as legacy_get:
            with self.assertRaises(HTTPException) as raised:
                image_inputs._download_image_url("http://127.0.0.1/private.png")

        self.assertEqual(raised.exception.status_code, 400)
        legacy_get.assert_not_called()

    def test_hostname_resolving_to_private_address_is_rejected(self) -> None:
        private_dns = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.8", 80)),
        ]
        with (
            mock.patch.object(remote_image.socket, "getaddrinfo", return_value=private_dns),
            mock.patch.object(remote_image.requests, "get") as legacy_get,
        ):
            with self.assertRaises(HTTPException):
                image_inputs._download_image_url("http://internal.example/image.png")

        legacy_get.assert_not_called()

    def test_redirect_target_is_validated_before_following(self) -> None:
        response = FakeResponse(
            status_code=302,
            headers={"location": "http://127.0.0.1/private.png"},
        )
        session = FakeSession(response)
        with (
            mock.patch.object(remote_image.socket, "getaddrinfo", return_value=PUBLIC_DNS_RESULT),
            mock.patch.object(remote_image.requests, "Session", return_value=session),
            mock.patch.object(remote_image.requests, "get", return_value=response) as legacy_get,
        ):
            with self.assertRaises(HTTPException):
                image_inputs._download_image_url("https://public.example/image.png")

        legacy_get.assert_not_called()
        self.assertEqual(len(session.calls), 1)
        self.assertFalse(session.calls[0][1]["allow_redirects"])

    def test_streaming_limit_stops_before_the_remaining_body(self) -> None:
        response = FakeResponse(chunks=[b"12345", b"67890", b"not-read"])
        session = FakeSession(response)
        with (
            mock.patch.object(image_inputs, "MAX_IMAGE_REFERENCE_BYTES", 8),
            mock.patch.object(remote_image.socket, "getaddrinfo", return_value=PUBLIC_DNS_RESULT),
            mock.patch.object(remote_image.requests, "Session", return_value=session),
            mock.patch.object(remote_image.requests, "get", return_value=response) as legacy_get,
        ):
            with self.assertRaises(HTTPException):
                image_inputs._download_image_url("https://public.example/image.png")

        legacy_get.assert_not_called()
        self.assertEqual(response.read_count, 2)
        self.assertTrue(response.closed)
        self.assertTrue(session.closed)

    def test_public_image_is_streamed_with_redirects_disabled(self) -> None:
        response = FakeResponse(chunks=[b"png-", b"bytes"])
        session = FakeSession(response)
        with (
            mock.patch.object(remote_image.socket, "getaddrinfo", return_value=PUBLIC_DNS_RESULT),
            mock.patch.object(remote_image.requests, "Session", return_value=session) as session_factory,
            mock.patch.object(
                remote_image.proxy_settings,
                "build_session_kwargs",
                return_value={"verify": False},
            ) as session_kwargs,
            mock.patch.object(remote_image.requests, "get", return_value=response) as legacy_get,
        ):
            data, filename, mime_type = image_inputs._download_image_url(
                "https://public.example/path/photo.png"
            )

        self.assertEqual(data, b"png-bytes")
        self.assertEqual(filename, "photo.png")
        self.assertEqual(mime_type, "image/png")
        legacy_get.assert_not_called()
        session_kwargs.assert_called_once_with(resource=True, upstream=True, verify=True)
        session_factory.assert_called_once()
        self.assertIs(session_factory.call_args.kwargs["verify"], False)
        self.assertIn(remote_image.CurlOpt.RESOLVE, session_factory.call_args.kwargs["curl_options"])
        self.assertTrue(session.calls[0][1]["stream"])
        self.assertFalse(session.calls[0][1]["allow_redirects"])
        self.assertTrue(response.closed)
        self.assertTrue(session.closed)


if __name__ == "__main__":
    unittest.main()
