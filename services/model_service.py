from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from threading import Condition, RLock, Thread
from typing import Any

from services.account_service import AccountService, account_service
from services.openai_backend_api import OpenAIBackendAPI
from utils.log import logger


@dataclass(frozen=True)
class ModelRoute:
    access_tokens: frozenset[str]
    allow_anonymous: bool = False


class ModelUnavailableError(RuntimeError):
    status_code = 400

    def __init__(self, model: str) -> None:
        self.model = str(model or "").strip()
        super().__init__(f"model {self.model!r} is not available to any active account")

    def to_openai_error(self) -> dict[str, Any]:
        return {
            "error": {
                "message": str(self),
                "type": "invalid_request_error",
                "param": "model",
                "code": "model_not_available",
            }
        }


class ModelCatalogService:
    """Caches the model catalog advertised by each active account."""

    def __init__(
        self,
        accounts: AccountService,
        *,
        backend_factory: Callable[..., Any] = OpenAIBackendAPI,
        cache_ttl_seconds: float = 300,
        clock: Callable[[], float] = time.monotonic,
        max_workers: int = 4,
        max_pending_requests: int = 32,
        request_timeout_seconds: float = 10,
        initial_wait_seconds: float = 15,
    ) -> None:
        self._accounts = accounts
        self._backend_factory = backend_factory
        self._cache_ttl_seconds = max(1.0, float(cache_ttl_seconds))
        self._clock = clock
        self._max_workers = max(1, int(max_workers))
        self._max_pending_requests = max(
            self._max_workers,
            int(max_pending_requests),
        )
        self._request_timeout_seconds = max(1.0, float(request_timeout_seconds))
        self._initial_wait_seconds = max(0.0, float(initial_wait_seconds))
        self._lock = RLock()
        self._condition = Condition(self._lock)
        self._expires_at = 0.0
        self._account_signature: tuple[tuple[str, str], ...] = ()
        self._anonymous_models: dict[str, dict[str, Any]] = {}
        self._models_by_access_token: dict[str, dict[str, dict[str, Any]]] = {}
        self._initialized = False
        self._refreshing = False

    @staticmethod
    def _model_map(result: object) -> dict[str, dict[str, Any]]:
        if not isinstance(result, dict) or not isinstance(result.get("data"), list):
            raise TypeError("upstream model response has no data list")
        models: dict[str, dict[str, Any]] = {}
        for item in result["data"]:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if model_id and model_id not in models:
                models[model_id] = dict(item)
        return models

    def _active_accounts_by_type(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for account in self._accounts.list_accounts():
            if not isinstance(account, dict) or account.get("status") in {"禁用", "异常"}:
                continue
            access_token = str(account.get("access_token") or "").strip()
            account_type = self._accounts._normalize_account_type(account.get("type"))
            if access_token and account_type:
                groups.setdefault(account_type, []).append(access_token)
        return groups

    @staticmethod
    def _signature(groups: dict[str, list[str]]) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted(
                (account_type, access_token)
                for account_type, access_tokens in groups.items()
                for access_token in access_tokens
            )
        )

    def _fetch_models(
        self,
        access_token: str = "",
    ) -> tuple[str, dict[str, dict[str, Any]] | None, str | None]:
        resolved_token = access_token
        try:
            if access_token:
                resolved_token = (
                    self._accounts.refresh_access_token(
                        access_token,
                        event="model_catalog",
                    )
                    or access_token
                )
            backend = self._backend_factory(access_token=resolved_token)
            try:
                models = self._model_map(
                    backend.list_models(timeout_secs=self._request_timeout_seconds)
                )
            finally:
                backend.close()
        except Exception as exc:  # noqa: BLE001 - report account failure to the worker
            return resolved_token, None, type(exc).__name__
        return resolved_token, models, None

    @staticmethod
    def _accounts_for_refresh(groups: dict[str, list[str]]) -> list[tuple[str, str]]:
        accounts: list[tuple[str, str]] = []
        for account_type in sorted(groups):
            accounts.extend(
                (account_type, access_token)
                for access_token in dict.fromkeys(groups[account_type])
            )
        return accounts

    def _publish_partial_account(
        self,
        original_token: str,
        resolved_token: str,
        models: dict[str, dict[str, Any]] | None,
    ) -> None:
        with self._condition:
            stale_models = None
            if original_token != resolved_token:
                stale_models = self._models_by_access_token.pop(original_token, None)
            if models is not None:
                self._models_by_access_token[resolved_token] = models
            elif stale_models is not None:
                self._models_by_access_token[resolved_token] = stale_models
            self._condition.notify_all()

    def _resolved_access_token(self, access_token: str) -> str:
        account = self._accounts.get_account(access_token)
        if not account:
            return access_token
        return str(account.get("access_token") or access_token).strip() or access_token

    def _refresh_worker(
        self,
        groups: dict[str, list[str]],
        accounts_to_refresh: list[tuple[str, str]],
    ) -> None:
        active_tokens = {
            access_token
            for access_tokens in groups.values()
            for access_token in access_tokens
        }
        with self._condition:
            self._models_by_access_token = {
                access_token: models
                for access_token, models in self._models_by_access_token.items()
                if access_token in active_tokens
            }

        pending: dict[
            Future[tuple[str, dict[str, dict[str, Any]] | None, str | None]],
            tuple[str | None, str],
        ] = {}
        processed_tokens: set[str] = set()
        try:
            jobs = iter([(None, ""), *accounts_to_refresh])
            worker_count = min(self._max_workers, len(accounts_to_refresh) + 1)
            with ThreadPoolExecutor(max_workers=max(1, worker_count)) as executor:
                def fill_pending() -> None:
                    while len(pending) < self._max_pending_requests:
                        try:
                            account_type, access_token = next(jobs)
                        except StopIteration:
                            return
                        pending[executor.submit(self._fetch_models, access_token)] = (
                            account_type,
                            access_token,
                        )

                fill_pending()
                while pending:
                    completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in completed:
                        account_type, access_token = pending.pop(future)
                        try:
                            resolved_token, models, error_type = future.result()
                        except Exception as exc:  # noqa: BLE001 - retain the last good catalog
                            if account_type is not None:
                                resolved_token = self._resolved_access_token(access_token)
                                processed_tokens.add(resolved_token)
                                self._publish_partial_account(
                                    access_token,
                                    resolved_token,
                                    None,
                                )
                            logger.warning({
                                "event": (
                                    "model_catalog_anonymous_failed"
                                    if account_type is None
                                    else "model_catalog_account_failed"
                                ),
                                **({"account_type": account_type} if account_type is not None else {}),
                                "error_type": type(exc).__name__,
                            })
                            continue
                        if error_type is not None:
                            if account_type is not None:
                                processed_tokens.add(resolved_token)
                                self._publish_partial_account(
                                    access_token,
                                    resolved_token,
                                    None,
                                )
                            logger.warning({
                                "event": (
                                    "model_catalog_anonymous_failed"
                                    if account_type is None
                                    else "model_catalog_account_failed"
                                ),
                                **({"account_type": account_type} if account_type is not None else {}),
                                "error_type": error_type,
                            })
                            continue
                        if account_type is None:
                            assert models is not None
                            with self._condition:
                                self._anonymous_models = models
                                self._condition.notify_all()
                        else:
                            assert models is not None
                            processed_tokens.add(resolved_token)
                            self._publish_partial_account(
                                access_token,
                                resolved_token,
                                models,
                            )
                    fill_pending()
        except Exception as exc:  # noqa: BLE001 - always release waiters after worker failure
            logger.warning({
                "event": "model_catalog_refresh_failed",
                "error_type": type(exc).__name__,
            })
        finally:
            current_groups = self._active_accounts_by_type()
            current_signature = self._signature(current_groups)
            current_tokens = {
                access_token
                for access_tokens in current_groups.values()
                for access_token in access_tokens
            }
            with self._condition:
                self._models_by_access_token = {
                    access_token: models
                    for access_token, models in self._models_by_access_token.items()
                    if access_token in current_tokens
                }
                self._account_signature = current_signature
                self._expires_at = (
                    self._clock()
                    if current_tokens - processed_tokens
                    else self._clock() + self._cache_ttl_seconds
                )
                self._initialized = True
                self._refreshing = False
                self._condition.notify_all()

    def _route_locked(self, model: str) -> ModelRoute:
        return ModelRoute(
            access_tokens=frozenset(
                access_token
                for access_token, models in self._models_by_access_token.items()
                if model in models
            ),
            allow_anonymous=model in self._anonymous_models,
        )

    def _ensure_catalog(self, requested_model: str = "") -> None:
        groups = self._active_accounts_by_type()
        signature = self._signature(groups)
        with self._condition:
            active_tokens = {
                access_token
                for access_tokens in groups.values()
                for access_token in access_tokens
            }
            if set(self._models_by_access_token) - active_tokens:
                self._models_by_access_token = {
                    access_token: models
                    for access_token, models in self._models_by_access_token.items()
                    if access_token in active_tokens
                }
            fresh = (
                self._initialized
                and signature == self._account_signature
                and self._clock() < self._expires_at
            )
            if not fresh and not self._refreshing:
                accounts_to_refresh = self._accounts_for_refresh(groups)
                self._refreshing = True
                worker = Thread(
                    target=self._refresh_worker,
                    args=(groups, accounts_to_refresh),
                    name="model-catalog-refresh",
                    daemon=True,
                )
                try:
                    worker.start()
                except Exception:
                    self._refreshing = False
                    self._condition.notify_all()
                    raise

            if self._initial_wait_seconds <= 0:
                return
            route_available = lambda: (
                bool(self._route_locked(requested_model).access_tokens)
                or self._route_locked(requested_model).allow_anonymous
            )
            if not self._initialized:
                self._condition.wait_for(
                    lambda: self._initialized or (bool(requested_model) and route_available()),
                    timeout=self._initial_wait_seconds,
                )
            elif requested_model and self._refreshing and not route_available():
                self._condition.wait_for(
                    lambda: (
                        route_available()
                        or not self._refreshing
                    ),
                    timeout=self._initial_wait_seconds,
                )

    def list_models(self) -> dict[str, Any]:
        self._ensure_catalog()
        with self._condition:
            union: dict[str, dict[str, Any]] = {
                model_id: dict(item)
                for model_id, item in self._anonymous_models.items()
            }
            for access_token in sorted(self._models_by_access_token):
                for model_id, item in self._models_by_access_token[access_token].items():
                    union.setdefault(model_id, dict(item))
        return {
            "object": "list",
            "data": [union[model_id] for model_id in sorted(union)],
        }

    def route_for_model(self, model: str) -> ModelRoute:
        model = str(model or "").strip()
        self._ensure_catalog(model)
        with self._condition:
            return self._route_locked(model)


model_catalog_service = ModelCatalogService(account_service)
