import unittest
import time
from threading import Event
from unittest.mock import patch

from services.proxy_service import ClearanceBundle, ProxyRuntimeProfile
from services.register import mail_provider
from services.register import openai_register


class FakeResponse:
    def __init__(self, status_code=200, text="", headers=None, url="https://auth.openai.com/test"):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.url = url

    def json(self):
        return {}


class FakeCookieJar:
    def __init__(self):
        self.items = []

    def set(self, name, value, domain=None):
        self.items.append({"name": name, "value": value, "domain": domain})


class FakeSession:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.headers = {}
        self.cookies = FakeCookieJar()
        self.closed = False

    def close(self):
        self.closed = True


class FakeProxySettings:
    def __init__(self, bundle=None, clearance_enabled=None):
        self.bundle = bundle
        self.clearance_enabled = bool(bundle is not None if clearance_enabled is None else clearance_enabled)
        self.refreshed = False
        self.session_kwargs_calls = []
        self.build_headers_calls = []
        self.refresh_calls = []

    def build_session_kwargs(self, **kwargs):
        self.session_kwargs_calls.append(kwargs)
        return dict(kwargs, proxy="http://runtime.example:8118")

    def get_profile(self, **kwargs):
        return ProxyRuntimeProfile(
            proxy_url=str(kwargs.get("proxy") or ""),
            proxy_source="explicit" if kwargs.get("proxy") else "direct",
            runtime_enabled=self.clearance_enabled,
            egress_mode="single_proxy",
            clearance={"enabled": self.clearance_enabled, "mode": "flaresolverr", "timeout_sec": 60},
        )

    def build_headers(self, headers=None, target_url="", proxy="", upstream=True, **kwargs):
        self.build_headers_calls.append({"target_url": target_url, "proxy": proxy, "upstream": upstream})
        merged = dict(headers or {})
        if self.refreshed and self.bundle and self.bundle.cookies:
            merged["Cookie"] = "; ".join(f"{key}={value}" for key, value in self.bundle.cookies.items())
        return merged

    def refresh_clearance(self, target_url="", proxy="", force=False, upstream=True, **kwargs):
        self.refresh_calls.append({"target_url": target_url, "proxy": proxy, "force": force, "upstream": upstream})
        self.refreshed = self.bundle is not None
        return self.bundle


class RegisterProxyRuntimeTests(unittest.TestCase):
    def test_mail_config_does_not_inherit_openai_register_proxy(self):
        original = dict(openai_register.config)
        try:
            openai_register.config.update(
                {
                    "proxy": "http://openai-proxy.example:8080",
                    "mail": {"request_timeout": 30, "wait_timeout": 30, "wait_interval": 2, "providers": []},
                }
            )

            mail_config = openai_register._mail_config()
        finally:
            openai_register.config.clear()
            openai_register.config.update(original)

        self.assertNotIn("proxy", mail_config)

    def test_mail_provider_fast_polling_defaults(self):
        conf = mail_provider._config({"request_timeout": 30, "wait_timeout": 30, "wait_interval": 3})

        self.assertEqual(conf["fast_wait_seconds"], 10)
        self.assertEqual(conf["fast_wait_interval"], 0.8)
        self.assertEqual(conf["wait_interval"], 3)

    def test_register_metrics_snapshot_aggregates_stage_provider_and_otp(self):
        openai_register.reset_stats(time.time())
        try:
            openai_register.record_register_success(
                {
                    "stage_ms": {"create_mailbox_ms": 100, "wait_otp_ms": 900},
                    "mailbox_provider": "cloudmail_gen",
                    "otp_wait_seconds": 0.9,
                }
            )
            openai_register.record_register_failure(openai_register.RegisterStageError("wait_otp", RuntimeError("timeout")))
            snapshot = openai_register.snapshot_extra_stats()
        finally:
            openai_register.reset_stats(0.0)

        self.assertEqual(snapshot["avg_stage_ms"]["create_mailbox_ms"], 100)
        self.assertEqual(snapshot["avg_stage_ms"]["wait_otp_ms"], 900)
        self.assertEqual(snapshot["mailbox_provider_success"]["cloudmail_gen"], 1)
        self.assertEqual(snapshot["otp_wait_avg_seconds"], 0.9)
        self.assertEqual(snapshot["last_errors_by_stage"]["wait_otp"], "timeout")

    def test_worker_saves_account_before_async_refresh_finishes(self):
        class FakeRegistrar:
            def __init__(self, proxy=""):
                self.proxy = proxy
                self.closed = False

            def register(self, index):
                return {
                    "email": "user@example.com",
                    "password": "secret",
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "id_token": "",
                    "source_type": "web",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "_register_metrics": {
                        "stage_ms": {"create_mailbox_ms": 10},
                        "mailbox_provider": "cloudmail_gen",
                        "otp_wait_seconds": 1,
                    },
                }

            def close(self):
                self.closed = True

        refresh_started = Event()
        refresh_release = Event()
        refresh_done = Event()
        saved_accounts = []

        def fake_add(items):
            saved_accounts.extend(items)

        def fake_refresh(tokens):
            refresh_started.set()
            refresh_release.wait(1)
            refresh_done.set()
            return {"errors": []}

        openai_register.reset_stats(time.time())
        try:
            with patch.object(openai_register, "PlatformRegistrar", FakeRegistrar), patch.object(
                openai_register.account_service,
                "add_account_items",
                side_effect=fake_add,
            ), patch.object(openai_register.account_service, "refresh_accounts", side_effect=fake_refresh):
                result = openai_register.worker(1)

            self.assertTrue(result["ok"])
            self.assertEqual(saved_accounts[0]["email"], "user@example.com")
            self.assertNotIn("_register_metrics", saved_accounts[0])
            self.assertTrue(refresh_started.wait(1))
            self.assertFalse(refresh_done.is_set())
            refresh_release.set()
            self.assertTrue(refresh_done.wait(1))
        finally:
            refresh_release.set()
            openai_register.reset_stats(0.0)

    def test_worker_failure_logs_standardized_stage(self):
        class FailingRegistrar:
            def __init__(self, proxy=""):
                self.stage_ms = {"wait_otp_ms": 5000}

            def register(self, index):
                raise openai_register.RegisterStageError("wait_otp", RuntimeError("timeout"))

            def close(self):
                pass

        messages = []

        openai_register.reset_stats(time.time())
        try:
            with patch.object(openai_register, "PlatformRegistrar", FailingRegistrar), patch.object(
                openai_register,
                "log",
                side_effect=lambda text, color="": messages.append(text),
            ):
                result = openai_register.worker(2)
            snapshot = openai_register.snapshot_extra_stats()
        finally:
            openai_register.reset_stats(0.0)

        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "wait_otp")
        self.assertTrue(any("stage=wait_otp" in message for message in messages))
        self.assertEqual(snapshot["avg_stage_ms"]["wait_otp_ms"], 5000)

    def test_create_session_uses_proxy_settings_without_breaking_existing_proxy_argument(self):
        fake_proxy = FakeProxySettings()
        created = []

        def fake_session_factory(**kwargs):
            session = FakeSession(**kwargs)
            created.append(session)
            return session

        with patch.object(openai_register, "proxy_settings", fake_proxy), patch.object(
            openai_register.requests,
            "Session",
            side_effect=fake_session_factory,
        ):
            session = openai_register.create_session("http://legacy-register.example:8080")

        self.assertIs(session, created[0])
        self.assertEqual(fake_proxy.session_kwargs_calls[0]["proxy"], "http://legacy-register.example:8080")
        self.assertTrue(fake_proxy.session_kwargs_calls[0]["upstream"])
        self.assertEqual(fake_proxy.session_kwargs_calls[0]["impersonate"], "chrome")
        self.assertFalse(fake_proxy.session_kwargs_calls[0]["verify"])
        self.assertEqual(session.kwargs["proxy"], "http://runtime.example:8118")

    def test_cloudflare_without_clearance_keeps_clear_register_error(self):
        fake_proxy = FakeProxySettings(bundle=None)
        cf_response = FakeResponse(
            status_code=403,
            text="<html><title>Just a moment...</title></html>",
            headers={"server": "cloudflare", "content-type": "text/html"},
            url="https://auth.openai.com/api/accounts/authorize",
        )

        with patch.object(openai_register, "proxy_settings", fake_proxy), patch.object(
            openai_register,
            "create_session",
            return_value=FakeSession(),
        ), patch.object(openai_register, "request_with_local_retry", return_value=(cf_response, "")):
            registrar = openai_register.PlatformRegistrar(proxy="http://legacy-register.example:8080")
            with self.assertRaisesRegex(RuntimeError, "Cloudflare") as ctx:
                registrar._platform_authorize("user@example.com", 1)

        self.assertEqual(len(fake_proxy.refresh_calls), 0)
        self.assertIn("status=403", str(ctx.exception))
        self.assertIn("Just a moment", str(ctx.exception))

    def test_openai_html_behind_cloudflare_is_not_treated_as_challenge(self):
        response = FakeResponse(
            status_code=200,
            text="""
            <!DOCTYPE html><html lang=\"en-US\"><head>
            <title>Create a password - OpenAI</title>
            </head><body>OpenAI account page</body></html>
            """,
            headers={"server": "cloudflare", "content-type": "text/html; charset=utf-8"},
            url="https://auth.openai.com/create-account/password",
        )

        self.assertFalse(openai_register._is_cloudflare_challenge(response))

    def test_cloudflare_challenge_refreshes_clearance_and_retries_once_with_matching_headers(self):
        bundle = ClearanceBundle(
            target_host="auth.openai.com",
            proxy_url="http://runtime.example:8118",
            cookies={"cf_clearance": "flare-token"},
            user_agent="Flare UA",
        )
        fake_proxy = FakeProxySettings(bundle=bundle)
        responses = [
            FakeResponse(
                status_code=403,
                text="<html><title>Just a moment...</title></html>",
                headers={"server": "cloudflare", "content-type": "text/html"},
                url="https://auth.openai.com/api/accounts/authorize",
            ),
            FakeResponse(status_code=200, text="{}", headers={"content-type": "application/json"}),
        ]
        request_calls = []

        def fake_request(session, method, url, retry_attempts=3, **kwargs):
            request_calls.append({"method": method, "url": url, "headers": dict(kwargs.get("headers") or {})})
            return responses.pop(0), ""

        with patch.object(openai_register, "proxy_settings", fake_proxy), patch.object(
            openai_register,
            "create_session",
            return_value=FakeSession(),
        ), patch.object(openai_register, "request_with_local_retry", side_effect=fake_request):
            registrar = openai_register.PlatformRegistrar(proxy="http://legacy-register.example:8080")
            registrar._platform_authorize("user@example.com", 1)

        self.assertEqual(len(request_calls), 2)
        self.assertEqual(len(fake_proxy.refresh_calls), 1)
        retry_headers = {key.lower(): value for key, value in request_calls[1]["headers"].items()}
        self.assertEqual(retry_headers["user-agent"], "Flare UA")
        self.assertEqual(retry_headers["cookie"], "cf_clearance=flare-token")
        self.assertEqual(fake_proxy.refresh_calls[0]["target_url"], openai_register.auth_base)
        self.assertEqual(fake_proxy.refresh_calls[0]["proxy"], "http://legacy-register.example:8080")
        self.assertTrue(fake_proxy.refresh_calls[0]["force"])

    def test_refresh_failure_reports_cloudflare_detail_without_infinite_retry(self):
        fake_proxy = FakeProxySettings(bundle=None, clearance_enabled=True)
        cf_response = FakeResponse(
            status_code=403,
            text="<html><title>Just a moment...</title><body>challenge body</body></html>",
            headers={"server": "cloudflare", "content-type": "text/html"},
            url="https://auth.openai.com/api/accounts/authorize",
        )
        request_calls = []

        def fake_request(session, method, url, retry_attempts=3, **kwargs):
            request_calls.append({"method": method, "url": url})
            return cf_response, ""

        with patch.object(openai_register, "proxy_settings", fake_proxy), patch.object(
            openai_register,
            "create_session",
            return_value=FakeSession(),
        ), patch.object(openai_register, "request_with_local_retry", side_effect=fake_request):
            registrar = openai_register.PlatformRegistrar(proxy="")
            with self.assertRaisesRegex(RuntimeError, "Cloudflare") as ctx:
                registrar._platform_authorize("user@example.com", 1)

        self.assertEqual(len(request_calls), 1)
        self.assertEqual(len(fake_proxy.refresh_calls), 1)
        message = str(ctx.exception)
        self.assertIn("status=403", message)
        self.assertIn("challenge body", message)


if __name__ == "__main__":
    unittest.main()
