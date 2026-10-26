import copy
import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from urllib.parse import urlparse

from services.config import DEFAULT_PROXY_RUNTIME
from services.proxy_service import (
    ClearanceBundle,
    FlareSolverrClearanceProvider,
    ProxySettingsStore,
    normalize_proxy_url,
)


class FakeConfig:
    def __init__(self, legacy_proxy: str = "", runtime: dict[str, object] | None = None) -> None:
        self.legacy_proxy = legacy_proxy
        self.runtime = runtime if runtime is not None else copy.deepcopy(DEFAULT_PROXY_RUNTIME)

    def get_proxy_settings(self) -> str:
        return self.legacy_proxy

    def get_proxy_runtime_settings(self) -> dict[str, object]:
        return copy.deepcopy(self.runtime)


def make_runtime(**overrides: object) -> dict[str, object]:
    runtime = copy.deepcopy(DEFAULT_PROXY_RUNTIME)
    clearance = overrides.pop("clearance", None)
    runtime.update(overrides)
    if clearance is not None:
        runtime["clearance"].update(clearance)  # type: ignore[index,union-attr]
    return runtime


class ProxyServiceTests(unittest.TestCase):
    def test_normalize_proxy_url_strips_and_converts_socks_schemes(self) -> None:
        self.assertEqual(normalize_proxy_url("  http://proxy.example:8080  "), "http://proxy.example:8080")
        self.assertEqual(normalize_proxy_url("\thttps://proxy.example:8443\n"), "https://proxy.example:8443")
        self.assertEqual(normalize_proxy_url(" socks://proxy.example:1080 "), "socks5h://proxy.example:1080")
        self.assertEqual(normalize_proxy_url("socks5://proxy.example:1080"), "socks5h://proxy.example:1080")
        self.assertEqual(normalize_proxy_url(" socks5h://proxy.example:1080 "), "socks5h://proxy.example:1080")
        self.assertEqual(normalize_proxy_url("   "), "")

    def test_build_session_kwargs_keeps_legacy_global_proxy_when_runtime_disabled(self) -> None:
        store = ProxySettingsStore(FakeConfig(legacy_proxy="  http://legacy.example:8080  "))

        kwargs = store.build_session_kwargs(impersonate="chrome")

        self.assertEqual(kwargs["impersonate"], "chrome")
        self.assertEqual(kwargs["proxy"], "http://legacy.example:8080")

    def test_runtime_proxy_is_limited_to_upstream_scope_by_default(self) -> None:
        runtime = make_runtime(enabled=True, egress_mode="single_proxy", proxy_url="http://runtime.example:8080")
        store = ProxySettingsStore(FakeConfig(legacy_proxy="http://legacy.example:8080", runtime=runtime))

        self.assertEqual(
            store.build_session_kwargs()["proxy"],
            "http://legacy.example:8080",
        )
        self.assertEqual(
            store.build_session_kwargs(upstream=True)["proxy"],
            "http://runtime.example:8080",
        )

    def test_account_proxy_wins_over_runtime_and_global_proxy(self) -> None:
        runtime = make_runtime(enabled=True, egress_mode="single_proxy", proxy_url="http://runtime.example:8080")
        store = ProxySettingsStore(FakeConfig(legacy_proxy="http://legacy.example:8080", runtime=runtime))

        kwargs = store.build_session_kwargs(account={"proxy": " socks://account.example:1080 "}, upstream=True)

        self.assertEqual(kwargs["proxy"], "socks5h://account.example:1080")

    def test_proxy_runtime_single_proxy_wins_over_explicit_and_legacy_proxy_when_enabled(self) -> None:
        runtime = make_runtime(enabled=True, egress_mode="single_proxy", proxy_url=" socks5://runtime.example:1080 ")
        store = ProxySettingsStore(FakeConfig(legacy_proxy="http://legacy.example:8080", runtime=runtime))

        kwargs = store.build_session_kwargs(proxy="http://explicit.example:8080", upstream=True)

        self.assertEqual(kwargs["proxy"], "socks5h://runtime.example:1080")

    def test_explicit_proxy_wins_over_legacy_global_proxy_when_runtime_disabled(self) -> None:
        store = ProxySettingsStore(FakeConfig(legacy_proxy="http://legacy.example:8080"))

        kwargs = store.build_session_kwargs(proxy=" socks5://explicit.example:1080 ")

        self.assertEqual(kwargs["proxy"], "socks5h://explicit.example:1080")

    def test_resource_requests_use_resource_proxy_url_when_configured(self) -> None:
        runtime = make_runtime(
            enabled=True,
            egress_mode="single_proxy",
            proxy_url="http://runtime.example:8080",
            resource_proxy_url=" socks5://resource.example:1080 ",
            resource_proxy_enabled=True,
        )
        store = ProxySettingsStore(FakeConfig(legacy_proxy="http://legacy.example:8080", runtime=runtime))

        kwargs = store.build_session_kwargs(resource=True, upstream=True)

        self.assertEqual(kwargs["proxy"], "socks5h://resource.example:1080")

    def test_resource_requests_stay_direct_until_explicitly_enabled(self) -> None:
        runtime = make_runtime(
            enabled=True,
            egress_mode="single_proxy",
            proxy_url="http://runtime.example:8080",
            resource_proxy_url="http://resource.example:1080",
        )
        store = ProxySettingsStore(FakeConfig(runtime=runtime))

        kwargs = store.build_session_kwargs(resource=True, upstream=True)

        self.assertNotIn("proxy", kwargs)

    def test_resource_proxy_switch_accepts_string_boolean(self) -> None:
        runtime = make_runtime(
            enabled=True,
            egress_mode="single_proxy",
            proxy_url="http://runtime.example:8080",
            resource_proxy_enabled="true",
        )
        store = ProxySettingsStore(FakeConfig(runtime=runtime))

        kwargs = store.build_session_kwargs(resource=True, upstream=True)

        self.assertEqual(kwargs["proxy"], "http://runtime.example:8080")

    def test_manual_clearance_merges_cookies_and_preserves_explicit_user_agent(self) -> None:
        runtime = make_runtime(
            enabled=True,
            egress_mode="single_proxy",
            proxy_url="http://runtime.example:8080",
            clearance={
                "enabled": True,
                "mode": "manual",
                "cf_cookies": "foo=bar; session=ok",
                "cf_clearance": "manual-token",
                "user_agent": "Manual UA",
            },
        )
        store = ProxySettingsStore(FakeConfig(runtime=runtime))

        headers = store.build_headers(headers={"Cookie": "existing=1"}, target_url="https://chatgpt.com/backend-api")

        self.assertEqual(headers["User-Agent"], "Manual UA")
        self.assertEqual(headers["Cookie"], "existing=1; foo=bar; session=ok; cf_clearance=manual-token")

        headers_with_ua = store.build_headers(
            headers={"User-Agent": "Caller UA", "Cookie": "cf_clearance=caller-token"},
            target_url="https://chatgpt.com/backend-api",
        )

        self.assertEqual(headers_with_ua["User-Agent"], "Caller UA")
        self.assertEqual(headers_with_ua["Cookie"], "cf_clearance=caller-token; foo=bar; session=ok")
        self.assertNotIn("cf_clearance=manual-token", headers_with_ua["Cookie"])

    def test_flaresolverr_provider_parses_solution_and_filters_cookies_by_host(self) -> None:
        calls: list[tuple[str, dict[str, object], dict[str, str], float]] = []

        def fake_request(endpoint: str, body: bytes, headers: dict[str, str], timeout: float) -> bytes:
            payload = json.loads(body.decode("utf-8"))
            calls.append((endpoint, payload, headers, timeout))
            return json.dumps(
                {
                    "status": "ok",
                    "solution": {
                        "userAgent": "Flare UA",
                        "cookies": [
                            {"name": "cf_clearance", "value": "host-token", "domain": ".chatgpt.com"},
                            {"name": "no_domain", "value": "kept"},
                            {"name": "wrong_host", "value": "dropped", "domain": "example.net"},
                        ],
                    },
                }
            ).encode("utf-8")

        provider = FlareSolverrClearanceProvider("http://flare.local/", request_method=fake_request)

        bundle = provider.get_clearance(
            "https://chatgpt.com/backend-api/conversation",
            proxy_url="socks5h://proxy.example:1080",
            timeout_sec=12,
        )

        self.assertIsNotNone(bundle)
        assert bundle is not None
        endpoint, payload, headers, timeout = calls[0]
        self.assertEqual(endpoint, "http://flare.local/v1")
        self.assertEqual(payload["cmd"], "request.get")
        self.assertEqual(payload["url"], "https://chatgpt.com/backend-api/conversation")
        self.assertEqual(payload["maxTimeout"], 12000)
        self.assertEqual(payload["proxy"], {"url": "socks5h://proxy.example:1080"})
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(timeout, 12)
        self.assertEqual(bundle.user_agent, "Flare UA")
        self.assertEqual(bundle.cookies, {"cf_clearance": "host-token", "no_domain": "kept"})

    def test_flaresolverr_provider_keeps_only_matching_or_no_domain_cookies(self) -> None:
        def fake_request(endpoint: str, body: bytes, headers: dict[str, str], timeout: float) -> bytes:
            return json.dumps(
                {
                    "status": "ok",
                    "solution": {
                        "userAgent": "Filtered UA",
                        "cookies": [
                            {"name": "wrong_host", "value": "dropped", "domain": "example.net"},
                            {"name": "also_wrong", "value": "dropped-too", "domain": ".example.org"},
                            {"name": "no_domain", "value": "kept"},
                        ],
                    },
                }
            ).encode("utf-8")

        provider = FlareSolverrClearanceProvider("http://flare.local", request_method=fake_request)

        bundle = provider.get_clearance("https://chatgpt.com", timeout_sec=5)

        self.assertIsNotNone(bundle)
        assert bundle is not None
        self.assertEqual(bundle.cookies, {"no_domain": "kept"})
        self.assertEqual(bundle.user_agent, "Filtered UA")

    def test_flaresolverr_provider_drops_all_wrong_domain_cookies(self) -> None:
        def fake_request(endpoint: str, body: bytes, headers: dict[str, str], timeout: float) -> bytes:
            return json.dumps(
                {
                    "status": "ok",
                    "solution": {
                        "cookies": [
                            {"name": "wrong_host", "value": "dropped", "domain": "example.net"},
                        ],
                    },
                }
            ).encode("utf-8")

        provider = FlareSolverrClearanceProvider("http://flare.local", request_method=fake_request)

        self.assertIsNone(provider.get_clearance("https://chatgpt.com", timeout_sec=5))

    def test_cached_flaresolverr_bundle_is_merged_by_build_headers_and_can_be_invalidated(self) -> None:
        runtime = make_runtime(
            enabled=True,
            egress_mode="single_proxy",
            proxy_url="http://runtime.example:8080",
            clearance={
                "enabled": True,
                "mode": "flaresolverr",
                "flaresolverr_url": "http://flare.local",
                "timeout_sec": 5,
            },
        )
        bundle = ClearanceBundle(
            target_host="chatgpt.com",
            proxy_url="http://runtime.example:8080",
            cookies={"cf_clearance": "flare-token"},
            user_agent="Flare UA",
        )

        class FakeProvider:
            def get_clearance(self, target_url: str, proxy_url: str = "", timeout_sec: int = 60) -> ClearanceBundle | None:
                return bundle

        store = ProxySettingsStore(FakeConfig(runtime=runtime), clearance_provider_factory=lambda _url: FakeProvider())
        store.refresh_clearance(target_url="https://chatgpt.com", force=True)

        headers = store.build_headers(headers={"Cookie": "existing=1"}, target_url="https://chatgpt.com/backend-api")

        self.assertEqual(headers["User-Agent"], "Flare UA")
        self.assertEqual(headers["Cookie"], "existing=1; cf_clearance=flare-token")

        store.invalidate_clearance(target_url="https://chatgpt.com")
        self.assertEqual(
            store.build_headers(headers={"Cookie": "existing=1"}, target_url="https://chatgpt.com/backend-api"),
            {"Cookie": "existing=1"},
        )

    def test_flaresolverr_refresh_failure_keeps_old_cached_bundle(self) -> None:
        runtime = make_runtime(
            enabled=True,
            egress_mode="single_proxy",
            proxy_url="http://runtime.example:8080",
            clearance={
                "enabled": True,
                "mode": "flaresolverr",
                "flaresolverr_url": "http://flare.local",
                "timeout_sec": 5,
            },
        )
        first_bundle = ClearanceBundle(
            target_host="chatgpt.com",
            proxy_url="http://runtime.example:8080",
            cookies={"cf_clearance": "old-token"},
            user_agent="Old UA",
        )

        class FakeProvider:
            def __init__(self) -> None:
                self.calls = 0

            def get_clearance(self, target_url: str, proxy_url: str = "", timeout_sec: int = 60) -> ClearanceBundle | None:
                self.calls += 1
                return first_bundle if self.calls == 1 else None

        provider = FakeProvider()
        store = ProxySettingsStore(FakeConfig(runtime=runtime), clearance_provider_factory=lambda _url: provider)

        refreshed = store.refresh_clearance(target_url="https://chatgpt.com", force=True)
        fallback = store.refresh_clearance(target_url="https://chatgpt.com", force=True)

        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertEqual(refreshed.cookies, first_bundle.cookies)
        self.assertIsNotNone(refreshed.expires_at)
        assert refreshed.expires_at is not None
        self.assertAlmostEqual(refreshed.expires_at - refreshed.created_at, 3600, places=2)
        self.assertIs(fallback, refreshed)
        self.assertEqual(provider.calls, 2)

    def test_flaresolverr_bundle_expires_after_refresh_interval(self) -> None:
        runtime = make_runtime(
            enabled=True,
            egress_mode="single_proxy",
            proxy_url="http://runtime.example:8080",
            clearance={
                "enabled": True,
                "mode": "flaresolverr",
                "flaresolverr_url": "http://flare.local",
                "timeout_sec": 5,
                "refresh_interval": 60,
            },
        )

        class FakeProvider:
            def get_clearance(self, target_url: str, proxy_url: str = "", timeout_sec: int = 60) -> ClearanceBundle | None:
                return ClearanceBundle(
                    target_host="chatgpt.com",
                    proxy_url=proxy_url,
                    cookies={"cf_clearance": "expiring-token"},
                    user_agent="Expiring UA",
                    created_at=1000,
                )

        store = ProxySettingsStore(FakeConfig(runtime=runtime), clearance_provider_factory=lambda _url: FakeProvider())
        with patch("services.proxy_service.time.time", return_value=1000):
            bundle = store.refresh_clearance(target_url="https://chatgpt.com", force=True)

        self.assertIsNotNone(bundle)
        assert bundle is not None
        self.assertEqual(bundle.expires_at, 1060)
        self.assertTrue(bundle.is_valid_for("chatgpt.com", "http://runtime.example:8080", now=1059))
        self.assertFalse(bundle.is_valid_for("chatgpt.com", "http://runtime.example:8080", now=1060))

    def test_profile_repr_does_not_expose_clearance_secrets(self) -> None:
        runtime = make_runtime(
            enabled=True,
            clearance={
                "enabled": True,
                "mode": "manual",
                "cf_cookies": "foo=secret-cookie",
                "cf_clearance": "secret-clearance",
            },
        )
        profile = ProxySettingsStore(FakeConfig(runtime=runtime)).get_profile()

        text = repr(profile)

        self.assertNotIn("secret-cookie", text)
        self.assertNotIn("secret-clearance", text)

    def test_proxy_test_error_redacts_proxy_credentials(self) -> None:
        class FailingSession:
            def __init__(self, **kwargs: object) -> None:
                pass

            def get(self, *args: object, **kwargs: object) -> object:
                raise RuntimeError("proxy failed for http://user:pass@proxy.example:8080")

            def close(self) -> None:
                pass

        with patch("services.proxy_service.Session", FailingSession):
            result = __import__("services.proxy_service", fromlist=["test_proxy"]).test_proxy(
                "http://user:pass@proxy.example:8080"
            )

        self.assertFalse(result["ok"])
        self.assertIn("[REDACTED]", result["error"])
        self.assertNotIn("user:pass", result["error"])

    def test_concurrent_flaresolverr_refresh_uses_single_flight_per_proxy_and_host(self) -> None:
        runtime = make_runtime(
            enabled=True,
            egress_mode="single_proxy",
            proxy_url="http://runtime.example:8080",
            clearance={
                "enabled": True,
                "mode": "flaresolverr",
                "flaresolverr_url": "http://flare.local",
                "timeout_sec": 5,
            },
        )

        class SlowProvider:
            def __init__(self) -> None:
                self.calls = 0
                self.lock = threading.Lock()

            def get_clearance(self, target_url: str, proxy_url: str = "", timeout_sec: int = 60) -> ClearanceBundle | None:
                with self.lock:
                    self.calls += 1
                time.sleep(0.15)
                return ClearanceBundle(
                    target_host=urlparse(target_url).hostname or "",
                    proxy_url=proxy_url,
                    cookies={"cf_clearance": "thread-token"},
                    user_agent="Thread UA",
                )

        provider = SlowProvider()
        store = ProxySettingsStore(FakeConfig(runtime=runtime), clearance_provider_factory=lambda _url: provider)
        workers = 6
        start = threading.Barrier(workers)

        def refresh() -> ClearanceBundle | None:
            start.wait(timeout=5)
            return store.refresh_clearance(target_url="https://chatgpt.com", force=True)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(lambda _index: refresh(), range(workers)))

        self.assertEqual(provider.calls, 1)
        self.assertTrue(all(result is results[0] for result in results))
        self.assertIsNotNone(results[0])


if __name__ == "__main__":
    unittest.main()
