"""CLIProxyAPI integration for browsing remote auth files and importing selected tokens."""

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

from curl_cffi import CurlMime
from curl_cffi.requests import Session

from services.account_service import account_service
from services.config import DATA_DIR
from services.log_service import LOG_TYPE_ACCOUNT, log_service
from services.proxy_service import proxy_settings


CPA_CONFIG_FILE = DATA_DIR / "cpa_config.json"
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"



def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_import_job(raw: object, *, fail_unfinished: bool) -> dict | None:
    if not isinstance(raw, dict):
        return None
    status = str(raw.get("status") or "failed").strip() or "failed"
    if fail_unfinished and status in {"pending", "running"}:
        status = "failed"
    return {
        "job_id": str(raw.get("job_id") or uuid.uuid4().hex).strip(),
        "status": status,
        "created_at": str(raw.get("created_at") or _now_iso()).strip() or _now_iso(),
        "updated_at": str(raw.get("updated_at") or raw.get("created_at") or _now_iso()).strip() or _now_iso(),
        "total": int(raw.get("total") or 0),
        "completed": int(raw.get("completed") or 0),
        "added": int(raw.get("added") or 0),
        "skipped": int(raw.get("skipped") or 0),
        "refreshed": int(raw.get("refreshed") or 0),
        "failed": int(raw.get("failed") or 0),
        "errors": raw.get("errors") if isinstance(raw.get("errors"), list) else [],
    }


def _normalize_pool(raw: dict) -> dict:
    return {
        "id": str(raw.get("id") or _new_id()).strip(),
        "name": str(raw.get("name") or "").strip(),
        "base_url": str(raw.get("base_url") or "").strip(),
        "secret_key": str(raw.get("secret_key") or "").strip(),
        "import_job": _normalize_import_job(raw.get("import_job"), fail_unfinished=True),
    }


def _management_headers(secret_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {secret_key}",
        "Accept": "application/json",
    }


class CPAConfig:
    def __init__(self, store_file: Path):
        self._store_file = store_file
        self._lock = Lock()
        self._pools: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if not self._store_file.exists():
            return []
        try:
            raw = json.loads(self._store_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "base_url" in raw:
                pool = _normalize_pool(raw)
                return [pool] if pool["base_url"] else []
            if isinstance(raw, list):
                return [_normalize_pool(item) for item in raw if isinstance(item, dict)]
        except Exception:
            pass
        return []

    def _save(self) -> None:
        self._store_file.parent.mkdir(parents=True, exist_ok=True)
        self._store_file.write_text(json.dumps(self._pools, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def list_pools(self) -> list[dict]:
        with self._lock:
            return [dict(pool) for pool in self._pools]

    def get_pool(self, pool_id: str) -> dict | None:
        with self._lock:
            for pool in self._pools:
                if pool["id"] == pool_id:
                    return dict(pool)
        return None

    def add_pool(self, name: str, base_url: str, secret_key: str) -> dict:
        pool = _normalize_pool({"id": _new_id(), "name": name, "base_url": base_url, "secret_key": secret_key})
        with self._lock:
            self._pools.append(pool)
            self._save()
        return dict(pool)

    def update_pool(self, pool_id: str, updates: dict) -> dict | None:
        with self._lock:
            for index, pool in enumerate(self._pools):
                if pool["id"] != pool_id:
                    continue
                merged = {**pool, **{key: value for key, value in updates.items() if value is not None}, "id": pool_id}
                self._pools[index] = _normalize_pool(merged)
                self._save()
                return dict(self._pools[index])
        return None

    def delete_pool(self, pool_id: str) -> bool:
        with self._lock:
            before = len(self._pools)
            self._pools = [pool for pool in self._pools if pool["id"] != pool_id]
            if len(self._pools) < before:
                self._save()
                return True
        return False

    def set_import_job(self, pool_id: str, import_job: dict | None) -> dict | None:
        with self._lock:
            for index, pool in enumerate(self._pools):
                if pool["id"] != pool_id:
                    continue
                next_pool = dict(pool)
                next_pool["import_job"] = _normalize_import_job(import_job, fail_unfinished=False)
                self._pools[index] = next_pool
                self._save()
                return dict(next_pool)
        return None

    def get_import_job(self, pool_id: str) -> dict | None:
        with self._lock:
            for pool in self._pools:
                if pool["id"] == pool_id:
                    job = pool.get("import_job")
                    return dict(job) if isinstance(job, dict) else None
        return None


def list_remote_files(pool: dict) -> list[dict]:
    base_url = str(pool.get("base_url") or "").strip()
    secret_key = str(pool.get("secret_key") or "").strip()
    if not base_url or not secret_key:
        return []

    url = f"{base_url.rstrip('/')}/v0/management/auth-files"
    session = Session(**proxy_settings.build_session_kwargs(verify=True))
    try:
        response = session.get(url, headers=_management_headers(secret_key), timeout=30)
        if not response.ok:
            raise RuntimeError(f"remote list failed: HTTP {response.status_code}")
        payload = response.json()
    finally:
        session.close()

    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list):
        raise RuntimeError("remote list payload is invalid")

    items: list[dict] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        email = str(item.get("email") or item.get("account") or "").strip()
        if not name:
            continue
        items.append({"name": name, "email": email})
    return items


def fetch_remote_access_token(pool: dict, file_name: str) -> tuple[str | None, str | None]:
    base_url = str(pool.get("base_url") or "").strip()
    secret_key = str(pool.get("secret_key") or "").strip()
    file_name = str(file_name or "").strip()
    if not base_url or not secret_key or not file_name:
        return None, "invalid request"

    url = f"{base_url.rstrip('/')}/v0/management/auth-files/download"
    session = Session(**proxy_settings.build_session_kwargs(verify=True))
    try:
        response = session.get(url, headers=_management_headers(secret_key), params={"name": file_name}, timeout=30)
        if not response.ok:
            return None, f"HTTP {response.status_code}"
        payload = response.json()
    except Exception as exc:
        return None, str(exc)
    finally:
        session.close()

    if not isinstance(payload, dict):
        return None, "invalid payload"

    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        return None, "missing access_token"
    return access_token, None


def _list_sync_pools() -> list[dict]:
    seen: set[tuple[str, str]] = set()
    pools: list[dict] = []
    for pool in cpa_config.list_pools():
        base_url = str(pool.get("base_url") or "").strip().rstrip("/")
        secret_key = str(pool.get("secret_key") or "").strip()
        if not base_url or not secret_key:
            continue
        key = (base_url, secret_key)
        if key in seen:
            continue
        seen.add(key)
        pools.append(pool)
    return pools


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    token = str(token or "").strip()
    if not token:
        return {}
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(__import__('base64').urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8"))
    except Exception:
        return {}


def _token_expired_at(*tokens: str) -> str | None:
    for token in tokens:
        payload = _decode_jwt_payload(token)
        try:
            exp = int(payload.get("exp") or 0)
        except Exception:
            exp = 0
        if exp > 0:
            return datetime.fromtimestamp(exp, timezone.utc).isoformat()
    return None


def _safe_filename_fragment(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    safe = safe.strip("._-")
    return safe or uuid.uuid4().hex


def _first_text(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
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
        for key in (
            name,
            f"https://api.openai.com/auth.{name}",
            f"https://api.openai.com/profile.{name}",
        ):
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
    value = str(value or "").strip()
    return bool(re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", value))


def _is_chatgpt_user_id(value: str) -> bool:
    return str(value or "").strip().startswith("user-")


def _extract_codex_identity(register_result: dict, local_account: dict | None = None) -> dict[str, str | int | None]:
    local_account = local_account or {}
    access_token = str(register_result.get("codex_access_token") or register_result.get("access_token") or "").strip()
    id_token = str(register_result.get("codex_id_token") or register_result.get("id_token") or "").strip()
    access_payload = _decode_jwt_payload(access_token)
    id_payload = _decode_jwt_payload(id_token)

    email = _first_text(
        register_result.get("email"),
        local_account.get("email"),
        _claim_from_payload(id_payload, "email"),
        _claim_from_payload(access_payload, "email"),
    )
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
    client_id = _first_text(
        register_result.get("codex_client_id"),
        register_result.get("client_id"),
        _claim_from_payload(access_payload, "client_id"),
        _claim_from_payload(id_payload, "azp", "client_id"),
        CODEX_OAUTH_CLIENT_ID,
    )
    return {
        "email": email,
        "chatgpt_account_id": chatgpt_account_id,
        "chatgpt_user_id": chatgpt_user_id,
        "account_id": chatgpt_account_id,
        "client_id": client_id,
        "expires_at": _token_exp_epoch(access_token, id_token),
    }


def _build_auth_file_payload(register_result: dict, local_account: dict | None = None) -> tuple[str, bytes, str]:
    local_account = local_account or {}
    access_token = str(register_result.get("codex_access_token") or register_result.get("access_token") or "").strip()
    refresh_token = str(register_result.get("codex_refresh_token") or register_result.get("refresh_token") or "").strip()
    id_token = str(register_result.get("codex_id_token") or register_result.get("id_token") or "").strip()
    if not access_token:
        raise ValueError("missing access_token")

    identity = _extract_codex_identity(register_result, local_account=local_account)
    email = str(identity.get("email") or "").strip()
    account_id = str(identity.get("account_id") or "").strip()
    chatgpt_account_id = str(identity.get("chatgpt_account_id") or "").strip()
    chatgpt_user_id = str(identity.get("chatgpt_user_id") or "").strip()
    client_id = CODEX_OAUTH_CLIENT_ID
    id_token = _inject_codex_identity_into_id_token(
        id_token,
        email=email,
        chatgpt_account_id=chatgpt_account_id,
        chatgpt_user_id=chatgpt_user_id,
        plan_type=str(local_account.get("chatgpt_plan_type") or local_account.get("type") or ""),
    )
    id_payload = _decode_jwt_payload(id_token)
    id_claim_account_id = _claim_from_payload(id_payload, "chatgpt_account_id")
    if not _is_chatgpt_account_id(id_claim_account_id):
        raise ValueError("codex_id_token_missing_chatgpt_account_id")
    if not _is_chatgpt_account_id(chatgpt_account_id):
        chatgpt_account_id = id_claim_account_id
        account_id = id_claim_account_id
    expired = _token_expired_at(access_token, id_token) or _now_iso()
    last_refresh = str(register_result.get("created_at") or _now_iso()).strip() or _now_iso()

    credentials = {
        "access_token": access_token,
        "id_token": id_token,
        "refresh_token": refresh_token,
        "session_token": str(register_result.get("session_token") or ""),
        "chatgpt_account_id": chatgpt_account_id,
        "chatgpt_user_id": chatgpt_user_id,
        "client_id": client_id,
    }
    credentials = {key: value for key, value in credentials.items() if value not in (None, "") or key == "session_token"}

    payload = {
        "access_token": access_token,
        "account_id": account_id,
        "chatgpt_account_id": chatgpt_account_id,
        "chatgpt_user_id": chatgpt_user_id,
        "credentials": credentials,
        "disabled": False,
        "email": email,
        "expired": expired,
        "id_token": id_token,
        "last_refresh": last_refresh,
        "refresh_token": refresh_token,
        "session_token": str(register_result.get("session_token") or ""),
        "type": "codex",
    }
    payload = {key: value for key, value in payload.items() if value not in (None, "") or key in {"disabled", "type", "session_token", "credentials"}}

    seed = email or account_id or chatgpt_user_id or uuid.uuid4().hex
    filename = f"codex-{_safe_filename_fragment(seed)}-{int(time.time() * 1000)}.json"
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return filename, content, email


def upload_auth_file(pool: dict, file_name: str, content: bytes) -> None:
    base_url = str(pool.get("base_url") or "").strip()
    secret_key = str(pool.get("secret_key") or "").strip()
    if not base_url or not secret_key:
        raise ValueError("invalid pool config")

    url = f"{base_url.rstrip('/')}/v0/management/auth-files"
    session = Session(**proxy_settings.build_session_kwargs(verify=True))
    multipart = CurlMime()
    multipart.addpart("files", filename=file_name, content_type="application/json", data=content)
    try:
        response = session.post(
            url,
            headers=_management_headers(secret_key),
            multipart=multipart,
            timeout=60,
        )
        if not response.ok:
            raise RuntimeError(f"remote upload failed: HTTP {response.status_code} {response.text[:200]}")
        try:
            payload = response.json()
        except Exception:
            payload = {}
        status = str(payload.get("status") or "ok").strip().lower() if isinstance(payload, dict) else "ok"
        if status not in {"ok", "success"}:
            raise RuntimeError(f"remote upload failed: {payload}")
    finally:
        multipart.close()
        session.close()


def sync_registered_account_to_pools(register_result: dict, local_account: dict | None = None) -> dict[str, Any]:
    pools = _list_sync_pools()
    summary: dict[str, Any] = {
        "attempted": len(pools),
        "succeeded": 0,
        "failed": 0,
        "filename": "",
        "errors": [],
    }
    if not pools:
        return summary

    file_name, content, email = _build_auth_file_payload(register_result, local_account=local_account)
    summary["filename"] = file_name
    for pool in pools:
        pool_name = str(pool.get("name") or pool.get("base_url") or pool.get("id") or "").strip()
        try:
            upload_auth_file(pool, file_name, content)
            summary["succeeded"] += 1
            log_service.add(
                LOG_TYPE_ACCOUNT,
                "CPA自动同步成功",
                {"pool": pool_name, "filename": file_name, "email": email},
            )
        except Exception as exc:
            summary["failed"] += 1
            error_text = str(exc)
            summary["errors"].append({"pool": pool_name, "error": error_text})
            log_service.add(
                LOG_TYPE_ACCOUNT,
                "CPA自动同步失败",
                {"pool": pool_name, "filename": file_name, "email": email, "error": error_text},
            )
    return summary


class CPAImportService:
    def __init__(self, cpa_config: CPAConfig):
        self._config = cpa_config

    def start_import(self, pool: dict, selected_files: list[str]) -> dict:
        names = [str(name or "").strip() for name in selected_files if str(name or "").strip()]
        if not names:
            raise ValueError("selected files is required")

        pool_id = str(pool.get("id") or "").strip()
        job = {
            "job_id": uuid.uuid4().hex,
            "status": "pending",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "total": len(names),
            "completed": 0,
            "added": 0,
            "skipped": 0,
            "refreshed": 0,
            "failed": 0,
            "errors": [],
        }
        saved_pool = self._config.set_import_job(pool_id, job)
        if saved_pool is None:
            raise ValueError("pool not found")

        thread = threading.Thread(
            target=self._run_import,
            args=(pool_id, pool, names),
            name=f"cpa-import-{pool_id}",
            daemon=True,
        )
        thread.start()
        return dict(saved_pool.get("import_job") or job)

    def _update_job(self, pool_id: str, **updates) -> dict | None:
        current = self._config.get_import_job(pool_id)
        if current is None:
            return None
        next_job = {**current, **updates, "updated_at": _now_iso()}
        pool = self._config.set_import_job(pool_id, next_job)
        if pool is None:
            return None
        job = pool.get("import_job")
        return dict(job) if isinstance(job, dict) else None

    def _append_error(self, pool_id: str, file_name: str, message: str) -> None:
        current = self._config.get_import_job(pool_id)
        if current is None:
            return
        errors = list(current.get("errors") or [])
        errors.append({"name": file_name, "error": message})
        self._update_job(pool_id, errors=errors, failed=len(errors))

    def _run_import(self, pool_id: str, pool: dict, names: list[str]) -> None:
        self._update_job(pool_id, status="running")

        tokens: list[str] = []
        max_workers = min(16, max(1, len(names)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(fetch_remote_access_token, pool, name): name for name in names}
            for future in as_completed(future_map):
                file_name = future_map[future]
                try:
                    token, error = future.result()
                except Exception as exc:
                    token, error = None, str(exc)

                if token:
                    tokens.append(token)
                else:
                    self._append_error(pool_id, file_name, error or "unknown error")

                current = self._config.get_import_job(pool_id) or {}
                failed = len(current.get("errors") or [])
                self._update_job(pool_id, completed=int(current.get("completed") or 0) + 1, failed=failed)

        if not tokens:
            current = self._config.get_import_job(pool_id) or {}
            self._update_job(
                pool_id,
                status="failed",
                completed=int(current.get("total") or 0),
                failed=len(current.get("errors") or []),
            )
            return

        add_result = account_service.add_accounts(tokens)
        refresh_result = account_service.refresh_accounts(tokens)
        current = self._config.get_import_job(pool_id) or {}
        self._update_job(
            pool_id,
            status="completed",
            completed=len(names),
            added=int(add_result.get("added") or 0),
            skipped=int(add_result.get("skipped") or 0),
            refreshed=int(refresh_result.get("refreshed") or 0),
            failed=len(current.get("errors") or []),
        )


cpa_config = CPAConfig(CPA_CONFIG_FILE)
cpa_import_service = CPAImportService(cpa_config)
