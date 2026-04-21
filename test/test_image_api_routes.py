from __future__ import annotations

import asyncio

from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.requests import Request

import services.api as api_module
from services.api import create_app, sanitize_validation_errors
from services.chatgpt_service import ChatGPTService
from services.config import config


PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+W9QAAAAASUVORK5CYII="
)


class _DummyThread:
    def join(self, timeout: float | None = None) -> None:
        return None


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {config.auth_key}"}


def test_images_edits_route_passes_reference_images(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_generate_with_pool(self, prompt, model, n, input_images=None):
        captured["prompt"] = prompt
        captured["model"] = model
        captured["n"] = n
        captured["input_images"] = input_images or []
        return {"created": 1, "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt}]}

    monkeypatch.setattr(api_module, "start_limited_account_watcher", lambda stop_event: _DummyThread())
    monkeypatch.setattr(ChatGPTService, "generate_with_pool", fake_generate_with_pool)

    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/images/edits",
            headers=_auth_headers(),
            json={
                "prompt": "把这张图改成电影质感",
                "model": "gpt-image-1",
                "images": [{"image_url": PNG_DATA_URL, "name": "source.png"}],
            },
        )

    assert response.status_code == 200
    assert captured["prompt"] == "把这张图改成电影质感"
    assert captured["model"] == "gpt-image-1"
    assert captured["n"] == 1
    assert len(captured["input_images"]) == 1


def test_images_edits_route_accepts_multipart_file(monkeypatch) -> None:
    captured: dict[str, object] = {}
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89"
        b"\x00\x00\x00\x0bIDATx\x9cc\xf8\xff\x1f\x00\x03\x03\x02\x00\xee\xfe[\xd4"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    def fake_generate_with_pool(self, prompt, model, n, input_images=None, response_format="b64_json"):
        captured["prompt"] = prompt
        captured["model"] = model
        captured["n"] = n
        captured["input_images"] = input_images or []
        captured["response_format"] = response_format
        return {"created": 5, "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt, "url": "https://example.com/image.png"}]}

    monkeypatch.setattr(api_module, "start_limited_account_watcher", lambda stop_event: _DummyThread())
    monkeypatch.setattr(ChatGPTService, "generate_with_pool", fake_generate_with_pool)

    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/images/edits",
            headers=_auth_headers(),
            data={
                "prompt": "保留主体，改成电影海报",
                "model": "gpt-image-2",
                "response_format": "url",
            },
            files=[("image", ("source.png", png_bytes, "image/png"))],
        )

    payload = response.json()
    assert response.status_code == 200
    assert captured["prompt"] == "保留主体，改成电影海报"
    assert captured["model"] == "gpt-image-2"
    assert captured["n"] == 1
    assert len(captured["input_images"]) == 1
    assert captured["response_format"] == "url"
    assert payload["data"][0]["url"] == "https://example.com/image.png"
    assert "b64_json" not in payload["data"][0]


def test_images_generation_route_honors_url_response_format(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_generate_with_pool(self, prompt, model, n, input_images=None, response_format="b64_json"):
        captured["response_format"] = response_format
        return {
            "created": 6,
            "data": [
                {
                    "b64_json": "ZmFrZQ==",
                    "revised_prompt": prompt,
                    "url": "https://example.com/generated.png",
                }
            ],
        }

    monkeypatch.setattr(api_module, "start_limited_account_watcher", lambda stop_event: _DummyThread())
    monkeypatch.setattr(ChatGPTService, "generate_with_pool", fake_generate_with_pool)

    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/images/generations",
            headers=_auth_headers(),
            json={
                "prompt": "生成一张电影海报",
                "model": "gpt-image-2",
                "response_format": "url",
            },
        )

    payload = response.json()
    assert response.status_code == 200
    assert captured["response_format"] == "url"
    assert payload["data"][0]["url"] == "https://example.com/generated.png"
    assert "b64_json" not in payload["data"][0]


def test_chat_completions_accepts_image_inputs(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_generate_with_pool(self, prompt, model, n, input_images=None):
        captured["prompt"] = prompt
        captured["model"] = model
        captured["input_images"] = input_images or []
        return {"created": 2, "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt}]}

    monkeypatch.setattr(api_module, "start_limited_account_watcher", lambda stop_event: _DummyThread())
    monkeypatch.setattr(ChatGPTService, "generate_with_pool", fake_generate_with_pool)

    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/chat/completions",
            headers=_auth_headers(),
            json={
                "model": "gpt-image-1",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "参考这张图，改成漫画"},
                            {"type": "image_url", "image_url": {"url": PNG_DATA_URL}},
                        ],
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert captured["prompt"] == "参考这张图，改成漫画"
    assert captured["model"] == "gpt-image-1"
    assert len(captured["input_images"]) == 1
    assert response.json()["choices"][0]["message"]["images"][0]["b64_json"] == "ZmFrZQ=="


def test_chat_completions_ignores_stream_flag_for_image_requests(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_generate_with_pool(self, prompt, model, n, input_images=None):
        captured["prompt"] = prompt
        captured["model"] = model
        captured["input_images"] = input_images or []
        return {
            "created": 7,
            "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt, "url": "https://example.com/stream.png"}],
        }

    monkeypatch.setattr(api_module, "start_limited_account_watcher", lambda stop_event: _DummyThread())
    monkeypatch.setattr(ChatGPTService, "generate_with_pool", fake_generate_with_pool)

    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/chat/completions",
            headers=_auth_headers(),
            json={
                "model": "gpt-image-2",
                "stream": True,
                "size": "3:4",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "保留主体，改成电影海报"},
                            {"type": "image_url", "image_url": {"url": PNG_DATA_URL}},
                        ],
                    }
                ],
            },
        )

    payload = response.json()
    assert response.status_code == 200
    assert captured["prompt"] == "保留主体，改成电影海报"
    assert captured["model"] == "gpt-image-2"
    assert len(captured["input_images"]) == 1
    assert payload["model"] == "gpt-image-2"
    assert payload["choices"][0]["message"]["images"][0]["b64_json"] == "ZmFrZQ=="


def test_chat_completions_accepts_non_image_model_when_message_has_image_inputs(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_generate_with_pool(self, prompt, model, n, input_images=None):
        captured["prompt"] = prompt
        captured["model"] = model
        captured["input_images"] = input_images or []
        return {"created": 4, "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt}]}

    monkeypatch.setattr(api_module, "start_limited_account_watcher", lambda stop_event: _DummyThread())
    monkeypatch.setattr(ChatGPTService, "generate_with_pool", fake_generate_with_pool)

    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/chat/completions",
            headers=_auth_headers(),
            json={
                "model": "gpt-4.1",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "按这张图的主体生成新海报"},
                            {"type": "image_url", "image_url": {"url": PNG_DATA_URL}},
                        ],
                    }
                ],
            },
        )

    payload = response.json()
    assert response.status_code == 200
    assert captured["prompt"] == "按这张图的主体生成新海报"
    assert captured["model"] == "gpt-image-1"
    assert len(captured["input_images"]) == 1
    assert payload["model"] == "gpt-4.1"
    assert payload["choices"][0]["message"]["images"][0]["b64_json"] == "ZmFrZQ=="


def test_responses_accepts_input_image(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_generate_with_pool(self, prompt, model, n, input_images=None):
        captured["prompt"] = prompt
        captured["model"] = model
        captured["input_images"] = input_images or []
        return {"created": 3, "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt}]}

    monkeypatch.setattr(api_module, "start_limited_account_watcher", lambda stop_event: _DummyThread())
    monkeypatch.setattr(ChatGPTService, "generate_with_pool", fake_generate_with_pool)

    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/responses",
            headers=_auth_headers(),
            json={
                "model": "gpt-5",
                "tools": [{"type": "image_generation"}],
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "让它更像海报"},
                            {"type": "input_image", "image_url": PNG_DATA_URL},
                        ],
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert captured["prompt"] == "让它更像海报"
    assert captured["model"] == "gpt-image-1"
    assert len(captured["input_images"]) == 1


def test_sanitize_validation_errors_replaces_bytes() -> None:
    errors = sanitize_validation_errors(
        [
            {
                "type": "missing",
                "loc": ["body", "image"],
                "msg": "Field required",
                "input": b"\xff\xd8\xffbinary",
            }
        ]
    )

    assert errors[0]["input"] == "<bytes len=9 hex=ffd8ff62696e617279>"


def test_request_validation_error_handler_handles_binary_input(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "start_limited_account_watcher", lambda stop_event: _DummyThread())
    app = create_app()

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/v1/images/edits",
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    request = Request(scope)
    exc = RequestValidationError(
        [
            {
                "type": "missing",
                "loc": ("body", "image"),
                "msg": "Field required",
                "input": b"\xff\xd8\xffbinary",
            }
        ]
    )

    response = None
    for exception_class, handler in app.exception_handlers.items():
        if exception_class is RequestValidationError:
            response = asyncio.run(handler(request, exc))
            break

    assert response is not None
    assert response.status_code == 422
    assert b"<bytes len=9 hex=ffd8ff62696e617279>" in response.body
