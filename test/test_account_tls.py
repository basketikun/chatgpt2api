from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.account_service import AccountService
from services.oauth_login_service import OAuthLoginService
from services.proxy_service import ProxyRuntimeProfile, proxy_settings
from services.storage.json_storage import JSONStorageBackend


class FakeTokenResponse:
    status_code = 200
    text = "token response"

    @staticmethod
    def json() -> dict[str, str]:
        return {
            "access_token": "access",
            "refresh_token": "refresh",
            "id_token": "id",
        }


class FakeTokenSession:
    def __init__(self) -> None:
        self.post_kwargs: dict | None = None
        self.closed = False

    def post(self, _url: str, **kwargs):
        self.post_kwargs = kwargs
        return FakeTokenResponse()

    def close(self) -> None:
        self.closed = True


class AccountTLSVerificationTests(unittest.TestCase):
    def test_required_tls_overrides_proxy_skip_verify(self) -> None:
        profile = ProxyRuntimeProfile(
            proxy_url="http://proxy.example:8080",
            runtime_enabled=True,
            skip_ssl_verify=True,
        )
        with mock.patch.object(proxy_settings, "get_profile", return_value=profile):
            kwargs = proxy_settings.build_session_kwargs(require_tls_verification=True)

        self.assertEqual(kwargs["proxy"], "http://proxy.example:8080")
        self.assertIs(kwargs["verify"], True)
        self.assertNotIn("require_tls_verification", kwargs)

    def test_oauth_code_exchange_uses_verified_session(self) -> None:
        session = FakeTokenSession()
        with (
            mock.patch.object(
                proxy_settings,
                "build_session_kwargs",
                return_value={"verify": True},
            ) as kwargs_builder,
            mock.patch("services.oauth_login_service.requests.Session", return_value=session) as session_factory,
        ):
            result = OAuthLoginService._exchange_code("code", "verifier", "https://example.test/callback")

        kwargs_builder.assert_called_once_with(
            impersonate="chrome",
            require_tls_verification=True,
        )
        session_factory.assert_called_once_with(verify=True)
        self.assertNotIn("verify", session.post_kwargs or {})
        self.assertTrue(session.closed)
        self.assertEqual(result["access_token"], "access")

    def test_password_login_constructs_a_verified_proxy_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = AccountService(JSONStorageBackend(Path(directory) / "accounts.json"))
            with (
                mock.patch.object(
                    proxy_settings,
                    "build_session_kwargs",
                    return_value={"impersonate": "chrome110", "verify": True},
                ) as kwargs_builder,
                mock.patch("services.account_service.config.get_proxy_settings", return_value=""),
                mock.patch("curl_cffi.requests.Session", side_effect=RuntimeError("session-created")) as session_factory,
                self.assertRaisesRegex(RuntimeError, "session-created"),
            ):
                service._login_with_password("user@example.test", "secret")

        kwargs_builder.assert_called_once_with(
            proxy="",
            impersonate="chrome110",
            require_tls_verification=True,
        )
        session_factory.assert_called_once_with(impersonate="chrome110", verify=True)


if __name__ == "__main__":
    unittest.main()
