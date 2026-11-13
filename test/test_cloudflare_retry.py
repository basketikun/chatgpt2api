"""A Cloudflare challenge must be retried everywhere, and must not throw away the fix.

Two independent failures used to hide here. The retry only wrapped the JSON preflight,
so an upload, a download or the model list that landed on a challenge simply failed; and
a challenge response installs its own Cloudflare cookies, which mostly earn another
challenge on the retry. Both now live in one place: the retry is installed on the
session's verbs, and the purge it runs before backing off spares the cookies the solver
browser gave this exit, because those are the ones that pass Cloudflare's per-path check.
"""

import unittest
from unittest import mock

from curl_cffi.requests import Headers

from services import openai_backend_api
from services.openai_backend_api import InvalidAccessTokenError, OpenAIBackendAPI


class _BackendTestCase(unittest.TestCase):
    """A real session with the retry wrapper `__init__` installs."""

    def setUp(self):
        self.api = OpenAIBackendAPI("")
        self.addCleanup(self.api.close)

    def response(self, status=403, headers=None, payload=None):
        response = mock.Mock(status_code=status, headers=Headers(headers or {}))
        response.json.return_value = payload or {}
        return response

    def install(self, verb, side_effect):
        """Wrap a mocked verb the way `__init__` wraps the real one.

        Patching `session.get` would replace the retry wrapper instead of feeding it, so
        these tests install the same wrapper around a mocked transport.
        """
        original = mock.Mock(side_effect=side_effect)
        setattr(self.api.session, verb, self.api._make_retrying_verb(original))
        return original


class CloudflareRetryTests(_BackendTestCase):
    def test_only_challenge_403_is_retryable(self):
        cases = [
            (403, {"CF-Mitigated": "challenge"}, True),
            (403, {"Content-Type": "text/html; charset=utf-8"}, True),
            (403, {"Content-Type": "application/json"}, False),
            (403, {"Content-Type": "application/problem+json", "CF-Mitigated": "challenge"}, False),
            (403, {"Content-Type": "text/plain"}, False),
            (403, {}, False),
            (401, {"Content-Type": "text/html", "CF-Mitigated": "challenge"}, False),
            (200, {"Content-Type": "text/html", "CF-Mitigated": "challenge"}, False),
        ]
        for status, headers, expected in cases:
            with self.subTest(status=status, headers=headers):
                self.assertEqual(self.api._is_cloudflare_challenge(self.response(status, headers)), expected)

    def test_every_session_verb_carries_the_retry(self):
        """The upload, the download and the model list used to be left bare."""
        wrapper = self.api._make_retrying_verb(mock.Mock())
        for verb in ("get", "post", "put", "patch", "delete"):
            with self.subTest(verb=verb):
                self.assertIs(getattr(self.api.session, verb).__code__, wrapper.__code__)

    def test_a_bare_call_site_recovers_from_a_challenge(self):
        """`list_models` is one of the paths that never went through the wrapped preflight."""
        with (
            mock.patch.object(OpenAIBackendAPI, "_bootstrap"),
            mock.patch.object(self.api.session, "request", side_effect=[
                self.response(headers={"Content-Type": "text/html"}),
                self.response(200, payload={"models": []}),
            ]) as request,
            mock.patch("services.openai_backend_api.time.sleep") as sleep,
        ):
            self.assertEqual(self.api.list_models(), {"object": "list", "data": []})
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(1.5)

    def test_all_refresh_endpoints_recover_after_two_challenges(self):
        cases = [
            ("_get_me", "get", "/backend-api/me"),
            ("_get_conversation_init", "post", "/backend-api/conversation/init"),
            ("_get_default_account", "get", "/backend-api/accounts/check/v4-2023-04-27"),
        ]
        for method, verb, path in cases:
            with (
                self.subTest(path=path),
                mock.patch("services.openai_backend_api.time.sleep") as sleep,
            ):
                request = self.install(verb, [
                    self.response(headers={"CF-Mitigated": "challenge"}),
                    self.response(headers={"Content-Type": "text/html"}),
                    self.response(200),
                ])
                self.assertEqual(getattr(self.api, method)(), {})
                self.assertEqual(request.call_count, 3)
                self.assertEqual(sleep.call_args_list, [mock.call(1.5), mock.call(3.0)])
                for call in request.call_args_list:
                    self.assertEqual(call.kwargs["headers"]["X-OpenAI-Target-Path"], path)
                    self.assertEqual(call.kwargs["headers"]["X-OpenAI-Target-Route"], path)
                    self.assertEqual(call, request.call_args_list[0])

    def test_exhausted_challenge_raises_after_three_attempts(self):
        with mock.patch("services.openai_backend_api.time.sleep") as sleep:
            request = self.install("get", [self.response(headers={"Content-Type": "text/html"})] * 3)
            with self.assertRaisesRegex(RuntimeError, r"/backend-api/me failed: HTTP 403"):
                self.api._get_me()
        self.assertEqual(request.call_count, 3)
        self.assertEqual(sleep.call_args_list, [mock.call(1.5), mock.call(3.0)])

    def test_json_403_and_401_fail_without_retry_on_all_refresh_endpoints(self):
        for method, verb in (("_get_me", "get"), ("_get_conversation_init", "post"),
                             ("_get_default_account", "get")):
            for status, error in ((403, RuntimeError), (401, InvalidAccessTokenError)):
                with (
                    self.subTest(method=method, status=status),
                    mock.patch("services.openai_backend_api.time.sleep") as sleep,
                ):
                    request = self.install(verb, [self.response(status, {"Content-Type": "application/json"})])
                    with self.assertRaises(error):
                        getattr(self.api, method)()
                    request.assert_called_once()
                    sleep.assert_not_called()

    def test_json_rejection_after_challenge_stops_retrying(self):
        with mock.patch("services.openai_backend_api.time.sleep") as sleep:
            request = self.install("get", [
                self.response(headers={"CF-Mitigated": "challenge"}),
                self.response(headers={"Content-Type": "application/json"}),
                self.response(200),
            ])
            with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
                self.api._get_me()
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(1.5)


class SolverCookieTests(_BackendTestCase):
    """Cloudflare scores some paths per client, so the cleared browser's cookies ride along."""

    def setUp(self):
        super().setUp()
        self.api.egress_proxy_url = "http://exit-us-1:8080"

    def solver_cookies(self, cookies):
        return mock.patch.object(openai_backend_api, "solver_cookies", return_value=cookies)

    def test_the_exit_this_session_leaves_through_is_the_one_asked(self):
        # A `__cf_bm` from another exit does nothing for this request, so the lookup is
        # keyed on the session's own egress rather than on "any warmed lane".
        with self.solver_cookies({"__cf_bm": "cleared", "oai-did": "device"}) as lookup:
            self.api._apply_solver_cookies()
        lookup.assert_called_once_with("http://exit-us-1:8080")
        self.assertEqual(self.api.session.cookies.get("__cf_bm", domain=".chatgpt.com"), "cleared")
        self.assertEqual(self.api.session.cookies.get("oai-did", domain=".chatgpt.com"), "device")

    def test_an_unwarmed_exit_stays_bare(self):
        with self.solver_cookies({}):
            self.api._apply_solver_cookies()
        self.assertIsNone(self.api.session.cookies.get("__cf_bm", domain=".chatgpt.com"))
        self.assertEqual(self.api._solver_cookie_names, set())

    def test_a_challenge_keeps_the_solvers_cookies_and_drops_the_flagged_ones(self):
        with self.solver_cookies({"__cf_bm": "from-solver"}):
            self.api._apply_solver_cookies()
        # What a challenge response leaves behind: same prefix, not from the solver.
        self.api.session.cookies.set("_cfuvid", "flagged", domain=".chatgpt.com", path="/")
        self.api.session.cookies.set("cf_clearance", "flagged", domain=".chatgpt.com", path="/")

        self.api._drop_cloudflare_cookies()

        self.assertEqual(self.api.session.cookies.get("__cf_bm", domain=".chatgpt.com"), "from-solver")
        self.assertIsNone(self.api.session.cookies.get("_cfuvid", domain=".chatgpt.com"))
        self.assertIsNone(self.api.session.cookies.get("cf_clearance", domain=".chatgpt.com"))

    def test_cookies_outside_the_cloudflare_prefixes_are_never_dropped(self):
        self.api.session.cookies.set("oai-did", "keep", domain=".chatgpt.com", path="/")
        with self.solver_cookies({}):
            self.api._apply_solver_cookies()
        self.api._drop_cloudflare_cookies()
        self.assertEqual(self.api.session.cookies.get("oai-did", domain=".chatgpt.com"), "keep")

    def test_cookies_arrive_before_the_first_upstream_call(self):
        """Attaching them afterwards would not help: the request is where it counts."""
        on_the_wire: list[object] = []

        def transport(*args, **kwargs):
            on_the_wire.append(self.api.session.cookies.get("__cf_bm", domain=".chatgpt.com"))
            return self.response(200)

        with (
            self.solver_cookies({"__cf_bm": "cleared", "oai-did": "device"}),
            mock.patch("services.openai_backend_api.time.sleep"),
        ):
            self.install("get", transport)
            self.api.session.get(self.api.base_url + "/backend-api/me")
        self.assertEqual(on_the_wire, ["cleared"])

    def test_the_lookup_happens_once_per_session(self):
        with (
            self.solver_cookies({"__cf_bm": "cleared"}) as lookup,
            mock.patch("services.openai_backend_api.time.sleep"),
        ):
            self.install("get", [self.response(200)] * 3)
            for _ in range(3):
                self.api.session.get(self.api.base_url + "/backend-api/me")
        self.assertEqual(lookup.call_count, 1)

    def test_a_failing_lookup_never_breaks_the_request(self):
        with (
            mock.patch.object(openai_backend_api, "solver_cookies", side_effect=OSError("solver down")),
            mock.patch("services.openai_backend_api.time.sleep"),
        ):
            request = self.install("get", [self.response(200)])
            self.api.session.get(self.api.base_url + "/backend-api/me")
        request.assert_called_once()

    def test_the_handshake_carries_them_into_prepare(self):
        api = self.api
        sent: list[tuple[str, object]] = []

        def transport(method, url, **kwargs):
            sent.append((url, api.session.cookies.get("__cf_bm", domain=".chatgpt.com")))
            response = self.response(200)
            response.json.return_value = (
                {"turnstile": {"required": True, "dx": "dx"}, "proofofwork": {}}
                if url.endswith("/prepare") else {"token": "requirements"}
            )
            return response

        with (
            # `request` is what the wrapped verb calls, so the retry stays in the path.
            mock.patch.object(api.session, "request", side_effect=transport),
            self.solver_cookies({"__cf_bm": "cleared"}),
            mock.patch.object(openai_backend_api, "solve_turnstile", return_value="turnstile"),
            mock.patch("services.openai_backend_api.time.sleep"),
        ):
            api._get_chat_requirements()
        self.assertEqual(len(sent), 2)
        for url, cookie in sent:
            self.assertEqual(cookie, "cleared", url)


if __name__ == "__main__":
    unittest.main()
