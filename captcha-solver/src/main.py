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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .auto_login import (
    get_session as get_login_session,
    list_sessions as list_login_sessions,
    start_auto_login,
    submit_2fa_code,
)
from .chatgpt_login import (
    get_session as get_chatgpt_session,
    start_chatgpt_login,
    submit_2fa_code as submit_chatgpt_2fa_code,
)
from .gemini_web_login import (
    get_session as get_gemini_web_session,
    start_gemini_web_login,
    submit_2fa_code as submit_gemini_web_2fa_code,
)
from .solvers.gemini_web import chat as gemini_web_chat
from .browser_pool import pool
from .settings import settings
from .solvers.browser_run import browser_run
from .solvers.flow_google import (
    generate_image as flow_generate_image,
    get_or_create_project as flow_get_or_create_project,
)
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

# Allow cross-origin POST from chatgpt2api's Settings UI (Flow tab) so the
# "Open noVNC + start Google login" button can call /v1/session/manual-login
# directly from the browser. Auth still required (Bearer header forwarded).
# allow_origins=["*"] is OK here because every protected endpoint
# enforces require_api_key — the Origin header alone never authenticates.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-flow-image-id", "x-flow-model", "x-flow-seed", "x-flow-elapsed-ms"],
)


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
    # When true, kill any cached context for this profile and launch a
    # fresh Chrome. Use this from the "Mở lại noVNC" button when the
    # previous window died or noVNC shows a blank desktop.
    force: bool = False


class AutoLoginReq(BaseModel):
    profile: str = "google-fx"
    email: str
    password: str


class TwoFactorCodeReq(BaseModel):
    code: str


class GetOrCreateProjectReq(BaseModel):
    profile: str = "google-fx"
    headless: bool = False
    timeout: int = Field(default=90, ge=20, le=300)


class ChatGPTOnboardReq(BaseModel):
    profile: str = "chatgpt-default"
    email: str
    password: str


class GeminiWebOnboardReq(BaseModel):
    profile: str = "gemini-web-default"
    email: str
    password: str


class GeminiWebChatReq(BaseModel):
    profile: str = "gemini-web-default"
    prompt: str
    timeout: int = Field(default=90, ge=20, le=300)
    headless: bool = False


class PhatNguoiReq(BaseModel):
    plate: str
    vehicle_type: int = Field(default=1, ge=1, le=3)
    profile: str = "phatnguoi"
    headless: bool = True
    timeout: int | None = Field(default=None, ge=10, le=300)


class FlowImageReq(BaseModel):
    project_id: str
    prompt: str
    # Default 16:9 landscape. Other supported values matching Flow's pill
    # buttons: IMAGE_ASPECT_RATIO_LANDSCAPE_4_3, _SQUARE, _PORTRAIT_3_4,
    # _PORTRAIT (9:16).
    aspect_ratio: str = "IMAGE_ASPECT_RATIO_LANDSCAPE"
    # Strongest model by default. NARWHAL = Nano Banana 2, IMAGEN_4 = Imagen 4.
    model: str = "NANO_BANANA_PRO"
    # 1-4 images per request. Best-effort — Flow uses project default if
    # the dropdown click misses.
    count: int = Field(default=1, ge=1, le=4)
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

    For `count > 1` we fan out N parallel calls to Flow (the API itself
    only generates 1 image per request — there's no batch field — so we
    parallelise the requests instead). Each call uses the same profile
    + project; the BrowserPool will serialise them if the profile only
    has one Chromium context, which keeps the same upper bound on
    parallelism as the user has logged-in accounts.
    """
    import asyncio

    async def _one() -> dict:
        return await flow_generate_image(
            project_id=req.project_id,
            prompt=req.prompt,
            aspect_ratio=req.aspect_ratio,
            model=req.model,
            count=1,  # always 1 per call — count handled at this layer
            tool=req.tool,
            profile=req.profile,
            headless=req.headless,
            timeout=req.timeout,
        )

    try:
        n = max(1, min(4, int(req.count or 1)))
        if n == 1:
            result = await _one()
        else:
            # Fan-out, gather all (and surface the first exception if any).
            results = await asyncio.gather(*[_one() for _ in range(n)], return_exceptions=True)
            ok_results = [r for r in results if isinstance(r, dict)]
            failures = [r for r in results if not isinstance(r, dict)]
            if not ok_results:
                raise RuntimeError(f"all {n} parallel calls failed: {failures[0]}")
            # Merge: keep first result's metadata, concatenate `images`.
            result = dict(ok_results[0])
            merged_images = []
            for r in ok_results:
                merged_images.extend(r.get("images") or [])
            result["images"] = merged_images
            if failures:
                logger.warning("flow_partial_failure ok=%d failed=%d first_error=%s",
                                len(ok_results), len(failures), failures[0])
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


@app.post(
    "/v1/google/flow/get-or-create-project",
    dependencies=[Depends(require_api_key)],
)
async def api_flow_get_or_create_project(req: GetOrCreateProjectReq) -> dict[str, Any]:
    """List Flow projects the logged-in account already owns and return
    the first one's UUID, or click "Dự án mới" to create a fresh one
    and return its UUID. The profile MUST already be logged in.

    Used by the chatgpt2api UI's "1-click add account" flow:
      1. POST /v1/session/auto-login {profile, email, password}
      2. Poll /v1/session/{profile}/auto-login-status until success
      3. POST /v1/google/flow/get-or-create-project {profile}
      4. PATCH /api/settings to add the {profile, project_id, label}
         to flow.accounts
    """
    try:
        return await flow_get_or_create_project(
            profile=req.profile,
            headless=req.headless,
            timeout=req.timeout,
        )
    except Exception as exc:
        logger.exception("flow get_or_create_project failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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

    Reuses the first existing page in the context (so the user sees ONE
    Chrome window in noVNC, not a new tab on every click). If `force=True`,
    any cached context for this profile is killed and a fresh Chrome is
    launched — use this when noVNC shows "Connected... :99" but the
    desktop is blank (Chrome died between calls).
    """
    ctx = await pool.get(
        profile=req.profile,
        headless=False,
        force_recreate=req.force,
    )
    # Reuse first non-closed page so noVNC user keeps ONE window.
    page = None
    for p in list(ctx.pages):
        try:
            if not p.is_closed():
                page = p
                break
        except Exception:
            continue
    if page is None:
        page = await ctx.new_page()
    try:
        await page.bring_to_front()
    except Exception:
        pass
    await page.goto(req.url, wait_until="domcontentloaded", timeout=30_000)
    return {
        "profile": req.profile,
        "url": req.url,
        "open_in_browser": settings.novnc_external_url,
        "force": req.force,
        "message": (
            "Mở noVNC URL ở trên, đăng nhập tài khoản trong cửa sổ Chromium. "
            "Cookies sẽ được lưu vào profile '{}' để các lần gọi sau dùng headless. "
            "Nếu desktop trống → gọi lại endpoint này với force=true.".format(req.profile)
        ),
    }


@app.post("/v1/session/auto-login", dependencies=[Depends(require_api_key)])
async def api_auto_login(req: AutoLoginReq) -> dict[str, Any]:
    """Start a CLI-driven Google login. Returns immediately with the
    initial session state — UI polls /v1/session/{profile}/auto-login-status
    to track progress and feeds 2FA codes via /auto-login-2fa-code.

    Anti-bot reality: Google often blocks automation in container/VPS
    setups. If state stalls or fails, the noVNC window is still open
    — the user can finish the remaining steps manually and the saved
    cookies persist either way.
    """
    session = await start_auto_login(
        profile=req.profile,
        email=req.email,
        password=req.password,
    )
    return {
        **session.to_dict(),
        "novnc": settings.novnc_external_url,
        "note": "Theo dõi tiến trình ở /v1/session/{profile}/auto-login-status. "
                "Mở noVNC để giám sát/can thiệp khi cần.",
    }


@app.get(
    "/v1/session/{profile}/auto-login-status",
    dependencies=[Depends(require_api_key)],
)
async def api_auto_login_status(profile: str) -> dict[str, Any]:
    session = get_login_session(profile)
    if session is None:
        return {"profile": profile, "state": "none", "message": "Chưa có phiên auto-login"}
    return session.to_dict()


@app.post(
    "/v1/session/{profile}/auto-login-2fa-code",
    dependencies=[Depends(require_api_key)],
)
async def api_auto_login_2fa_code(profile: str, req: TwoFactorCodeReq) -> dict[str, Any]:
    """Feed an SMS / TOTP / backup code to a session currently in
    state=need_code. Returns 409 if the session isn't asking for one."""
    ok = submit_2fa_code(profile, req.code)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="Phiên không ở trạng thái cần mã (chỉ submit được khi state=need_code)",
        )
    return {"profile": profile, "submitted": True}


@app.get("/v1/session/auto-login-sessions", dependencies=[Depends(require_api_key)])
async def api_auto_login_sessions() -> dict[str, Any]:
    """Snapshot of every auto-login session (running + recently finished)."""
    return {"sessions": list_login_sessions()}


# ── ChatGPT login via Google OAuth ──────────────────────────────────────

@app.post("/v1/chatgpt/onboard", dependencies=[Depends(require_api_key)])
async def api_chatgpt_onboard(req: ChatGPTOnboardReq) -> dict[str, Any]:
    """Start a ChatGPT-via-Google login on the given profile. Returns the
    initial session state — poll /v1/chatgpt/{profile}/onboard-status for
    progress and feed 2FA codes via /v1/chatgpt/{profile}/onboard-2fa-code.

    On success the response includes a JWT `access_token` ready to add
    into chatgpt2api's account pool (it's a chatgpt.com-audience JWT).
    """
    session = await start_chatgpt_login(
        profile=req.profile,
        email=req.email,
        password=req.password,
    )
    return {
        **session.to_dict(),
        "novnc": settings.novnc_external_url,
        "note": "Theo dõi tiến trình ở /v1/chatgpt/{profile}/onboard-status. "
                "Khi state=success, lấy access_token để add vào chatgpt2api.",
    }


@app.get("/v1/chatgpt/{profile}/onboard-status", dependencies=[Depends(require_api_key)])
async def api_chatgpt_onboard_status(profile: str) -> dict[str, Any]:
    session = get_chatgpt_session(profile)
    if session is None:
        return {"profile": profile, "state": "none", "message": "Chưa có phiên onboard"}
    return session.to_dict()


@app.post("/v1/chatgpt/{profile}/onboard-2fa-code", dependencies=[Depends(require_api_key)])
async def api_chatgpt_onboard_2fa_code(profile: str, req: TwoFactorCodeReq) -> dict[str, Any]:
    ok = submit_chatgpt_2fa_code(profile, req.code)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="Phiên không ở state=need_code (chỉ submit được khi đang cần mã)",
        )
    return {"profile": profile, "submitted": True}


# ── Gemini Web (gemini.google.com) ──────────────────────────────────────

@app.post("/v1/gemini-web/onboard", dependencies=[Depends(require_api_key)])
async def api_gemini_web_onboard(req: GeminiWebOnboardReq) -> dict[str, Any]:
    """Onboard a profile for Gemini Web (gemini.google.com).

    Short-circuits to success if the profile already has a valid Google
    session (from Flow / ChatGPT onboard). Otherwise runs the standard
    Google login flow.
    """
    session = await start_gemini_web_login(
        profile=req.profile, email=req.email, password=req.password,
    )
    return {
        **session.to_dict(),
        "novnc": settings.novnc_external_url,
        "note": "Theo dõi tiến trình ở /v1/gemini-web/{profile}/onboard-status. "
                "Khi state=success, gọi /v1/gemini-web/chat để chat.",
    }


@app.get("/v1/gemini-web/{profile}/onboard-status", dependencies=[Depends(require_api_key)])
async def api_gemini_web_onboard_status(profile: str) -> dict[str, Any]:
    session = get_gemini_web_session(profile)
    if session is None:
        return {"profile": profile, "state": "none", "message": "Chưa có phiên onboard"}
    return session.to_dict()


@app.post("/v1/gemini-web/{profile}/onboard-2fa-code", dependencies=[Depends(require_api_key)])
async def api_gemini_web_onboard_2fa_code(profile: str, req: TwoFactorCodeReq) -> dict[str, Any]:
    ok = submit_gemini_web_2fa_code(profile, req.code)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="Phiên không ở state=need_code",
        )
    return {"profile": profile, "submitted": True}


@app.post("/v1/gemini-web/chat", dependencies=[Depends(require_api_key)])
async def api_gemini_web_chat(req: GeminiWebChatReq) -> dict[str, Any]:
    """Send a prompt to gemini.google.com (DOM-scrape approach).

    Profile must already be logged in via /v1/gemini-web/onboard.
    Returns the assistant's text response + elapsed_ms.
    """
    try:
        return await gemini_web_chat(
            profile=req.profile, prompt=req.prompt,
            timeout=req.timeout, headless=req.headless,
        )
    except Exception as exc:
        logger.exception("gemini_web chat failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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
                "loaded": pool.is_loaded(child.name),
                "size_bytes": size,
                "path": str(child),
            })
    return {"profiles": profiles, "count": len(profiles)}


@app.get("/v1/session/{profile}/status", dependencies=[Depends(require_api_key)])
async def api_session_status(profile: str) -> dict[str, Any]:
    ctx = pool.get_cached(profile)
    if ctx is None:
        return {"profile": profile, "loaded": False, "pages": 0, "cookies": 0}
    try:
        cookies = await ctx.cookies()
    except Exception:
        # Context exists in cache but is dead — return zeroes; next /get
        # call will evict it.
        return {"profile": profile, "loaded": False, "pages": 0, "cookies": 0, "stale": True}
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
