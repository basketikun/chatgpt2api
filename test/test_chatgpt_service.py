from __future__ import annotations

import services.chatgpt_service as chatgpt_service_module
from services.chatgpt_service import ChatGPTService
from services.image_service import ImageGenerationError


class _FakeAccountService:
    def __init__(self) -> None:
        self.mark_calls: list[tuple[str, bool]] = []

    def get_available_access_token(self) -> str:
        return "token-1234567890abcdef"

    def mark_image_result(self, access_token: str, success: bool):
        self.mark_calls.append((access_token, success))
        return {"quota": 7, "status": "active"}

    def get_account(self, access_token: str):
        return {"email": "user@example.com", "type": "Plus"}

    def remove_token(self, access_token: str) -> None:
        raise AssertionError("remove_token should not be called for successful requests")


def test_generate_single_image_with_local_pool_ignores_usage_log_write_failures(monkeypatch) -> None:
    account_service = _FakeAccountService()
    service = ChatGPTService(account_service)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        chatgpt_service_module,
        "generate_image_result",
        lambda access_token, prompt, model, input_images=None: {
            "created": 1,
            "upstream_model": "gpt-5-3",
            "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt}],
        },
    )

    def _failing_append(**kwargs):
        captured.update(kwargs)
        raise OSError("disk full")

    monkeypatch.setattr(chatgpt_service_module.usage_log_service, "append", _failing_append)

    result = service._generate_single_image_with_local_pool("生成电影海报", "gpt-image-2", 1, 1)

    assert result["created"] == 1
    assert account_service.mark_calls == [("token-1234567890abcdef", True)]
    assert captured["model"] == "gpt-image-2"
    assert captured["upstream_model"] == "gpt-5-3"
    assert captured["account_email"] == "user@example.com"


def test_generate_single_image_with_local_pool_logs_upstream_model_on_failures(monkeypatch) -> None:
    account_service = _FakeAccountService()
    service = ChatGPTService(account_service)
    captured: dict[str, object] = {}

    def _raise_generation_error(access_token, prompt, model, input_images=None):
        raise ImageGenerationError("upstream rejected request", upstream_model="gpt-5-3")

    monkeypatch.setattr(chatgpt_service_module, "generate_image_result", _raise_generation_error)
    monkeypatch.setattr(
        chatgpt_service_module.usage_log_service,
        "append",
        lambda **kwargs: captured.update(kwargs) or dict(kwargs),
    )

    try:
        service._generate_single_image_with_local_pool("生成电影海报", "gpt-image-2", 1, 1)
    except ImageGenerationError as exc:
        assert str(exc) == "upstream rejected request"
    else:
        raise AssertionError("expected ImageGenerationError")

    assert account_service.mark_calls == [("token-1234567890abcdef", False)]
    assert captured["success"] is False
    assert captured["upstream_model"] == "gpt-5-3"


def test_create_image_generation_forwards_url_response_format(monkeypatch) -> None:
    account_service = _FakeAccountService()
    service = ChatGPTService(account_service)
    captured: dict[str, object] = {}

    def _fake_generate_with_pool(prompt, model, n, input_images=None, response_format="b64_json"):
        captured["prompt"] = prompt
        captured["model"] = model
        captured["n"] = n
        captured["response_format"] = response_format
        return {
            "created": 1,
            "data": [{"url": "https://example.com/generated.png", "revised_prompt": prompt}],
        }

    monkeypatch.setattr(service, "generate_with_pool", _fake_generate_with_pool)

    result = service.create_image_generation(
        {
            "prompt": "生成一张电影海报",
            "model": "gpt-image-2",
            "response_format": "url",
        }
    )

    assert result["data"][0]["url"] == "https://example.com/generated.png"
    assert captured["response_format"] == "url"
