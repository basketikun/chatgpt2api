from __future__ import annotations

import base64
import json
import unittest
from typing import Any

from services.invoice_service import InvoiceService, InvoiceServiceError
from services.openai_backend_api import BillingAPIError


def make_jwt(account_id: str) -> str:
    def encode(value: dict[str, Any]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f'{encode({"alg": "none"})}.{encode({"https://api.openai.com/auth": {"chatgpt_account_id": account_id}})}.sig'


class FakeAccounts:
    _decode_jwt_payload = staticmethod(
        lambda token: json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "===")) if "." in token else {}
    )

    def __init__(self, accounts: list[dict[str, Any]]) -> None:
        self.items = accounts
        self.refresh_calls: list[tuple[str, bool, str]] = []
        self.forced_token = ""

    def list_accounts(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.items]

    def refresh_access_token(self, token: str, *, force: bool = False, event: str = "") -> str:
        self.refresh_calls.append((token, force, event))
        return self.forced_token if force and self.forced_token else token


class FakeBackend:
    def __init__(self, token: str, outcome: object) -> None:
        self.token = token
        self.outcome = outcome
        self.closed = False

    def list_transactions(self, account_id: str, limit: int, cursor: str):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    def close(self) -> None:
        self.closed = True


class BackendFactory:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.instances: list[FakeBackend] = []

    def __call__(self, token: str) -> FakeBackend:
        backend = FakeBackend(token, self.outcomes.pop(0))
        self.instances.append(backend)
        return backend


def invoice_payload() -> dict[str, Any]:
    return {
        "items": [
            {
                "id": "in_test",
                "created_at": "2026-08-25T09:32:57Z",
                "amount": 27523,
                "currency": "sgd",
                "status": "paid",
                "invoice_url": "https://invoice.stripe.com/i/test?s=ap",
                "product": {"type": "subscription", "plan": "chatgptpro"},
            }
        ],
        "next_cursor": None,
    }


class InvoiceServiceTests(unittest.TestCase):
    def test_account_options_exclude_mismatches_and_duplicate_identities(self) -> None:
        accounts = FakeAccounts(
            [
                {"access_token": make_jwt("acct_good"), "email": "good@example.com"},
                {"access_token": make_jwt("acct_mismatch"), "account_id": "acct_stored"},
                {"access_token": make_jwt("acct_duplicate"), "email": "one@example.com"},
                {"access_token": make_jwt("acct_duplicate") + "second", "email": "two@example.com"},
            ]
        )
        service = InvoiceService(accounts, BackendFactory([]))  # type: ignore[arg-type]

        self.assertEqual(
            service.list_account_options(),
            [
                {
                    "account_id": "acct_good",
                    "email": "good@example.com",
                    "plan": None,
                    "status": None,
                    "has_active_subscription": None,
                    "subscription_plan": None,
                    "billing_period": None,
                    "renews_at": None,
                    "cancels_at": None,
                }
            ],
        )

    def test_account_options_expose_server_derived_renewal_fields(self) -> None:
        accounts = FakeAccounts(
            [
                {
                    "access_token": make_jwt("acct_pro"),
                    "email": "pro@example.com",
                    "type": "Pro",
                    "status": "正常",
                    "has_active_subscription": True,
                    "subscription_plan": "chatgptpro",
                    "billing_period": "monthly",
                    "renews_at": "2026-09-05T08:06:08+00:00",
                    "cancels_at": None,
                }
            ]
        )
        service = InvoiceService(accounts, BackendFactory([]))  # type: ignore[arg-type]

        [option] = service.list_account_options()

        self.assertEqual(option["account_id"], "acct_pro")
        self.assertEqual(option["renews_at"], "2026-09-05T08:06:08+00:00")
        self.assertEqual(option["billing_period"], "monthly")
        self.assertTrue(option["has_active_subscription"])

    def test_list_returns_the_validated_invoice_url_from_the_same_fetch(self) -> None:
        accounts = FakeAccounts([{"access_token": make_jwt("acct_a"), "email": "a@example.com"}])
        factory = BackendFactory([invoice_payload()])
        service = InvoiceService(accounts, factory)  # type: ignore[arg-type]

        listed = service.list_invoices("acct_a")

        self.assertEqual(listed["items"][0]["invoice_url"], "https://invoice.stripe.com/i/test?s=ap")
        self.assertEqual(len(factory.instances), 1)
        self.assertTrue(all(instance.closed for instance in factory.instances))

    def test_request_cannot_switch_stored_account_identity(self) -> None:
        accounts = FakeAccounts(
            [{"access_token": make_jwt("acct_b"), "account_id": "acct_a", "email": "a@example.com"}]
        )
        service = InvoiceService(accounts, BackendFactory([]))  # type: ignore[arg-type]

        with self.assertRaises(InvoiceServiceError) as ctx:
            service.list_invoices("acct_a")

        self.assertEqual(ctx.exception.code, "ACCOUNT_IDENTITY_MISMATCH")
        self.assertEqual(accounts.refresh_calls, [])

        with self.assertRaises(InvoiceServiceError) as token_claim_ctx:
            service.list_invoices("acct_b")
        self.assertEqual(token_claim_ctx.exception.code, "ACCOUNT_IDENTITY_MISMATCH")

    def test_unauthorized_refreshes_once_then_retries_with_rotated_token(self) -> None:
        old_token = make_jwt("acct_a")
        new_token = make_jwt("acct_a") + "rotated"
        accounts = FakeAccounts([{"access_token": old_token, "account_id": "acct_a"}])
        accounts.forced_token = new_token
        factory = BackendFactory([BillingAPIError("BILLING_AUTH_REQUIRED", 401), invoice_payload()])
        service = InvoiceService(accounts, factory)  # type: ignore[arg-type]

        result = service.list_invoices("acct_a")

        self.assertEqual(result["items"][0]["id"], "in_test")
        self.assertEqual([backend.token for backend in factory.instances], [old_token, new_token])
        self.assertEqual(sum(1 for _, force, _ in accounts.refresh_calls if force), 1)

    def test_duplicate_account_id_fails_closed(self) -> None:
        accounts = FakeAccounts(
            [
                {"access_token": make_jwt("acct_a")},
                {"access_token": make_jwt("acct_a") + "second"},
            ]
        )
        service = InvoiceService(accounts, BackendFactory([]))  # type: ignore[arg-type]

        with self.assertRaises(InvoiceServiceError) as ctx:
            service.list_invoices("acct_a")

        self.assertEqual(ctx.exception.code, "AMBIGUOUS_ACCOUNT_ID")


if __name__ == "__main__":
    unittest.main()
