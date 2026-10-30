from __future__ import annotations

import os

import copy
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.system as system_module
from services.config import DEFAULT_PROXY_RUNTIME


AUTH_KEY = os.environ.get("CHATGPT2API_AUTH_KEY", "chatgpt2api")
AUTH_HEADERS = {"Authorization": f"Bearer {AUTH_KEY}"}


class FakeStorage:
    def get_backend_info(self) -> dict[str, object]:
        return {"type": "json"}

    def health_check(self) -> dict[str, object]:
        return {"ok": True}


class FakeConfig:
    def __init__(self) -> None:
        self.data: dict[str, object] = {
            "proxy": "",
            "proxy_runtime": copy.deepcopy(DEFAULT_PROXY_RUNTIME),
        }

    def get(self) -> dict[str, object]:
        return copy.deepcopy(self.data)

    def update(self, updates: dict[str, object]) -> dict[str, object]:
        self.data.update(copy.deepcopy(updates))
        return self.get()

    def get_proxy_settings(self) -> str:
        return str(self.data.get("proxy") or "").strip()

    def get_proxy_runtime_settings(self) -> dict[str, object]:
        return copy.deepcopy(self.data["proxy_runtime"])  # type: ignore[index]

    def get_public_proxy_runtime_settings(self) -> dict[str, object]:
        return self.get_proxy_runtime_settings()

    def get_storage_backend(self) -> FakeStorage:
        return FakeStorage()


class FakeProxySettings:
    def get_runtime_status(self) -> dict[str, object]:
        return {
            "enabled": True,
            "egress_mode": "single_proxy",
            "proxy_source": "proxy_runtime",
            "has_proxy": True,
            "clearance_enabled": True,
            "clearance_mode": "flaresolverr",
            "has_clearance_bundle": False,
            "cached_clearance_hosts": [],
        }


class FakeAccountService:
    def get_stats(self) -> dict[str, object]:
        return {
            "total": 1,
            "cumulative_total": 1,
            "active": 1,
            "total_quota": 1,
            "limited": 0,
            "abnormal": 0,
            "disabled": 0,
            "total_success": 0,
            "total_fail": 0,
            "by_type": {"web": 1},
        }


class ProxyRuntimeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_config = FakeConfig()
        self.fake_proxy_settings = FakeProxySettings()
        self.test_proxy_calls: list[str] = []
        self.test_clearance_calls: list[str] = []

        def fake_test_proxy(url: str = "") -> dict[str, object]:
            self.test_proxy_calls.append(url)
            return {
                "ok": True,
                "status": 204,
                "latency_ms": 12,
                "error": None,
                "proxy_source": "proxy_runtime" if not url else "input",
                "has_proxy": True,
            }

        def fake_test_clearance(target_url: str = "https://chatgpt.com") -> dict[str, object]:
            self.test_clearance_calls.append(target_url)
            return {
                "ok": True,
                "status": "ok",
                "latency_ms": 34,
                "has_cookies": True,
                "user_agent": "Flare UA",
                "error": None,
                "runtime": self.fake_proxy_settings.get_runtime_status(),
            }

        self.patchers = [
            mock.patch.object(system_module, "config", self.fake_config),
            mock.patch.object(system_module, "require_admin", lambda _authorization: {"role": "admin"}),
            mock.patch.object(system_module, "test_proxy", fake_test_proxy),
            mock.patch.object(system_module, "test_clearance", fake_test_clearance, create=True),
            mock.patch.object(system_module, "proxy_settings", self.fake_proxy_settings, create=True),
            mock.patch("services.account_service.account_service", FakeAccountService()),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        app = FastAPI()
        app.include_router(system_module.create_router("9.9.9-test"))
        self.client = TestClient(app)

    def test_proxy_test_can_use_active_runtime_when_url_is_empty(self) -> None:
        response = self.client.post("/api/proxy/test", headers=AUTH_HEADERS, json={})

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()["result"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["proxy_source"], "proxy_runtime")
        self.assertEqual(self.test_proxy_calls, [""])

    def test_proxy_runtime_endpoint_reads_and_updates_runtime_config(self) -> None:
        get_response = self.client.get("/api/proxy/runtime", headers=AUTH_HEADERS)
        self.assertEqual(get_response.status_code, 200, get_response.text)
        self.assertEqual(get_response.json()["runtime"]["enabled"], False)
        self.assertEqual(get_response.json()["status"]["proxy_source"], "proxy_runtime")

        runtime = copy.deepcopy(DEFAULT_PROXY_RUNTIME)
        runtime["enabled"] = True
        runtime["egress_mode"] = "single_proxy"
        runtime["proxy_url"] = "http://privoxy:8118"
        runtime["clearance"]["enabled"] = True  # type: ignore[index]
        runtime["clearance"]["mode"] = "flaresolverr"  # type: ignore[index]
        runtime["clearance"]["flaresolverr_url"] = "http://flaresolverr:8191"  # type: ignore[index]

        post_response = self.client.post("/api/proxy/runtime", headers=AUTH_HEADERS, json=runtime)

        self.assertEqual(post_response.status_code, 200, post_response.text)
        self.assertTrue(post_response.json()["runtime"]["enabled"])
        self.assertEqual(self.fake_config.data["proxy_runtime"], runtime)

    def test_clearance_test_endpoint_runs_clearance_refresh_without_returning_cookie_values(self) -> None:
        response = self.client.post(
            "/api/proxy/clearance/test",
            headers=AUTH_HEADERS,
            json={"target_url": "https://chatgpt.com/backend-api/models"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()["result"]
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["has_cookies"])
        self.assertNotIn("cf_clearance", response.text)
        self.assertEqual(self.test_clearance_calls, ["https://chatgpt.com/backend-api/models"])

    def test_health_json_includes_proxy_runtime_status(self) -> None:
        response = self.client.get("/health?format=json")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["version"], "9.9.9-test")
        self.assertEqual(payload["proxy_runtime"]["clearance_mode"], "flaresolverr")


if __name__ == "__main__":
    unittest.main()
