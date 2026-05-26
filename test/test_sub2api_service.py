import unittest
from unittest.mock import MagicMock, patch

from services import sub2api_service


class FakeResponse:
    def __init__(self, payload: dict, *, ok: bool = True, status_code: int = 200) -> None:
        self._payload = payload
        self.ok = ok
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class FakeSession:
    responses: list[FakeResponse] = []
    requests: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        if not self.responses:
            raise AssertionError("No fake response queued")
        return self.responses.pop(0)

    def close(self) -> None:
        pass


class Sub2APIServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeSession.responses = []
        FakeSession.requests = []

    def test_list_remote_accounts_keeps_redacted_accounts_with_access_token_status(self) -> None:
        FakeSession.responses = [
            FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "id": 123,
                                "name": "user@example.com",
                                "platform": "openai",
                                "type": "oauth",
                                "status": "active",
                                "credentials": {"email": "user@example.com", "plan_type": "Plus"},
                                "credentials_status": {
                                    "has_access_token": True,
                                    "has_refresh_token": True,
                                },
                            }
                        ],
                        "total": 1,
                    },
                }
            )
        ]

        with patch.object(sub2api_service, "Session", FakeSession):
            accounts = sub2api_service.list_remote_accounts(
                {"base_url": "https://sub2api.test", "api_key": "admin-key"}
            )

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["id"], "123")
        self.assertEqual(accounts[0]["email"], "user@example.com")
        self.assertEqual(accounts[0]["plan_type"], "Plus")
        self.assertTrue(accounts[0]["has_refresh_token"])

    def test_list_remote_accounts_skips_redacted_accounts_without_access_token_status(self) -> None:
        FakeSession.responses = [
            FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "id": 123,
                                "name": "missing-token",
                                "credentials": {"email": "missing@example.com"},
                                "credentials_status": {"has_refresh_token": True},
                            }
                        ],
                        "total": 1,
                    },
                }
            )
        ]

        with patch.object(sub2api_service, "Session", FakeSession):
            accounts = sub2api_service.list_remote_accounts(
                {"base_url": "https://sub2api.test", "api_key": "admin-key"}
            )

        self.assertEqual(accounts, [])

    def test_fetch_access_token_prefers_data_export_and_ignores_refresh_token(self) -> None:
        FakeSession.responses = [
            FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "accounts": [
                            {
                                "name": "user@example.com",
                                "credentials": {
                                    "access_token": "access-token-from-export",
                                    "refresh_token": "refresh-token-must-not-be-imported",
                                    "id_token": "id-token-must-not-be-imported",
                                    "email": "user@example.com",
                                    "plan_type": "Pro",
                                },
                            }
                        ]
                    },
                }
            )
        ]

        with patch.object(sub2api_service, "Session", FakeSession):
            token, meta = sub2api_service._fetch_access_token_for_account(
                {"base_url": "https://sub2api.test", "api_key": "admin-key"},
                "123",
            )

        self.assertEqual(token, "access-token-from-export")
        self.assertEqual(meta, {"email": "user@example.com", "plan_type": "Pro"})
        self.assertEqual(len(FakeSession.requests), 1)
        self.assertTrue(FakeSession.requests[0]["url"].endswith("/api/v1/admin/accounts/data"))
        self.assertEqual(FakeSession.requests[0]["params"]["include_proxies"], "false")

    def test_fetch_access_token_falls_back_to_legacy_detail_when_data_export_is_missing(self) -> None:
        FakeSession.responses = [
            FakeResponse({"message": "not found"}, ok=False, status_code=404),
            FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "credentials": {
                            "access_token": "legacy-access-token",
                            "refresh_token": "legacy-refresh-token-must-not-be-imported",
                            "email": "legacy@example.com",
                        }
                    },
                }
            ),
        ]

        with patch.object(sub2api_service, "Session", FakeSession):
            token, meta = sub2api_service._fetch_access_token_for_account(
                {"base_url": "https://sub2api.test", "api_key": "admin-key"},
                "123",
            )

        self.assertEqual(token, "legacy-access-token")
        self.assertEqual(meta, {"email": "legacy@example.com", "plan_type": ""})
        self.assertEqual(len(FakeSession.requests), 2)
        self.assertTrue(FakeSession.requests[1]["url"].endswith("/api/v1/admin/accounts/123"))

    def test_run_import_still_adds_only_access_tokens(self) -> None:
        config = MagicMock()
        config.get_import_job.return_value = {
            "total": 1,
            "completed": 0,
            "errors": [],
        }
        importer = sub2api_service.Sub2APIImportService(config)
        account_service = MagicMock()
        account_service.add_accounts.return_value = {"added": 1, "skipped": 0}
        account_service.refresh_accounts.return_value = {"refreshed": 1}

        with (
            patch.object(sub2api_service, "_fetch_access_token_for_account", return_value=("access-only", {})),
            patch.object(sub2api_service, "account_service", account_service),
        ):
            importer._run_import("server-id", {"id": "server-id"}, ["123"])

        account_service.add_accounts.assert_called_once_with(["access-only"])
        account_service.refresh_accounts.assert_called_once_with(["access-only"])


if __name__ == "__main__":
    unittest.main()
