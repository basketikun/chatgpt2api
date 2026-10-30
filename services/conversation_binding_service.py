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
    def read_text(self, body: dict[str, Any]) -> dict[str, Any]:
        """Read an already-issued cursor on its bound account; never send a message."""
        keys = ("provider_binding_id", "provider_account_identity", "client_conversation_id",
                "conversation_id", "parent_message_id")
        if any(not isinstance(body.get(key), str) or not body[key].strip() for key in keys):
            raise ConversationBindingError("original text cursor is required", code="CONVERSATION_BINDING_CONTRACT_INVALID")
        binding_id = body["provider_binding_id"]
        if account_service.get_bound_account_identity(binding_id) != body["provider_account_identity"]:
            raise ConversationBindingError("provider account identity changed", code="CONVERSATION_BINDING_MISMATCH")
        token = account_service.get_bound_text_access_token(binding_id, model="auto")
        with account_service.conversation_binding_lock(binding_id, body["client_conversation_id"]):
            backend = OpenAIBackendAPI(access_token=token)
            try:
                return self._read_text_result(backend, body)
            finally:
                backend.close()

    @staticmethod
    def _read_text_result(backend: OpenAIBackendAPI, cursor: dict[str, Any]) -> dict[str, Any]:
        document = backend._get_conversation(cursor["conversation_id"])
        if document.get("conversation_id", cursor["conversation_id"]) != cursor["conversation_id"]:
            raise ConversationBindingError("conversation identity changed", code="CONVERSATION_BINDING_MISMATCH")
        mapping = document.get("mapping") or {}
        current = str(document.get("current_node") or "")
        node_id = current
        visited: set[str] = set()
        while node_id and node_id not in visited:
            visited.add(node_id)
            node = mapping.get(node_id) or {}
            if node_id == cursor["parent_message_id"]:
                break
            # A later user turn is not the result of the original request.
            if (node.get("message") or {}).get("author", {}).get("role") == "user":
                raise ConversationBindingError("original turn was superseded", code="CONVERSATION_BINDING_MISMATCH")
            node_id = str(node.get("parent") or "")
        if node_id != cursor["parent_message_id"]:
            raise ConversationBindingError("original turn is not on the active branch", code="CONVERSATION_BINDING_MISMATCH")
        message = (mapping.get(current) or {}).get("message") or {}
        result = {key: cursor[key] for key in ("provider_binding_id", "provider_account_identity", "client_conversation_id", "conversation_id", "parent_message_id")}
        if (message.get("id") != current or message.get("author", {}).get("role") != "assistant"
                or message.get("status") != "finished_successfully" or message.get("end_turn") is not True
                or message.get("channel") not in (None, "final")):
            return {**result, "binding_status": "unknown", "status": "running"}
        content = message.get("content") or {}
        parts = content.get("parts")
        if content.get("content_type") != "text" or not isinstance(parts, list) or not parts or not all(isinstance(part, str) for part in parts):
            return {**result, "binding_status": "unknown", "status": "running"}
        text = "".join(parts).strip()
        if not text:
            return {**result, "binding_status": "unknown", "status": "running"}
        return {**result, "binding_status": "bound", "status": "succeeded", "parent_message_id": current, "content": text}

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
                        # A stream timeout may happen after the answer was saved.
                        # Read that turn once, never regenerate it or accept an old continuation answer.
                        if recovered_parent and not conversation_id:
                            recovered = self._read_text_result(backend, {
                                "provider_binding_id": binding_id,
                                "provider_account_identity": account_identity,
                                "client_conversation_id": client_conversation_id,
                                "conversation_id": returned_conversation_id,
                                "parent_message_id": recovered_parent,
                            })
                            if recovered.get("status") == "succeeded":
                                return recovered
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
