from __future__ import annotations

from fastapi.testclient import TestClient

import services.api as api_module
from services.api import create_app
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
