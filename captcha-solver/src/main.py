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

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .browser_pool import pool
from .settings import settings
from .solvers.browser_run import browser_run
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
