from __future__ import annotations

import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock

from services.account_service import AccountService
from services.model_service import ModelCatalogService
from services.storage.json_storage import JSONStorageBackend


def model_list(*model_ids: str) -> dict:
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": 0,
                "owned_by": "chatgpt",
                "permission": [],
                "root": model_id,
                "parent": None,
            }
            for model_id in model_ids
        ],
    }


class FakeBackend:
    def __init__(self, access_token: str, outcomes: dict[str, object], calls: list[str], closed: list[str]) -> None:
        self.access_token = access_token
        self._outcomes = outcomes
        self._calls = calls
        self._closed = closed

    def list_models(self, timeout_secs: float = 30) -> dict:
        del timeout_secs
        self._calls.append(self.access_token)
        outcome = self._outcomes[self.access_token]
        if callable(outcome):
            outcome = outcome()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def close(self) -> None:
        self._closed.append(self.access_token)


class ModelCatalogServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.accounts = AccountService(
            JSONStorageBackend(Path(self.temp_dir.name) / "accounts.json")
        )
        self.accounts.add_account_items(
            [
                {"access_token": "free-bad", "type": "free", "status": "正常"},
                {"access_token": "free-good", "type": "FREE", "status": "正常"},
                {"access_token": "plus", "type": "Plus", "status": "正常"},
                {"access_token": "pro", "type": "pro", "status": "正常"},
                {"access_token": "team-disabled", "type": "Team", "status": "禁用"},
            ]
        )
        self.accounts.refresh_access_token = lambda token, **_kwargs: token
        self.now = 1000.0
        self.calls: list[str] = []
        self.closed: list[str] = []
        self.outcomes: dict[str, object] = {
            "": model_list("anon", "shared"),
            "free-bad": RuntimeError("expired"),
            "free-good": model_list("free-only", "shared"),
            "plus": model_list("plus-only", "shared"),
            "pro": model_list("pro-only"),
        }
        self.catalog = ModelCatalogService(
            self.accounts,
            backend_factory=lambda access_token="": FakeBackend(
                access_token, self.outcomes, self.calls, self.closed
            ),
            cache_ttl_seconds=300,
            clock=lambda: self.now,
        )

    def test_catalog_unions_anonymous_and_each_active_account_type(self) -> None:
        result = self.catalog.list_models()

        self.assertEqual(
            [item["id"] for item in result["data"]],
            ["anon", "free-only", "plus-only", "pro-only", "shared"],
        )
        self.assertCountEqual(self.calls, ["", "free-bad", "free-good", "plus", "pro"])
        self.assertCountEqual(self.closed, self.calls)
        self.assertNotIn("team-disabled", self.calls)

        pro_route = self.catalog.route_for_model("pro-only")
        self.assertEqual(pro_route.access_tokens, frozenset({"pro"}))
        self.assertFalse(pro_route.allow_anonymous)

        shared_route = self.catalog.route_for_model("shared")
        self.assertEqual(shared_route.access_tokens, frozenset({"free-good", "plus"}))
        self.assertTrue(shared_route.allow_anonymous)

    def test_same_type_accounts_keep_distinct_model_capabilities(self) -> None:
        self.accounts.add_account_items([
            {"access_token": "pro-alt", "type": "Pro", "status": "正常"},
        ])
        self.outcomes["pro-alt"] = model_list("pro-alt-only")

        result = self.catalog.list_models()

        self.assertIn("pro-alt-only", {item["id"] for item in result["data"]})
        self.assertEqual(
            self.catalog.route_for_model("pro-only").access_tokens,
            frozenset({"pro"}),
        )
        self.assertEqual(
            self.catalog.route_for_model("pro-alt-only").access_tokens,
            frozenset({"pro-alt"}),
        )

    def test_model_discovery_refreshes_and_routes_a_rotated_token(self) -> None:
        refresh_calls: list[str] = []

        def rotate_token(token: str, **_kwargs) -> str:
            refresh_calls.append(token)
            if token != "pro":
                return token
            self.accounts.delete_accounts(["pro"])
            self.accounts.add_account_items([
                {"access_token": "pro-rotated", "type": "Pro", "status": "正常"},
            ])
            return "pro-rotated"

        self.accounts.refresh_access_token = rotate_token
        self.outcomes["pro-rotated"] = model_list("pro-rotated-only")

        result = self.catalog.list_models()

        self.assertIn("pro", refresh_calls)
        self.assertIn("pro-rotated-only", {item["id"] for item in result["data"]})
        self.assertNotIn("pro", self.calls)
        self.assertEqual(
            self.catalog.route_for_model("pro-rotated-only").access_tokens,
            frozenset({"pro-rotated"}),
        )

    def test_catalog_is_cached_until_ttl_expires(self) -> None:
        self.catalog.list_models()
        self.catalog.list_models()
        self.catalog.route_for_model("pro-only")

        self.assertEqual(self.calls.count("pro"), 1)
        self.assertEqual(self.calls.count(""), 1)

    def test_concurrent_readers_share_one_catalog_refresh(self) -> None:
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _index: self.catalog.list_models(), range(8)))

        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(self.calls.count(""), 1)
        self.assertEqual(self.calls.count("free-good"), 1)
        self.assertEqual(self.calls.count("plus"), 1)
        self.assertEqual(self.calls.count("pro"), 1)

    def test_failed_refresh_keeps_last_successful_models_for_that_type(self) -> None:
        self.catalog.list_models()
        self.outcomes["pro"] = RuntimeError("temporary upstream failure")
        self.now += 301

        result = self.catalog.list_models()

        self.assertIn("pro-only", {item["id"] for item in result["data"]})
        deadline = time.monotonic() + 1
        while self.calls.count("pro") < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(
            self.catalog.route_for_model("pro-only").access_tokens,
            frozenset({"pro"}),
        )
        self.assertEqual(self.calls.count("pro"), 2)

    def test_stale_catalog_is_served_while_refresh_runs_in_background(self) -> None:
        self.catalog.list_models()
        release = Event()

        def blocked_models() -> dict:
            release.wait(timeout=1)
            return model_list("pro-new")

        self.outcomes["pro"] = blocked_models
        self.now += 301

        started = time.monotonic()
        result = self.catalog.list_models()
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.2)
        self.assertIn("pro-only", {item["id"] for item in result["data"]})
        release.set()

    def test_removed_account_type_drops_its_stale_capabilities(self) -> None:
        self.catalog.list_models()
        self.accounts.delete_accounts(["pro"])

        result = self.catalog.list_models()

        self.assertNotIn("pro-only", {item["id"] for item in result["data"]})
        self.assertEqual(
            self.catalog.route_for_model("pro-only").access_tokens,
            frozenset(),
        )

    def test_refresh_queries_every_active_account_with_bounded_concurrency(self) -> None:
        extra_accounts = [
            {"access_token": f"business-{index}", "type": "Business", "status": "正常"}
            for index in range(6)
        ]
        self.accounts.add_account_items(extra_accounts)
        concurrency_lock = Lock()
        active = 0
        peak_active = 0

        def unavailable() -> dict:
            nonlocal active, peak_active
            with concurrency_lock:
                active += 1
                peak_active = max(peak_active, active)
            try:
                time.sleep(0.02)
                raise RuntimeError("upstream unavailable")
            finally:
                with concurrency_lock:
                    active -= 1

        for account in extra_accounts:
            self.outcomes[account["access_token"]] = unavailable
        catalog = ModelCatalogService(
            self.accounts,
            backend_factory=lambda access_token="": FakeBackend(
                access_token, self.outcomes, self.calls, self.closed
            ),
            cache_ttl_seconds=300,
            max_workers=2,
            max_pending_requests=2,
            clock=lambda: self.now,
        )

        catalog.list_models()

        business_calls = [token for token in self.calls if token.startswith("business-")]
        self.assertCountEqual(
            business_calls,
            [account["access_token"] for account in extra_accounts],
        )
        self.assertLessEqual(peak_active, 2)

    def test_account_result_is_published_before_slow_anonymous_result(self) -> None:
        release = Event()

        def slow_anonymous() -> dict:
            release.wait(timeout=1)
            return model_list("anon")

        self.outcomes[""] = slow_anonymous
        catalog = ModelCatalogService(
            self.accounts,
            backend_factory=lambda access_token="": FakeBackend(
                access_token, self.outcomes, self.calls, self.closed
            ),
            initial_wait_seconds=0.5,
            clock=lambda: self.now,
        )

        try:
            started = time.monotonic()
            route = catalog.route_for_model("pro-only")
            elapsed = time.monotonic() - started
        finally:
            release.set()

        self.assertLess(elapsed, 0.2)
        self.assertEqual(route.access_tokens, frozenset({"pro"}))

    def test_token_rotation_waits_for_replacement_account_capabilities(self) -> None:
        self.catalog.list_models()
        self.accounts.delete_accounts(["pro"])
        self.accounts.add_account_items([
            {"access_token": "pro-rotated", "type": "Pro", "status": "正常"},
        ])
        self.outcomes["pro-rotated"] = model_list("pro-only")

        route = self.catalog.route_for_model("pro-only")

        self.assertEqual(route.access_tokens, frozenset({"pro-rotated"}))

    def test_account_added_during_refresh_is_discovered_before_routing(self) -> None:
        refresh_started = Event()
        release_refresh = Event()

        def blocked_pro_models() -> dict:
            refresh_started.set()
            release_refresh.wait(timeout=1)
            return model_list("pro-only")

        self.outcomes["pro"] = blocked_pro_models
        with ThreadPoolExecutor(max_workers=1) as executor:
            initial_refresh = executor.submit(self.catalog.list_models)
            self.assertTrue(refresh_started.wait(timeout=1))
            self.accounts.add_account_items([
                {"access_token": "late-pro", "type": "Pro", "status": "正常"},
            ])
            self.outcomes["late-pro"] = model_list("late-pro-only")
            release_refresh.set()
            initial_refresh.result(timeout=1)

        route = self.catalog.route_for_model("late-pro-only")

        self.assertEqual(route.access_tokens, frozenset({"late-pro"}))

    def test_failed_discovery_keeps_stale_models_on_a_rotated_token(self) -> None:
        self.catalog.list_models()

        def rotate_token(token: str, **_kwargs) -> str:
            if token != "pro":
                return token
            self.accounts.delete_accounts(["pro"])
            self.accounts.add_account_items([
                {"access_token": "pro-rotated", "type": "Pro", "status": "正常"},
            ])
            return "pro-rotated"

        self.accounts.refresh_access_token = rotate_token
        self.outcomes["pro-rotated"] = RuntimeError("temporary upstream failure")
        self.now += 301

        self.catalog.list_models()
        deadline = time.monotonic() + 1
        while "pro-rotated" not in self.calls and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertIn("pro-rotated", self.calls)
        self.assertEqual(
            self.catalog.route_for_model("pro-only").access_tokens,
            frozenset({"pro-rotated"}),
        )


if __name__ == "__main__":
    unittest.main()
