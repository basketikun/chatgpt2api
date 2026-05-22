from __future__ import annotations

import json
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict

from api.support import require_admin, require_identity, resolve_image_base_url
from services.backup_service import BackupError, backup_service
from services.config import config
from services.image_service import delete_images, download_images_zip, get_image_download_response, get_thumbnail_response, list_images
from services.image_tags_service import delete_tag, get_all_tags, set_tags
from services.log_service import log_service
from services.proxy_service import test_proxy
from services.state_backup import state_backup
from services.backend_router import backend_router
from services.model_cooldown import model_cooldown
from services.providers.opencode import opencode_provider
from services.rate_limit_backoff import rate_limit_backoff
from services.quota_watcher import quota_watcher
from services.ninerouter_backup_import import import_9router_backup_from_api
from services.oauth_service import get_codex_auth_url, exchange_codex_code, get_chatgpt_session_url, detect_token_type


def _check_gemini_status() -> dict:
    """Check Gemini API and ALL custom provider instances (all ports)."""
    import requests as req

    result = {
        "gemini_api": "unknown",
        "models_count": 0,
        "instances": [],  # list of all provider instances with per-key status
    }

    # Check Gemini API with ALL keys individually
    provider_config = (config.data.get("providers") or {}).get("gemini_free") or {}
    gemini_single_key = str(provider_config.get("api_key") or "").strip()
    gemini_multi_keys = provider_config.get("api_keys") or []
    if not isinstance(gemini_multi_keys, list):
        gemini_multi_keys = []
    gemini_all_keys = [k.strip() for k in gemini_multi_keys if k.strip()]
    if gemini_single_key and gemini_single_key not in gemini_all_keys:
        gemini_all_keys.insert(0, gemini_single_key)

    gemini_key_statuses = []
    gemini_available = 0
    total_models = 0

    for key in gemini_all_keys:
        ks = {"key_preview": key[:12] + "..." + key[-4:] if len(key) > 20 else key, "status": "unknown", "error": None, "models": 0}
        try:
            resp = req.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                timeout=10
            )
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                ks["status"] = "available"
                ks["models"] = len(models)
                gemini_available += 1
                total_models = max(total_models, len(models))
            elif resp.status_code == 429:
                ks["status"] = "rate_limited"
                ks["error"] = "Rate limit exceeded — too many requests"
            elif resp.status_code in (401, 403):
                ks["status"] = "auth_error"
                ks["error"] = f"HTTP {resp.status_code} — API key invalid"
            else:
                ks["status"] = f"error_{resp.status_code}"
                try:
                    ks["error"] = resp.json().get("error", {}).get("message", str(resp.status_code))
                except Exception:
                    ks["error"] = str(resp.status_code)
        except Exception as e:
            ks["status"] = "network_error"
            ks["error"] = str(e)[:80]
        gemini_key_statuses.append(ks)

    # Overall Gemini status
    if gemini_available == len(gemini_all_keys) and len(gemini_all_keys) > 0:
        result["gemini_api"] = "available"
    elif gemini_available > 0:
        result["gemini_api"] = "partial"
    elif any(k["status"] == "rate_limited" for k in gemini_key_statuses):
        result["gemini_api"] = "rate_limited"
    elif any(k["status"] == "auth_error" for k in gemini_key_statuses):
        result["gemini_api"] = "auth_error"
    elif gemini_all_keys:
        result["gemini_api"] = gemini_key_statuses[0]["status"]
    else:
        result["gemini_api"] = "no_key"
    result["models_count"] = total_models

    # Add Gemini as an instance with per-key details
    if gemini_all_keys:
        result["instances"].append({
            "id": "gemini_free",
            "name": "Gemini API",
            "prefix": "gemini_free",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "status": result["gemini_api"],
            "port": "443",
            "models": total_models,
            "clients": 0,
            "entries": 0,
            "total_keys": len(gemini_all_keys),
            "available_keys": gemini_available,
            "keys": gemini_key_statuses,
            "error": next((k["error"] for k in gemini_key_statuses if k["status"] != "available" and k["error"]), None),
        })

    # Check ALL custom providers (all ports/instances) with per-key status
    custom_providers = config.data.get("custom_providers") or {}
    for cp_id, cp_cfg in custom_providers.items():
        if not isinstance(cp_cfg, dict) or not cp_cfg.get("enabled", True):
            continue
        base_url = cp_cfg.get("base_url") or ""
        name = cp_cfg.get("name") or cp_id
        prefix = cp_cfg.get("prefix") or cp_id

        # Collect all API keys (single + multi)
        single_key = str(cp_cfg.get("api_key") or "").strip()
        multi_keys = cp_cfg.get("api_keys") or []
        if not isinstance(multi_keys, list):
            multi_keys = []
        all_keys = [k.strip() for k in multi_keys if k.strip()]
        if single_key and single_key not in all_keys:
            all_keys.insert(0, single_key)

        # Auto-detect API style and paths
        is_no_v1 = "deepseek.com" in base_url or "perplexity.ai" in base_url
        base_has_v1 = base_url.rstrip("/").endswith("/v1")
        if is_no_v1:
            models_path = "/models" if "deepseek.com" in base_url else "/v1/models"
            chat_path = "/chat/completions" if "deepseek.com" in base_url else "/v1/chat/completions"
        elif base_has_v1:
            models_path = "/models"
            chat_path = "/chat/completions"
        else:
            models_path = "/v1/models"
            chat_path = "/v1/chat/completions"

        # Check each key's status
        key_statuses = []
        available_keys = 0
        for key in all_keys:
            key_status = {"key_preview": key[:12] + "..." + key[-4:] if len(key) > 20 else key, "status": "unknown", "error": None}
            try:
                resp = req.get(f"{base_url}{models_path}", headers={"Authorization": f"Bearer {key}"}, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    models_list = data.get("data") or data.get("models") or []
                    key_status["status"] = "available"
                    key_status["models"] = len(models_list)
                    available_keys += 1
                elif resp.status_code == 401 or resp.status_code == 403:
                    key_status["status"] = "auth_error"
                    key_status["error"] = f"HTTP {resp.status_code} — API key invalid"
                elif resp.status_code == 429:
                    key_status["status"] = "rate_limited"
                    key_status["error"] = "Rate limited"
                elif resp.status_code >= 500:
                    key_status["status"] = "server_error"
                    key_status["error"] = f"HTTP {resp.status_code}"
                else:
                    key_status["status"] = f"http_{resp.status_code}"
                    key_status["error"] = f"HTTP {resp.status_code}"
            except Exception as e:
                key_status["status"] = "network_error"
                key_status["error"] = str(e)[:80]
            key_statuses.append(key_status)

        # Determine overall status
        if available_keys == len(all_keys) and len(all_keys) > 0:
            overall_status = "available"
        elif available_keys > 0:
            overall_status = "partial"
        elif any(k["status"] == "auth_error" for k in key_statuses):
            overall_status = "auth_error"
        elif any(k["status"] == "network_error" for k in key_statuses):
            overall_status = "network_error"
        else:
            overall_status = key_statuses[0]["status"] if key_statuses else "no_keys"

        # Also check /health for geminiapi-style providers
        clients = 0
        entries = 0
        if not is_no_v1:
            try:
                resp = req.get(f"{base_url}/health", timeout=4)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        clients = len(data.get("clients") or {})
                        entries = data.get("storage", {}).get("entries", 0)
            except Exception:
                pass

        instance = {
            "id": cp_id,
            "name": name,
            "prefix": prefix,
            "base_url": base_url,
            "status": overall_status,
            "port": base_url.split(":")[-1].rstrip("/") if ":" in base_url else "—",
            "models": sum(k.get("models", 0) for k in key_statuses),
            "clients": clients,
            "entries": entries,
            "total_keys": len(all_keys),
            "available_keys": available_keys,
            "keys": key_statuses,
            "error": None,
        }
        # Set primary error from first failing key
        for k in key_statuses:
            if k["status"] != "available" and k["error"]:
                instance["error"] = k["error"]
                break

        result["instances"].append(instance)

    return result


def _is_model_enabled(model_id: str, enabled_by_provider: dict) -> bool:
    """Check if a model is in the enabled list. If no providers configured, all models are enabled."""
    if not enabled_by_provider:
        return True
    # Core models + image models always enabled
    if model_id in {"cx/auto", "oc/auto", "chatgpt/auto", "gemini_free/auto", "gpt-image-2", "codex-gpt-image-2"}:
        return True
    for provider_models in enabled_by_provider.values():
        if isinstance(provider_models, list) and model_id in provider_models:
            return True
    return False


def _create_backup() -> dict:
    """Create local full-state backup."""
    payload = state_backup.export_all()
    filepath = state_backup.save_to_file(payload)
    return {
        "status": "ok",
        "path": str(filepath),
        "size_bytes": filepath.stat().st_size,
        "created_at": payload["created_at"],
    }


class SettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")


class ProxyTestRequest(BaseModel):
    url: str = ""


class ImageDeleteRequest(BaseModel):
    paths: list[str] = []
    start_date: str = ""
    end_date: str = ""
    all_matching: bool = False

class ImageDownloadRequest(BaseModel):
    paths: list[str]

class ImageTagsRequest(BaseModel):
    path: str
    tags: list[str]

class LogDeleteRequest(BaseModel):
    ids: list[str] = []
class BackupDeleteRequest(BaseModel):
    key: str = ""

class Import9RouterRequest(BaseModel):
    path: str = ""

class RestoreRequest(BaseModel):
    path: str = ""


class CodexExchangeRequest(BaseModel):
    redirect_url: str = ""


class AntigravityExchangeRequest(BaseModel):
    redirect_url: str = ""


def create_router(app_version: str) -> APIRouter:
    router = APIRouter()

    @router.post("/auth/login")
    async def login(authorization: str | None = Header(default=None)):
        identity = require_identity(authorization)
        return {
            "ok": True,
            "version": app_version,
            "role": identity.get("role"),
            "subject_id": identity.get("id"),
            "name": identity.get("name"),
        }

    @router.get("/version")
    async def get_version():
        return {"version": app_version}

    @router.get("/api/settings")
    async def get_settings(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return {"config": config.get()}

    @router.post("/api/settings")
    async def save_settings(body: SettingsUpdateRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        result = config.update(body.model_dump(mode="python"))
        # If tunnel token changed, restart tunnel
        if "cloudflare_tunnel_token" in (body.model_dump() or {}):
            try:
                from services.cloudflare_tunnel import restart_tunnel
                restart_tunnel()
            except Exception:
                pass
        # If telegram token changed, re-register webhook
        if any(k in (body.model_dump() or {}) for k in ("telegram_bot_token", "telegram_webhook_url")):
            try:
                from services.telegram_bot import register_webhook
                register_webhook()
            except Exception:
                pass
        return {"config": result}

    # ── Cloudflare Tunnel ──
    @router.get("/api/tunnel/status")
    async def tunnel_status(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        from services.cloudflare_tunnel import get_status
        return get_status()

    @router.post("/api/tunnel/restart")
    async def tunnel_restart(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        from services.cloudflare_tunnel import restart_tunnel
        return {"ok": restart_tunnel()}

    # ── Telegram ──
    @router.get("/api/telegram/status")
    async def telegram_status(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        from services.telegram_bot import get_status
        return get_status()

    @router.post("/telegram/webhook")
    async def telegram_webhook(request: Request):
        """Public endpoint for Telegram to send messages to."""
        from services.telegram_bot import handle_webhook
        return await handle_webhook(request)

    @router.post("/api/telegram/test")
    async def telegram_test(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        from services.telegram_bot import _chat_ids, send_message
        ids = _chat_ids()
        if not ids:
            raise HTTPException(400, "Chưa cấu hình telegram_chat_ids")
        r = send_message(ids[0], "✅ Test từ chatgpt2api")
        return {"ok": r.get("ok", False)}

    @router.get("/api/images")
    async def get_images(request: Request, start_date: str = "", end_date: str = "", authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return list_images(resolve_image_base_url(request), start_date=start_date.strip(), end_date=end_date.strip())

    @router.get("/image-thumbnails/{image_path:path}", include_in_schema=False)
    async def get_image_thumbnail(image_path: str):
        return get_thumbnail_response(image_path)

    @router.post("/api/images/delete")
    async def delete_images_endpoint(body: ImageDeleteRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return delete_images(body.paths, start_date=body.start_date.strip(), end_date=body.end_date.strip(), all_matching=body.all_matching)

    @router.post("/api/images/download")
    async def download_images_endpoint(body: ImageDownloadRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        buf = download_images_zip(body.paths)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="images.zip"'},
        )

    @router.get("/api/images/download/{image_path:path}")
    async def download_single_image_endpoint(image_path: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return get_image_download_response(image_path)

    @router.get("/api/logs")
    async def get_logs(type: str = "", start_date: str = "", end_date: str = "", authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return {"items": log_service.list(type=type.strip(), start_date=start_date.strip(), end_date=end_date.strip())}

    @router.post("/api/logs/delete")
    async def delete_logs(body: LogDeleteRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return log_service.delete(body.ids)

    @router.post("/api/proxy/test")
    async def test_proxy_endpoint(body: ProxyTestRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        candidate = (body.url or "").strip() or config.get_proxy_settings()
        if not candidate:
            raise HTTPException(status_code=400, detail={"error": "proxy url is required"})
        return {"result": await run_in_threadpool(test_proxy, candidate)}

    @router.get("/api/storage/info")
    async def get_storage_info(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        storage = config.get_storage_backend()
        return {
            "backend": storage.get_backend_info(),
            "health": storage.health_check(),
        }

    @router.post("/api/backup/test")
    async def test_backup_connection(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            return {"result": await run_in_threadpool(backup_service.test_connection)}
        except BackupError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    @router.get("/api/backups")
    async def get_backups(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            return {
                "items": await run_in_threadpool(backup_service.list_backups),
                "state": backup_service.get_status(),
                "settings": backup_service.get_settings(),
            }
        except BackupError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    @router.post("/api/backups/run")
    async def run_backup_endpoint(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            return {"result": await run_in_threadpool(backup_service.run_backup)}
        except BackupError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    @router.post("/api/backups/delete")
    async def delete_backup_endpoint(body: BackupDeleteRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            await run_in_threadpool(backup_service.delete_backup, body.key)
            return {"ok": True}
        except BackupError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    @router.get("/api/backups/detail")
    async def get_backup_detail(key: str = "", authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            return {"item": await run_in_threadpool(backup_service.get_backup_detail, key)}
        except BackupError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    @router.get("/api/backups/download")
    async def download_backup_endpoint(key: str = "", authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            item = await run_in_threadpool(backup_service.download_backup, key)
        except BackupError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        filename = str(item.get("name") or "backup.bin")
        quoted = quote(filename)
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted}",
            "Content-Length": str(int(item.get("size") or 0)),
        }
        return Response(
            content=bytes(item.get("payload") or b""),
            media_type=str(item.get("content_type") or "application/octet-stream"),
            headers=headers,
        )


    @router.get("/api/images/tags")
    async def list_image_tags(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return {"tags": get_all_tags()}

    @router.post("/api/images/tags")
    async def update_image_tags(body: ImageTagsRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        rel = body.path.strip().lstrip("/")
        if not rel:
            raise HTTPException(status_code=400, detail={"error": "path is required"})
        tags = set_tags(rel, body.tags)
        return {"ok": True, "tags": tags}

    @router.delete("/api/images/tags/{tag}")
    async def delete_image_tag(tag: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        count = delete_tag(tag)
        return {"ok": True, "removed_from": count}

    # ── Backup / Restore (local full-state) ──

    @router.post("/api/v1/import-9router")
    async def import_9router_backup(
        body: Import9RouterRequest,
        authorization: str | None = Header(default=None),
    ):
        """Import token từ file backup 9router vào chatgpt2api (theo đường dẫn file)."""
        require_admin(authorization)
        path = (body.path or "").strip()
        if not path:
            raise HTTPException(status_code=400, detail={"error": "path is required"})

        def _import():
            return import_9router_backup_from_api(path)

        result = await run_in_threadpool(_import)
        return result

    @router.post("/api/v1/import-9router-upload")
    async def import_9router_backup_upload(
        body: dict,
        authorization: str | None = Header(default=None),
    ):
        """Import token từ nội dung file backup 9router (upload trực tiếp)."""
        require_admin(authorization)
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail={"error": "Invalid JSON body"})

        def _import():
            import tempfile
            import os
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
                json.dump(body, f)
                tmp_path = f.name
            try:
                return import_9router_backup_from_api(tmp_path)
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        result = await run_in_threadpool(_import)
        return result

    @router.post("/api/v1/backup")
    async def create_local_backup(authorization: str | None = Header(default=None)):
        """Export toàn bộ state ra file JSON và lưu local."""
        require_admin(authorization)
        result = await run_in_threadpool(_create_backup)
        return result

    @router.get("/api/v1/backups")
    async def list_local_backups(authorization: str | None = Header(default=None)):
        """Danh sách backup local."""
        require_admin(authorization)
        return {"backups": state_backup.list_backups()}

    @router.post("/api/v1/restore")
    async def restore_from_backup(
        body: RestoreRequest,
        authorization: str | None = Header(default=None),
    ):
        """Phục hồi state từ file backup local."""
        require_admin(authorization)
        path = (body.path or "").strip()
        if not path:
            raise HTTPException(status_code=400, detail={"error": "path is required"})

        def _restore():
            payload = state_backup.load_from_file(path)
            return state_backup.import_all(payload)

        report = await run_in_threadpool(_restore)
        return report.to_dict()

    @router.delete("/api/v1/backups/{filename}")
    async def delete_local_backup(filename: str, authorization: str | None = Header(default=None)):
        """Xóa một file backup local."""
        require_admin(authorization)
        ok = state_backup.delete_backup(filename)
        return {"ok": ok}

    # ── Health / Providers ──

    @router.get("/api/v1/health")
    async def system_health(authorization: str | None = Header(default=None)):
        """Trạng thái hệ thống: backends, providers, accounts."""
        require_admin(authorization)
        from services.account_service import account_service
        accounts = account_service.list_accounts()
        backoff_stats = rate_limit_backoff.get_stats()

        return {
            "status": "ok",
            "version": app_version,
            "accounts": {
                "total": len(accounts),
                "active": sum(1 for a in accounts if a.get("status") == "active"),
                "limited": sum(1 for a in accounts if a.get("status") == "limited"),
                "error": sum(1 for a in accounts if a.get("status") in ("error", "disabled")),
            },
            "backoff": backoff_stats,
            "quota_watcher": quota_watcher.get_stats(),
            "model_cooldown": model_cooldown.get_stats(),
            "opencode": {
                "available": opencode_provider.is_available,
            },
            "gemini": _check_gemini_status(),
        }

    @router.get("/api/v1/usage/stats")
    async def usage_stats(authorization: str | None = Header(default=None)):
        """Usage statistics: total requests, tokens, costs from actual usage log."""
        require_admin(authorization)
        from services.usage_tracker import get_usage_stats, get_active_providers
        stats = get_usage_stats()
        stats["activeProviders"] = get_active_providers()
        return stats

    @router.get("/api/v1/usage/recent")
    async def recent_requests(authorization: str | None = Header(default=None)):
        """Recent API requests from usage log."""
        require_admin(authorization)
        from services.usage_tracker import get_recent_requests
        return {"requests": get_recent_requests()}

    @router.get("/api/v1/providers")
    async def list_providers(authorization: str | None = Header(default=None)):
        """Danh sách provider đang active."""
        require_admin(authorization)
        provider_configs = config.data.get("providers") or {}

        providers = []
        for name, cfg in provider_configs.items():
            if isinstance(cfg, dict):
                providers.append({
                    "name": name,
                    "enabled": cfg.get("enabled", False),
                    "noAuth": cfg.get("noAuth", False),
                    "has_api_key": bool(cfg.get("api_key")),
                    "has_base_url": bool(cfg.get("base_url")),
                })

        return {"providers": providers}

    @router.get("/api/v1/providers/{provider_id}/models")
    async def provider_models(provider_id: str, authorization: str | None = Header(default=None)):
        """Lấy danh sách model của một provider."""
        require_admin(authorization)
        if provider_id == "opencode":
            models = opencode_provider.list_models()
            return {"models": models}
        return {"models": []}

    @router.post("/api/v1/providers/{provider_id}/test")
    async def test_provider(provider_id: str, authorization: str | None = Header(default=None)):
        """Test kết nối đến một provider."""
        require_admin(authorization)
        if provider_id == "opencode":
            available = opencode_provider.is_available
            return {"provider": provider_id, "available": available}
        if provider_id == "nvidia_nim":
            from services.providers.nvidia_nim import nvidia_nim_provider
            available = nvidia_nim_provider.is_available
            return {"provider": provider_id, "available": available}
        raise HTTPException(status_code=404, detail={"error": f"unknown provider: {provider_id}"})

    # ── OAuth Login ──

    @router.get("/api/oauth/codex/start")
    async def start_codex_oauth(request: Request, authorization: str | None = Header(default=None)):
        """Generate Codex OAuth URL for user to login."""
        require_admin(authorization)
        host = request.headers.get("host", "localhost:1455")
        scheme = "https" if request.url.scheme == "https" else "http"
        base = config.base_url or f"{scheme}://{host}"
        result = get_codex_auth_url(base)
        result["help"] = (
            "1. Mở URL trên trong browser. "
            "2. Đăng nhập và authorize. "
            "3. Sau khi redirect, copy TOÀN Bộ URL trên thanh địa chỉ. "
            "4. Dán URL đó vào POST /api/oauth/codex/exchange với body {\"redirect_url\": \"URL_DA_COPY\"}"
        )
        return result

    @router.get("/auth/callback")
    async def codex_auth_callback(code: str = "", state: str = ""):
        """Handle Codex OAuth callback (matches 9router path)."""
        if not code or not state:
            raise HTTPException(status_code=400, detail={"error": "Missing code or state"})
        try:
            result = exchange_codex_code(code, state)
            return HTMLResponse(content=f"""
            <html><body style="font-family:sans-serif;padding:40px;text-align:center">
            <h2>{result['message']}</h2>
            <p>Bạn có thể đóng tab này.</p>
            <script>setTimeout(function(){{window.close()}},3000)</script>
            </body></html>
            """)
        except Exception as exc:
            return HTMLResponse(content=f"""
            <html><body style="font-family:sans-serif;padding:40px;text-align:center">
            <h2 style="color:red">Lỗi: {str(exc)}</h2>
            <p>Copy URL này và dùng API exchange thủ công.</p>
            </body></html>
            """, status_code=400)

    @router.get("/api/oauth/codex/callback")
    async def codex_oauth_callback(code: str = "", state: str = ""):
        """Handle Codex OAuth callback — exchange code for token."""
        if not code or not state:
            raise HTTPException(status_code=400, detail={"error": "Missing code or state"})
        try:
            result = exchange_codex_code(code, state)
            return HTMLResponse(content=f"""
            <html><body style="font-family:sans-serif;padding:40px;text-align:center">
            <h2>{result['message']}</h2>
            <p>Bạn có thể đóng tab này.</p>
            <script>setTimeout(function(){{window.close()}},3000)</script>
            </body></html>
            """)
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)})

    @router.post("/api/oauth/codex/exchange")
    async def codex_oauth_exchange(body: CodexExchangeRequest, authorization: str | None = Header(default=None)):
        """Exchange Codex OAuth code manually — user pastes redirect URL."""
        require_admin(authorization)
        from urllib.parse import urlparse, parse_qs
        url = (body.redirect_url or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail={"error": "redirect_url is required"})
        # Replace localhost with actual host if needed
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        code = (params.get("code") or [""])[0]
        state = (params.get("state") or [""])[0]
        if not code or not state:
            raise HTTPException(status_code=400, detail={"error": "URL không chứa code và state. Copy TOÀN Bộ URL sau khi redirect."})
        try:
            result = exchange_codex_code(code, state)
            return result
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)})

    # ── Antigravity Google OAuth Login ──

    @router.get("/api/oauth/antigravity/start")
    async def start_antigravity_oauth(request: Request, authorization: str | None = Header(default=None)):
        """Generate Antigravity Google OAuth URL for user to login."""
        require_admin(authorization)
        from services.oauth_service import get_antigravity_auth_url
        result = get_antigravity_auth_url()
        result["help"] = (
            "1. Mở URL trên trong browser. "
            "2. Đăng nhập Google và cấp quyền. "
            "3. Sau khi redirect, copy TOÀN BỘ URL trên thanh địa chỉ (có dạng http://localhost:8080/callback?code=...). "
            "4. Dán URL đó vào POST /api/oauth/antigravity/exchange với body {\"redirect_url\": \"URL_DA_COPY\"}"
        )
        return result

    @router.post("/api/oauth/antigravity/exchange")
    async def antigravity_oauth_exchange(body: AntigravityExchangeRequest, authorization: str | None = Header(default=None)):
        """Exchange Antigravity Google OAuth code manually — user pastes redirect URL."""
        require_admin(authorization)
        from urllib.parse import urlparse, parse_qs
        from services.oauth_service import exchange_antigravity_code
        url = (body.redirect_url or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail={"error": "redirect_url is required"})
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        code = (params.get("code") or [""])[0]
        state = (params.get("state") or [""])[0]
        if not code or not state:
            raise HTTPException(status_code=400, detail={"error": "URL không chứa code và state. Copy TOÀN BỘ URL sau khi redirect."})
        try:
            result = exchange_antigravity_code(code, state)
            return result
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)})

    @router.get("/api/oauth/session-url")
    async def get_session_url(authorization: str | None = Header(default=None)):
        """Return chatgpt.com session URL for getting image token."""
        require_admin(authorization)
        return {"url": get_chatgpt_session_url()}

    @router.post("/api/oauth/detect-token")
    async def detect_token(body: dict, authorization: str | None = Header(default=None)):
        """Detect token type (codex vs google)."""
        require_admin(authorization)
        token = str(body.get("token") or "").strip()
        if not token:
            raise HTTPException(status_code=400, detail={"error": "token is required"})
        return {"type": detect_token_type(token)}

    # ── Custom Providers ──

    @router.get("/api/v1/custom-providers")
    async def list_custom_providers(authorization: str | None = Header(default=None)):
        """Lấy danh sách custom providers."""
        require_admin(authorization)
        from services.providers.custom_openai import get_custom_providers
        return {"custom_providers": get_custom_providers()}

    @router.post("/api/v1/custom-providers")
    async def save_custom_provider(body: dict, authorization: str | None = Header(default=None)):
        """Thêm hoặc cập nhật một custom provider."""
        require_admin(authorization)
        provider = body.get("provider") or {}
        if not isinstance(provider, dict):
            raise HTTPException(status_code=400, detail={"error": "provider object is required"})

        provider_id = str(provider.get("prefix") or provider.get("name") or "").strip().lower().replace(" ", "_")
        if not provider_id:
            raise HTTPException(status_code=400, detail={"error": "provider prefix or name is required"})

        base_url = str(provider.get("base_url") or "").strip().rstrip("/")
        api_key = str(provider.get("api_key") or "").strip()
        api_keys = provider.get("api_keys") or []
        if not isinstance(api_keys, list):
            api_keys = []
        api_keys = [k.strip() for k in api_keys if k.strip()]
        # Support api_key + api_keys combination
        if api_key and api_key not in api_keys:
            api_keys.insert(0, api_key)
        name = str(provider.get("name") or provider_id).strip()
        enabled = provider.get("enabled", True)
        prefix = str(provider.get("prefix") or provider_id).strip().lower().replace(" ", "_")

        # Validate: test connection with first key
        test_key = api_keys[0] if api_keys else api_key
        if not test_key:
            raise HTTPException(status_code=400, detail={"error": "At least one API key is required"})
        try:
            from curl_cffi import requests as cffi_req
            resp = cffi_req.get(
                f"{base_url}/v1/models",
                headers={"Authorization": f"Bearer {test_key}"},
                timeout=10,
            )
            if resp.status_code >= 400:
                raise HTTPException(
                    status_code=400,
                    detail={"error": f"Cannot connect to {base_url}: HTTP {resp.status_code}"},
                )
        except Exception as exc:
            if not isinstance(exc, HTTPException):
                raise HTTPException(
                    status_code=400,
                    detail={"error": f"Cannot connect to {base_url}: {exc}"},
                )
            raise

        # Save to config
        custom_providers = dict(config.data.get("custom_providers") or {})
        if not isinstance(custom_providers, dict):
            custom_providers = {}
        custom_providers[provider_id] = {
            "name": name,
            "base_url": base_url,
            "api_key": api_keys[0] if api_keys else "",
            "api_keys": api_keys,
            "prefix": prefix,
            "enabled": enabled,
        }
        config.data["custom_providers"] = custom_providers
        config._save()
        from services.protocol.openai_v1_models import invalidate_models_cache
        invalidate_models_cache()

        return {
            "custom_providers": custom_providers,
            "saved": True,
            "provider_id": provider_id,
        }

    @router.delete("/api/v1/custom-providers/{provider_id}")
    async def delete_custom_provider(provider_id: str, authorization: str | None = Header(default=None)):
        """Xóa một custom provider."""
        require_admin(authorization)
        custom_providers = dict(config.data.get("custom_providers") or {})
        if not isinstance(custom_providers, dict):
            custom_providers = {}
        if provider_id in custom_providers:
            del custom_providers[provider_id]
            config.data["custom_providers"] = custom_providers
            config._save()
            from services.protocol.openai_v1_models import invalidate_models_cache
            invalidate_models_cache()
            return {"deleted": True, "provider_id": provider_id}
        raise HTTPException(status_code=404, detail={"error": f"provider '{provider_id}' not found"})

    # ── Model Settings ──

    @router.get("/api/v1/model-settings")
    async def get_model_settings(authorization: str | None = Header(default=None)):
        """Lấy cấu hình model (enabled models + defaults per provider)."""
        require_admin(authorization)
        ms = config.data.get("model_settings") or {}
        if not isinstance(ms, dict):
            ms = {}
        return {
            "model_settings": {
                "enabled_models": ms.get("enabled_models") or {},
                "default_models": ms.get("default_models") or {},
            }
        }

    @router.get("/api/v1/available-models")
    async def get_available_models(authorization: str | None = Header(default=None), refresh: str = ""):
        """Lấy toàn bộ model có sẵn từ cache (nhanh). Thêm ?refresh=true để tải lại."""
        require_admin(authorization)
        from services.protocol.openai_v1_models import list_models
        force = refresh.lower() == "true"
        result = list_models(force_refresh=force, apply_filter=False)
        # Group models by owned_by
        grouped: dict[str, list[str]] = {}
        for item in result.get("data", []):
            owner = str(item.get("owned_by") or "chatgpt")
            mid = str(item.get("id") or "").strip()
            if mid:
                if owner not in grouped:
                    grouped[owner] = []
                grouped[owner].append(mid)
        # Sort each group
        for owner in grouped:
            grouped[owner].sort()
        return {"providers": grouped}

    @router.get("/api/v1/models-with-capabilities")
    async def get_models_with_capabilities(authorization: str | None = Header(default=None)):
        """Lấy danh sách model kèm phân loại capability (chat/vision/image)."""
        require_admin(authorization)
        from utils.helper import classify_model_capability, get_model_capability_label

        # Get enabled models from model_settings
        ms = config.data.get("model_settings") or {}
        if not isinstance(ms, dict):
            ms = {}
        enabled_by_provider = ms.get("enabled_models") or {}
        if not isinstance(enabled_by_provider, dict):
            enabled_by_provider = {}

        # Fetch all available models (unfiltered — UI decides what to show)
        from services.protocol.openai_v1_models import list_models
        result = list_models(apply_filter=False)
        all_models = result.get("data", [])

        enriched: list[dict] = []
        for model in all_models:
            mid = str(model.get("id") or "").strip()
            if not mid:
                continue
            caps = classify_model_capability(mid)
            enriched.append({
                "id": mid,
                "owned_by": str(model.get("owned_by") or ""),
                "capability": caps[0] if caps else "chat",  # Primary capability
                "capabilities": caps,  # All capabilities
                "capability_labels": [get_model_capability_label(c) for c in caps],
                "enabled": _is_model_enabled(mid, enabled_by_provider),
            })

        # Sort: chat first, then vision, then image, then video
        def _sort_key(m):
            caps = m.get("capabilities", ["chat"])
            if "video" in caps: return 3
            if "image" in caps: return 2
            if "vision" in caps: return 1
            return 0
        enriched.sort(key=lambda m: (_sort_key(m), m["id"]))

        return {
            "models": enriched,
            "counts": {
                "chat": sum(1 for m in enriched if "chat" in (m.get("capabilities") or ["chat"])),
                "vision": sum(1 for m in enriched if "vision" in (m.get("capabilities") or [])),
                "image": sum(1 for m in enriched if "image" in (m.get("capabilities") or [])),
                "video": sum(1 for m in enriched if "video" in (m.get("capabilities") or [])),
            },
        }

    @router.post("/api/v1/model-settings")
    async def save_model_settings(body: dict, authorization: str | None = Header(default=None)):
        """Lưu cấu hình model."""
        require_admin(authorization)
        model_settings = body.get("model_settings")
        if not isinstance(model_settings, dict):
            raise HTTPException(status_code=400, detail={"error": "model_settings is required"})
        enabled = model_settings.get("enabled_models")
        defaults = model_settings.get("default_models")
        if not isinstance(enabled, dict):
            enabled = {}
        if not isinstance(defaults, dict):
            defaults = {}
        config.data["model_settings"] = {
            "enabled_models": enabled,
            "default_models": defaults,
        }
        config._save()
        from services.protocol.openai_v1_models import invalidate_models_cache
        invalidate_models_cache()
        return {"model_settings": config.data["model_settings"], "saved": True}

    return router
