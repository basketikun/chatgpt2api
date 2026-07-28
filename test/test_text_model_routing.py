from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from services.account_service import AccountService
from services.model_service import ModelRoute, ModelUnavailableError
from services.protocol import (
    anthropic_v1_messages,
    conversation,
    openai_v1_chat_complete,
    openai_v1_response,
)
from services.storage.json_storage import JSONStorageBackend


class TextAccountRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.service = AccountService(
            JSONStorageBackend(Path(self.temp_dir.name) / "accounts.json")
        )
        self.service.add_account_items(
            [
                {"access_token": "free", "type": "free", "status": "正常"},
                {"access_token": "plus", "type": "Plus", "status": "正常"},
                {"access_token": "pro", "type": "Pro", "status": "正常"},
                {"access_token": "pro-disabled", "type": "Pro", "status": "禁用"},
            ]
        )
        self.service.refresh_access_token = lambda token, **_kwargs: token

    def test_explicit_model_selects_only_advertising_account(self) -> None:
        self.service.add_account_items([
            {"access_token": "pro-alt", "type": "Pro", "status": "正常"},
        ])
        route = ModelRoute(access_tokens=frozenset({"pro"}), allow_anonymous=False)
        with mock.patch(
            "services.model_service.model_catalog_service.route_for_model",
            return_value=route,
        ):
            token = self.service.get_text_access_token(model="pro-only")

        self.assertEqual(token, "pro")

    def test_auto_model_keeps_existing_unfiltered_rotation(self) -> None:
        with mock.patch(
            "services.model_service.model_catalog_service.route_for_model",
            side_effect=AssertionError("auto must not load the model catalog"),
        ):
            tokens = {
                self.service.get_text_access_token(model="auto"),
                self.service.get_text_access_token(model="auto"),
                self.service.get_text_access_token(model="auto"),
            }

        self.assertEqual(tokens, {"free", "plus", "pro"})

    def test_anonymous_model_uses_anonymous_backend(self) -> None:
        route = ModelRoute(access_tokens=frozenset(), allow_anonymous=True)
        with mock.patch(
            "services.model_service.model_catalog_service.route_for_model",
            return_value=route,
        ):
            token = self.service.get_text_access_token(model="anon-only")

        self.assertEqual(token, "")

    def test_model_without_eligible_account_fails_closed(self) -> None:
        route = ModelRoute(access_tokens=frozenset(), allow_anonymous=False)
        with mock.patch(
            "services.model_service.model_catalog_service.route_for_model",
            return_value=route,
        ), self.assertRaisesRegex(ModelUnavailableError, "team-only"):
            self.service.get_text_access_token(model="team-only")


class TextProtocolRoutingTests(unittest.TestCase):
    def test_text_backend_passes_requested_model_to_account_selector(self) -> None:
        backend = mock.Mock()
        with (
            mock.patch.object(
                conversation.account_service,
                "get_text_access_token",
                return_value="pro",
            ) as selector,
            mock.patch.object(conversation, "OpenAIBackendAPI", return_value=backend),
        ):
            result = conversation.text_backend("pro-only")

        self.assertIs(result, backend)
        selector.assert_called_once_with(model="pro-only")

    def test_chat_completions_passes_requested_model_to_text_backend(self) -> None:
        body = {
            "model": "pro-chat",
            "messages": [{"role": "user", "content": "route chat"}],
        }
        with (
            mock.patch.object(openai_v1_chat_complete, "text_backend", return_value=object()) as backend,
            mock.patch.object(openai_v1_chat_complete, "collect_text", return_value="ok"),
        ):
            openai_v1_chat_complete.handle(body)

        backend.assert_called_once_with("pro-chat")

    def test_responses_passes_requested_model_to_text_backend(self) -> None:
        body = {"model": "pro-response", "input": "route response"}
        with (
            mock.patch.object(openai_v1_response, "text_backend", return_value=object()) as backend,
            mock.patch.object(openai_v1_response, "stream_text_deltas", return_value=iter(["ok"])),
        ):
            openai_v1_response.handle(body)

        backend.assert_called_once_with("pro-response")

    def test_anthropic_messages_passes_requested_model_to_account_selector(self) -> None:
        with (
            mock.patch.object(
                anthropic_v1_messages.account_service,
                "get_text_access_token",
                return_value="pro",
            ) as selector,
            mock.patch.object(anthropic_v1_messages, "OpenAIBackendAPI"),
        ):
            request = anthropic_v1_messages.message_request({
                "model": "pro-anthropic",
                "messages": [{"role": "user", "content": "route anthropic"}],
            })

        self.assertEqual(request.model, "pro-anthropic")
        selector.assert_called_once_with(model="pro-anthropic")

    def test_invalid_token_retry_keeps_requested_model_filter(self) -> None:
        initial_backend = SimpleNamespace(access_token="bad")
        request = conversation.ConversationRequest(
            model="pro-only",
            messages=[{"role": "user", "content": "hello"}],
        )

        def fake_events(backend, **_kwargs):
            if backend.access_token == "bad":
                raise RuntimeError("token_invalidated")
            yield {"type": "conversation.delta", "delta": "ok"}

        with (
            mock.patch.object(conversation, "OpenAIBackendAPI", side_effect=lambda access_token: SimpleNamespace(
                access_token=access_token,
                close=lambda: None,
            )),
            mock.patch.object(conversation, "conversation_events", side_effect=fake_events),
            mock.patch.object(
                conversation.account_service,
                "refresh_access_token",
                return_value="bad",
            ),
            mock.patch.object(conversation.account_service, "remove_invalid_token"),
            mock.patch.object(
                conversation.account_service,
                "get_text_access_token",
                return_value="pro",
            ) as selector,
            mock.patch.object(conversation.account_service, "mark_text_used"),
        ):
            result = list(conversation.stream_text_deltas(initial_backend, request))

        self.assertEqual(result, ["ok"])
        selector.assert_called_once_with(
            excluded_tokens={"bad"},
            model="pro-only",
        )

    def test_invalid_token_can_fall_back_to_anonymous_backend(self) -> None:
        initial_backend = SimpleNamespace(access_token="bad")
        request = conversation.ConversationRequest(
            model="shared-model",
            messages=[{"role": "user", "content": "hello"}],
        )
        attempted: list[str] = []

        def backend_factory(access_token: str):
            attempted.append(access_token)
            return SimpleNamespace(access_token=access_token, close=lambda: None)

        def fake_events(backend, **_kwargs):
            if backend.access_token == "bad":
                raise RuntimeError("token_invalidated")
            yield {"type": "conversation.delta", "delta": "anonymous-ok"}

        with (
            mock.patch.object(conversation, "OpenAIBackendAPI", side_effect=backend_factory),
            mock.patch.object(conversation, "conversation_events", side_effect=fake_events),
            mock.patch.object(conversation.account_service, "refresh_access_token", return_value="bad"),
            mock.patch.object(conversation.account_service, "remove_invalid_token"),
            mock.patch.object(conversation.account_service, "get_text_access_token", return_value=""),
            mock.patch.object(conversation.account_service, "mark_text_used"),
        ):
            result = list(conversation.stream_text_deltas(initial_backend, request))

        self.assertEqual(result, ["anonymous-ok"])
        self.assertEqual(attempted, ["bad", ""])


if __name__ == "__main__":
    unittest.main()
