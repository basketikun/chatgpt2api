from __future__ import annotations

from fastapi import HTTPException

from services.account_service import AccountService
from services.cpa_service import cpa_service
from services.image_service import ImageGenerationError, generate_image_result, is_token_invalid_error
from services.utils import (
    build_chat_image_completion,
    extract_chat_prompt_and_images,
    extract_generation_images,
    extract_response_prompt_and_images,
    has_response_image_generation_tool,
    InputImage,
    is_image_chat_request,
    parse_image_count,
)


class ChatGPTService:
    def __init__(self, account_service: AccountService):
        self.account_service = account_service

    def _generate_single_image_with_local_pool(
        self,
        prompt: str,
        model: str,
        index: int,
        total: int,
        input_images: list[InputImage] | None = None,
    ) -> dict[str, object]:
        while True:
            try:
                request_token = self.account_service.get_available_access_token()
            except RuntimeError as exc:
                print(f"[image-generate] stop index={index}/{total} error={exc}")
                raise ImageGenerationError("image generation failed") from exc

            print(f"[image-generate] start pooled token={request_token[:12]}... model={model} index={index}/{total}")
            try:
                result = generate_image_result(request_token, prompt, model, input_images=input_images)
                account = self.account_service.mark_image_result(request_token, success=True)
                print(
                    f"[image-generate] success pooled token={request_token[:12]}... "
                    f"quota={account.get('quota') if account else 'unknown'} status={account.get('status') if account else 'unknown'}"
                )
                return result
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
                raise

    def _generate_single_image_with_cpa(
        self,
        prompt: str,
        model: str,
        index: int,
        total: int,
        input_images: list[InputImage] | None = None,
    ) -> dict[str, object]:
        attempted_tokens: set[str] = set()
        while True:
            request_token = cpa_service.get_token(excluded_tokens=attempted_tokens)
            if not request_token:
                raise ImageGenerationError("No access_token available from CPA")

            attempted_tokens.add(request_token)
            print(f"[image-generate] start cpa token={request_token[:12]}... model={model} index={index}/{total}")
            try:
                result = generate_image_result(request_token, prompt, model, input_images=input_images)
                print(f"[image-generate] success cpa token={request_token[:12]}...")
                return result
            except ImageGenerationError as exc:
                message = str(exc)
                print(f"[image-generate] fail cpa token={request_token[:12]}... error={message}")
                if is_token_invalid_error(message):
                    cpa_service.invalidate_cache()
                    continue
                raise

    def generate_with_pool(
        self,
        prompt: str,
        model: str,
        n: int,
        input_images: list[InputImage] | None = None,
    ):
        created = None
        image_items: list[dict[str, object]] = []

        for index in range(1, n + 1):
            if cpa_service.enabled:
                result = self._generate_single_image_with_cpa(prompt, model, index, n, input_images)
            else:
                result = self._generate_single_image_with_local_pool(prompt, model, index, n, input_images)

            if created is None:
                created = result.get("created")
            data = result.get("data")
            if isinstance(data, list):
                image_items.extend(item for item in data if isinstance(item, dict))

        if not image_items:
            raise ImageGenerationError("image generation failed")

        return {
            "created": created,
            "data": image_items,
        }

    def create_image_generation(self, body: dict[str, object], *, require_input_images: bool = False) -> dict[str, object]:
        prompt = str(body.get("prompt") or "").strip()
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "prompt is required"})

        model = str(body.get("model") or "gpt-image-1").strip() or "gpt-image-1"
        n = parse_image_count(body.get("n"))
        input_images = extract_generation_images(body, require_image=require_input_images)

        try:
            return self.generate_with_pool(prompt, model, n, input_images)
        except ImageGenerationError as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

    def create_image_completion(self, body: dict[str, object]) -> dict[str, object]:
        if not is_image_chat_request(body):
            raise HTTPException(
                status_code=400,
                detail={"error": "only image generation requests are supported on this endpoint"},
            )

        if bool(body.get("stream")):
            raise HTTPException(status_code=400, detail={"error": "stream is not supported for image generation"})

        requested_model = str(body.get("model") or "gpt-image-1").strip() or "gpt-image-1"
        generation_model = requested_model if requested_model in {"gpt-image-1", "gpt-image-2"} else "gpt-image-1"
        n = parse_image_count(body.get("n"))
        prompt, input_images = extract_chat_prompt_and_images(body)
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "prompt is required"})

        try:
            image_result = self.generate_with_pool(prompt, generation_model, n, input_images)
        except ImageGenerationError as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        return build_chat_image_completion(requested_model, prompt, image_result)

    def create_response(self, body: dict[str, object]) -> dict[str, object]:
        if bool(body.get("stream")):
            raise HTTPException(status_code=400, detail={"error": "stream is not supported"})

        if not has_response_image_generation_tool(body):
            raise HTTPException(
                status_code=400,
                detail={"error": "only image_generation tool requests are supported on this endpoint"},
            )

        prompt, input_images = extract_response_prompt_and_images(body.get("input"))
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "input text is required"})

        model = str(body.get("model") or "gpt-5").strip() or "gpt-5"
        try:
            image_result = self.generate_with_pool(prompt, "gpt-image-1", 1, input_images)
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
