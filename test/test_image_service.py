from __future__ import annotations

import pytest
from curl_cffi.requests.exceptions import RequestException

import services.image_service as image_service


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


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
