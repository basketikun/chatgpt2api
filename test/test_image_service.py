from __future__ import annotations

import pytest
from curl_cffi.requests.exceptions import RequestException

import services.image_service as image_service


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeDownloadResponse:
    def __init__(self, *, ok: bool, status_code: int, content: bytes, headers: dict[str, str] | None = None) -> None:
        self.ok = ok
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


class _InterruptedSSEOpenResponse:
    ok = True
    text = ""
    status_code = 200

    def iter_lines(self):
        yield 'data: {"conversation_id":"conv_123","type":"message_marker"}'
        raise RequestException("Failed to perform, curl: (92) HTTP/2 stream 1 was not closed cleanly")


def test_generate_image_result_recovers_from_interrupted_sse(monkeypatch) -> None:
    session = _FakeSession()

    monkeypatch.setattr(image_service, "_new_session", lambda access_token: (session, {}))
    monkeypatch.setattr(image_service, "_resolve_upstream_model", lambda access_token, model: "gpt-5-3")
    monkeypatch.setattr(image_service, "_bootstrap", lambda session_obj, fp: "device-123")
    monkeypatch.setattr(image_service, "_chat_requirements", lambda session_obj, access_token, device_id: ("chat-token", {}))
    monkeypatch.setattr(image_service, "_send_conversation", lambda *args, **kwargs: _InterruptedSSEOpenResponse())
    monkeypatch.setattr(image_service, "_poll_image_ids", lambda *args, **kwargs: ["file_123"])
    monkeypatch.setattr(
        image_service,
        "_fetch_download_url",
        lambda *args, **kwargs: "https://example.com/generated.png",
    )
    monkeypatch.setattr(image_service, "_download_as_base64", lambda *args, **kwargs: "ZmFrZQ==")

    result = image_service.generate_image_result("token", "把这张图改成电影海报", "gpt-image-2")

    assert result["data"][0]["b64_json"] == "ZmFrZQ=="
    assert result["data"][0]["url"] == "https://example.com/generated.png"
    assert result["upstream_model"] == "gpt-5-3"
    assert session.closed is True


def test_generate_image_result_wraps_request_exception(monkeypatch) -> None:
    session = _FakeSession()

    monkeypatch.setattr(image_service, "_new_session", lambda access_token: (session, {}))
    monkeypatch.setattr(image_service, "_bootstrap", lambda session_obj, fp: "device-123")
    monkeypatch.setattr(image_service, "_chat_requirements", lambda session_obj, access_token, device_id: ("chat-token", {}))

    def _raise_request_exception(*args, **kwargs):
        raise RequestException("curl: (92) HTTP/2 stream 1 was not closed cleanly")

    monkeypatch.setattr(image_service, "_send_conversation", _raise_request_exception)

    with pytest.raises(image_service.ImageGenerationError, match="upstream request failed"):
        image_service.generate_image_result("token", "把这张图改成电影海报", "gpt-image-2")

    assert session.closed is True


def test_generate_image_result_skips_download_for_url_response_format(monkeypatch) -> None:
    session = _FakeSession()
    download_called = False

    monkeypatch.setattr(image_service, "_new_session", lambda access_token: (session, {}))
    monkeypatch.setattr(image_service, "_resolve_upstream_model", lambda access_token, model: "gpt-5-3")
    monkeypatch.setattr(image_service, "_bootstrap", lambda session_obj, fp: "device-123")
    monkeypatch.setattr(image_service, "_chat_requirements", lambda session_obj, access_token, device_id: ("chat-token", {}))
    monkeypatch.setattr(image_service, "_send_conversation", lambda *args, **kwargs: _InterruptedSSEOpenResponse())
    monkeypatch.setattr(image_service, "_poll_image_ids", lambda *args, **kwargs: ["file_123"])
    monkeypatch.setattr(
        image_service,
        "_fetch_download_url",
        lambda *args, **kwargs: "https://example.com/generated.png",
    )

    def _fail_if_downloaded(*args, **kwargs):
        nonlocal download_called
        download_called = True
        raise AssertionError("download should be skipped for url response_format")

    monkeypatch.setattr(image_service, "_download_as_base64", _fail_if_downloaded)

    result = image_service.generate_image_result(
        "token",
        "把这张图改成电影海报",
        "gpt-image-2",
        response_format="url",
    )

    assert result["data"][0]["url"] == "https://example.com/generated.png"
    assert result["data"][0]["b64_json"] == ""
    assert download_called is False
    assert session.closed is True


def test_download_as_base64_refreshes_download_url_after_404() -> None:
    responses = [
        _FakeDownloadResponse(
            ok=False,
            status_code=404,
            content=b"not found",
            headers={"content-type": "text/plain"},
        ),
        _FakeDownloadResponse(
            ok=True,
            status_code=200,
            content=b"PNGDATA",
            headers={"content-type": "image/png"},
        ),
    ]

    class _DownloadSession:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def get(self, url: str, timeout=None):
            self.urls.append(url)
            return responses.pop(0)

    session = _DownloadSession()
    refresh_calls: list[str] = []

    result = image_service._download_as_base64(
        session,
        "https://example.com/expired.png",
        refresh_download_url=lambda: refresh_calls.append("refresh") or "https://example.com/fresh.png",
    )

    assert result == "UE5HREFUQQ=="
    assert refresh_calls == ["refresh"]
    assert session.urls == [
        "https://example.com/expired.png",
        "https://example.com/fresh.png",
    ]
