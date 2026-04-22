import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

from services import api as api_module


class _FakeThread:
    def join(self, timeout: float | None = None) -> None:
        return None


class _FakeChatGPTService:
    last_call: dict[str, object] | None = None

    def __init__(self, _account_service) -> None:
        return None

    def edit_with_pool(
        self,
        prompt: str,
        images,
        model: str,
        n: int,
        response_format: str = "b64_json",
        base_url: str | None = None,
    ):
        normalized_images = list(images)
        type(self).last_call = {
            "prompt": prompt,
            "images": normalized_images,
            "model": model,
            "n": n,
            "response_format": response_format,
            "base_url": base_url,
        }
        return {
            "created": 123,
            "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt}],
        }


class ImageEditsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeChatGPTService.last_call = None
        self.auth_header = {"Authorization": "Bearer test-auth"}
        self.patches = [
            mock.patch.object(api_module, "ChatGPTService", _FakeChatGPTService),
            mock.patch.object(
                api_module,
                "config",
                SimpleNamespace(
                    auth_key="test-auth",
                    refresh_account_interval_minute=60,
                    images_dir=Path("test-images"),
                    base_url="http://localhost:8000",
                ),
            ),
            mock.patch.object(api_module, "start_limited_account_watcher", lambda _stop_event: _FakeThread()),
        ]
        for patcher in self.patches:
            patcher.start()
        self.addCleanup(self._cleanup_patches)
        self.client = TestClient(api_module.create_app())
        self.addCleanup(self.client.close)

    def _cleanup_patches(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()

    def test_accepts_repeated_image_field(self) -> None:
        response = self.client.post(
            "/v1/images/edits",
            headers=self.auth_header,
            data={"prompt": "test prompt", "model": "gpt-image-1", "n": "1"},
            files=[
                ("image", ("first.png", b"first", "image/png")),
                ("image", ("second.png", b"second", "image/png")),
            ],
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(_FakeChatGPTService.last_call)
        self.assertEqual(len(_FakeChatGPTService.last_call["images"]), 2)
        self.assertEqual(
            [item[1] for item in _FakeChatGPTService.last_call["images"]],
            ["first.png", "second.png"],
        )

    def test_accepts_repeated_image_bracket_field(self) -> None:
        response = self.client.post(
            "/v1/images/edits",
            headers=self.auth_header,
            data={"prompt": "test prompt", "model": "gpt-image-1", "n": "1"},
            files=[
                ("image[]", ("first.png", b"first", "image/png")),
                ("image[]", ("second.png", b"second", "image/png")),
            ],
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(_FakeChatGPTService.last_call)
        self.assertEqual(len(_FakeChatGPTService.last_call["images"]), 2)
        self.assertEqual(
            [item[1] for item in _FakeChatGPTService.last_call["images"]],
            ["first.png", "second.png"],
        )


if __name__ == "__main__":
    unittest.main()
