from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Condition, Lock
from typing import Any
from datetime import datetime

from services.config import config
from services.log_service import (
    LOG_TYPE_ACCOUNT,
    log_service,
)
from services.rate_limit_backoff import rate_limit_backoff
from services.storage.base import StorageBackend
from utils.helper import anonymize_token
from utils.log import logger

# Token audience values for routing
_TOKEN_AUDIENCE_CHATGPT = "chatgpt.com"
_TOKEN_AUDIENCE_OPENAI_API = "api.openai.com"


def detect_token_audience(access_token: str) -> str:
    """Decode JWT to determine which API the token works with."""
    if not access_token or not access_token.startswith("eyJ"):
        return "unknown"
    try:
        import base64, json
        parts = access_token.split(".")
        if len(parts) >= 2:
            # Fix base64 padding: JWT uses base64url without padding
            padded = parts[1] + "=" * (-len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded))
            aud = payload.get("aud", "")
            if isinstance(aud, list):
                aud = aud[0] if aud else ""
            aud_str = str(aud).lower()
            if "api.openai.com" in aud_str:
                return _TOKEN_AUDIENCE_OPENAI_API
            if "chatgpt.com" in aud_str:
                return _TOKEN_AUDIENCE_CHATGPT
    except Exception:
        pass
    return "unknown"

# Status migration: Chinese → English (backward compatible)
_STATUS_MIGRATION = {
    "正常": "active",
    "限流": "limited",
    "异常": "error",
    "禁用": "disabled",
}
_STATUS_REVERSE = {v: k for k, v in _STATUS_MIGRATION.items()}

DISPLAY_STATUS = {
    "active": "Hoạt động",
    "limited": "Giới hạn",
    "error": "Lỗi",
    "disabled": "Vô hiệu",
}


# NoAuth providers — virtual connections (port from 9router FREE_PROVIDERS)
NO_AUTH_PROVIDERS = {"opencode"}


class AccountService:
    """账号池服务，使用 token -> account 的 dict 保存账号。"""

    def __init__(self, storage_backend: StorageBackend):
        self.storage = storage_backend
        self._lock = Lock()
        self._image_slot_condition = Condition(self._lock)
        self._index = 0
        self._accounts = self._load_accounts()
        self._image_inflight: dict[str, int] = {}

    def _load_accounts(self) -> dict[str, dict]:
        accounts = self.storage.load_accounts()
        return {
            normalized["access_token"]: normalized
            for item in accounts
            if (normalized := self._normalize_account(item)) is not None
        }

    def _save_accounts(self) -> None:
        self.storage.save_accounts(list(self._accounts.values()))

    @staticmethod
    def _is_image_account_available(account: dict) -> bool:
        if not isinstance(account, dict):
            return False
        if account.get("status") in {"disabled", "limited", "error"}:
            return False
        if "antigravity" in str(account.get("type") or "").split(","):
            return False
        if bool(account.get("image_quota_unknown")):
            return True
        return int(account.get("quota") or 0) > 0

    def _normalize_account(self, item: dict) -> dict | None:
        if not isinstance(item, dict):
            return None
        access_token = item.get("access_token") or ""
        if not access_token:
            return None
        normalized = dict(item)
        normalized["access_token"] = access_token
        normalized["type"] = normalized.get("type") or "free"
        normalized["plan"] = normalized.get("plan") or None
        normalized["audience"] = normalized.get("audience") or detect_token_audience(access_token)
        # Auto-migrate Chinese status to English
        raw_status = normalized.get("status") or "active"
        normalized["status"] = _STATUS_MIGRATION.get(raw_status, raw_status)
        normalized["quota"] = max(0, int(normalized.get("quota") if normalized.get("quota") is not None else 0))
        normalized["image_quota_unknown"] = bool(normalized.get("image_quota_unknown"))
        normalized["email"] = normalized.get("email") or None
        normalized["user_id"] = normalized.get("user_id") or None
        limits_progress = normalized.get("limits_progress")
        normalized["limits_progress"] = limits_progress if isinstance(limits_progress, list) else []
        normalized["default_model_slug"] = normalized.get("default_model_slug") or None
        normalized["restore_at"] = normalized.get("restore_at") or None
        normalized["project_id"] = normalized.get("project_id") or None
        normalized["success"] = int(normalized.get("success") or 0)
        normalized["fail"] = int(normalized.get("fail") or 0)
        normalized["last_used_at"] = normalized.get("last_used_at")
        return normalized

    def list_tokens(self) -> list[str]:
        with self._lock:
            return list(self._accounts)

    def _list_ready_candidate_tokens(self, excluded_tokens: set[str] | None = None) -> list[str]:
        excluded = set(excluded_tokens or set())
        return [
            token
            for item in self._accounts.values()
            if self._is_image_account_available(item)
               and (token := item.get("access_token") or "")
               and token not in excluded
        ]

    def _list_available_candidate_tokens(self, excluded_tokens: set[str] | None = None) -> list[str]:
        max_concurrency = max(1, int(config.image_account_concurrency or 1))
        return [
            token
            for token in self._list_ready_candidate_tokens(excluded_tokens)
            if int(self._image_inflight.get(token, 0)) < max_concurrency
        ]

    def _acquire_next_candidate_token(self, excluded_tokens: set[str] | None = None) -> str:
        with self._image_slot_condition:
            while True:
                if not self._list_ready_candidate_tokens(excluded_tokens):
                    raise RuntimeError("no available image quota")
                tokens = self._list_available_candidate_tokens(excluded_tokens)
                if tokens:
                    access_token = tokens[self._index % len(tokens)]
                    self._index += 1
                    self._image_inflight[access_token] = int(self._image_inflight.get(access_token, 0)) + 1
                    return access_token
                self._image_slot_condition.wait(timeout=1.0)

    def release_image_slot(self, access_token: str) -> None:
        if not access_token:
            return
        with self._image_slot_condition:
            current_inflight = int(self._image_inflight.get(access_token, 0))
            if current_inflight <= 1:
                self._image_inflight.pop(access_token, None)
            else:
                self._image_inflight[access_token] = current_inflight - 1
            self._image_slot_condition.notify_all()

    def get_available_access_token(self) -> str:
        attempted_tokens: set[str] = set()
        while True:
            access_token = self._acquire_next_candidate_token(excluded_tokens=attempted_tokens)
            attempted_tokens.add(access_token)
            try:
                account = self.fetch_remote_info(access_token, "get_available_access_token")
            except Exception:
                self.release_image_slot(access_token)
                continue
            if self._is_image_account_available(account or {}):
                return access_token
            self.release_image_slot(access_token)

    def get_text_access_token(
        self,
        excluded_tokens: set[str] | None = None,
        account_type: str | None = None,
    ) -> str:
        """Priority-FIFO selection. Optionally filter to one account type.

        Codex and ChatGPT-free are separate logical pools — each maintains
        its own #1 because demote_account() moves items within the shared
        ordered dict but type-filtered iteration only sees its own type.
        Pass `account_type="free"` for ChatGPT-free only, `"codex"` for
        codex JWT only, or omit (default) to scan any non-antigravity type
        — the chatgpt provider auto-routes by token format after selection.
        """
        excluded = set(excluded_tokens or set())
        with self._lock:
            for account in self._accounts.values():
                status = account.get("status")
                if status in {"disabled", "error", "limited"}:
                    continue
                types = str(account.get("type") or "").split(",")
                if "antigravity" in types:
                    continue
                if account_type and account_type not in types:
                    continue
                token = account.get("access_token") or ""
                if not token or token in excluded:
                    continue
                return token
            return ""

    def mark_text_used(self, access_token: str) -> None:
        if not access_token:
            return
        with self._lock:
            current = self._accounts.get(access_token)
            if current is None:
                return
            next_item = dict(current)
            next_item["last_used_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            account = self._normalize_account(next_item)
            if account is None:
                return
            self._accounts[access_token] = account
            self._save_accounts()

    def remove_invalid_token(self, access_token: str, event: str) -> bool:
        if not config.auto_remove_invalid_accounts:
            self.update_account(access_token, {"status": "error", "quota": 0})
            return False
        removed = bool(self.delete_accounts([access_token])["removed"])
        if removed:
            log_service.add(LOG_TYPE_ACCOUNT, "Tự động xóa tài khoản lỗi",
                            {"source": event, "token": anonymize_token(access_token)})
        elif access_token:
            self.update_account(access_token, {"status": "error", "quota": 0})
        return removed

    def get_account(self, access_token: str) -> dict | None:
        if not access_token:
            return None
        with self._lock:
            account = self._accounts.get(access_token)
            return dict(account) if account else None

    def demote_account(self, access_token: str) -> None:
        """Move this account to the END of the ordered pool.

        Used after a 429/quota burn so the next request lands on a fresh
        account at the front of the queue. When the demoted account is
        auto-restored later, it stays at the back until older accounts
        also fail and rotate down — guaranteeing "always prefer #1" with
        FIFO demotion, exactly the rotation the user asked for.

        No-op if the token isn't in the pool.
        """
        if not access_token:
            return
        with self._lock:
            current = self._accounts.pop(access_token, None)
            if current is None:
                return
            self._accounts[access_token] = current  # re-insert at tail
            self._save_accounts()

    def promote_account(self, access_token: str) -> None:
        """Move this account to the FRONT of the ordered pool.

        Inverse of demote_account — used after an explicit user action
        ("set this account as primary") or by quota_watcher when an
        account is auto-restored and you want it back at #1.
        """
        if not access_token:
            return
        with self._lock:
            current = self._accounts.pop(access_token, None)
            if current is None:
                return
            new_accounts = {access_token: current}
            new_accounts.update(self._accounts)
            self._accounts = new_accounts
            self._save_accounts()

    def list_accounts(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._accounts.values()]

    def find_by_refresh_token(self, refresh_token: str) -> dict | None:
        """Return the account dict matching a given refresh_token, or None.

        Used by token-refresh code paths that hold a per-token mutex: once a
        thread finishes refreshing, a second thread that was waiting on the
        same mutex can re-read the account here and observe the fresh
        access_token instead of issuing another OAuth call (which would
        trigger refresh-token rotation race and brick the account).
        """
        if not refresh_token:
            return None
        with self._lock:
            for account in self._accounts.values():
                if account.get("refresh_token") == refresh_token:
                    return dict(account)
        return None

    def list_limited_tokens(self) -> list[str]:
        with self._lock:
            return [
                token
                for item in self._accounts.values()
                if item.get("status") == "limited"
                   and (token := item.get("access_token") or "")
            ]

    def add_accounts(self, tokens: list[str]) -> dict:
        tokens = list(dict.fromkeys(token for token in tokens if token))
        if not tokens:
            return {"added": 0, "skipped": 0, "items": self.list_accounts()}

        with self._lock:
            added = 0
            skipped = 0
            for access_token in tokens:
                current = self._accounts.get(access_token)
                if current is None:
                    added += 1
                    current = {}
                else:
                    skipped += 1
                account = self._normalize_account(
                    {
                        **current,
                        "access_token": access_token,
                        "type": str(current.get("type") or "free"),
                    }
                )
                if account is not None:
                    self._accounts[access_token] = account
            self._save_accounts()
            items = [dict(item) for item in self._accounts.values()]
            log_service.add(LOG_TYPE_ACCOUNT, f"新增 {added}  tài khoản，跳过 {skipped} 个",
                            {"added": added, "skipped": skipped})
        return {"added": added, "skipped": skipped, "items": items}

    def add_accounts_with_type(self, tokens: list[str], account_type: str = "codex") -> dict:
        """Add accounts with a specific type (e.g. 'codex' for 9router OAuth tokens)."""
        tokens = list(dict.fromkeys(token for token in tokens if token))
        if not tokens:
            return {"added": 0, "skipped": 0, "items": self.list_accounts()}

        with self._lock:
            added = 0
            skipped = 0
            updated = 0
            for access_token in tokens:
                current = self._accounts.get(access_token)
                if current is not None:
                    # Merge type: add new type to existing (e.g. existing "free" + new "codex" → "free,codex")
                    existing_types = set(str(current.get("type") or "").split(","))
                    new_types = set(str(account_type).split(","))
                    merged = ",".join(sorted(existing_types | new_types))
                    if merged != str(current.get("type") or ""):
                        current["type"] = merged
                        updated += 1
                        logger.info({"event": "account_type_merged", "token": anonymize_token(access_token), "new_type": merged})
                    else:
                        skipped += 1
                    continue
                added += 1
                account = self._normalize_account({
                    "access_token": access_token,
                    "type": account_type,
                    "status": "active",
                })
                if account is not None:
                    self._accounts[access_token] = account
            self._save_accounts()
            items = [dict(item) for item in self._accounts.values()]
            log_service.add(LOG_TYPE_ACCOUNT, f"Thêm {added} tài khoản {account_type}, cập nhật {updated}, bỏ qua {skipped}",
                            {"added": added, "skipped": skipped, "updated": updated, "type": account_type})
        return {"added": added, "skipped": skipped, "updated": updated, "items": items}

    def add_accounts_with_credentials(self, creds: list[dict], account_type: str = "codex") -> dict:
        """Add Codex OAuth accounts with full credential payload (access + refresh + expiry).

        Each cred dict accepts: access_token (required), refresh_token, expires_at.
        Existing accounts are merged: refresh_token / expires_at are updated even
        when the access_token already exists, so older imports get refreshable.
        """
        added = 0
        skipped = 0
        updated = 0
        with self._lock:
            for cred in creds or []:
                if not isinstance(cred, dict):
                    continue
                access_token = str(cred.get("access_token") or "").strip()
                if not access_token:
                    continue
                refresh_token = str(cred.get("refresh_token") or "").strip() or None
                expires_at = cred.get("expires_at") or None
                current = self._accounts.get(access_token)
                if current is None:
                    added += 1
                    base = {"access_token": access_token, "type": account_type, "status": "active"}
                else:
                    base = dict(current)
                    existing_types = set(str(base.get("type") or "").split(","))
                    new_types = set(str(account_type).split(","))
                    base["type"] = ",".join(sorted(existing_types | new_types))
                    skipped += 1
                if refresh_token:
                    base["refresh_token"] = refresh_token
                    updated += 1
                if expires_at:
                    base["expires_at"] = expires_at
                if cred.get("project_id"):
                    base["project_id"] = cred["project_id"]
                if cred.get("email"):
                    base["email"] = cred["email"]
                account = self._normalize_account(base)
                if account is not None:
                    self._accounts[access_token] = account
            self._save_accounts()
            items = [dict(item) for item in self._accounts.values()]
            log_service.add(
                LOG_TYPE_ACCOUNT,
                f"Thêm {added} tài khoản {account_type} có refresh, cập nhật {updated}, bỏ qua {skipped}",
                {"added": added, "skipped": skipped, "updated": updated, "type": account_type},
            )
        return {"added": added, "skipped": skipped, "updated": updated, "items": items}

    def delete_accounts(self, tokens: list[str]) -> dict:
        target_set = set(token for token in tokens if token)
        if not target_set:
            return {"removed": 0, "items": self.list_accounts()}
        with self._lock:
            removed = sum(self._accounts.pop(token, None) is not None for token in target_set)
            for token in target_set:
                self._image_inflight.pop(token, None)
            if removed:
                if self._accounts:
                    self._index %= len(self._accounts)
                else:
                    self._index = 0
                self._save_accounts()
                log_service.add(LOG_TYPE_ACCOUNT, f"删除 {removed}  tài khoản", {"removed": removed})
            items = [dict(item) for item in self._accounts.values()]
        return {"removed": removed, "items": items}

    def update_account(self, access_token: str, updates: dict) -> dict | None:
        if not access_token:
            return None
        with self._lock:
            current = self._accounts.get(access_token)
            if current is None:
                return None
            account = self._normalize_account({**current, **updates, "access_token": access_token})
            if account is None:
                return None
            if account.get("status") == "limited" and config.auto_remove_rate_limited_accounts:
                self._accounts.pop(access_token, None)
                self._save_accounts()
                log_service.add(LOG_TYPE_ACCOUNT, "Tự động xóa tài khoản giới hạn", {"token": anonymize_token(access_token)})
                return None
            self._accounts[access_token] = account
            self._save_accounts()
            log_service.add(LOG_TYPE_ACCOUNT, "Cập nhật tài khoản",
                            {"token": anonymize_token(access_token), "status": account.get("status")})
            return dict(account)
        return None

    def mark_image_result(self, access_token: str, success: bool) -> dict | None:
        if not access_token:
            return None
        self.release_image_slot(access_token)
        with self._lock:
            current = self._accounts.get(access_token)
            if current is None:
                return None
            next_item = dict(current)
            next_item["last_used_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            image_quota_unknown = bool(next_item.get("image_quota_unknown"))
            if success:
                next_item["success"] = int(next_item.get("success") or 0) + 1
                if not image_quota_unknown:
                    next_item["quota"] = max(0, int(next_item.get("quota") or 0) - 1)
                if not image_quota_unknown and next_item["quota"] == 0:
                    next_item["status"] = "limited"
                    next_item["restore_at"] = next_item.get("restore_at") or None
                elif next_item.get("status") == "limited":
                    next_item["status"] = "active"
            else:
                next_item["fail"] = int(next_item.get("fail") or 0) + 1
            account = self._normalize_account(next_item)
            if account is None:
                return None
            if account.get("status") == "limited" and config.auto_remove_rate_limited_accounts:
                self._accounts.pop(access_token, None)
                self._save_accounts()
                log_service.add(LOG_TYPE_ACCOUNT, "Tự động xóa tài khoản giới hạn", {"token": anonymize_token(access_token)})
                return None
            self._accounts[access_token] = account
            self._save_accounts()
            return dict(account)
        return None

    def fetch_remote_info(self, access_token: str, event: str = "fetch_remote_info") -> dict[str, Any] | None:
        if not access_token:
            raise ValueError("access_token is required")

        try:
            from services.openai_backend_api import InvalidAccessTokenError, OpenAIBackendAPI
            result = OpenAIBackendAPI(access_token).get_user_info()
        except InvalidAccessTokenError:
            # Token can't access chatgpt.com — keep existing data, don't set error
            logger.info({"event": "fetch_remote_401_skip", "token": anonymize_token(access_token)})
            return self.get_account(access_token)
        except Exception as exc:
            msg = str(exc).lower()
            if any(k in msg for k in ("openssl", "tls", "invalid library", "curl: (35)")):
                logger.warning({"event": "fetch_remote_tls_skip", "token": anonymize_token(access_token), "error": str(exc)[:120]})
                return self.get_account(access_token)
            raise
        return self.update_account(access_token, result)

    def refresh_accounts(self, access_tokens: list[str]) -> dict[str, Any]:
        access_tokens = list(dict.fromkeys(token for token in access_tokens if token))
        if not access_tokens:
            return {"refreshed": 0, "errors": [], "items": self.list_accounts()}

        refreshed = 0
        errors = []
        max_workers = min(10, len(access_tokens))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.fetch_remote_info, token, "refresh_accounts"): token
                for token in access_tokens
            }
            for future in as_completed(futures):
                try:
                    account = future.result()
                except Exception as exc:
                    errors.append({"token": anonymize_token(futures[future]), "error": str(exc)})
                    continue
                if account is not None:
                    refreshed += 1

        return {
            "refreshed": refreshed,
            "errors": errors,
            "items": self.list_accounts(),
        }


    def get_health_score(self, access_token: str) -> float:
        """Calculate health score for an account (0.0-1.0).

        Ported from 9router health scoring pattern:
        - 0.35: rate-limit status
        - 0.20: response latency (placeholder)
        - 0.20: concurrency saturation
        - 0.15: token last used recency
        - 0.10: success/fail ratio
        """
        account = self.get_account(access_token)
        if not account:
            return 0.0

        score = 0.0

        # Rate-limit status (0.35)
        status = str(account.get("status") or "active")
        if status == "active":
            score += 0.35
        elif status == "limited":
            score += 0.0
        else:
            score += 0.1

        # Concurrency saturation (0.20)
        max_conc = max(1, int(config.image_account_concurrency or 1))
        inflight = int(self._image_inflight.get(access_token, 0))
        saturation = inflight / max_conc
        score += (1 - saturation) * 0.20

        # Token recency (0.15)
        last_used = account.get("last_used_at")
        if last_used:
            try:
                from datetime import datetime
                last_dt = datetime.strptime(str(last_used), "%Y-%m-%d %H:%M:%S")
                age_minutes = (datetime.now() - last_dt).total_seconds() / 60
                if age_minutes < 5:
                    score += 0.15
                elif age_minutes < 30:
                    score += 0.10
                else:
                    score += 0.03
            except (ValueError, TypeError):
                score += 0.05
        else:
            score += 0.05

        # Success/fail ratio (0.10)
        success = int(account.get("success") or 0)
        fail = int(account.get("fail") or 0)
        total = success + fail
        if total > 0:
            score += (success / total) * 0.10
        else:
            score += 0.05

        # Latency placeholder (0.20) — default to mid-range
        score += 0.10

        return max(0.0, min(1.0, score))

    def get_provider_credentials(
        self,
        provider_id: str,
        exclude_connection_ids: set[str] | None = None,
        model: str = "",
    ) -> dict[str, Any] | None:
        """Get credentials for a provider, supporting noAuth virtual connections.

        Ported from 9router src/sse/services/auth.js getProviderCredentials().
        Returns None if no credentials available.

        For noAuth providers (opencode): returns a virtual connection with
        id="noauth" and accessToken="public".
        """
        # Check for noAuth provider first (port from 9router FREE_PROVIDERS check)
        if provider_id in NO_AUTH_PROVIDERS:
            return {
                "id": "noauth",
                "connectionName": "Public",
                "isActive": True,
                "accessToken": "public",
                "noAuth": True,
            }

        # For chatgpt provider, use existing token pool
        if provider_id == "chatgpt":
            token = self.get_text_access_token(exclude_connection_ids)
            if not token:
                return None
            return {
                "id": anonymize_token(token),
                "connectionName": "ChatGPT",
                "isActive": True,
                "accessToken": token,
                "noAuth": False,
            }

        return None

    def is_noauth_provider(self, provider_id: str) -> bool:
        """Check if a provider uses noAuth virtual connections."""
        return provider_id in NO_AUTH_PROVIDERS


account_service = AccountService(config.get_storage_backend())
