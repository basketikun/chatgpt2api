from __future__ import annotations

import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

from services.register.proxy_pool import RegisterProxyPool, classify_proxy_failure, parse_proxy_lines, proxy_cooldown_seconds


class _ProxyListHandler(BaseHTTPRequestHandler):
    body = "127.0.0.1:8080\nsocks5://127.0.0.2:1080\nhttp://127.0.0.3:8080\n"

    def do_GET(self) -> None:
        payload = self.body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def proxy_list_server(body: str) -> Iterator[str]:
    _ProxyListHandler.body = body
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProxyListHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/proxies.txt"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class RegisterProxyPoolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_pool(self) -> RegisterProxyPool:
        pool = RegisterProxyPool()
        pool._state_file = Path(self.temp_dir.name) / "register_proxy_state.json"
        pool._proxy_state = {}
        return pool

    def test_parse_proxy_lines_normalizes_and_deduplicates(self) -> None:
        proxies = parse_proxy_lines(
            """
            # comment
            127.0.0.1:8080
            http://127.0.0.1:8080
            socks5://127.0.0.2:1080
            invalid
            """
        )

        self.assertEqual(proxies, ["http://127.0.0.1:8080", "socks5h://127.0.0.2:1080"])

    def test_text_mode_rotates_proxies(self) -> None:
        pool = self.make_pool()
        pool.configure(
            mode="text",
            single_proxy="",
            proxy_url="",
            proxy_list_text="127.0.0.1:8080\n127.0.0.2:8080",
            refresh_interval=120,
        )

        self.assertEqual(pool.next_proxy().proxy, "http://127.0.0.1:8080")
        self.assertEqual(pool.next_proxy().proxy, "http://127.0.0.2:8080")
        self.assertEqual(pool.next_proxy().proxy, "http://127.0.0.1:8080")

    def test_url_mode_fetches_proxy_list(self) -> None:
        with proxy_list_server("127.0.0.1:8080\nsocks5://127.0.0.2:1080\n") as url:
            pool = self.make_pool()
            state = pool.configure(
                mode="url",
                single_proxy="",
                proxy_url=url,
                proxy_list_text="",
                refresh_interval=120,
                fetch_now=True,
            )

            self.assertEqual(state.count, 2)
            self.assertEqual(pool.next_proxy().proxy, "http://127.0.0.1:8080")
            self.assertEqual(pool.next_proxy().proxy, "socks5h://127.0.0.2:1080")

    def test_url_refresh_failure_keeps_existing_pool(self) -> None:
        pool = self.make_pool()
        with proxy_list_server("127.0.0.1:8080\n127.0.0.2:8080\n") as url:
            pool.configure(
                mode="url",
                single_proxy="",
                proxy_url=url,
                proxy_list_text="",
                refresh_interval=120,
                fetch_now=True,
            )
            self.assertEqual(pool.state().count, 2)

        state = pool.refresh_url(force=True)

        self.assertEqual(state.count, 2)
        self.assertIn("failed to fetch proxy URL", state.last_error)
        self.assertEqual(pool.next_proxy().proxy, "http://127.0.0.1:8080")

    def test_proxy_result_state_cools_and_scores_aggressively_for_list_modes(self) -> None:
        pool = self.make_pool()
        pool.configure(
            mode="text",
            single_proxy="",
            proxy_url="",
            proxy_list_text="127.0.0.1:8080",
            refresh_interval=120,
        )

        new_proxy_outcome = pool.record_result("127.0.0.1:8080", success=False, error="Cloudflare cf-ray=abc")
        self.assertEqual(new_proxy_outcome["bucket"], "cloudflare_403")
        self.assertEqual(new_proxy_outcome["cooldown_seconds"], 24 * 3600)

        pool.reset_proxy_blacklist()
        pool.record_result("127.0.0.1:8080", success=True, platform_authorize_ms=1200)
        known_proxy_outcome = pool.record_result("127.0.0.1:8080", success=False, error="Cloudflare cf-ray=abc")
        self.assertEqual(known_proxy_outcome["cooldown_seconds"], 30 * 60)

    def test_hard_proxy_failures_and_otp_timeout_are_bucketed_correctly(self) -> None:
        self.assertEqual(classify_proxy_failure("Failed to perform, curl: (56) Proxy CONNECT aborted"), "proxy_closed")
        self.assertEqual(classify_proxy_failure("Recv failure: Connection reset by peer"), "proxy_closed")
        self.assertEqual(classify_proxy_failure("等待注册验证码超时"), "otp_timeout")
        self.assertEqual(proxy_cooldown_seconds("network_timeout", 1, has_success=False, aggressive=True), 48 * 3600)
        self.assertEqual(proxy_cooldown_seconds("network_timeout", 1, has_success=True, aggressive=True), 24 * 3600)
        self.assertEqual(proxy_cooldown_seconds("otp_timeout", 1, has_success=False, aggressive=True), 0)

    def test_selection_cycle_reset_keeps_blacklist_but_restarts_from_first_proxy(self) -> None:
        pool = self.make_pool()
        pool.configure(
            mode="text",
            single_proxy="",
            proxy_url="",
            proxy_list_text="127.0.0.1:8080\n127.0.0.2:8080",
            refresh_interval=120,
        )

        first = pool.next_proxy()
        pool.record_result(first.proxy, success=True)
        second = pool.next_proxy()
        pool.record_result(second.proxy, success=False, error="Failed to connect")
        state = pool.reset_selection_cycle()

        self.assertEqual(state.count, 2)
        self.assertEqual(pool.next_proxy().proxy, "http://127.0.0.1:8080")
        self.assertGreater(pool.proxy_state_metrics()["proxy_blacklist_count"], 0)

    def test_new_proxy_exploration_is_limited_after_success_history_exists(self) -> None:
        pool = self.make_pool()
        proxies = [f"127.0.0.{index}:8000" for index in range(1, 11)] + [f"127.0.1.{index}:9000" for index in range(1, 91)]
        pool.configure(
            mode="text",
            single_proxy="",
            proxy_url="",
            proxy_list_text="\n".join(proxies),
            refresh_interval=120,
        )
        for proxy in pool._proxies[:10]:
            pool._proxy_state[proxy] = {"success_count": 1, "score": 5.0}
        pool.reset_selection_cycle()

        reasons: list[str] = []
        for _ in range(100):
            selection = pool.next_proxy()
            reasons.append(selection.selection_reason)
            if selection.selection_reason == "new_proxy":
                pool.record_result(selection.proxy, success=False, error="等待注册验证码超时")
            else:
                pool.record_result(selection.proxy, success=True)

        self.assertLessEqual(reasons.count("new_proxy"), 25)


if __name__ == "__main__":
    unittest.main()

