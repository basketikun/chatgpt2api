from __future__ import annotations

import unittest
from unittest import mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import api.invoices as invoices_module
from services.invoice_service import InvoiceServiceError


class FakeInvoiceService:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.error: InvoiceServiceError | None = None

    def list_account_options(self):
        self.calls.append(("accounts",))
        return [{"account_id": "acct_a", "email": "a@example.com", "plan": "Pro", "status": "正常"}]

    def list_invoices(self, account_id: str, limit: int, cursor: str):
        self.calls.append(("list", account_id, limit, cursor))
        if self.error:
            raise self.error
        return {
            "account_id": account_id,
            "items": [{"id": "in_test", "invoice_url": "https://invoice.stripe.com/i/test?s=ap"}],
            "next_cursor": None,
        }


class InvoiceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FakeInvoiceService()

        def require_admin(value: str | None):
            if value != "Bearer admin":
                raise HTTPException(status_code=403, detail={"error": "admin required"})
            return {"role": "admin"}

        self.patchers = [
            mock.patch.object(invoices_module, "invoice_service", self.service),
            mock.patch.object(invoices_module, "require_admin", require_admin),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        app = FastAPI()
        app.include_router(invoices_module.create_router())
        self.client = TestClient(app)

    def test_user_key_cannot_read_invoice_accounts(self) -> None:
        response = self.client.get("/api/invoices/accounts", headers={"Authorization": "Bearer user"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.service.calls, [])

    def test_account_and_list_responses_are_not_cacheable(self) -> None:
        accounts = self.client.get(
            "/api/invoices/accounts",
            headers={"Authorization": "Bearer admin"},
        )
        listed = self.client.get(
            "/api/invoices/acct_a?limit=4&cursor=cursor-1",
            headers={"Authorization": "Bearer admin"},
        )

        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["items"][0]["invoice_url"], "https://invoice.stripe.com/i/test?s=ap")
        for response in (accounts, listed):
            self.assertIn("no-store", response.headers["cache-control"])
            self.assertEqual(response.headers["pragma"], "no-cache")
            self.assertEqual(response.headers["referrer-policy"], "no-referrer")
        self.assertEqual(
            self.service.calls,
            [
                ("accounts",),
                ("list", "acct_a", 4, "cursor-1"),
            ],
        )

    def test_invalid_pagination_never_reaches_service(self) -> None:
        response = self.client.get(
            "/api/invoices/acct_a?limit=101",
            headers={"Authorization": "Bearer admin"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.service.calls, [])

    def test_typed_rate_limit_preserves_only_safe_retry_after(self) -> None:
        self.service.error = InvoiceServiceError("BILLING_RATE_LIMITED", 429, "30")

        response = self.client.get(
            "/api/invoices/acct_a",
            headers={"Authorization": "Bearer admin"},
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), {"detail": {"error": "BILLING_RATE_LIMITED"}})
        self.assertEqual(response.headers["retry-after"], "30")
        self.assertIn("no-store", response.headers["cache-control"])


if __name__ == "__main__":
    unittest.main()
