import unittest
from unittest.mock import patch

from services import sub2api_service


class FakeResponse:
    def __init__(self, payload: dict, ok: bool = True, status_code: int = 200) -> None:
        self._payload = payload
        self.ok = ok
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class FakeSession:
    calls: list[tuple[str, dict | None]] = []

    def __init__(self, *args, **kwargs) -> None:
        return None

    def get(self, url: str, headers: dict | None = None, params: dict | None = None, timeout: int = 30) -> FakeResponse:
        self.calls.append((url, params))
        if url.endswith("/api/v1/admin/accounts"):
            return FakeResponse({
                "code": 0,
                "data": {
                    "items": [
                        {
                            "id": 123,
                            "name": "user@example.com",
                            "status": "active",
                            "credentials": {
                                "email": "user@example.com",
                                "plan_type": "pro",
                            },
                            "credentials_status": {
                                "has_access_token": True,
                                "has_refresh_token": True,
                            },
                        }
                    ],
                    "total": 1,
                },
            })
        if url.endswith("/api/v1/admin/accounts/data"):
            return FakeResponse({
                "code": 0,
                "data": {
                    "accounts": [
                        {
                            "name": "user@example.com",
                            "credentials": {
                                "access_token": "access-token",
                                "refresh_token": "refresh-token",
                                "email": "user@example.com",
                                "plan_type": "pro",
                            },
                        }
                    ],
                    "proxies": [],
                },
            })
        raise AssertionError(f"unexpected URL: {url}")

    def close(self) -> None:
        return None


class Sub2APIServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeSession.calls = []

    @patch.object(sub2api_service, "Session", FakeSession)
    def test_list_remote_accounts_keeps_redacted_accounts_with_credential_status(self) -> None:
        accounts = sub2api_service.list_remote_accounts({
            "base_url": "https://sub2api.example",
            "api_key": "admin-key",
            "group_id": "3",
        })

        self.assertEqual(accounts, [{
            "id": "123",
            "name": "user@example.com",
            "email": "user@example.com",
            "plan_type": "pro",
            "status": "active",
            "expires_at": "",
            "has_refresh_token": True,
        }])
        self.assertEqual(FakeSession.calls[0][1]["status"], "active")
        self.assertEqual(FakeSession.calls[0][1]["page_size"], sub2api_service._LIST_PAGE_SIZE)

    @patch.object(sub2api_service, "Session", FakeSession)
    def test_fetch_access_token_uses_accounts_data_export_endpoint(self) -> None:
        token, meta = sub2api_service._fetch_access_token_for_account({
            "base_url": "https://sub2api.example",
            "api_key": "admin-key",
        }, "123")

        self.assertEqual(token, "access-token")
        self.assertEqual(meta, {"email": "user@example.com", "plan_type": "pro"})
        self.assertEqual(FakeSession.calls[0][0], "https://sub2api.example/api/v1/admin/accounts/data")
        self.assertEqual(FakeSession.calls[0][1]["ids"], "123")
        self.assertEqual(FakeSession.calls[0][1]["include_proxies"], "false")


if __name__ == "__main__":
    unittest.main()
