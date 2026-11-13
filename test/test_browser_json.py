import asyncio
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from services import openai_backend_api as backend
from services import sentinel_solver_client as client
from services.account_service import AccountService
from utils.identity import identity_timezone_offset_min


class BrowserRoutingTests(unittest.TestCase):
    def setUp(self):
        self.api = backend.OpenAIBackendAPI("")
        self.api.access_token = "account-token"
        self.addCleanup(self.api.close)
        patcher = mock.patch.object(backend, "config", mock.Mock(sentinel_solver_url="http://solver"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def result(self, status=200, data=None, content_type="application/json"):
        return {"status": status, "headers": {"Content-Type": content_type}, "text": json.dumps(data or {})}

    def test_refresh_is_serial_and_uses_browser_without_curl(self):
        with (
            mock.patch.object(backend, "browser_request", side_effect=[
                self.result(data={"email": "test@example.com"}),
                self.result(data={"limits_progress": [{"feature_name": "image_gen", "remaining": 3}]}),
                self.result(data={"accounts": {"default": {"account": {"plan_type": "plus"}}}}),
            ]) as browser,
            mock.patch.object(self.api.session, "get") as get,
            mock.patch.object(self.api.session, "post") as post,
        ):
            result = self.api.get_user_info()
        self.assertEqual(result["quota"], 3)
        self.assertEqual(result["type"], "plus")
        self.assertEqual([c.args[1].split("chatgpt.com")[1] for c in browser.call_args_list], [
            "/backend-api/me", "/backend-api/conversation/init",
            # The offset flips with US daylight saving, so it is never a literal here.
            f"/backend-api/accounts/check/v4-2023-04-27?timezone_offset_min={identity_timezone_offset_min()}",
        ])
        for call in browser.call_args_list:
            headers = call.args[2]
            self.assertEqual(headers["Authorization"], "Bearer account-token")
            self.assertNotIn("?", headers["X-OpenAI-Target-Route"])
        get.assert_not_called()
        post.assert_not_called()

    def test_homepage_challenge_does_not_abort_browser_handshake(self):
        response = mock.Mock(status_code=403, headers={"content-type": "text/html"})
        with mock.patch.object(self.api.session, "get", return_value=response):
            self.api._bootstrap()
        self.assertEqual(self.api.pow_script_sources, [backend.DEFAULT_POW_SCRIPT])
        self.assertEqual(self.api.pow_data_build, "")
        response.headers = {"content-type": "application/json"}
        with mock.patch.object(self.api.session, "get", return_value=response):
            with self.assertRaises(backend.UpstreamHTTPError):
                self.api._bootstrap()

    def test_auth_rejection_is_not_retried_or_sent_to_curl(self):
        for status, error in ((401, backend.InvalidAccessTokenError), (403, RuntimeError)):
            with self.subTest(status=status), mock.patch.object(
                backend, "browser_request", return_value=self.result(status)
            ) as browser, mock.patch.object(self.api.session, "get") as curl:
                with self.assertRaises(error):
                    self.api._get_me()
                browser.assert_called_once()
                curl.assert_not_called()

    def test_browser_challenge_retries_and_preserves_challenge_error(self):
        with (
            mock.patch.object(backend, "browser_request", return_value=self.result(403, content_type="text/html")) as browser,
            mock.patch.object(self.api.session, "get") as curl,
            mock.patch.object(backend.time, "sleep") as sleep,
        ):
            with self.assertRaises(backend.CloudflareChallengeError):
                self.api._get_me()
        self.assertEqual(browser.call_count, 3)
        self.assertEqual(sleep.call_args_list, [mock.call(1.5), mock.call(3.0)])
        curl.assert_not_called()

    def test_transport_failure_falls_back_to_curl(self):
        for failure in (client.SentinelSolverError("offline"), self.result(0)):
            kwargs = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
            with mock.patch.object(backend, "browser_request", **kwargs), mock.patch.object(
                self.api.session, "get", return_value=mock.Mock(status_code=200)
            ) as curl:
                curl.return_value.json.return_value = {"id": "user"}
                self.assertEqual(self.api._get_me(), {"id": "user"})
                curl.assert_called_once()

    def test_prepare_finalize_use_browser_and_preserve_payloads(self):
        with (
            mock.patch.object(backend, "browser_request", side_effect=[
                self.result(data={"prepare_token": "prepared"}), self.result(data={"token": "solved"}),
            ]) as browser,
            mock.patch.object(backend, "solver_user_agent", return_value="UA"),
            mock.patch.object(backend, "build_legacy_requirements_token", return_value="seed"),
            mock.patch.object(self.api.session, "post") as curl,
        ):
            self.assertEqual(self.api._get_chat_requirements().token, "solved")
        self.assertTrue(browser.call_args_list[0].args[1].endswith("/prepare"))
        self.assertEqual(json.loads(browser.call_args_list[0].args[3]), {"p": "seed"})
        self.assertTrue(browser.call_args_list[1].args[1].endswith("/finalize"))
        self.assertEqual(json.loads(browser.call_args_list[1].args[3])["prepare_token"], "prepared")
        curl.assert_not_called()

    def test_account_retry_closes_sessions_and_only_retries_challenges(self):
        for error, attempts in ((backend.CloudflareChallengeError("challenge"), 3),
                                (backend.InvalidAccessTokenError("invalid"), 1), (RuntimeError("403"), 1)):
            with mock.patch.object(backend, "OpenAIBackendAPI") as factory, mock.patch(
                "services.account_service.time.sleep"
            ) as sleep:
                factory.return_value.__enter__.return_value.get_user_info.side_effect = error
                with self.assertRaises(type(error)):
                    AccountService._fetch_user_info_with_challenge_retry("account-token")
                self.assertEqual(factory.call_count, attempts)
                self.assertEqual(factory.return_value.__exit__.call_count, attempts)
                self.assertEqual(sleep.call_args_list, [mock.call(20), mock.call(40)] if attempts == 3 else [])


class BrowserClientTests(unittest.TestCase):
    def test_malformed_envelope_is_reported_as_solver_failure(self):
        for payload in ([], {}, {"status": "200"}, {"status": 200, "headers": [], "text": "ok"}):
            response = mock.Mock(status_code=200)
            response.json.return_value = payload
            with mock.patch.object(client, "config", mock.Mock(sentinel_solver_url="http://solver")), mock.patch.object(
                client.requests, "post", return_value=response
            ):
                with self.assertRaises(client.SentinelSolverError):
                    client.browser_request("GET", "https://chatgpt.com/backend-api/me")


class BrowserEndpointTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if importlib.util.find_spec("playwright") is None or importlib.util.find_spec("playwright_stealth") is None:
            raise unittest.SkipTest("install sentinel_solver/requirements.txt for solver endpoint tests")
        directory = Path(__file__).resolve().parents[1] / "sentinel_solver"
        spec = importlib.util.spec_from_file_location("solver_browser_test_app", directory / "app.py")
        cls.module = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, "path", [str(directory), *sys.path]):
            spec.loader.exec_module(cls.module)

    async def test_headers_filtered_and_restricted_cookie_cleared(self):
        module = self.module
        solver = module.SolverPage()
        lane = module._Lane(solver, "test", {})
        lane.evaluate = mock.AsyncMock(return_value={"status": 200})
        lane._context = mock.Mock(clear_cookies=mock.AsyncMock())
        solver._lane = mock.AsyncMock(return_value=lane)
        request = module.BrowserRequest(method="POST", url="https://chatgpt.com/backend-api/sentinel/chat-requirements/finalize",
                                        headers={"Cookie": "private", "Sec-Ch-Ua": "bad", "User-Agent": "bad",
                                                 "Origin": "bad", "Proxy-Authorization": "bad",
                                                 "Authorization": "Bearer account", "Content-Type": "application/json"})
        with mock.patch.object(module, "solver", solver), mock.patch.object(module, "SOLVER_KEY", "secret"):
            result = await module.browser_request(request, "Bearer secret")
        self.assertEqual(result, {"status": 200})
        self.assertEqual(lane.evaluate.call_args.args[1][2], {
            "Authorization": "Bearer account", "Content-Type": "application/json"})
        lane._context.clear_cookies.assert_awaited_once_with(name="oai-sc")

    async def test_auth_and_route_limits_prevent_fetch(self):
        module = self.module
        with mock.patch.object(module, "solver") as solver, mock.patch.object(module, "SOLVER_KEY", "secret"):
            for url, method, key, status in (
                ("https://chatgpt.com/backend-api/me", "GET", "wrong", 401),
                ("https://other.example/backend-api/me", "GET", "secret", 400),
                ("https://chatgpt.com/backend-api/conversation", "POST", "secret", 400),
                ("https://chatgpt.com/backend-api/me", "DELETE", "secret", 400),
            ):
                with self.assertRaises(module.HTTPException) as caught:
                    await module.browser_request(module.BrowserRequest(url=url, method=method), "Bearer " + key)
                self.assertEqual(caught.exception.status_code, status)
            solver.evaluate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
