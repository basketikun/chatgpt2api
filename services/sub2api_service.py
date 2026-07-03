"""Sub2API integration for browsing and importing ChatGPT OAuth accounts from a sub2api admin."""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from curl_cffi.requests import Session

from services.account_service import account_service
from services.config import DATA_DIR


SUB2API_CONFIG_FILE = DATA_DIR / "sub2api_config.json"

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
                account_id = account.get("id")
                if account_id is None:
                    continue
                items.append({
                    "id": str(account_id),
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


def _fetch_access_tokens_for_accounts(server: dict, account_ids: list[str]) -> tuple[list[str], list[dict]]:
    """Return exported access tokens and per-account errors from sub2api."""
    base_url = _clean(server.get("base_url"))
    headers = _auth_headers(server)
    ids = [_clean(item) for item in account_ids if _clean(item)]
    if not ids:
        return [], []

    session = Session(verify=True)
    try:
        response = session.get(
            f"{base_url.rstrip('/')}/api/v1/admin/accounts/data",
            headers=headers,
            params={"ids": ",".join(ids), "timezone": "Asia/Shanghai"},
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}")
        payload = response.json()
    finally:
        session.close()

    data = _unwrap_envelope(payload)
    accounts = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(accounts, list):
        raise RuntimeError("invalid export payload")

    tokens: list[str] = []
    errors: list[dict] = []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        credentials = account.get("credentials") if isinstance(account.get("credentials"), dict) else {}
        token = _extract_access_token(credentials)
        account_id = _clean(account.get("id")) or _clean(credentials.get("chatgpt_account_id")) or _clean(account.get("name"))
        if token:
            tokens.append(token)
        else:
            errors.append({"name": account_id or _clean(account.get("name")) or "unknown", "error": "missing access_token"})

    if len(accounts) < len(ids):
        errors.append({"name": ",".join(ids), "error": f"exported {len(accounts)}/{len(ids)} accounts"})

    return tokens, errors


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

        try:
            tokens, errors = _fetch_access_tokens_for_accounts(server, account_ids)
        except Exception as exc:
            message = str(exc) or "unknown error"
            for account_id in account_ids:
                self._append_error(server_id, account_id, message)
            tokens = []
        else:
            for error in errors:
                self._append_error(server_id, _clean(error.get("name")), _clean(error.get("error")) or "unknown error")

        current = self._config.get_import_job(server_id) or {}
        self._update_job(
            server_id,
            completed=len(account_ids),
            failed=len(current.get("errors") or []),
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

        add_result = account_service.add_accounts(tokens, source_type="codex")
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
