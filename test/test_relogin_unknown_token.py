import unittest
from typing import Any

from services.account_service import AccountService


class MemoryStorage:
    def __init__(self, accounts: list[dict[str, Any]] | None = None) -> None:
        self.accounts = list(accounts or [])

    def load_accounts(self) -> list[dict[str, Any]]:
        return list(self.accounts)

    def save_accounts(self, accounts: list[dict[str, Any]]) -> None:
        self.accounts = list(accounts)

    def load_auth_keys(self) -> list[dict[str, Any]]:
        return []

    def save_auth_keys(self, auth_keys: list[dict[str, Any]]) -> None:
        pass

    def health_check(self) -> dict[str, Any]:
        return {"ok": True}

    def get_backend_info(self) -> dict[str, Any]:
        return {"type": "memory"}


class ReLoginUnknownTokenTests(unittest.TestCase):
    def test_re_login_accounts_reports_unknown_token_without_raising(self) -> None:
        """Regression test for an UnboundLocalError that used to abort the whole
        batch: re_login_accounts binds a local `t` (threading.Thread) later in
        the function body, which shadowed the module-level `t` (utils.i18n.t)
        for the entire function, including the earlier unknown-account branch."""
        service = AccountService(MemoryStorage())

        result = service.re_login_accounts(["token-not-in-pool"])

        self.assertEqual(result["relogined"], 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["error"], "账号不存在")


if __name__ == "__main__":
    unittest.main()
