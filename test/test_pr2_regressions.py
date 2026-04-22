from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from services.account_service import AccountService
from services.image_service import _resolve_conversation_state


def build_image_payload(*, current_node: str = "") -> dict[str, object]:
    return {
        "current_node": current_node,
        "mapping": {
            "tool-node": {
                "message": {
                    "author": {"role": "tool"},
                    "metadata": {"async_task_type": "image_gen"},
                    "content": {
                        "content_type": "multimodal_text",
                        "parts": [{"asset_pointer": "file-service://file-1"}],
                    },
                }
            }
        },
    }


class AccountAvailabilityTests(unittest.TestCase):
    def test_unknown_quota_still_respects_throttled_status(self) -> None:
        self.assertFalse(
            AccountService._is_image_account_available(
                {"status": "限流", "image_quota_unknown": True, "quota": 0}
            )
        )
        self.assertTrue(
            AccountService._is_image_account_available(
                {"status": "正常", "image_quota_unknown": True, "quota": 0}
            )
        )


class ResolveConversationStateTests(unittest.TestCase):
    @patch("services.image_service.time.sleep", return_value=None)
    @patch("services.image_service._fetch_conversation_payload", return_value=build_image_payload())
    def test_returns_file_ids_immediately_when_required(self, fetch_payload: Mock, _: Mock) -> None:
        state = _resolve_conversation_state(Mock(), "token", "device", "conversation", require_file_ids=True)

        self.assertEqual(state["current_node"], "")
        self.assertEqual(state["file_ids"], ["file-1"])
        fetch_payload.assert_called_once()

    @patch("services.image_service.time.sleep", return_value=None)
    @patch("services.image_service._fetch_conversation_payload", return_value=build_image_payload())
    def test_returns_file_ids_immediately_without_waiting_for_current_node(self, fetch_payload: Mock, _: Mock) -> None:
        state = _resolve_conversation_state(Mock(), "token", "device", "conversation", require_file_ids=False)

        self.assertEqual(state["current_node"], "")
        self.assertEqual(state["file_ids"], ["file-1"])
        fetch_payload.assert_called_once()


if __name__ == "__main__":
    unittest.main()
