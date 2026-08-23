from __future__ import annotations

from typing import Any

from services.account_service import account_service
from services.openai_backend_api import OpenAIBackendAPI
from services.protocol.conversation import conversation_events


class ConversationBindingError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "CONVERSATION_BINDING_UNAVAILABLE",
        provider_binding_id: str = "",
        provider_account_identity: str = "",
        conversation_id: str = "",
        parent_message_id: str = "",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider_binding_id = provider_binding_id
        self.provider_account_identity = provider_account_identity
        self.conversation_id = conversation_id
        self.parent_message_id = parent_message_id


class ConversationBindingService:
    def complete_text(self, body: dict[str, Any]) -> dict[str, Any]:
        binding_id = str(body.get("provider_binding_id") or "").strip()
        account_identity = str(body.get("provider_account_identity") or "").strip()
        client_conversation_id = str(body.get("client_conversation_id") or "").strip()
        conversation_id = str(body.get("conversation_id") or "").strip()
        parent_message_id = str(body.get("parent_message_id") or "").strip()
        model = str(body.get("model") or "auto").strip() or "auto"
        image_model = str(body.get("image_model") or "gpt-image-2").strip() or "gpt-image-2"
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ConversationBindingError(
                "conversation messages are required",
                code="CONVERSATION_BINDING_CONTRACT_INVALID",
            )
        if not client_conversation_id:
            raise ConversationBindingError(
                "client_conversation_id is required",
                code="CONVERSATION_BINDING_CONTRACT_INVALID",
            )
        if binding_id:
            if not account_identity:
                raise ConversationBindingError(
                    "provider account identity is required for a bound account",
                    code="CONVERSATION_BINDING_CONTRACT_INVALID",
                )
            if bool(conversation_id) != bool(parent_message_id):
                raise ConversationBindingError(
                    "conversation continuation requires conversation_id and parent_message_id",
                    code="CONVERSATION_BINDING_CONTRACT_INVALID",
                )
            try:
                authoritative_identity = account_service.get_bound_account_identity(binding_id)
            except RuntimeError as exc:
                raise ConversationBindingError(str(exc)) from exc
            if authoritative_identity != account_identity:
                raise ConversationBindingError(
                    "provider account identity changed",
                    code="CONVERSATION_BINDING_MISMATCH",
                )
        elif conversation_id or parent_message_id:
            raise ConversationBindingError(
                "upstream cursor requires provider_binding_id",
                code="CONVERSATION_BINDING_CONTRACT_INVALID",
            )
        else:
            try:
                binding_id, account_identity, image_token = account_service.create_conversation_binding(
                    image_model=image_model
                )
                account_service.release_image_slot(image_token)
            except RuntimeError as exc:
                raise ConversationBindingError(str(exc)) from exc

        try:
            access_token = account_service.get_bound_text_access_token(
                binding_id,
                model=model,
            )
        except RuntimeError as exc:
            raise ConversationBindingError(str(exc)) from exc

        with account_service.conversation_binding_lock(binding_id, client_conversation_id):
            backend = OpenAIBackendAPI(access_token=access_token)
            try:
                parts: list[str] = []
                returned_conversation_id = ""
                for event in conversation_events(
                    backend,
                    messages=messages,
                    model=model,
                    thinking_effort=str(body.get("thinking_effort") or ""),
                    conversation_id=conversation_id,
                    parent_message_id=parent_message_id,
                ):
                    returned_conversation_id = str(
                        event.get("conversation_id") or returned_conversation_id
                    )
                    if event.get("type") == "conversation.delta":
                        delta = str(event.get("delta") or "")
                        if delta:
                            parts.append(delta)
                if not returned_conversation_id:
                    raise ConversationBindingError(
                        "upstream response has no conversation_id",
                        code="CONVERSATION_OUTCOME_UNKNOWN",
                        provider_binding_id=binding_id,
                        provider_account_identity=account_identity,
                    )
                if conversation_id and returned_conversation_id != conversation_id:
                    raise ConversationBindingError(
                        "upstream conversation identity changed",
                        code="CONVERSATION_BINDING_MISMATCH",
                        provider_binding_id=binding_id,
                        provider_account_identity=account_identity,
                        conversation_id=returned_conversation_id,
                    )
                content = "".join(parts).strip()
                if not content:
                    raise ConversationBindingError(
                        "upstream response was empty",
                        code="CONVERSATION_OUTCOME_UNKNOWN",
                        provider_binding_id=binding_id,
                        provider_account_identity=account_identity,
                        conversation_id=returned_conversation_id,
                    )
                next_parent_message_id = backend.get_conversation_parent_message_id(
                    returned_conversation_id
                )
                account_service.mark_text_used(access_token)
                return {
                    "content": content,
                    "provider_binding_id": binding_id,
                    "provider_account_identity": account_identity,
                    "conversation_id": returned_conversation_id,
                    "parent_message_id": next_parent_message_id,
                    "binding_status": "bound",
                }
            except ConversationBindingError:
                raise
            except Exception as exc:
                recovered_parent = ""
                if returned_conversation_id:
                    try:
                        recovered_parent = backend.get_conversation_parent_message_id(
                            returned_conversation_id
                        )
                    except Exception:
                        pass
                raise ConversationBindingError(
                    str(exc) or "upstream conversation outcome is unknown",
                    code="CONVERSATION_OUTCOME_UNKNOWN",
                    provider_binding_id=binding_id,
                    provider_account_identity=account_identity,
                    conversation_id=returned_conversation_id,
                    parent_message_id=recovered_parent,
                ) from exc
            finally:
                backend.close()


conversation_binding_service = ConversationBindingService()
