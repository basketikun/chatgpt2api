from __future__ import annotations

import time
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
    def __init__(self, _account_service) -> None:
        return None


class _FakeImageSessionService:
    last_create_session_call: dict[str, object] | None = None
    last_create_turn_call: dict[str, object] | None = None

    def __init__(self, _account_service) -> None:
        return None

    def create_session(self, prompt: str, model: str, images=None):
        normalized_images = list(images) if images else None
        type(self).last_create_session_call = {
            "prompt": prompt,
            "model": model,
            "images": normalized_images,
        }
        session = SimpleNamespace(session_id="session-1", updated_at=time.time())
        result = {
            "created": 123,
            "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt}],
            "upstream_conversation_id": "conversation-1",
            "upstream_parent_message_id": "message-1",
        }
        return session, result

    def create_turn(self, session_id: str, prompt: str, model: str, images=None):
        if session_id == "expired":
            raise api_module.ImageSessionExpiredError("连续对话会话已失效，请从当前结果图重新开始编辑")

        normalized_images = list(images) if images else None
        type(self).last_create_turn_call = {
            "session_id": session_id,
            "prompt": prompt,
            "model": model,
            "images": normalized_images,
        }
        session = SimpleNamespace(session_id=session_id, updated_at=time.time())
        result = {
            "created": 124,
            "data": [{"b64_json": "YmFy", "revised_prompt": prompt}],
            "upstream_conversation_id": "conversation-1",
            "upstream_parent_message_id": "message-2",
        }
        return session, result


class ImageSessionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeImageSessionService.last_create_session_call = None
        _FakeImageSessionService.last_create_turn_call = None
        self.auth_header = {"Authorization": "Bearer test-auth"}
        self.patches = [
            mock.patch.object(api_module, "ChatGPTService", _FakeChatGPTService),
            mock.patch.object(api_module, "ImageSessionService", _FakeImageSessionService),
            mock.patch.object(
                api_module,
                "config",
                SimpleNamespace(
                    auth_key="test-auth",
                    refresh_account_interval_minute=60,
                    base_url="http://localhost:8000",
                    images_dir=Path("test-images"),
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

    def test_requires_auth_for_session_creation(self) -> None:
        response = self.client.post("/api/image/sessions", data={"prompt": "test prompt"})

        self.assertEqual(response.status_code, 401)

    def test_create_session_accepts_repeated_image_field(self) -> None:
        response = self.client.post(
            "/api/image/sessions",
            headers=self.auth_header,
            data={"prompt": "test prompt", "model": "gpt-image-1"},
            files=[
                ("image", ("first.png", b"first", "image/png")),
                ("image", ("second.png", b"second", "image/png")),
            ],
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(_FakeImageSessionService.last_create_session_call)
        self.assertEqual(len(_FakeImageSessionService.last_create_session_call["images"]), 2)
        self.assertEqual(
            [item[1] for item in _FakeImageSessionService.last_create_session_call["images"]],
            ["first.png", "second.png"],
        )
        payload = response.json()
        self.assertEqual(payload["session_id"], "session-1")
        self.assertIn("expires_at", payload)
        self.assertNotIn("upstream_conversation_id", payload)

    def test_create_turn_accepts_repeated_image_bracket_field(self) -> None:
        response = self.client.post(
            "/api/image/sessions/session-1/turns",
            headers=self.auth_header,
            data={"prompt": "test prompt", "model": "gpt-image-1"},
            files=[
                ("image[]", ("first.png", b"first", "image/png")),
                ("image[]", ("second.png", b"second", "image/png")),
            ],
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(_FakeImageSessionService.last_create_turn_call)
        self.assertEqual(_FakeImageSessionService.last_create_turn_call["session_id"], "session-1")
        self.assertEqual(len(_FakeImageSessionService.last_create_turn_call["images"]), 2)

    def test_create_turn_returns_410_for_expired_session(self) -> None:
        response = self.client.post(
            "/api/image/sessions/expired/turns",
            headers=self.auth_header,
            data={"prompt": "test prompt", "model": "gpt-image-1"},
        )

        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.json()["detail"]["error"], "连续对话会话已失效，请从当前结果图重新开始编辑")


if __name__ == "__main__":
    unittest.main()
