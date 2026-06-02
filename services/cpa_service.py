"""CLIProxyAPI integration for browsing remote auth files and importing selected tokens."""

from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from curl_cffi.requests import Session

from services.account_service import account_service
from services.config import DATA_DIR
from services.proxy_service import proxy_settings


CPA_CONFIG_FILE = DATA_DIR / "cpa_config.json"


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
        except (json.JSONDecodeError, OSError):
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

        add_result = account_service.add_accounts(tokens, source_type="codex")
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
