"""Sub2API integration for browsing and importing ChatGPT OAuth accounts from a sub2api admin."""

from __future__ import annotations

import base64
import json
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from curl_cffi.requests import Session

from services.account_service import account_service
from services.config import DATA_DIR
from services.log_service import LOG_TYPE_ACCOUNT, log_service


SUB2API_CONFIG_FILE = DATA_DIR / "sub2api_config.json"
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


# Cached JWT per server to avoid re-login on every list/import call.
# Token lifetime on sub2api defaults to 24h; we refresh 5 min before expiry.
_TOKEN_REFRESH_SKEW = 5 * 60


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: object) -> str:
    return str(value or "").strip()


def _normalize_import_job(raw: object, *, fail_unfinished: bool) -> dict | None:
    if not isinstance(raw, dict):
        return None
    status = _clean(raw.get("status")) or "failed"
    if fail_unfinished and status in {"pending", "running"}:
        status = "failed"
    return {
        "job_id": _clean(raw.get("job_id")) or uuid.uuid4().hex,
        "status": status,
        "created_at": _clean(raw.get("created_at")) or _now_iso(),
        "updated_at": _clean(raw.get("updated_at")) or _clean(raw.get("created_at")) or _now_iso(),
        "total": int(raw.get("total") or 0),
        "completed": int(raw.get("completed") or 0),
        "added": int(raw.get("added") or 0),
        "skipped": int(raw.get("skipped") or 0),
        "refreshed": int(raw.get("refreshed") or 0),
        "failed": int(raw.get("failed") or 0),
        "errors": raw.get("errors") if isinstance(raw.get("errors"), list) else [],
    }


def _normalize_server(raw: dict) -> dict:
    return {
        "id": _clean(raw.get("id")) or _new_id(),
        "name": _clean(raw.get("name")),
        "base_url": _clean(raw.get("base_url")),
        "email": _clean(raw.get("email")),
        "password": _clean(raw.get("password")),
        "api_key": _clean(raw.get("api_key")),
        "group_id": _clean(raw.get("group_id")),
        "import_job": _normalize_import_job(raw.get("import_job"), fail_unfinished=True),
    }


class Sub2APIConfig:
    def __init__(self, store_file: Path):
        self._store_file = store_file
        self._lock = Lock()
        self._servers: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if not self._store_file.exists():
            return []
        try:
            raw = json.loads(self._store_file.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return [_normalize_server(item) for item in raw if isinstance(item, dict)]
        except Exception:
            pass
        return []

    def _save(self) -> None:
        self._store_file.parent.mkdir(parents=True, exist_ok=True)
        self._store_file.write_text(
            json.dumps(self._servers, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def list_servers(self) -> list[dict]:
        with self._lock:
            return [dict(server) for server in self._servers]

    def get_server(self, server_id: str) -> dict | None:
        with self._lock:
            for server in self._servers:
                if server["id"] == server_id:
                    return dict(server)
        return None

    def add_server(
        self,
        *,
        name: str,
        base_url: str,
        email: str,
        password: str,
        api_key: str,
        group_id: str = "",
    ) -> dict:
        server = _normalize_server({
            "id": _new_id(),
            "name": name,
            "base_url": base_url,
            "email": email,
            "password": password,
            "api_key": api_key,
            "group_id": group_id,
        })
        with self._lock:
            self._servers.append(server)
            self._save()
        _token_cache.pop(server["id"], None)
        return dict(server)

    def update_server(self, server_id: str, updates: dict) -> dict | None:
        with self._lock:
            for index, server in enumerate(self._servers):
                if server["id"] != server_id:
                    continue
                merged = {**server, **{k: v for k, v in updates.items() if v is not None}, "id": server_id}
                self._servers[index] = _normalize_server(merged)
                self._save()
                result = dict(self._servers[index])
                break
            else:
                return None
        _token_cache.pop(server_id, None)
        return result

    def delete_server(self, server_id: str) -> bool:
        with self._lock:
            before = len(self._servers)
            self._servers = [server for server in self._servers if server["id"] != server_id]
            removed = len(self._servers) < before
            if removed:
                self._save()
        if removed:
            _token_cache.pop(server_id, None)
        return removed

    def set_import_job(self, server_id: str, import_job: dict | None) -> dict | None:
        with self._lock:
            for index, server in enumerate(self._servers):
                if server["id"] != server_id:
                    continue
                next_server = dict(server)
                next_server["import_job"] = _normalize_import_job(import_job, fail_unfinished=False)
                self._servers[index] = next_server
                self._save()
                return dict(next_server)
        return None

    def get_import_job(self, server_id: str) -> dict | None:
        with self._lock:
            for server in self._servers:
                if server["id"] == server_id:
                    job = server.get("import_job")
                    return dict(job) if isinstance(job, dict) else None
        return None


# Per-server cached access token: {server_id: (jwt, expires_at_epoch)}
_token_cache: dict[str, tuple[str, float]] = {}
_token_cache_lock = Lock()


def _login(base_url: str, email: str, password: str) -> tuple[str, float]:
    url = f"{base_url.rstrip('/')}/api/v1/auth/login"
    session = Session(verify=True)
    try:
        response = session.post(
            url,
            json={"email": email, "password": password},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"sub2api login failed: HTTP {response.status_code} {response.text[:200]}")
        payload = response.json()
    finally:
        session.close()

    body = _unwrap_envelope(payload)
    if not isinstance(body, dict):
        raise RuntimeError("sub2api login payload is invalid")

    token = _clean(body.get("access_token"))
    if not token:
        raise RuntimeError("sub2api login did not return access_token")

    expires_in = int(body.get("expires_in") or 3600)
    expires_at = time.time() + max(60, expires_in) - _TOKEN_REFRESH_SKEW
    return token, expires_at


def _auth_headers(server: dict) -> dict[str, str]:
    api_key = _clean(server.get("api_key"))
    if api_key:
        return {"x-api-key": api_key, "Accept": "application/json"}

    email = _clean(server.get("email"))
    password = _clean(server.get("password"))
    if not email or not password:
        raise RuntimeError("sub2api server requires email+password or api_key")

    server_id = _clean(server.get("id"))
    base_url = _clean(server.get("base_url"))

    with _token_cache_lock:
        cached = _token_cache.get(server_id)
        if cached and cached[1] > time.time():
            return {"Authorization": f"Bearer {cached[0]}", "Accept": "application/json"}

    token, expires_at = _login(base_url, email, password)
    with _token_cache_lock:
        _token_cache[server_id] = (token, expires_at)
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _extract_access_token(credentials: object) -> str:
    if not isinstance(credentials, dict):
        return ""
    for key in ("access_token", "accessToken", "token"):
        value = _clean(credentials.get(key))
        if value:
            return value
    return ""


def _unwrap_envelope(payload: object) -> object:
    """Peel sub2api's `{code, message, data}` envelope, returning the inner `data` field
    when present. Also handles unwrapped responses from older/alt versions."""
    if isinstance(payload, dict) and "data" in payload and "code" in payload:
        return payload.get("data")
    return payload


def _extract_paged_items(payload: object) -> tuple[list, int]:
    """Return (items, total) from a paginated sub2api response.

    Handles both the wrapped shape `{code,data:{items,total,...}}` and a few looser
    variants (`{data:[...]}`, `[...]`, `{items:[...],total:N}`)."""
    inner = _unwrap_envelope(payload)
    if isinstance(inner, list):
        return inner, len(inner)
    if isinstance(inner, dict):
        for key in ("items", "data", "list"):
            value = inner.get(key)
            if isinstance(value, list):
                return value, int(inner.get("total") or len(value))
    return [], 0


def list_remote_accounts(server: dict) -> list[dict]:
    """Return a flat list of OpenAI OAuth accounts from a sub2api server."""
    base_url = _clean(server.get("base_url"))
    if not base_url:
        return []

    headers = _auth_headers(server)
    group_id = _clean(server.get("group_id"))

    session = Session(verify=True)
    items: list[dict] = []
    try:
        page = 1
        while True:
            params: dict[str, object] = {
                "platform": "openai",
                "type": "oauth",
                "page": page,
                "page_size": 200,
            }
            if group_id:
                params["group"] = group_id
            response = session.get(
                f"{base_url.rstrip('/')}/api/v1/admin/accounts",
                headers=headers,
                params=params,
                timeout=30,
            )
            if not response.ok:
                raise RuntimeError(f"sub2api list failed: HTTP {response.status_code} {response.text[:200]}")
            payload = response.json()

            data, total = _extract_paged_items(payload)
            if not data:
                break

            for account in data:
                if not isinstance(account, dict):
                    continue
                credentials = account.get("credentials") if isinstance(account.get("credentials"), dict) else {}
                access_token = _extract_access_token(credentials)
                if not access_token:
                    continue
                account_id = account.get("id")
                items.append({
                    "id": str(account_id) if account_id is not None else _clean(credentials.get("chatgpt_account_id")),
                    "name": _clean(account.get("name")),
                    "email": _clean(credentials.get("email")) or _clean(account.get("name")),
                    "plan_type": _clean(credentials.get("plan_type")),
                    "status": _clean(account.get("status")),
                    "expires_at": _clean(credentials.get("expires_at")),
                    "has_refresh_token": bool(_clean(credentials.get("refresh_token"))),
                })

            if page * 200 >= total or len(data) < 200:
                break
            page += 1
    finally:
        session.close()

    return items


def list_remote_groups(server: dict) -> list[dict]:
    """Return OpenAI account groups from a sub2api server."""
    base_url = _clean(server.get("base_url"))
    if not base_url:
        return []

    headers = _auth_headers(server)

    session = Session(verify=True)
    items: list[dict] = []
    try:
        page = 1
        while True:
            response = session.get(
                f"{base_url.rstrip('/')}/api/v1/admin/groups",
                headers=headers,
                params={
                    "page": page,
                    "page_size": 200,
                },
                timeout=30,
            )
            if not response.ok:
                raise RuntimeError(f"sub2api groups failed: HTTP {response.status_code} {response.text[:200]}")
            payload = response.json()

            data, total = _extract_paged_items(payload)
            if not data:
                break

            for group in data:
                if not isinstance(group, dict):
                    continue
                group_id = group.get("id")
                if group_id is None:
                    continue
                items.append({
                    "id": str(group_id),
                    "name": _clean(group.get("name")),
                    "description": _clean(group.get("description")),
                    "platform": _clean(group.get("platform")),
                    "status": _clean(group.get("status")),
                    "account_count": int(group.get("account_count") or 0),
                    "active_account_count": int(group.get("active_account_count") or 0),
                })

            if page * 200 >= total or len(data) < 200:
                break
            page += 1
    finally:
        session.close()

    return items


def _fetch_access_token_for_account(server: dict, account_id: str) -> tuple[str, dict]:
    """Return (access_token, account_meta) for a single sub2api account id."""
    base_url = _clean(server.get("base_url"))
    headers = _auth_headers(server)

    session = Session(verify=True)
    try:
        response = session.get(
            f"{base_url.rstrip('/')}/api/v1/admin/accounts/{account_id}",
            headers=headers,
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}")
        payload = response.json()
    finally:
        session.close()

    account = _unwrap_envelope(payload)
    if not isinstance(account, dict):
        account = payload if isinstance(payload, dict) else {}
    credentials = account.get("credentials") if isinstance(account.get("credentials"), dict) else {}
    access_token = _extract_access_token(credentials)
    if not access_token:
        raise RuntimeError("missing access_token")
    return access_token, {
        "email": _clean(credentials.get("email")),
        "plan_type": _clean(credentials.get("plan_type")),
    }


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    token = _clean(token)
    if not token:
        return {}
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _first_text(*values: object) -> str:
    for value in values:
        text = _clean(value)
        if text:
            return text
    return ""


def _b64url_json(payload: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).rstrip(b"=").decode("ascii")


def _inject_codex_identity_into_id_token(id_token: str, *, email: str, chatgpt_account_id: str, chatgpt_user_id: str, plan_type: str = "") -> str:
    id_token = str(id_token or "").strip()
    chatgpt_account_id = str(chatgpt_account_id or "").strip()
    if not id_token or not chatgpt_account_id:
        return id_token
    try:
        parts = id_token.split(".")
        if len(parts) != 3:
            return id_token
        header_segment, payload_segment, signature_segment = parts
        payload_segment += "=" * (-len(payload_segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_segment.encode("utf-8")).decode("utf-8"))
        if not isinstance(payload, dict):
            return id_token
        payload["aud"] = [CODEX_OAUTH_CLIENT_ID]
        payload["azp"] = CODEX_OAUTH_CLIENT_ID
        if email:
            payload["email"] = email
        auth_payload = payload.get("https://api.openai.com/auth")
        if not isinstance(auth_payload, dict):
            auth_payload = {}
        auth_payload["chatgpt_account_id"] = chatgpt_account_id
        if chatgpt_user_id:
            auth_payload["chatgpt_user_id"] = chatgpt_user_id
            auth_payload["user_id"] = chatgpt_user_id
        if plan_type:
            auth_payload["chatgpt_plan_type"] = str(plan_type).lower()
        payload["https://api.openai.com/auth"] = auth_payload
        return f"{header_segment}.{_b64url_json(payload)}.{signature_segment or 'sig'}"
    except Exception:
        return id_token

def _claim_from_payload(payload: dict[str, Any], *names: str) -> str:
    if not isinstance(payload, dict):
        return ""
    auth = payload.get("https://api.openai.com/auth")
    profile = payload.get("https://api.openai.com/profile")
    for scope in (auth, profile):
        if isinstance(scope, dict):
            for name in names:
                value = _first_text(scope.get(name))
                if value:
                    return value
    for name in names:
        for key in (name, f"https://api.openai.com/auth.{name}", f"https://api.openai.com/profile.{name}"):
            value = _first_text(payload.get(key))
            if value:
                return value
    return ""


def _token_exp_epoch(*tokens: str) -> int | None:
    for token in tokens:
        payload = _decode_jwt_payload(token)
        try:
            exp = int(payload.get("exp") or 0)
        except Exception:
            exp = 0
        if exp > 0:
            return exp
    return None


def _is_chatgpt_account_id(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", _clean(value)))


def _is_chatgpt_user_id(value: str) -> bool:
    return _clean(value).startswith("user-")


def _extract_registered_identity(register_result: dict, local_account: dict | None = None) -> dict[str, str | int | None]:
    local_account = local_account or {}
    access_token = _clean(register_result.get("codex_access_token") or register_result.get("access_token"))
    id_token = _clean(register_result.get("codex_id_token") or register_result.get("id_token"))
    access_payload = _decode_jwt_payload(access_token)
    id_payload = _decode_jwt_payload(id_token)
    email = _first_text(register_result.get("email"), local_account.get("email"), _claim_from_payload(id_payload, "email"), _claim_from_payload(access_payload, "email"))
    chatgpt_account_id = _first_text(
        register_result.get("codex_chatgpt_account_id"),
        register_result.get("chatgpt_account_id"),
        local_account.get("chatgpt_account_id"),
        _claim_from_payload(id_payload, "chatgpt_account_id"),
        _claim_from_payload(access_payload, "chatgpt_account_id"),
    )
    existing_account_id = _first_text(register_result.get("account_id"), local_account.get("account_id"))
    if not chatgpt_account_id and _is_chatgpt_account_id(existing_account_id):
        chatgpt_account_id = existing_account_id
    chatgpt_user_id = _first_text(
        register_result.get("codex_chatgpt_user_id"),
        register_result.get("chatgpt_user_id"),
        local_account.get("chatgpt_user_id"),
        local_account.get("user_id"),
        _claim_from_payload(id_payload, "chatgpt_user_id", "user_id", "chatgpt_account_user_id"),
        _claim_from_payload(access_payload, "chatgpt_user_id", "user_id", "chatgpt_account_user_id"),
    )
    if not chatgpt_user_id and _is_chatgpt_user_id(existing_account_id):
        chatgpt_user_id = existing_account_id
    client_id = _first_text(register_result.get("codex_client_id"), register_result.get("client_id"), _claim_from_payload(access_payload, "client_id"), _claim_from_payload(id_payload, "azp", "client_id"), CODEX_OAUTH_CLIENT_ID)
    return {
        "email": email,
        "chatgpt_account_id": chatgpt_account_id,
        "chatgpt_user_id": chatgpt_user_id,
        "client_id": client_id,
        "expires_at": _token_exp_epoch(access_token, id_token),
    }


def _group_ids(server: dict) -> list[int]:
    raw = _clean(server.get("group_id"))
    if not raw:
        return []
    try:
        group_id = int(raw)
    except (TypeError, ValueError):
        return []
    return [group_id] if group_id > 0 else []


def _build_registered_account_payload(register_result: dict, local_account: dict | None = None) -> tuple[dict, str]:
    access_token = _clean(register_result.get("codex_access_token") or register_result.get("access_token"))
    refresh_token = _clean(register_result.get("codex_refresh_token") or register_result.get("refresh_token"))
    id_token = _clean(register_result.get("codex_id_token") or register_result.get("id_token"))
    if not access_token:
        raise ValueError("missing access_token")
    identity = _extract_registered_identity(register_result, local_account=local_account)
    email = _clean(identity.get("email"))
    chatgpt_account_id = _clean(identity.get("chatgpt_account_id"))
    chatgpt_user_id = _clean(identity.get("chatgpt_user_id"))
    client_id = CODEX_OAUTH_CLIENT_ID
    id_token = _inject_codex_identity_into_id_token(
        id_token,
        email=email,
        chatgpt_account_id=chatgpt_account_id,
        chatgpt_user_id=chatgpt_user_id,
        plan_type=_clean(local_account.get("chatgpt_plan_type") or local_account.get("type")),
    )
    id_payload = _decode_jwt_payload(id_token)
    id_claim_account_id = _claim_from_payload(id_payload, "chatgpt_account_id")
    if not _is_chatgpt_account_id(id_claim_account_id):
        raise ValueError("codex_id_token_missing_chatgpt_account_id")
    if not _is_chatgpt_account_id(chatgpt_account_id):
        chatgpt_account_id = id_claim_account_id
    credentials: dict[str, object] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "id_token": id_token,
        "email": email,
        "chatgpt_account_id": chatgpt_account_id,
        "chatgpt_user_id": chatgpt_user_id,
        "client_id": client_id,
        "session_token": _clean(register_result.get("session_token")),
    }
    expires_at = identity.get("expires_at")
    if isinstance(expires_at, int) and expires_at > 0:
        credentials["expires_at"] = expires_at
    credentials = {key: value for key, value in credentials.items() if value not in (None, "") or key == "session_token"}
    extra: dict[str, object] = {}
    if client_id == CODEX_OAUTH_CLIENT_ID:
        extra["codex_cli_only"] = True
    payload: dict[str, object] = {
        "name": email or chatgpt_account_id,
        "platform": "openai",
        "type": "oauth",
        "credentials": credentials,
        "concurrency": 10,
        "priority": 1,
        "group_ids": [],
        "auto_pause_on_expired": True,
    }
    if extra:
        payload["extra"] = extra
    if isinstance(expires_at, int) and expires_at > 0:
        payload["expires_at"] = expires_at
    return payload, email


def _list_sync_servers() -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    servers: list[dict] = []
    for server in sub2api_config.list_servers():
        base_url = _clean(server.get("base_url")).rstrip("/")
        auth_key = _clean(server.get("api_key")) or f"{_clean(server.get('email'))}:{_clean(server.get('password'))}"
        group_id = _clean(server.get("group_id"))
        if not base_url or not auth_key:
            continue
        key = (base_url, auth_key, group_id)
        if key in seen:
            continue
        seen.add(key)
        servers.append(server)
    return servers


def create_remote_account(server: dict, payload: dict) -> None:
    base_url = _clean(server.get("base_url"))
    if not base_url:
        raise ValueError("invalid sub2api server config")
    body = dict(payload)
    body["group_ids"] = _group_ids(server)
    headers = {**_auth_headers(server), "Content-Type": "application/json"}
    session = Session(verify=True)
    try:
        response = session.post(
            f"{base_url.rstrip('/')}/api/v1/admin/accounts",
            headers=headers,
            json=body,
            timeout=60,
        )
        if response.status_code == 409:
            try:
                conflict = response.json()
            except Exception:
                conflict = {}
            if isinstance(conflict, dict) and conflict.get("error") == "mixed_channel_warning":
                body["confirm_mixed_channel_risk"] = True
                response = session.post(
                    f"{base_url.rstrip('/')}/api/v1/admin/accounts",
                    headers=headers,
                    json=body,
                    timeout=60,
                )
        if not response.ok:
            raise RuntimeError(f"sub2api create failed: HTTP {response.status_code} {response.text[:200]}")
    finally:
        session.close()


def sync_registered_account_to_sub2api(register_result: dict, local_account: dict | None = None) -> dict[str, Any]:
    servers = _list_sync_servers()
    summary: dict[str, Any] = {
        "attempted": len(servers),
        "succeeded": 0,
        "failed": 0,
        "email": "",
        "errors": [],
    }
    if not servers:
        return summary
    payload, email = _build_registered_account_payload(register_result, local_account=local_account)
    summary["email"] = email
    for server in servers:
        server_name = _clean(server.get("name")) or _clean(server.get("base_url")) or _clean(server.get("id"))
        try:
            create_remote_account(server, payload)
            summary["succeeded"] += 1
            log_service.add(LOG_TYPE_ACCOUNT, "Sub2API自动同步成功", {"server": server_name, "email": email})
        except Exception as exc:
            summary["failed"] += 1
            error_text = str(exc)
            summary["errors"].append({"server": server_name, "error": error_text})
            log_service.add(LOG_TYPE_ACCOUNT, "Sub2API自动同步失败", {"server": server_name, "email": email, "error": error_text})
    return summary


class Sub2APIImportService:
    def __init__(self, sub2api_config: Sub2APIConfig):
        self._config = sub2api_config

    def start_import(self, server: dict, account_ids: list[str]) -> dict:
        ids = [_clean(item) for item in account_ids if _clean(item)]
        if not ids:
            raise ValueError("account ids is required")

        server_id = _clean(server.get("id"))
        job = {
            "job_id": uuid.uuid4().hex,
            "status": "pending",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "total": len(ids),
            "completed": 0,
            "added": 0,
            "skipped": 0,
            "refreshed": 0,
            "failed": 0,
            "errors": [],
        }
        saved = self._config.set_import_job(server_id, job)
        if saved is None:
            raise ValueError("server not found")

        thread = threading.Thread(
            target=self._run_import,
            args=(server_id, server, ids),
            name=f"sub2api-import-{server_id}",
            daemon=True,
        )
        thread.start()
        return dict(saved.get("import_job") or job)

    def _update_job(self, server_id: str, **updates) -> None:
        current = self._config.get_import_job(server_id)
        if current is None:
            return
        next_job = {**current, **updates, "updated_at": _now_iso()}
        self._config.set_import_job(server_id, next_job)

    def _append_error(self, server_id: str, account_id: str, message: str) -> None:
        current = self._config.get_import_job(server_id)
        if current is None:
            return
        errors = list(current.get("errors") or [])
        errors.append({"name": account_id, "error": message})
        self._update_job(server_id, errors=errors, failed=len(errors))

    def _run_import(self, server_id: str, server: dict, account_ids: list[str]) -> None:
        self._update_job(server_id, status="running")

        tokens: list[str] = []
        max_workers = min(8, max(1, len(account_ids)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_fetch_access_token_for_account, server, account_id): account_id
                for account_id in account_ids
            }
            for future in as_completed(future_map):
                account_id = future_map[future]
                try:
                    token, _meta = future.result()
                    tokens.append(token)
                except Exception as exc:
                    self._append_error(server_id, account_id, str(exc) or "unknown error")

                current = self._config.get_import_job(server_id) or {}
                failed = len(current.get("errors") or [])
                self._update_job(
                    server_id,
                    completed=int(current.get("completed") or 0) + 1,
                    failed=failed,
                )

        if not tokens:
            current = self._config.get_import_job(server_id) or {}
            self._update_job(
                server_id,
                status="failed",
                completed=int(current.get("total") or 0),
                failed=len(current.get("errors") or []),
            )
            return

        add_result = account_service.add_accounts(tokens)
        refresh_result = account_service.refresh_accounts(tokens)
        current = self._config.get_import_job(server_id) or {}
        self._update_job(
            server_id,
            status="completed",
            completed=len(account_ids),
            added=int(add_result.get("added") or 0),
            skipped=int(add_result.get("skipped") or 0),
            refreshed=int(refresh_result.get("refreshed") or 0),
            failed=len(current.get("errors") or []),
        )


sub2api_config = Sub2APIConfig(SUB2API_CONFIG_FILE)
sub2api_import_service = Sub2APIImportService(sub2api_config)
