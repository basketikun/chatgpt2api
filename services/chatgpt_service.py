from __future__ import annotations

from typing import Iterable

from fastapi import HTTPException

from services.account_service import AccountService
from services.image_service import ImageGenerationError, edit_image_result, generate_image_result, is_token_invalid_error
from services.utils import (
    build_chat_image_completion,
    extract_chat_image,
    extract_chat_prompt,
    extract_image_from_message_content,
    extract_response_prompt,
    has_response_image_generation_tool,
    is_image_chat_request,
    parse_image_count,
)


def _extract_response_image(input_value: object) -> tuple[bytes, str] | None:
    if isinstance(input_value, dict):
        return extract_image_from_message_content(input_value.get("content"))
    if not isinstance(input_value, list):
        return None

    latest_user_index = None

    for index in range(len(input_value) - 1, -1, -1):
        item = input_value[index]
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() == "input_image":
            import base64 as b64

            image_url = str(item.get("image_url") or "")
            if image_url.startswith("data:"):
                header, _, data = image_url.partition(",")
                mime = header.split(";")[0].removeprefix("data:")
                return b64.b64decode(data), mime or "image/png"

        role = str(item.get("role") or "").strip().lower()
        if role == "user":
            latest_user_index = index
            result = extract_image_from_message_content(item.get("content"))
            if result:
                return result
            break

        if str(item.get("type") or "").strip() == "input_text":
            latest_user_index = index
            break

    if latest_user_index is None:
        return None

    for index in range(latest_user_index - 1, -1, -1):
        item = input_value[index]
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role != "assistant":
            continue
        result = extract_image_from_message_content(item.get("content"))
        if result:
            return result
    return None


class ChatGPTService:
    def __init__(self, account_service: AccountService):
        self.account_service = account_service

    def generate_with_pool(self, prompt: str, model: str, n: int):
        created = None
        image_items: list[dict[str, object]] = []

        for index in range(1, n + 1):
            while True:
                try:
                    request_token = self.account_service.get_available_access_token()
                except RuntimeError as exc:
                    print(f"[image-generate] stop index={index}/{n} error={exc}")
                    break

                print(f"[image-generate] start pooled token={request_token[:12]}... model={model} index={index}/{n}")
                try:
                    result = generate_image_result(request_token, prompt, model)
                    account = self.account_service.mark_image_result(request_token, success=True)
                    if created is None:
                        created = result.get("created")
                    data = result.get("data")
                    if isinstance(data, list):
                        image_items.extend(item for item in data if isinstance(item, dict))
                    print(
                        f"[image-generate] success pooled token={request_token[:12]}... "
                        f"quota={account.get('quota') if account else 'unknown'} status={account.get('status') if account else 'unknown'}"
                    )
                    break
                except ImageGenerationError as exc:
                    account = self.account_service.mark_image_result(request_token, success=False)
                    message = str(exc)
                    print(
                        f"[image-generate] fail pooled token={request_token[:12]}... "
                        f"error={message} quota={account.get('quota') if account else 'unknown'} status={account.get('status') if account else 'unknown'}"
                    )
                    if is_token_invalid_error(message):
                        self.account_service.remove_token(request_token)
                        print(f"[image-generate] remove invalid token={request_token[:12]}...")
                        continue
                    break

        if not image_items:
            raise ImageGenerationError("image generation failed")

        return {
            "created": created,
            "data": image_items,
        }

    def edit_with_pool(
        self,
        prompt: str,
        images: Iterable[tuple[bytes, str, str]],
        model: str,
        n: int,
    ):
        created = None
        image_items: list[dict[str, object]] = []
        normalized_images = list(images)
        if not normalized_images:
            raise ImageGenerationError("image is required")

        for index in range(1, n + 1):
            while True:
                try:
                    request_token = self.account_service.get_available_access_token()
                except RuntimeError as exc:
                    print(f"[image-edit] stop index={index}/{n} error={exc}")
                    break

                print(
                    f"[image-edit] start pooled token={request_token[:12]}... "
                    f"model={model} index={index}/{n} images={len(normalized_images)}"
                )
                try:
                    result = edit_image_result(request_token, prompt, normalized_images, model)
                    account = self.account_service.mark_image_result(request_token, success=True)
                    if created is None:
                        created = result.get("created")
                    data = result.get("data")
                    if isinstance(data, list):
                        image_items.extend(item for item in data if isinstance(item, dict))
                    print(
                        f"[image-edit] success pooled token={request_token[:12]}... "
                        f"quota={account.get('quota') if account else 'unknown'} status={account.get('status') if account else 'unknown'}"
                    )
                    break
                except ImageGenerationError as exc:
                    account = self.account_service.mark_image_result(request_token, success=False)
                    message = str(exc)
                    print(
                        f"[image-edit] fail pooled token={request_token[:12]}... "
                        f"error={message} quota={account.get('quota') if account else 'unknown'} status={account.get('status') if account else 'unknown'}"
                    )
                    if is_token_invalid_error(message):
                        self.account_service.remove_token(request_token)
                        print(f"[image-edit] remove invalid token={request_token[:12]}...")
                        continue
                    break

        if not image_items:
            raise ImageGenerationError("image edit failed")

        return {
            "created": created,
            "data": image_items,
        }

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

        image_info = extract_chat_image(body)
        try:
            if image_info:
                image_data, mime_type = image_info
                image_result = self.edit_with_pool(prompt, [(image_data, "image.png", mime_type)], model, n)
            else:
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

        image_info = _extract_response_image(body.get("input"))
        model = str(body.get("model") or "gpt-5").strip() or "gpt-5"
        try:
            if image_info:
                image_data, mime_type = image_info
                image_result = self.edit_with_pool(prompt, [(image_data, "image.png", mime_type)], "gpt-image-1", 1)
            else:
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
