from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from threading import Event

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import accounts, ai, image_tasks, mcp, oauth, register, system
from api.support import resolve_web_asset, start_limited_account_watcher, require_admin
from api.veo_video import handle_video_generation
from services.backup_service import backup_service
from services.config import config
from services.karpathy_guidelines import refresh_guidelines
from services.quota_watcher import quota_watcher


def create_app() -> FastAPI:
    app_version = config.app_version

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        stop_event = Event()
        thread = start_limited_account_watcher(stop_event)
        backup_service.start()
        config.cleanup_old_images()
        # Fetch latest Karpathy guidelines + start quota watcher (fire-and-forget)
        refresh_guidelines()
        watcher_task = asyncio.create_task(quota_watcher.start())
        # Start JWT auto-refresh scheduler (ChatGPT free 28-day expiry)
        try:
            from services.jwt_refresh_scheduler import start as start_jwt_refresh
            start_jwt_refresh()
        except Exception:
            pass
        # Start models-catalogue auto-refresh (every 6h ± 30 min).
        # Keeps the dynamic gmw/* + cgw/* + codex live lists warm even
        # when nothing hits /v1/models — so the dropdown the user opens
        # tomorrow already reflects upstream's renames/additions today.
        try:
            from services.models_refresh_scheduler import start as start_models_refresh
            start_models_refresh()
        except Exception:
            pass
        # Pre-load HA client to start background scheduler
        try:
            from services.ha_client import format_states_context
            format_states_context()  # Triggers initial device registry fetch
        except Exception:
            pass
        # Prewarm MCP tools cache in background so the first chat request
        # doesn't pay the cold-start probe (e.g. a dead remote MCP that
        # times out at 5s adds latency to whoever asks first).
        try:
            from services.mcp_client import prewarm_tools_cache
            prewarm_tools_cache()
        except Exception:
            pass
        # Prewarm web browser contexts (ChatGPT, Gemini, Flow)
        try:
            from services.web_prewarmer import start as start_web_prewarm
            start_web_prewarm()
        except Exception:
            pass
        # Start Cloudflare Tunnel if token configured
        try:
            from services.cloudflare_tunnel import start_tunnel, start_monitor
            start_tunnel()
            start_monitor()
        except Exception:
            pass
        # Register Telegram webhook if token configured
        try:
            from services.telegram_bot import register_webhook
            register_webhook()
        except Exception:
            pass
        # Start Codex-inspired usage snapshot poller (15s proactive rate-limit polling)
        try:
            from services.usage_snapshot_poller import usage_snapshot_poller
            poller_task = asyncio.create_task(usage_snapshot_poller.start())
        except Exception:
            poller_task = None
        # Initialize project docs watcher (AGENTS.md / CLAUDE.md auto-reload)
        try:
            from services.project_docs_watcher import project_docs_watcher
            project_docs_watcher.force_reload()
        except Exception:
            pass
        try:
            yield
        finally:
            await quota_watcher.stop()
            if poller_task is not None:
                await usage_snapshot_poller.stop()
            stop_event.set()
            thread.join(timeout=1)
            backup_service.stop()
            try:
                from services.cloudflare_tunnel import stop_tunnel
                stop_tunnel()
            except Exception:
                pass

    app = FastAPI(title="chatgpt2api", version=app_version, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(ai.create_router())
    app.include_router(accounts.create_router())
    app.include_router(oauth.create_router())
    app.include_router(image_tasks.create_router())
    app.include_router(mcp.create_router())
    app.include_router(register.create_router())
    app.include_router(system.create_router(app_version))
    if config.images_dir.exists():
        app.mount("/images", StaticFiles(directory=str(config.images_dir)), name="images")

    # Veo video generation
    @app.post("/v1/video/generations")
    async def create_video(body: dict, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return await handle_video_generation(body, authorization)

    async def serve_web(full_path: str):
        asset = resolve_web_asset(full_path)
        if asset is not None:
            return FileResponse(asset)
        if full_path.strip("/").startswith("_next/"):
            raise HTTPException(status_code=404, detail="Not Found")
        fallback = resolve_web_asset("")
        if fallback is None:
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(fallback)

    app.add_api_route("/{full_path:path}", serve_web, methods=["GET", "HEAD"], include_in_schema=False)

    return app
