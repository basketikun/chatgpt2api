from __future__ import annotations

import time

from fastapi import HTTPException

from services.account_service import AccountService
from services.cpa_service import cpa_service
from services.image_service import ImageGenerationError, generate_image_result, is_token_invalid_error
from services.usage_log_service import usage_log_service
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

    def _extract_preparsed_input_images(
        self,
        body: dict[str, object],
        *,
        require_input_images: bool = False,
    ) -> list[InputImage]:
        raw_images = body.get("_input_images")
        if isinstance(raw_images, list) and all(isinstance(item, InputImage) for item in raw_images):
            if require_input_images and not raw_images:
                raise HTTPException(status_code=400, detail={"error": "image is required"})
            return list(raw_images)
        return extract_generation_images(body, require_image=require_input_images)

    def _normalize_generation_response_format(self, raw_value: object) -> str:
        response_format = str(raw_value or "b64_json").strip().lower() or "b64_json"
        if response_format not in {"b64_json", "url"}:
            raise HTTPException(status_code=400, detail={"error": "response_format must be b64_json or url"})
        return response_format

    def _format_image_generation_result(
        self,
        image_result: dict[str, object],
        *,
        response_format: str,
    ) -> dict[str, object]:
        image_items = image_result.get("data")
        if not isinstance(image_items, list):
            return image_result

        formatted_items: list[dict[str, object]] = []
        for item in image_items:
            if not isinstance(item, dict):
                continue
            formatted_item: dict[str, object] = {}
            revised_prompt = str(item.get("revised_prompt") or "").strip()
            if revised_prompt:
                formatted_item["revised_prompt"] = revised_prompt

            if response_format == "url":
                url = str(item.get("url") or "").strip()
                if not url:
                    raise HTTPException(status_code=502, detail={"error": "image url is unavailable"})
                formatted_item["url"] = url
            else:
                b64_json = str(item.get("b64_json") or "").strip()
                if not b64_json:
                    raise HTTPException(status_code=502, detail={"error": "image base64 is unavailable"})
                formatted_item["b64_json"] = b64_json

            formatted_items.append(formatted_item)

        return {
            "created": image_result.get("created"),
            "data": formatted_items,
        }

    def _log_usage(
        self,
        *,
        access_token: str,
        source: str,
        model: str,
        prompt: str,
        success: bool,
        started_at: float,
        error: str | None,
        input_images: list[InputImage] | None,
        upstream_model: str | None = None,
    ) -> None:
        account = self.account_service.get_account(access_token) or {}
        try:
            usage_log_service.append(
                access_token=access_token,
                source=source,
                model=model,
                prompt=prompt,
                success=success,
                duration_ms=int((time.perf_counter() - started_at) * 1000),
                error=error,
                account_email=account.get("email"),
                account_type=account.get("type"),
                upstream_model=upstream_model,
                has_reference_image=bool(input_images),
            )
        except Exception as exc:
            print(
                f"[usage-log] append failed token={access_token[:12]}... "
                f"source={source} success={success} error={exc}"
            )

    def _generate_single_image_with_local_pool(
        self,
        prompt: str,
        model: str,
        index: int,
        total: int,
        input_images: list[InputImage] | None = None,
        *,
        response_format: str = "b64_json",
    ) -> dict[str, object]:
        while True:
            try:
                request_token = self.account_service.get_available_access_token()
            except RuntimeError as exc:
                print(f"[image-generate] stop index={index}/{total} error={exc}")
                raise ImageGenerationError("image generation failed") from exc

            print(f"[image-generate] start pooled token={request_token[:12]}... model={model} index={index}/{total}")
            started_at = time.perf_counter()
            try:
                if response_format == "b64_json":
                    result = generate_image_result(request_token, prompt, model, input_images=input_images)
                else:
                    result = generate_image_result(
                        request_token,
                        prompt,
                        model,
                        input_images=input_images,
                        response_format=response_format,
                    )
                upstream_model = str(result.get("upstream_model") or "").strip() or None
                account = self.account_service.mark_image_result(request_token, success=True)
                print(
                    f"[image-generate] success pooled token={request_token[:12]}... "
                    f"quota={account.get('quota') if account else 'unknown'} status={account.get('status') if account else 'unknown'}"
                )
                self._log_usage(
                    access_token=request_token,
                    source="pool",
                    model=model,
                    prompt=prompt,
                    success=True,
                    started_at=started_at,
                    error=None,
                    input_images=input_images,
                    upstream_model=upstream_model,
                )
                return result
            except ImageGenerationError as exc:
                account = self.account_service.mark_image_result(request_token, success=False)
                message = str(exc)
                upstream_model = str(getattr(exc, "upstream_model", "") or "").strip() or None
                print(
                    f"[image-generate] fail pooled token={request_token[:12]}... "
                    f"error={message} quota={account.get('quota') if account else 'unknown'} status={account.get('status') if account else 'unknown'}"
                )
                self._log_usage(
                    access_token=request_token,
                    source="pool",
                    model=model,
                    prompt=prompt,
                    success=False,
                    started_at=started_at,
                    error=message,
                    input_images=input_images,
                    upstream_model=upstream_model,
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
        *,
        response_format: str = "b64_json",
    ) -> dict[str, object]:
        attempted_tokens: set[str] = set()
        while True:
            request_token = cpa_service.get_token(excluded_tokens=attempted_tokens)
            if not request_token:
                raise ImageGenerationError("No access_token available from CPA")

            attempted_tokens.add(request_token)
            print(f"[image-generate] start cpa token={request_token[:12]}... model={model} index={index}/{total}")
            started_at = time.perf_counter()
            try:
                if response_format == "b64_json":
                    result = generate_image_result(request_token, prompt, model, input_images=input_images)
                else:
                    result = generate_image_result(
                        request_token,
                        prompt,
                        model,
                        input_images=input_images,
                        response_format=response_format,
                    )
                upstream_model = str(result.get("upstream_model") or "").strip() or None
                # Also update local account metrics if this token is tracked locally
                self.account_service.mark_image_result(request_token, success=True)
                print(f"[image-generate] success cpa token={request_token[:12]}...")
                self._log_usage(
                    access_token=request_token,
                    source="cpa",
                    model=model,
                    prompt=prompt,
                    success=True,
                    started_at=started_at,
                    error=None,
                    input_images=input_images,
                    upstream_model=upstream_model,
                )
                return result
            except ImageGenerationError as exc:
                self.account_service.mark_image_result(request_token, success=False)
                message = str(exc)
                upstream_model = str(getattr(exc, "upstream_model", "") or "").strip() or None
                print(f"[image-generate] fail cpa token={request_token[:12]}... error={message}")
                self._log_usage(
                    access_token=request_token,
                    source="cpa",
                    model=model,
                    prompt=prompt,
                    success=False,
                    started_at=started_at,
                    error=message,
                    input_images=input_images,
                    upstream_model=upstream_model,
                )
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
        *,
        response_format: str = "b64_json",
    ):
        created = None
        image_items: list[dict[str, object]] = []

        for index in range(1, n + 1):
            if cpa_service.enabled:
                result = self._generate_single_image_with_cpa(
                    prompt,
                    model,
                    index,
                    n,
                    input_images,
                    response_format=response_format,
                )
            else:
                result = self._generate_single_image_with_local_pool(
                    prompt,
                    model,
                    index,
                    n,
                    input_images,
                    response_format=response_format,
                )

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
        response_format = self._normalize_generation_response_format(body.get("response_format"))
        input_images = self._extract_preparsed_input_images(body, require_input_images=require_input_images)

        try:
            if response_format == "b64_json":
                image_result = self.generate_with_pool(prompt, model, n, input_images)
            else:
                image_result = self.generate_with_pool(
                    prompt,
                    model,
                    n,
                    input_images,
                    response_format=response_format,
                )
        except ImageGenerationError as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc
        return self._format_image_generation_result(image_result, response_format=response_format)

    def create_image_completion(self, body: dict[str, object]) -> dict[str, object]:
        if not is_image_chat_request(body):
            raise HTTPException(
                status_code=400,
                detail={"error": "only image generation requests are supported on this endpoint"},
            )

        # 为兼容现有 chat/completions 生图工作流，允许传 stream=true，
        # 但当前仍返回标准 JSON 响应，不做 SSE 分块。
        if "stream" in body:
            body["stream"] = False

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
