from __future__ import annotations

from pathlib import Path
from threading import Event, Thread
import time

from fastapi import HTTPException, Request

from services.account_service import account_service
from services.auth_service import auth_service
from services.config import config

BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIST_DIR = BASE_DIR / "web_dist"


def extract_bearer_token(authorization: str | None) -> str:
    scheme, _, value = str(authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return ""
    return value.strip()


def _legacy_admin_identity(token: str) -> dict[str, object] | None:
    auth_key = str(config.auth_key or "").strip()
    if auth_key and token == auth_key:
        return {"id": "admin", "name": "管理员", "role": "admin"}
    return None


def require_identity(authorization: str | None) -> dict[str, object]:
    token = extract_bearer_token(authorization)
    identity = _legacy_admin_identity(token) or auth_service.authenticate(token)
    if identity is None:
        raise HTTPException(status_code=401, detail={"error": "密钥无效或已失效，请重新登录"})
    return identity


def require_auth_key(authorization: str | None) -> None:
    require_identity(authorization)


def require_admin(authorization: str | None) -> dict[str, object]:
    identity = require_identity(authorization)
    if identity.get("role") != "admin":
        raise HTTPException(status_code=403, detail={"error": "需要管理员权限才能执行这个操作"})
    return identity


def resolve_image_base_url(request: Request) -> str:
    return config.base_url or f"{request.url.scheme}://{request.headers.get('host', request.url.netloc)}"


def raise_image_quota_error(exc: Exception) -> None:
    message = str(exc)
    if "no available image quota" in message.lower():
        raise HTTPException(status_code=429, detail={"error": "no available image quota"}) from exc
    raise HTTPException(status_code=502, detail={"error": message}) from exc


def sanitize_cpa_pool(pool: dict | None) -> dict | None:
    if not isinstance(pool, dict):
        return None
    return {key: value for key, value in pool.items() if key != "secret_key"}


def sanitize_cpa_pools(pools: list[dict]) -> list[dict]:
    return [sanitized for pool in pools if (sanitized := sanitize_cpa_pool(pool)) is not None]


def sanitize_sub2api_server(server: dict | None) -> dict | None:
    if not isinstance(server, dict):
        return None
    sanitized = {key: value for key, value in server.items() if key not in {"password", "api_key"}}
    sanitized["has_api_key"] = bool(str(server.get("api_key") or "").strip())
    return sanitized


def sanitize_sub2api_servers(servers: list[dict]) -> list[dict]:
    return [sanitized for server in servers if (sanitized := sanitize_sub2api_server(server)) is not None]


def start_limited_account_watcher(stop_event: Event) -> Thread:
    def worker() -> None:
        last_refresh_at = 0.0
        last_free_cleanup_at = 0.0
        while not stop_event.is_set():
            refresh_interval_seconds = max(60, config.refresh_account_interval_minute * 60)
            free_cleanup_settings = config.get_free_account_cleanup_settings()
            free_cleanup_enabled = bool(free_cleanup_settings.get("enabled"))
            free_cleanup_interval_seconds = max(60, int(free_cleanup_settings.get("interval_minutes") or 10) * 60)
            now = time.monotonic()
            try:
                if now - last_refresh_at >= refresh_interval_seconds:
                    limited_tokens = account_service.list_limited_tokens()
                    normal_tokens = account_service.list_normal_tokens()
                    expiring_tokens = account_service.list_expiring_access_tokens()
                    keepalive_tokens = account_service.list_refresh_token_keepalive_tokens()
                    tokens = list(dict.fromkeys([*limited_tokens, *normal_tokens, *expiring_tokens]))
                    expiring_token_set = set(expiring_tokens)
                    keepalive_tokens = [token for token in keepalive_tokens if token not in expiring_token_set]
                    if tokens:
                        print(
                            "[account-watcher] checking "
                            f"{len(limited_tokens)} limited accounts, "
                            f"{len(normal_tokens)} normal accounts, "
                            f"{len(expiring_tokens)} expiring access tokens"
                        )
                        account_service.refresh_accounts(tokens)
                    if keepalive_tokens:
                        print(f"[account-watcher] keepalive {len(keepalive_tokens)} refresh tokens")
                        result = account_service.keepalive_refresh_tokens(keepalive_tokens)
                        if result.get("errors"):
                            print(f"[account-watcher] keepalive errors: {result['errors']}")
                    last_refresh_at = now
                if free_cleanup_enabled and now - last_free_cleanup_at >= free_cleanup_interval_seconds:
                    result = account_service.refresh_normal_free_accounts("account_watcher_free_cleanup")
                    checked = int(result.get("checked") or 0)
                    if checked:
                        print(
                            "[account-watcher] free cleanup "
                            f"checked {checked} normal free accounts, "
                            f"refreshed {result.get('refreshed', 0)}, "
                            f"errors {len(result.get('errors') or [])}"
                        )
                    last_free_cleanup_at = now
            except Exception as exc:
                print(f"[account-watcher] fail {exc}")
                last_refresh_at = now
                if free_cleanup_enabled:
                    last_free_cleanup_at = now
            wait_candidates = [last_refresh_at + refresh_interval_seconds]
            if free_cleanup_enabled:
                wait_candidates.append(last_free_cleanup_at + free_cleanup_interval_seconds)
            wait_seconds = max(1.0, min(wait_candidates) - time.monotonic())
            stop_event.wait(wait_seconds)

    thread = Thread(target=worker, name="account-watcher", daemon=True)
    thread.start()
    return thread


def resolve_web_asset(requested_path: str) -> Path | None:
    if not WEB_DIST_DIR.exists():
        return None
    clean_path = requested_path.strip("/")
    base_dir = WEB_DIST_DIR.resolve()
    candidates = [base_dir / "index.html"] if not clean_path else [
        base_dir / Path(clean_path),
        base_dir / clean_path / "index.html",
        base_dir / f"{clean_path}.html",
    ]
    for candidate in candidates:
        try:
            candidate.resolve().relative_to(base_dir)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None
