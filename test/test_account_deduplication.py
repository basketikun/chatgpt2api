from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from services.account_service import AccountService
from services.storage.database_storage import DatabaseStorageBackend
from services.storage.json_storage import JSONStorageBackend


class MemoryStorage:
    def __init__(self, accounts: list[dict[str, Any]] | None = None) -> None:
        self.accounts = [dict(item) for item in accounts or []]

    def load_accounts(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.accounts]

    def save_accounts(self, accounts: list[dict[str, Any]]) -> None:
        self.accounts = [dict(item) for item in accounts]

    def load_auth_keys(self) -> list[dict[str, Any]]:
        return []

    def save_auth_keys(self, auth_keys: list[dict[str, Any]]) -> None:
        pass

    def health_check(self) -> dict[str, Any]:
        return {"ok": True}

    def get_backend_info(self) -> dict[str, Any]:
        return {"type": "memory"}


class IsolatedAccountService(AccountService):
    def _load_cumulative_total(self) -> int:
        return len(self._accounts)

    def _save_cumulative_total(self) -> None:
        pass


def make_jwt(payload: dict[str, Any]) -> str:
    def encode(value: dict[str, Any]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f'{encode({"alg": "none", "typ": "JWT"})}.{encode(payload)}.sig'


def make_access_token(
    *,
    account_id: str = "",
    subject: str = "",
    email: str = "",
    exp: int = 0,
    iat: int = 0,
) -> str:
    payload: dict[str, Any] = {"exp": exp, "iat": iat}
    if account_id:
        payload["https://api.openai.com/auth"] = {"chatgpt_account_id": account_id}
    if subject:
        payload["sub"] = subject
    if email:
        payload["https://api.openai.com/profile"] = {"email": email}
    return make_jwt(payload)


class AccountDeduplicationTests(unittest.TestCase):
    def test_cpa_batch_keeps_only_the_token_with_the_latest_expiry(self) -> None:
        old_token = make_access_token(
            account_id="acct-1",
            subject="user-1",
            email="same@example.com",
            exp=100,
            iat=10,
        )
        new_token = make_access_token(
            account_id="acct-1",
            subject="user-1",
            email="same@example.com",
            exp=200,
            iat=20,
        )
        service = IsolatedAccountService(MemoryStorage())

        result = service.add_accounts([old_token, new_token], source_type="codex")

        self.assertEqual(result["added"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(service.list_tokens(), [new_token])
        self.assertEqual(service.get_account(old_token)["access_token"], new_token)

    def test_newer_token_replaces_existing_identity_and_preserves_metadata(self) -> None:
        old_token = make_access_token(account_id="acct-1", exp=100, iat=10)
        new_token = make_access_token(account_id="acct-1", exp=200, iat=20)
        service = IsolatedAccountService(
            MemoryStorage(
                [
                    {
                        "access_token": old_token,
                        "created_at": "2026-01-01 00:00:00",
                        "success": 3,
                        "fail": 1,
                        "password": "preserved-password",
                        "status": "正常",
                    }
                ]
            )
        )

        result = service.add_accounts([new_token], source_type="codex")

        self.assertEqual(result["added"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(service.list_tokens(), [new_token])
        account = service.get_account(new_token)
        self.assertEqual(account["created_at"], "2026-01-01 00:00:00")
        self.assertEqual(account["success"], 3)
        self.assertEqual(account["fail"], 1)
        self.assertEqual(account["password"], "preserved-password")
        self.assertEqual(service.get_account(old_token)["access_token"], new_token)

    def test_older_import_does_not_replace_a_newer_existing_token(self) -> None:
        old_token = make_access_token(account_id="acct-1", exp=100, iat=10)
        new_token = make_access_token(account_id="acct-1", exp=200, iat=20)
        service = IsolatedAccountService(MemoryStorage([{"access_token": new_token, "success": 4}]))

        result = service.add_accounts([old_token], source_type="codex")

        self.assertEqual(result["added"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(service.list_tokens(), [new_token])
        self.assertEqual(service.get_account(old_token)["access_token"], new_token)
        self.assertEqual(service.get_account(new_token)["success"], 4)

    def test_account_id_keeps_workspaces_separate_even_when_user_and_email_match(self) -> None:
        personal = make_access_token(
            account_id="acct-personal",
            subject="user-1",
            email="same@example.com",
            exp=100,
        )
        team = make_access_token(
            account_id="acct-team",
            subject="user-1",
            email="same@example.com",
            exp=200,
        )
        service = IsolatedAccountService(MemoryStorage())

        result = service.add_accounts([personal, team], source_type="codex")

        self.assertEqual(result["added"], 2)
        self.assertEqual(result["skipped"], 0)
        self.assertCountEqual(service.list_tokens(), [personal, team])

    def test_subject_and_then_email_are_used_when_account_id_is_missing(self) -> None:
        old_subject_token = make_access_token(subject="user-1", exp=100)
        new_subject_token = make_access_token(subject="user-1", exp=200)
        service = IsolatedAccountService(MemoryStorage())

        subject_result = service.add_accounts([old_subject_token, new_subject_token])
        first_email_token = "opaque-token-1"
        second_email_token = "opaque-token-2"
        email_result = service.add_account_items(
            [
                {"access_token": first_email_token, "email": " User@Example.com "},
                {"access_token": second_email_token, "email": "user@example.com"},
            ]
        )

        self.assertEqual(subject_result["added"], 1)
        self.assertEqual(subject_result["skipped"], 1)
        self.assertEqual(email_result["added"], 1)
        self.assertEqual(email_result["skipped"], 1)
        self.assertEqual(len(service.list_tokens()), 2)
        self.assertIn(new_subject_token, service.list_tokens())
        self.assertIn(second_email_token, service.list_tokens())

    def test_repeated_opaque_tokens_do_not_create_an_alias_cycle(self) -> None:
        service = IsolatedAccountService(MemoryStorage())

        result = service.add_account_items(
            [
                {"access_token": "opaque-a", "email": "same@example.com"},
                {"access_token": "opaque-b", "email": "same@example.com"},
                {"access_token": "opaque-a", "email": "same@example.com"},
            ]
        )

        self.assertEqual(result["added"], 1)
        self.assertEqual(result["skipped"], 2)
        self.assertEqual(service.list_tokens(), ["opaque-a"])
        self.assertEqual(service.resolve_access_token("opaque-b"), "opaque-a")

    def test_token_account_id_takes_precedence_over_stale_import_metadata(self) -> None:
        old_token = make_access_token(account_id="acct-1", exp=100)
        new_token = make_access_token(account_id="acct-1", exp=200)
        service = IsolatedAccountService(MemoryStorage())

        result = service.add_account_items(
            [
                {"access_token": old_token, "account_id": "stale-old"},
                {"access_token": new_token, "account_id": "stale-new"},
            ]
        )

        self.assertEqual(result["added"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(service.list_tokens(), [new_token])

    def test_refresh_accounts_resolves_aliases_before_deduplicating(self) -> None:
        old_token = make_access_token(account_id="acct-1", exp=100)
        new_token = make_access_token(account_id="acct-1", exp=200)
        service = IsolatedAccountService(MemoryStorage())
        service.add_accounts([old_token, new_token], source_type="codex")

        with mock.patch.object(
            service,
            "fetch_remote_info",
            side_effect=lambda token, *_args: service.get_account(token),
        ) as fetch_remote_info:
            result = service.refresh_accounts([old_token, new_token])

        self.assertEqual(result["refreshed"], 1)
        fetch_remote_info.assert_called_once()
        self.assertEqual(fetch_remote_info.call_args.args[0], new_token)

    def test_replaced_token_is_persisted_by_json_and_database_backends(self) -> None:
        old_token = make_access_token(account_id="acct-1", exp=100, iat=10)
        new_token = make_access_token(account_id="acct-1", exp=200, iat=20)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            backends = [
                JSONStorageBackend(root / "accounts.json"),
                DatabaseStorageBackend(f"sqlite:///{root / 'accounts.db'}"),
            ]
            try:
                for backend in backends:
                    service = IsolatedAccountService(backend)
                    service.add_accounts([old_token], source_type="codex")
                    service.add_accounts([new_token], source_type="codex")

                    reloaded = IsolatedAccountService(backend)
                    self.assertEqual(reloaded.list_tokens(), [new_token])
            finally:
                for backend in backends:
                    if isinstance(backend, DatabaseStorageBackend):
                        backend.engine.dispose()


if __name__ == "__main__":
    unittest.main()
