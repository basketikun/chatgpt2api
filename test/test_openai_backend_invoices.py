from __future__ import annotations

import unittest

from services.openai_backend_api import BillingAPIError, OpenAIBackendAPI


class FakeResponse:
    def __init__(self, status_code: int, payload: object, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = "sensitive upstream body"

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.headers = {"Authorization": "Bearer secret-token"}
        self.response = response
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response


def make_backend(response: FakeResponse) -> tuple[OpenAIBackendAPI, FakeSession]:
    backend = OpenAIBackendAPI.__new__(OpenAIBackendAPI)
    backend.base_url = "https://chatgpt.com"
    backend.access_token = "secret-token"
    session = FakeSession(response)
    backend.session = session
    return backend, session


class OpenAIBackendInvoiceTests(unittest.TestCase):
    def test_list_transactions_uses_fixed_path_and_normalizes_invoices(self) -> None:
        backend, session = make_backend(
            FakeResponse(
                200,
                {
                    "transactions": [
                        {
                            "type": "invoice",
                            "id": "in_test",
                            "created_at": "2026-08-25T09:32:57Z",
                            "amount": 27523,
                            "currency": "SGD",
                            "status": "paid",
                            "invoice_url": "https://invoice.stripe.com/i/test?s=ap",
                            "product": {"type": "subscription", "plan": "chatgptpro"},
                        },
                        {"type": "refund", "id": "refund_test"},
                    ],
                    "next_cursor": "cursor-2",
                },
            )
        )

        result = backend.list_transactions("acct_test", limit=4, cursor="cursor-1")

        self.assertEqual(result["next_cursor"], "cursor-2")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["currency"], "sgd")
        [call] = session.calls
        self.assertEqual(call["url"], "https://chatgpt.com/backend-api/payments/transaction-history")
        self.assertEqual(
            call["params"],
            {"account_id": "acct_test", "limit": 4, "cursor": "cursor-1"},
        )
        self.assertNotIn("secret-token", str(result))

    def test_untrusted_invoice_host_fails_closed(self) -> None:
        backend, _ = make_backend(
            FakeResponse(
                200,
                {
                    "transactions": [
                        {
                            "type": "invoice",
                            "id": "in_test",
                            "created_at": "2026-08-25T09:32:57Z",
                            "amount": 1,
                            "currency": "usd",
                            "status": "paid",
                            "invoice_url": "https://evil.example/invoice",
                            "product": {},
                        }
                    ],
                    "next_cursor": None,
                },
            )
        )

        with self.assertRaises(BillingAPIError) as ctx:
            backend.list_transactions("acct_test")

        self.assertEqual(ctx.exception.code, "UNTRUSTED_INVOICE_URL")

    def test_upstream_error_is_typed_without_response_body(self) -> None:
        backend, _ = make_backend(FakeResponse(429, {}, {"Retry-After": "30"}))

        with self.assertRaises(BillingAPIError) as ctx:
            backend.list_transactions("acct_test")

        self.assertEqual(ctx.exception.code, "BILLING_RATE_LIMITED")
        self.assertEqual(ctx.exception.retry_after, "30")
        self.assertNotIn("sensitive", str(ctx.exception))

    def test_upstream_statuses_and_schema_drift_remain_typed(self) -> None:
        cases = [
            (401, {}, "BILLING_AUTH_REQUIRED"),
            (403, {}, "BILLING_FORBIDDEN"),
            (500, {}, "BILLING_UPSTREAM_ERROR"),
            (200, {"transactions": "not-a-list"}, "BILLING_SCHEMA_CHANGED"),
        ]
        for status_code, payload, expected_code in cases:
            with self.subTest(status_code=status_code, expected_code=expected_code):
                backend, _ = make_backend(FakeResponse(status_code, payload))

                with self.assertRaises(BillingAPIError) as ctx:
                    backend.list_transactions("acct_test")

                self.assertEqual(ctx.exception.code, expected_code)
                self.assertNotIn("sensitive", str(ctx.exception))

    def test_invalid_pagination_is_rejected_before_network(self) -> None:
        backend, session = make_backend(FakeResponse(200, {"transactions": [], "next_cursor": None}))

        with self.assertRaises(ValueError):
            backend.list_transactions("acct_test", limit=101)
        with self.assertRaises(ValueError):
            backend.list_transactions("acct_test", cursor="x" * 2049)

        self.assertEqual(session.calls, [])


if __name__ == "__main__":
    unittest.main()
