from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from threading import Event, Thread
import time

from fastapi import APIRouter, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from services.account_service import account_service
from services.chatgpt_service import ChatGPTService
from services.config import config

from services.image_service import ImageGenerationError
from services.image_file_store import save_image_result_files
from services.image_prompt_optimizer import optimize_image_prompt
from services.image_trace_logger import start_image_trace
from services.openai_image_service import (
    edit_openai_image_result,
    generate_openai_image_result,
    is_openai_image_upstream_configured,
)
from services.version import get_app_version

BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIST_DIR = BASE_DIR / "web_dist"


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    original_prompt: str | None = None
    model: str = "gpt-image-2"
    n: int = Field(default=1, ge=1, le=4)
    response_format: str = "b64_json"
    history_disabled: bool = True


class ImagePromptOptimizeRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    mode: str = "generate"


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


def build_model_item(model_id: str) -> dict[str, object]:
    return {
        "id": model_id,
        "object": "model",
        "created": 0,
        "owned_by": "chatgpt2api",
    }


def extract_bearer_token(authorization: str | None) -> str:
    scheme, _, value = str(authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return ""
    return value.strip()


def _saved_image_summary(result: dict[str, object]) -> list[dict[str, object]]:
    data = result.get("data")
    if not isinstance(data, list):
        return []
    saved: list[dict[str, object]] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue
        if item.get("file_name") or item.get("file_path"):
            saved.append(
                {
                    "index": index,
                    "file_name": item.get("file_name"),
                    "file_path": item.get("file_path"),
                    "file_size": item.get("file_size"),
                }
            )
    return saved


def get_runtime_summary() -> dict[str, object]:
    accounts = account_service.list_accounts()
    available_quota = sum(
        max(0, int(account.get("quota") or 0))
        for account in accounts
        if account.get("status") != "禁用"
    )
    return {
        "available_quota": available_quota,
        "image_upstream": "openai" if is_openai_image_upstream_configured() else "chatgpt_pool",
    }


def require_auth_key(authorization: str | None) -> None:
    if extract_bearer_token(authorization) != str(config.auth_key or "").strip():
        raise HTTPException(status_code=401, detail={"error": "authorization is invalid"})


def start_limited_account_watcher(stop_event: Event) -> Thread:
    interval_seconds = config.refresh_account_interval_minute * 60

    def worker() -> None:
        while not stop_event.is_set():
            try:
                limited_tokens = account_service.list_limited_tokens()
                if limited_tokens:
                    print(f"[account-limited-watcher] checking {len(limited_tokens)} limited accounts")
                    account_service.refresh_accounts(limited_tokens)
            except Exception as exc:
                print(f"[account-limited-watcher] fail {exc}")
            stop_event.wait(interval_seconds)

    thread = Thread(target=worker, name="limited-account-watcher", daemon=True)
    thread.start()
    return thread


def resolve_web_asset(requested_path: str) -> Path | None:
    if not WEB_DIST_DIR.exists():
        return None

    clean_path = requested_path.strip("/")
    if not clean_path:
        candidates = [WEB_DIST_DIR / "index.html"]
    else:
        relative_path = Path(clean_path)
        candidates = [
            WEB_DIST_DIR / relative_path,
            WEB_DIST_DIR / relative_path / "index.html",
            WEB_DIST_DIR / f"{clean_path}.html",
        ]

    for candidate in candidates:
        try:
            candidate.relative_to(WEB_DIST_DIR)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate

    return None


def create_app() -> FastAPI:
    chatgpt_service = ChatGPTService(account_service)
    app_version = get_app_version()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        stop_event = Event()
        thread = start_limited_account_watcher(stop_event)
        try:
            yield
        finally:
            stop_event.set()
            thread.join(timeout=1)

    app = FastAPI(title="chatgpt2api", version=app_version, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    router = APIRouter()

    @router.get("/v1/models")
    async def list_models():
        return {
            "object": "list",
            "data": [
                build_model_item("gpt-image-1"),
                build_model_item("gpt-image-2"),
            ],
        }

    @router.post("/auth/login")
    async def login(authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        return {"ok": True, "version": app_version}

    @router.get("/version")
    async def get_version():
        return {"version": app_version}

    @router.get("/api/runtime")
    async def get_runtime(authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        return get_runtime_summary()

    @router.post("/v1/images/generations")
    async def generate_images(body: ImageGenerationRequest, authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        upstream = "openai" if is_openai_image_upstream_configured() else "chatgpt_pool"
        trace = start_image_trace(
            "generation",
            body.prompt,
            model=body.model,
            n=body.n,
            response_format=body.response_format,
            upstream=upstream,
            route="/v1/images/generations",
            original_prompt=body.original_prompt or "",
            optimized=bool(body.original_prompt and body.original_prompt.strip() and body.original_prompt.strip() != body.prompt.strip()),
        )
        started = time.time()
        try:
            if upstream == "openai":
                result = await run_in_threadpool(
                    generate_openai_image_result,
                    body.prompt,
                    body.model,
                    body.n,
                    body.response_format,
                    trace,
                )
            else:
                trace.event("chatgpt_pool.generate.start", model=body.model, n=body.n)
                result = await run_in_threadpool(chatgpt_service.generate_with_pool, body.prompt, body.model, body.n)
                trace.event("chatgpt_pool.generate.success")
            saved_result = await run_in_threadpool(save_image_result_files, result, trace)
            trace.event(
                "request.success",
                duration_ms=int((time.time() - started) * 1000),
                saved_images=_saved_image_summary(saved_result),
                item_count=len(saved_result.get("data", [])) if isinstance(saved_result.get("data"), list) else 0,
            )
            return saved_result
        except ImageGenerationError as exc:
            trace.event(
                "request.error",
                duration_ms=int((time.time() - started) * 1000),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

    @router.post("/api/image-prompts/optimize")
    async def optimize_prompt(body: ImagePromptOptimizeRequest, authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        trace = start_image_trace(
            "prompt_optimize",
            body.prompt,
            route="/api/image-prompts/optimize",
            mode=body.mode,
        )
        started = time.time()
        result = await run_in_threadpool(optimize_image_prompt, body.prompt, body.mode, trace=trace)
        trace.event(
            "request.success",
            duration_ms=int((time.time() - started) * 1000),
            optimizer=result.get("optimizer"),
            original_length=result.get("original_length"),
            optimized_length=result.get("optimized_length"),
            changed=result.get("changed"),
        )
        return result

    @router.post("/v1/images/edits")
    async def edit_images(
            authorization: str | None = Header(default=None),
            image: list[UploadFile] = File(...),
            prompt: str = Form(...),
            model: str = Form(default="gpt-image-2"),
            n: int = Form(default=1),
    ):
        require_auth_key(authorization)
        trace = start_image_trace(
            "edit",
            prompt,
            model=model,
            n=n,
            response_format="b64_json",
            route="/v1/images/edits",
        )
        started = time.time()
        if n < 1 or n > 4:
            trace.event("request.validation_error", field="n", error="n must be between 1 and 4")
            raise HTTPException(status_code=400, detail={"error": "n must be between 1 and 4"})

        images: list[tuple[bytes, str, str]] = []
        for upload in image:
            image_data = await upload.read()
            if not image_data:
                trace.event("request.validation_error", field="image", file_name=upload.filename, error="image file is empty")
                raise HTTPException(status_code=400, detail={"error": "image file is empty"})

            file_name = upload.filename or "image.png"
            mime_type = upload.content_type or "image/png"
            images.append((image_data, file_name, mime_type))

        trace.event(
            "request.uploads.read",
            input_images=[
                {"file_name": file_name, "mime_type": mime_type, "size": len(image_data)}
                for image_data, file_name, mime_type in images
            ],
        )

        try:
            if is_openai_image_upstream_configured():
                result = await run_in_threadpool(
                    edit_openai_image_result,
                    prompt,
                    images,
                    model,
                    n,
                    "b64_json",
                    trace,
                )
            else:
                trace.event("chatgpt_pool.edit.start", model=model, n=n)
                result = await run_in_threadpool(
                    chatgpt_service.edit_with_pool, prompt, images, model, n
                )
                trace.event("chatgpt_pool.edit.success")
            saved_result = await run_in_threadpool(save_image_result_files, result, trace)
            trace.event(
                "request.success",
                duration_ms=int((time.time() - started) * 1000),
                saved_images=_saved_image_summary(saved_result),
                item_count=len(saved_result.get("data", [])) if isinstance(saved_result.get("data"), list) else 0,
            )
            return saved_result
        except ImageGenerationError as exc:
            trace.event(
                "request.error",
                duration_ms=int((time.time() - started) * 1000),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

    @router.post("/v1/chat/completions")
    async def create_chat_completion(body: ChatCompletionRequest, authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        return await run_in_threadpool(chatgpt_service.create_image_completion, body.model_dump(mode="python"))

    @router.post("/v1/responses")
    async def create_response(body: ResponseCreateRequest, authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        return await run_in_threadpool(chatgpt_service.create_response, body.model_dump(mode="python"))


    app.include_router(router)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_web(full_path: str):
        asset = resolve_web_asset(full_path)
        if asset is not None:
            return FileResponse(asset)

        # Static assets (_next/*) must not fallback to HTML — return 404
        if full_path.strip("/").startswith("_next/"):
            raise HTTPException(status_code=404, detail="Not Found")

        fallback = resolve_web_asset("")
        if fallback is None:
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(fallback)

    return app
