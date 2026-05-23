"""Captcha solver HTTP API.

Endpoints (all require Authorization: Bearer <CAPTCHA_SOLVER_API_KEY>):

    POST /v1/solve/turnstile          → solve Cloudflare Turnstile
    POST /v1/solve/recaptcha2         → solve reCAPTCHA v2 (checkbox/audio)
    POST /v1/solve/recaptcha3         → solve reCAPTCHA v3 (invisible)
    POST /v1/browser/run              → open URL, run JS, return DOM
    POST /v1/session/manual-login     → open URL in headful mode for VNC
    POST /v1/session/{profile}/close  → close a persistent profile's context
    GET  /v1/session/{profile}/status → quick health check on a profile
    GET  /health                      → unauthenticated liveness probe
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .browser_pool import pool
from .settings import settings
from .solvers.browser_run import browser_run
from .solvers.flow_google import generate_image as flow_generate_image
from .solvers.phatnguoi import lookup_phatnguoi
from .solvers.recaptcha import solve_recaptcha_v2, solve_recaptcha_v3
from .solvers.turnstile import solve_turnstile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("captcha-solver")


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    expected = settings.api_key or ""
    if not expected:
        return  # auth disabled (dev only)
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="invalid api key")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await pool.start()
    yield
    await pool.stop()


app = FastAPI(title="captcha-solver", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "novnc": settings.novnc_external_url}


class TurnstileReq(BaseModel):
    url: str
    sitekey: str | None = None
    profile: str = "default"
    headless: bool = True
    timeout: int | None = Field(default=None, ge=5, le=300)


class Recaptcha3Req(BaseModel):
    url: str
    sitekey: str
    action: str = "submit"
    profile: str = "default"
    headless: bool = True
    timeout: int | None = Field(default=None, ge=5, le=300)


class Recaptcha2Req(BaseModel):
    url: str
    profile: str = "default"
    headless: bool = True
    timeout: int | None = Field(default=None, ge=5, le=300)


class BrowserRunReq(BaseModel):
    url: str
    script: str | None = None
    wait_for: str | None = None
    profile: str = "default"
    headless: bool = True
    timeout: int = Field(default=30, ge=5, le=300)


class ManualLoginReq(BaseModel):
    url: str
    profile: str = "default"


class PhatNguoiReq(BaseModel):
    plate: str
    vehicle_type: int = Field(default=1, ge=1, le=3)
    profile: str = "phatnguoi"
    headless: bool = True
    timeout: int | None = Field(default=None, ge=10, le=300)


class FlowImageReq(BaseModel):
    project_id: str
    prompt: str
    aspect_ratio: str = "IMAGE_ASPECT_RATIO_LANDSCAPE"  # ..._SQUARE, _PORTRAIT
    model: str = "NARWHAL"
    tool: str = "PINHOLE"
    profile: str = "google-fx"
    # Flow's React app doesn't hydrate in true headless mode, so we default
    # to headful on Xvfb. Leave as-is unless you really know why.
    headless: bool = False
    timeout: int = Field(default=120, ge=15, le=300)
    # When true, the response is a single image/png body (the first image
    # downloaded from the Google CDN). Use this from Home Assistant or n8n
    # binary-handling nodes so you don't need a second HTTP call.
    return_binary: bool = False


@app.post("/v1/solve/turnstile", dependencies=[Depends(require_api_key)])
async def api_solve_turnstile(req: TurnstileReq) -> dict[str, Any]:
    try:
        return await solve_turnstile(
            url=req.url,
            sitekey=req.sitekey,
            profile=req.profile,
            headless=req.headless,
            timeout=req.timeout,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("turnstile solve failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/solve/recaptcha3", dependencies=[Depends(require_api_key)])
async def api_solve_recaptcha3(req: Recaptcha3Req) -> dict[str, Any]:
    try:
        return await solve_recaptcha_v3(
            url=req.url,
            sitekey=req.sitekey,
            action=req.action,
            profile=req.profile,
            headless=req.headless,
            timeout=req.timeout,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("recaptcha3 solve failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/solve/recaptcha2", dependencies=[Depends(require_api_key)])
async def api_solve_recaptcha2(req: Recaptcha2Req) -> dict[str, Any]:
    try:
        return await solve_recaptcha_v2(
            url=req.url,
            profile=req.profile,
            headless=req.headless,
            timeout=req.timeout,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("recaptcha2 solve failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/google/flow/generate-image", dependencies=[Depends(require_api_key)])
async def api_flow_generate(req: FlowImageReq):
    """End-to-end Google Labs Flow image gen. Requires the `google-fx`
    profile to be logged in first via /v1/session/manual-login.

    Returns JSON by default. With `return_binary: true`, downloads the
    first generated image and returns it as `image/png` (handy for Home
    Assistant `rest_command`, n8n HTTP Request → Binary Data, etc).
    """
    try:
        result = await flow_generate_image(
            project_id=req.project_id,
            prompt=req.prompt,
            aspect_ratio=req.aspect_ratio,
            model=req.model,
            tool=req.tool,
            profile=req.profile,
            headless=req.headless,
            timeout=req.timeout,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("flow generate failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not req.return_binary:
        return result

    images = result.get("images") or []
    if not images:
        raise HTTPException(status_code=502, detail="flow returned no images")
    first = images[0]
    url = first.get("url")
    if not url:
        raise HTTPException(status_code=502, detail="first image has no URL")
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
    except Exception as exc:
        logger.exception("download flow image failed")
        raise HTTPException(status_code=502, detail=f"download failed: {exc}") from exc

    # Prefer the CDN's actual Content-Type — Flow serves JPEG even though
    # our extractor defaults to "image/png".
    cdn_ct = (r.headers.get("content-type") or "").split(";")[0].strip()
    return Response(
        content=r.content,
        media_type=cdn_ct or first.get("mime") or "image/png",
        headers={
            "x-flow-image-id": str(first.get("id") or ""),
            "x-flow-model": str(first.get("model") or ""),
            "x-flow-seed": str(first.get("seed") or ""),
            "x-flow-elapsed-ms": str(result.get("elapsed_ms") or ""),
            "content-disposition": f'inline; filename="flow_{first.get("id","image")}.png"',
        },
    )


@app.post("/v1/forms/phatnguoi", dependencies=[Depends(require_api_key)])
async def api_phatnguoi(req: PhatNguoiReq) -> dict[str, Any]:
    try:
        return await lookup_phatnguoi(
            plate=req.plate,
            vehicle_type=req.vehicle_type,
            profile=req.profile,
            headless=req.headless,
            timeout=req.timeout,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("phatnguoi lookup failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/browser/run", dependencies=[Depends(require_api_key)])
async def api_browser_run(req: BrowserRunReq) -> dict[str, Any]:
    try:
        return await browser_run(
            url=req.url,
            script=req.script,
            wait_for=req.wait_for,
            profile=req.profile,
            headless=req.headless,
            timeout=req.timeout,
        )
    except Exception as exc:
        logger.exception("browser run failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/session/manual-login", dependencies=[Depends(require_api_key)])
async def api_manual_login(req: ManualLoginReq) -> dict[str, Any]:
    """Open `url` in a headful browser on the noVNC display so the user can
    sign in manually. The profile's user-data-dir persists, so the next
    automated call with the same `profile` is already logged in.
    """
    ctx = await pool.get(profile=req.profile, headless=False)
    page = await ctx.new_page()
    await page.goto(req.url, wait_until="domcontentloaded", timeout=30_000)
    return {
        "profile": req.profile,
        "url": req.url,
        "open_in_browser": settings.novnc_external_url,
        "message": (
            "Mở noVNC URL ở trên, đăng nhập tài khoản trong cửa sổ Chromium. "
            "Cookies sẽ được lưu vào profile '{}' để các lần gọi sau dùng headless.".format(req.profile)
        ),
    }


@app.get("/v1/session/list", dependencies=[Depends(require_api_key)])
async def api_session_list() -> dict[str, Any]:
    """List all known profiles (each is a chromium user-data-dir) along
    with whether they're currently held open in the pool."""
    root = settings.data_dir / "profiles"
    profiles: list[dict[str, Any]] = []
    if root.exists():
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            size = 0
            try:
                size = sum(p.stat().st_size for p in child.rglob("*") if p.is_file())
            except Exception:
                pass
            profiles.append({
                "name": child.name,
                "loaded": child.name in pool._contexts,
                "size_bytes": size,
                "path": str(child),
            })
    return {"profiles": profiles, "count": len(profiles)}


@app.get("/v1/session/{profile}/status", dependencies=[Depends(require_api_key)])
async def api_session_status(profile: str) -> dict[str, Any]:
    ctx = pool._contexts.get(profile)
    if ctx is None:
        return {"profile": profile, "loaded": False, "pages": 0, "cookies": 0}
    cookies = await ctx.cookies()
    return {
        "profile": profile,
        "loaded": True,
        "pages": len(ctx.pages),
        "cookies": len(cookies),
    }


@app.post("/v1/session/{profile}/close", dependencies=[Depends(require_api_key)])
async def api_session_close(profile: str) -> dict[str, Any]:
    closed = await pool.close_profile(profile)
    return {"profile": profile, "closed": closed}
