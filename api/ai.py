from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from api.support import require_identity, resolve_image_base_url
from utils.helper import normalize_json_edit_images, parse_image_count
from services.content_filter import check_request, request_text
from services.log_service import LoggedCall
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


class ImageEditJsonRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    prompt: str = Field(..., min_length=1)
    model: str | None = None
    n: object = 1
    size: str | None = None
    response_format: str | None = None
    stream: bool | None = None
    image: object | None = None
    images: object | None = None


def _is_json_request(request: Request) -> bool:
    return "application/json" in request.headers.get("content-type", "").lower()


async def _collect_multipart_edit_payload(
        request: Request,
) -> tuple[str, str, object, str | None, str, bool | None, list[tuple[bytes, str, str]]]:
    form = await request.form()
    prompt = str(form.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=422, detail={"error": "prompt is required"})
    model = str(form.get("model") or "gpt-image-2")
    n = form.get("n") or 1
    size_value = form.get("size")
    size = str(size_value) if isinstance(size_value, str) else None
    response_format = str(form.get("response_format") or "b64_json")
    stream_value = form.get("stream")
    stream = None
    if isinstance(stream_value, str):
        stream = str(stream_value).strip().lower() in {"1", "true", "yes", "on"}

    uploads = [
        upload
        for key in ("image", "image[]")
        for upload in form.getlist(key)
        if hasattr(upload, "read")
    ]
    if not uploads:
        raise HTTPException(status_code=400, detail={"error": "image file is required"})
    images: list[tuple[bytes, str, str]] = []
    for upload in uploads:
        image_data = await upload.read()
        if not image_data:
            raise HTTPException(status_code=400, detail={"error": "image file is empty"})
        images.append((image_data, upload.filename or "image.png", upload.content_type or "image/png"))
    return prompt, model, n, size, response_format, stream, images


async def _collect_json_edit_payload(
        request: Request,
) -> tuple[str, str, object, str | None, str, bool | None, list[tuple[bytes, str, str]]]:
    try:
        body = ImageEditJsonRequest.model_validate(await request.json())
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid image edit JSON request"}) from exc
    prompt = body.prompt
    model = body.model or "gpt-image-2"
    response_format = body.response_format or "b64_json"
    images = normalize_json_edit_images(image=body.image, images=body.images)
    return prompt, model, body.n, body.size, response_format, body.stream, images


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


async def filter_or_log(call: LoggedCall, text: str) -> None:
    try:
        await run_in_threadpool(check_request, text)
    except HTTPException as exc:
        call.log("调用失败", status="failed", error=str(exc.detail))
        raise


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
        call = LoggedCall(identity, "/v1/images/generations", body.model, "文生图", request_text=body.prompt)
        await filter_or_log(call, body.prompt)
        return await call.run(openai_v1_image_generations.handle, payload)

    @router.post("/v1/images/edits")
    async def edit_images(
            request: Request,
            authorization: str | None = Header(default=None),
    ):
        identity = require_identity(authorization)
        if _is_json_request(request):
            prompt, model, n, size, response_format, stream, images = await _collect_json_edit_payload(request)
        else:
            prompt, model, n, size, response_format, stream, images = await _collect_multipart_edit_payload(request)

        n = parse_image_count(n)
        call = LoggedCall(identity, "/v1/images/edits", model, "图生图", request_text=prompt)
        await filter_or_log(call, prompt)
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
        return await call.run(openai_v1_image_edit.handle, payload)

    @router.post("/v1/chat/completions")
    async def create_chat_completion(body: ChatCompletionRequest, authorization: str | None = Header(default=None)):
        identity = require_identity(authorization)
        payload = body.model_dump(mode="python")
        model = str(payload.get("model") or "auto")
        request_preview = request_text(payload.get("prompt"), payload.get("messages"))
        call = LoggedCall(identity, "/v1/chat/completions", model, "文本生成", request_text=request_preview)
        await filter_or_log(call, request_preview)
        return await call.run(openai_v1_chat_complete.handle, payload)

    @router.post("/v1/responses")
    async def create_response(body: ResponseCreateRequest, authorization: str | None = Header(default=None)):
        identity = require_identity(authorization)
        payload = body.model_dump(mode="python")
        model = str(payload.get("model") or "auto")
        request_preview = request_text(payload.get("input"), payload.get("instructions"))
        call = LoggedCall(identity, "/v1/responses", model, "Responses", request_text=request_preview)
        await filter_or_log(call, request_preview)
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
        request_preview = request_text(payload.get("system"), payload.get("messages"), payload.get("tools"))
        call = LoggedCall(identity, "/v1/messages", model, "Messages", request_text=request_preview)
        await filter_or_log(call, request_preview)
        return await call.run(anthropic_v1_messages.handle, payload, sse="anthropic")

    return router
