from __future__ import annotations

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from api.support import require_identity, resolve_image_base_url
from services.log_service import LoggedCall
from services.quota_service import openai_quota_error, reserve_image_quota
from services.user_service import UserServiceError
from services.protocol import (
    anthropic_v1_messages,
    openai_v1_chat_complete,
    openai_v1_image_edit,
    openai_v1_image_generations,
    openai_v1_models,
    openai_v1_response,
)


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    model: str = "gpt-image-2"
    n: int = Field(default=1, ge=1, le=4)
    size: str | None = None
    response_format: str = "b64_json"
    history_disabled: bool = True
    stream: bool | None = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str | None = None
    prompt: str | None = None
    n: int | None = None
    stream: bool | None = None
    modalities: list[str] | None = None
    messages: list[dict[str, object]] | None = None


class ResponseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str | None = None
    input: object | None = None
    tools: list[dict[str, object]] | None = None
    tool_choice: object | None = None
    stream: bool | None = None


class AnthropicMessageRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str | None = None
    messages: list[dict[str, object]] | None = None
    system: object | None = None
    stream: bool | None = None


def _requested_image_count(value: object) -> int:
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def _reserve_or_error(identity: dict[str, object], count: int, endpoint: str):
    try:
        return reserve_image_quota(identity, count, endpoint)
    except UserServiceError as exc:
        if exc.status_code == 429:
            return JSONResponse(status_code=429, content=openai_quota_error(exc))
        raise HTTPException(status_code=exc.status_code, detail={"error": exc.message}) from exc


def _is_image_chat_request(payload: dict[str, object]) -> bool:
    model = str(payload.get("model") or "").lower()
    if "image" in model:
        return True
    modalities = payload.get("modalities")
    if isinstance(modalities, list) and any(str(item).lower() == "image" for item in modalities):
        return True
    return False


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/v1/models")
    async def list_models(authorization: str | None = Header(default=None)):
        require_identity(authorization)
        try:
            return await run_in_threadpool(openai_v1_models.list_models)
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

    @router.post("/v1/images/generations")
    async def generate_images(
            body: ImageGenerationRequest,
            request: Request,
            authorization: str | None = Header(default=None),
    ):
        identity = require_identity(authorization)
        payload = body.model_dump(mode="python")
        payload["base_url"] = resolve_image_base_url(request)
        quota_reservation = _reserve_or_error(identity, body.n, "/v1/images/generations")
        if isinstance(quota_reservation, JSONResponse):
            return quota_reservation
        call = LoggedCall(identity, "/v1/images/generations", body.model, "文生图")
        return await call.run(openai_v1_image_generations.handle, payload, quota_reservation)

    @router.post("/v1/images/edits")
    async def edit_images(
            request: Request,
            authorization: str | None = Header(default=None),
            image: list[UploadFile] | None = File(default=None),
            image_list: list[UploadFile] | None = File(default=None, alias="image[]"),
            prompt: str = Form(...),
            model: str = Form(default="gpt-image-2"),
            n: int = Form(default=1),
            size: str | None = Form(default=None),
            response_format: str = Form(default="b64_json"),
            stream: bool | None = Form(default=None),
    ):
        identity = require_identity(authorization)
        if n < 1 or n > 4:
            raise HTTPException(status_code=400, detail={"error": "n must be between 1 and 4"})
        uploads = [*(image or []), *(image_list or [])]
        if not uploads:
            raise HTTPException(status_code=400, detail={"error": "image file is required"})
        images: list[tuple[bytes, str, str]] = []
        for upload in uploads:
            image_data = await upload.read()
            if not image_data:
                raise HTTPException(status_code=400, detail={"error": "image file is empty"})
            images.append((image_data, upload.filename or "image.png", upload.content_type or "image/png"))
        payload = {
            "prompt": prompt,
            "images": images,
            "model": model,
            "n": n,
            "size": size,
            "response_format": response_format,
            "stream": stream,
            "base_url": resolve_image_base_url(request),
        }
        quota_reservation = _reserve_or_error(identity, n, "/v1/images/edits")
        if isinstance(quota_reservation, JSONResponse):
            return quota_reservation
        call = LoggedCall(identity, "/v1/images/edits", model, "图生图")
        return await call.run(openai_v1_image_edit.handle, payload, quota_reservation)

    @router.post("/v1/chat/completions")
    async def create_chat_completion(body: ChatCompletionRequest, authorization: str | None = Header(default=None)):
        identity = require_identity(authorization)
        payload = body.model_dump(mode="python")
        model = str(payload.get("model") or "auto")
        quota_reservation = None
        summary = "文本生成"
        if _is_image_chat_request(payload):
            quota_reservation = _reserve_or_error(identity, _requested_image_count(payload.get("n")), "/v1/chat/completions")
            if isinstance(quota_reservation, JSONResponse):
                return quota_reservation
            summary = "图片生成"
        call = LoggedCall(identity, "/v1/chat/completions", model, "文本生成")
        call.summary = summary
        if quota_reservation is None:
            return await call.run(openai_v1_chat_complete.handle, payload)
        return await call.run(openai_v1_chat_complete.handle, payload, quota_reservation)

    @router.post("/v1/responses")
    async def create_response(body: ResponseCreateRequest, authorization: str | None = Header(default=None)):
        identity = require_identity(authorization)
        payload = body.model_dump(mode="python")
        model = str(payload.get("model") or "auto")
        call = LoggedCall(identity, "/v1/responses", model, "Responses")
        return await call.run(openai_v1_response.handle, payload)

    @router.post("/v1/messages")
    async def create_message(
            body: AnthropicMessageRequest,
            authorization: str | None = Header(default=None),
            x_api_key: str | None = Header(default=None, alias="x-api-key"),
            anthropic_version: str | None = Header(default=None, alias="anthropic-version"),
    ):
        identity = require_identity(authorization or (f"Bearer {x_api_key}" if x_api_key else None))
        payload = body.model_dump(mode="python")
        model = str(payload.get("model") or "auto")
        call = LoggedCall(identity, "/v1/messages", model, "Messages")
        return await call.run(anthropic_v1_messages.handle, payload, sse="anthropic")

    return router
