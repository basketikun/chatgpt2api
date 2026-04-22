from __future__ import annotations

from fastapi import HTTPException

from services.account_service import AccountService
from services.image_service import ImageGenerationError, edit_image_result, generate_image_result, is_token_invalid_error
from services.utils import (
    anonymize_token,
    build_chat_image_completion,
    extract_chat_prompt,
    extract_response_prompt,
    has_response_image_generation_tool,
    is_image_chat_request,
    parse_image_count,
)


class ChatGPTService:
    def __init__(self, account_service: AccountService):
        self.account_service = account_service

    def _run_with_pool(
        self,
        prompt: str,
        model: str,
        n: int,
        runner,
        *,
        preferred_account_id: str | None = None,
        upstream_conversation_id: str | None = None,
        upstream_parent_message_id: str | None = None,
    ):
        preferred_account_id = str(preferred_account_id or "").strip() or None
        upstream_conversation_id = str(upstream_conversation_id or "").strip() or None
        upstream_parent_message_id = str(upstream_parent_message_id or "").strip() or None
        if (preferred_account_id or upstream_conversation_id or upstream_parent_message_id) and n != 1:
            raise ImageGenerationError("continued image conversation only supports n=1")

        created = None
        image_items: list[dict[str, object]] = []
        response_context: dict[str, object] = {}

        if preferred_account_id or upstream_conversation_id or upstream_parent_message_id:
            if not preferred_account_id:
                raise ImageGenerationError("account_id is required for continued image conversation")
            request_token = self.account_service.get_access_token_by_public_id(preferred_account_id)
            if not request_token:
                raise ImageGenerationError("bound account for continued image conversation was not found")
            account = self.account_service.refresh_account_state(request_token)
            if not self.account_service._is_image_account_available(account or {}):
                raise ImageGenerationError("bound account for continued image conversation is unavailable")
            token_ref = anonymize_token(request_token)
            print(
                f"[image-generate] continue token={token_ref} model={model} "
                f"account_id={preferred_account_id} conversation_id={upstream_conversation_id or '-'}"
            )
            try:
                result = runner(
                    request_token,
                    upstream_conversation_id=upstream_conversation_id,
                    upstream_parent_message_id=upstream_parent_message_id,
                )
                account = self.account_service.mark_image_result(request_token, success=True)
            except ImageGenerationError as exc:
                account = self.account_service.mark_image_result(request_token, success=False)
                message = str(exc)
                print(
                    f"[image-generate] continue fail token={token_ref} "
                    f"error={message} quota={account.get('quota') if account else 'unknown'} "
                    f"status={account.get('status') if account else 'unknown'}"
                )
                if is_token_invalid_error(message):
                    self.account_service.remove_token(request_token)
                raise

            created = result.get("created")
            data = result.get("data")
            if isinstance(data, list):
                image_items.extend(item for item in data if isinstance(item, dict))
            response_context = {
                "account_id": self.account_service.get_public_id_by_access_token(request_token),
                "upstream_conversation_id": result.get("upstream_conversation_id"),
                "upstream_parent_message_id": result.get("upstream_parent_message_id"),
            }
            print(
                f"[image-generate] continue success token={token_ref} "
                f"quota={account.get('quota') if account else 'unknown'} status={account.get('status') if account else 'unknown'}"
            )
            if not image_items:
                raise ImageGenerationError("image generation failed")
            return {
                "created": created,
                "data": image_items,
                **response_context,
            }

        for index in range(1, n + 1):
            while True:
                try:
                    request_token = self.account_service.get_available_access_token()
                except RuntimeError as exc:
                    print(f"[image-generate] stop index={index}/{n} error={exc}")
                    break

                token_ref = anonymize_token(request_token)
                print(f"[image-generate] start pooled token={token_ref} model={model} index={index}/{n}")
                try:
                    result = runner(
                        request_token,
                        upstream_conversation_id=upstream_conversation_id,
                        upstream_parent_message_id=upstream_parent_message_id,
                    )
                    account = self.account_service.mark_image_result(request_token, success=True)
                    if created is None:
                        created = result.get("created")
                    data = result.get("data")
                    if isinstance(data, list):
                        image_items.extend(item for item in data if isinstance(item, dict))
                    if index == 1:
                        response_context = {
                            "account_id": self.account_service.get_public_id_by_access_token(request_token),
                            "upstream_conversation_id": result.get("upstream_conversation_id"),
                            "upstream_parent_message_id": result.get("upstream_parent_message_id"),
                        }
                    print(
                        f"[image-generate] success pooled token={token_ref} "
                        f"quota={account.get('quota') if account else 'unknown'} status={account.get('status') if account else 'unknown'}"
                    )
                    break
                except ImageGenerationError as exc:
                    account = self.account_service.mark_image_result(request_token, success=False)
                    message = str(exc)
                    print(
                        f"[image-generate] fail pooled token={token_ref} "
                        f"error={message} quota={account.get('quota') if account else 'unknown'} status={account.get('status') if account else 'unknown'}"
                    )
                    if is_token_invalid_error(message):
                        self.account_service.remove_token(request_token)
                        print(f"[image-generate] remove invalid token={token_ref}")
                        continue
                    break

        if not image_items:
            raise ImageGenerationError("image generation failed")

        return {
            "created": created,
            "data": image_items,
            **response_context,
        }

    def generate_with_pool(
        self,
        prompt: str,
        model: str,
        n: int,
        preferred_account_id: str | None = None,
        upstream_conversation_id: str | None = None,
        upstream_parent_message_id: str | None = None,
    ):
        return self._run_with_pool(
            prompt,
            model,
            n,
            lambda request_token, **context: generate_image_result(
                request_token,
                prompt,
                model,
                conversation_id=context.get("upstream_conversation_id"),
                parent_message_id=context.get("upstream_parent_message_id"),
            ),
            preferred_account_id=preferred_account_id,
            upstream_conversation_id=upstream_conversation_id,
            upstream_parent_message_id=upstream_parent_message_id,
        )

    def edit_with_pool(
        self,
        prompt: str,
        model: str,
        n: int,
        image_bytes: bytes,
        image_mime_type: str,
        image_filename: str | None,
        preferred_account_id: str | None = None,
        upstream_conversation_id: str | None = None,
        upstream_parent_message_id: str | None = None,
    ):
        return self._run_with_pool(
            prompt,
            model,
            n,
            lambda request_token, **context: edit_image_result(
                request_token,
                prompt,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                image_filename=image_filename,
                model=model,
                conversation_id=context.get("upstream_conversation_id"),
                parent_message_id=context.get("upstream_parent_message_id"),
            ),
            preferred_account_id=preferred_account_id,
            upstream_conversation_id=upstream_conversation_id,
            upstream_parent_message_id=upstream_parent_message_id,
        )

    def create_image_completion(self, body: dict[str, object]) -> dict[str, object]:
        if not is_image_chat_request(body):
            raise HTTPException(
                status_code=400,
                detail={"error": "only image generation requests are supported on this endpoint"},
            )

        if bool(body.get("stream")):
            raise HTTPException(status_code=400, detail={"error": "stream is not supported for image generation"})

        model = str(body.get("model") or "gpt-image-1").strip() or "gpt-image-1"
        n = parse_image_count(body.get("n"))
        prompt = extract_chat_prompt(body)
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "prompt is required"})

        try:
            image_result = self.generate_with_pool(prompt, model, n)
        except ImageGenerationError as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        return build_chat_image_completion(model, prompt, image_result)

    def create_response(self, body: dict[str, object]) -> dict[str, object]:
        if bool(body.get("stream")):
            raise HTTPException(status_code=400, detail={"error": "stream is not supported"})

        if not has_response_image_generation_tool(body):
            raise HTTPException(
                status_code=400,
                detail={"error": "only image_generation tool requests are supported on this endpoint"},
            )

        prompt = extract_response_prompt(body.get("input"))
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "input text is required"})

        model = str(body.get("model") or "gpt-5").strip() or "gpt-5"
        try:
            image_result = self.generate_with_pool(prompt, "gpt-image-1", 1)
        except ImageGenerationError as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        image_items = image_result.get("data") if isinstance(image_result.get("data"), list) else []
        output = []
        for item in image_items:
            if not isinstance(item, dict):
                continue
            b64_json = str(item.get("b64_json") or "").strip()
            if not b64_json:
                continue
            output.append(
                {
                    "id": f"ig_{len(output) + 1}",
                    "type": "image_generation_call",
                    "status": "completed",
                    "result": b64_json,
                    "revised_prompt": str(item.get("revised_prompt") or prompt).strip(),
                }
            )

        if not output:
            raise HTTPException(status_code=502, detail={"error": "image generation failed"})

        created = int(image_result.get("created") or 0)
        return {
            "id": f"resp_{created}",
            "object": "response",
            "created_at": created,
            "status": "completed",
            "error": None,
            "incomplete_details": None,
            "model": model,
            "output": output,
            "parallel_tool_calls": False,
        }
