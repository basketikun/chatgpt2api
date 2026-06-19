from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Body, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.support import require_admin
from services.register_service import register_service


class RegisterConfigRequest(BaseModel):
    mail: dict | None = None
    proxy: str | None = None
    total: int | None = None
    threads: int | None = None
    mode: str | None = None
    target_quota: int | None = None
    target_available: int | None = None
    check_interval: int | None = None
    otp_resend: str | None = None
    otp_resend_delay: int | None = None


class OutlookPoolResetRequest(BaseModel):
    scope: str | None = None


class RegisterPresetRequest(RegisterConfigRequest):
    pass


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/register")
    async def get_register_config(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return {"register": register_service.get()}

    @router.post("/api/register")
    async def update_register_config(body: RegisterConfigRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return {"register": register_service.update(body.model_dump(exclude_none=True))}

    @router.post("/api/register/start")
    async def start_register(
        body: RegisterConfigRequest | None = Body(default=None),
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        if body is not None:
            register_service.update(body.model_dump(exclude_none=True))
        return {"register": register_service.start()}

    @router.post("/api/register/stop")
    async def stop_register(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return {"register": register_service.stop()}

    @router.post("/api/register/reset")
    async def reset_register(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return {"register": register_service.reset()}

    @router.post("/api/register/outlook-pool/reset")
    async def reset_outlook_pool(body: OutlookPoolResetRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return {"register": register_service.reset_outlook_pool(body.scope or "all")}

    @router.get("/api/register/presets")
    async def list_register_presets(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return register_service.list_presets()

    @router.post("/api/register/presets/{name}")
    async def save_register_preset(name: str, body: RegisterPresetRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            return register_service.save_preset(name, body.model_dump(exclude_none=True))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @router.post("/api/register/presets/{name}/apply")
    async def apply_register_preset(name: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            return {"register": register_service.apply_preset(name)}
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/api/register/events")
    async def register_events(token: str = ""):
        require_admin(f"Bearer {token}")

        async def stream():
            last = ""
            while True:
                payload = json.dumps(register_service.get(), ensure_ascii=False)
                if payload != last:
                    last = payload
                    yield f"data: {payload}\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return router
