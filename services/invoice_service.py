from __future__ import annotations

from collections.abc import Callable
from typing import Any

from services.account_service import AccountService, account_service
from services.openai_backend_api import BillingAPIError, OpenAIBackendAPI


class InvoiceServiceError(RuntimeError):
    def __init__(self, code: str, status_code: int, retry_after: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.retry_after = retry_after


class InvoiceService:
    def __init__(
        self,
        accounts: AccountService = account_service,
        backend_factory: Callable[[str], OpenAIBackendAPI] = OpenAIBackendAPI,
    ) -> None:
        self.accounts = accounts
        self.backend_factory = backend_factory

    def _account_identity(self, account: dict[str, Any]) -> tuple[str, bool, str, str]:
        stored_account_id = str(account.get("account_id") or "").strip()
        access_token = str(account.get("access_token") or "").strip()
        token_payload = self.accounts._decode_jwt_payload(access_token)
        auth_claim = token_payload.get("https://api.openai.com/auth")
        auth_claim = auth_claim if isinstance(auth_claim, dict) else {}
        token_account_id = str(auth_claim.get("chatgpt_account_id") or "").strip()
        mismatch = bool(stored_account_id and token_account_id and stored_account_id != token_account_id)
        return stored_account_id or token_account_id, mismatch, stored_account_id, token_account_id

    def list_account_options(self) -> list[dict[str, Any]]:
        candidates: dict[str, list[dict[str, Any]]] = {}
        for account in self.accounts.list_accounts():
            if not isinstance(account, dict):
                continue
            account_id, mismatch, _, _ = self._account_identity(account)
            if not account_id or mismatch:
                continue
            candidates.setdefault(account_id, []).append(account)

        result = []
        for account_id, matches in sorted(candidates.items()):
            if len(matches) != 1:
                continue
            account = matches[0]
            result.append(
                {
                    "account_id": account_id,
                    "email": str(account.get("email") or "").strip() or None,
                    "plan": str(account.get("type") or "").strip() or None,
                    "status": str(account.get("status") or "").strip() or None,
                }
            )
        return result

    def _resolve_account(self, account_id: str) -> dict[str, Any]:
        normalized_account_id = str(account_id or "").strip()
        if not normalized_account_id or len(normalized_account_id) > 128:
            raise InvoiceServiceError("INVALID_ACCOUNT_ID", 400)

        matches: list[dict[str, Any]] = []
        identity_mismatch = False
        for account in self.accounts.list_accounts():
            if not isinstance(account, dict):
                continue
            resolved_account_id, mismatch, stored_account_id, token_account_id = self._account_identity(account)
            if mismatch and normalized_account_id in {stored_account_id, token_account_id}:
                identity_mismatch = True
            if not mismatch and resolved_account_id == normalized_account_id:
                matches.append(account)

        if identity_mismatch:
            raise InvoiceServiceError("ACCOUNT_IDENTITY_MISMATCH", 409)
        if not matches:
            raise InvoiceServiceError("ACCOUNT_NOT_FOUND", 404)
        if len(matches) != 1:
            raise InvoiceServiceError("AMBIGUOUS_ACCOUNT_ID", 409)
        return matches[0]

    @staticmethod
    def _map_upstream_error(exc: BillingAPIError) -> InvoiceServiceError:
        status_code = 429 if exc.code == "BILLING_RATE_LIMITED" else 502
        return InvoiceServiceError(exc.code, status_code, exc.retry_after)

    def _fetch(self, account: dict[str, Any], account_id: str, limit: int, cursor: str) -> dict[str, Any]:
        access_token = str(account.get("access_token") or "").strip()
        if not access_token:
            raise InvoiceServiceError("BILLING_AUTH_REQUIRED", 502)
        active_token = self.accounts.refresh_access_token(access_token, event="invoice_list:preflight") or access_token

        for attempt in range(2):
            backend = self.backend_factory(active_token)
            try:
                return backend.list_transactions(account_id, limit=limit, cursor=cursor)
            except BillingAPIError as exc:
                if exc.code == "BILLING_AUTH_REQUIRED" and attempt == 0:
                    refreshed_token = self.accounts.refresh_access_token(
                        active_token,
                        force=True,
                        event="invoice_list:invalid_access_token",
                    )
                    if refreshed_token and refreshed_token != active_token:
                        active_token = refreshed_token
                        continue
                raise self._map_upstream_error(exc) from None
            finally:
                backend.close()
        raise InvoiceServiceError("BILLING_AUTH_REQUIRED", 502)

    def list_invoices(self, account_id: str, limit: int = 20, cursor: str = "") -> dict[str, Any]:
        account = self._resolve_account(account_id)
        payload = self._fetch(account, account_id, limit, cursor)
        return {
            "account_id": account_id,
            "items": [
                {
                    "id": item["id"],
                    "created_at": item["created_at"],
                    "amount": item["amount"],
                    "currency": item["currency"],
                    "status": item["status"],
                    "product": item["product"],
                    "invoice_url": item.get("invoice_url") or None,
                }
                for item in payload["items"]
            ],
            "next_cursor": payload.get("next_cursor"),
        }


invoice_service = InvoiceService()
