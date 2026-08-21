from __future__ import annotations

import unittest
from contextlib import nullcontext
from unittest import mock

from services.openai_backend_api import OpenAIBackendAPI
from services.conversation_binding_service import ConversationBindingService
from services.protocol.conversation import (
    ConversationRequest,
    ImageGenerationError,
    ImageOutput,
    _generate_bound_single_image,
)


class ConversationContinuationPayloadTests(unittest.TestCase):
    def test_continuation_sends_exact_conversation_and_parent(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)

        payload = backend._conversation_payload(
            [{"role": "user", "content": "continue"}],
            "auto",
            "UTC",
            conversation_id="conversation-1",
            parent_message_id="message-1",
        )

        self.assertEqual(payload["conversation_id"], "conversation-1")
        self.assertEqual(payload["parent_message_id"], "message-1")

    def test_partial_continuation_cursor_fails_closed(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)

        with self.assertRaisesRegex(RuntimeError, "requires parent_message_id"):
            backend._conversation_payload(
                [{"role": "user", "content": "continue"}],
                "auto",
                "UTC",
                conversation_id="conversation-1",
            )

    def test_bound_image_uses_exact_account_and_advances_parent(self) -> None:
        request = ConversationRequest(
            model="gpt-image-2",
            prompt="continue",
            provider_binding_id="cb-account-a",
            conversation_id="conversation-1",
            parent_message_id="message-1",
            retain_conversation=True,
        )

        class FakeBackend:
            def __init__(self, access_token: str) -> None:
                self.access_token = access_token
                self.progress_callback = None

            def get_conversation_parent_message_id(self, conversation_id: str) -> str:
                self.test_case.assertEqual(conversation_id, "conversation-1")
                return "message-2"

            def close(self) -> None:
                pass

        FakeBackend.test_case = self
        output = ImageOutput(
            kind="result",
            model="gpt-image-2",
            index=1,
            total=1,
            data=[{"url": "image.png"}],
            conversation_id="conversation-1",
        )
        with (
            mock.patch(
                "services.protocol.conversation.account_service.acquire_bound_image_access_token",
                return_value="token-a",
            ) as acquire,
            mock.patch(
                "services.protocol.conversation.account_service.get_available_access_token",
                side_effect=AssertionError("bound image must not round-robin"),
            ),
            mock.patch(
                "services.protocol.conversation.account_service.get_account",
                return_value={"email": "a@example.test"},
            ),
            mock.patch(
                "services.protocol.conversation.account_service.conversation_binding_lock",
                return_value=nullcontext(),
            ),
            mock.patch("services.protocol.conversation.account_service.mark_image_result"),
            mock.patch("services.protocol.conversation.account_service.release_image_slot"),
            mock.patch("services.protocol.conversation.OpenAIBackendAPI", FakeBackend),
            mock.patch(
                "services.protocol.conversation.stream_image_outputs",
                return_value=iter([output]),
            ),
        ):
            result = _generate_bound_single_image(request, 1, 1)

        acquire.assert_called_once_with("cb-account-a", image_model="gpt-image-2")
        self.assertEqual(result[0].provider_binding_id, "cb-account-a")
        self.assertEqual(result[0].conversation_id, "conversation-1")
        self.assertEqual(result[0].parent_message_id, "message-2")

    def test_unavailable_bound_account_fails_without_fallback(self) -> None:
        request = ConversationRequest(
            model="gpt-image-2",
            provider_binding_id="cb-account-a",
            conversation_id="conversation-1",
            parent_message_id="message-1",
            retain_conversation=True,
        )
        with (
            mock.patch(
                "services.protocol.conversation.account_service.acquire_bound_image_access_token",
                side_effect=RuntimeError("conversation binding unavailable"),
            ),
            mock.patch(
                "services.protocol.conversation.account_service.get_available_access_token",
                side_effect=AssertionError("must not fall back"),
            ),
        ):
            with self.assertRaises(ImageGenerationError) as captured:
                _generate_bound_single_image(request, 1, 1)

        self.assertEqual(captured.exception.code, "CONVERSATION_BINDING_UNAVAILABLE")

    def test_text_binding_is_created_once_then_reused(self) -> None:
        service = ConversationBindingService()

        class FakeBackend:
            def __init__(self, access_token: str) -> None:
                self.access_token = access_token

            def get_conversation_parent_message_id(self, conversation_id: str) -> str:
                return "message-2" if conversation_id == "conversation-1" else ""

            def close(self) -> None:
                pass

        events = [
            {
                "type": "conversation.delta",
                "delta": "ok",
                "conversation_id": "conversation-1",
            }
        ]
        with (
            mock.patch(
                "services.conversation_binding_service.account_service.create_conversation_binding",
                return_value=("cb-account-a", "token-a"),
            ) as create_binding,
            mock.patch(
                "services.conversation_binding_service.account_service.release_image_slot"
            ),
            mock.patch(
                "services.conversation_binding_service.account_service.get_bound_text_access_token",
                return_value="token-a",
            ) as bound_token,
            mock.patch(
                "services.conversation_binding_service.account_service.conversation_binding_lock",
                return_value=nullcontext(),
            ),
            mock.patch("services.conversation_binding_service.account_service.mark_text_used"),
            mock.patch("services.conversation_binding_service.OpenAIBackendAPI", FakeBackend),
            mock.patch(
                "services.conversation_binding_service.conversation_events",
                side_effect=(iter(events), iter(events)),
            ) as conversation_events,
        ):
            first = service.complete_text(
                {"messages": [{"role": "user", "content": "first"}]}
            )
            second = service.complete_text(
                {
                    "messages": [{"role": "user", "content": "second"}],
                    "provider_binding_id": first["provider_binding_id"],
                    "conversation_id": first["conversation_id"],
                    "parent_message_id": first["parent_message_id"],
                }
            )

        create_binding.assert_called_once()
        self.assertEqual(bound_token.call_count, 2)
        self.assertEqual(first["provider_binding_id"], "cb-account-a")
        self.assertEqual(second["provider_binding_id"], "cb-account-a")
        self.assertEqual(second["conversation_id"], "conversation-1")
        self.assertEqual(second["parent_message_id"], "message-2")
        second_call = conversation_events.call_args_list[1].kwargs
        self.assertEqual(second_call["conversation_id"], "conversation-1")
        self.assertEqual(second_call["parent_message_id"], "message-2")


if __name__ == "__main__":
    unittest.main()
