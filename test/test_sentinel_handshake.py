from __future__ import annotations

import base64
import json
import unittest
from unittest import mock

from services import sentinel_solver_client
from services.openai_backend_api import ChatRequirements, OpenAIBackendAPI
from services import openai_backend_api
from utils.pow import build_legacy_requirements_token, build_pow_config, build_proof_token

SCRIPT_SOURCES = ["https://chatgpt.com/backend-api/sentinel/sdk.js"]


class PowTokenTests(unittest.TestCase):
    def test_requirements_token_is_the_25_field_config(self):
        token = build_legacy_requirements_token("UA", SCRIPT_SOURCES, "prod-build")
        self.assertTrue(token.startswith("gAAAAAC"))
        config = json.loads(base64.b64decode(token[len("gAAAAAC"):]))
        self.assertEqual(len(config), 25)
        # The counter fields the proof of work mutates.
        self.assertEqual(config[3], 1)
        self.assertIsInstance(config[9], float)

    def test_proof_token_uses_fnv_and_carries_the_marker_suffix(self):
        proof = build_proof_token("0.5", "00ff", "UA", SCRIPT_SOURCES, "prod-build")
        self.assertTrue(proof.startswith("gAAAAAB"))
        self.assertTrue(proof.endswith("~S"))
        body = json.loads(base64.b64decode(proof[len("gAAAAAB"):-len("~S")]))
        self.assertEqual(len(body), 25)

    def test_pow_solution_meets_the_requested_difficulty(self):
        from utils.pow import _fnv1a_32, _pow_generate

        config = build_pow_config("UA", SCRIPT_SOURCES, "prod-build")
        payload, solved = _pow_generate("seed-1", "00ff", config)
        self.assertTrue(solved)
        self.assertLessEqual(_fnv1a_32("seed-1" + payload)[:4], "00ff")


class ImageModelSlugTests(unittest.TestCase):
    def test_web_image_models_map_to_auto(self):
        api = OpenAIBackendAPI("")
        for model in ("gpt-image-2", "gpt-image-2.5", "auto", ""):
            self.assertEqual(api._image_model_settings(model), ("auto", ""), model)

    def test_codex_image_model_keeps_its_own_slug(self):
        self.assertEqual(OpenAIBackendAPI("")._image_model_settings("codex-gpt-image-2"), ("codex-gpt-image-2", ""))


class SolverClientTests(unittest.TestCase):
    def setUp(self):
        sentinel_solver_client._health_cache.clear()

    def _config(self, url: str = "http://solver:8080", key: str = "secret"):
        return mock.patch.object(
            sentinel_solver_client,
            "config",
            mock.Mock(sentinel_solver_url=url, sentinel_solver_key=key),
        )

    def test_unconfigured_solver_fails_closed(self):
        with self._config(url=""):
            with self.assertRaises(sentinel_solver_client.SentinelSolverError):
                sentinel_solver_client.solve_turnstile("dx", "p")

    def test_solved_token_is_returned(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {"token": "solved-token"}
        with self._config(), mock.patch.object(sentinel_solver_client.requests, "post", return_value=response) as post:
            token = sentinel_solver_client.solve_turnstile("dx-value", "p-value")
        self.assertEqual(token, "solved-token")
        self.assertEqual(post.call_args.kwargs["json"], {"dx": "dx-value", "p": "p-value"})
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer secret")

    def test_empty_token_fails_closed(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {"token": ""}
        with self._config(), mock.patch.object(sentinel_solver_client.requests, "post", return_value=response):
            with self.assertRaises(sentinel_solver_client.SentinelSolverError):
                sentinel_solver_client.solve_turnstile("dx", "p")

    def test_solver_error_status_fails_closed(self):
        response = mock.Mock(status_code=503, text="turnstile solve failed")
        with self._config(), mock.patch.object(sentinel_solver_client.requests, "post", return_value=response):
            with self.assertRaises(sentinel_solver_client.SentinelSolverError):
                sentinel_solver_client.solve_turnstile("dx", "p")

    def test_user_agent_is_read_from_health_and_cached(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {"user_agent": "UA-from-solver"}
        with self._config(), mock.patch.object(
            sentinel_solver_client.requests, "get", return_value=response
        ) as get:
            self.assertEqual(sentinel_solver_client.solver_user_agent(), "UA-from-solver")
            self.assertEqual(sentinel_solver_client.solver_user_agent(), "UA-from-solver")
        self.assertEqual(get.call_count, 1)

    def test_unreachable_solver_leaves_user_agent_empty(self):
        with self._config(), mock.patch.object(
            sentinel_solver_client.requests, "get", side_effect=OSError("connection refused")
        ):
            self.assertEqual(sentinel_solver_client.solver_user_agent(), "")

    def test_the_ua_and_the_exits_cookies_come_from_one_call(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {
            "user_agent": "UA-from-solver",
            "exit": {"lane": "abc", "warmed": True, "cookies": {"__cf_bm": "cleared", "oai-did": "device"}},
        }
        with self._config(), mock.patch.object(
            sentinel_solver_client.requests, "get", return_value=response
        ) as get:
            user_agent, cookies = sentinel_solver_client.solver_identity("http://exit-us-1:8080")
        self.assertEqual(user_agent, "UA-from-solver")
        self.assertEqual(cookies, {"__cf_bm": "cleared", "oai-did": "device"})
        self.assertEqual(get.call_args.kwargs["params"], {"proxy": "http://exit-us-1:8080"})

    def test_another_exits_cookies_are_never_borrowed(self):
        """A `__cf_bm` is bound to the IP that earned it, so there is no shared set."""
        response = mock.Mock(status_code=200)
        response.json.return_value = {
            "user_agent": "UA",
            "lanes": {"abc": {"cookies": {"__cf_bm": "earned-elsewhere"}}},
            "exit": {"lane": None, "warmed": False, "cookies": {}},
        }
        with self._config(), mock.patch.object(sentinel_solver_client.requests, "get", return_value=response):
            self.assertEqual(sentinel_solver_client.solver_cookies("http://exit-us-2:8080"), {})
            # Not even when the caller cannot name an exit: the solver's own default
            # egress is a different IP, so its cookies would be worse than none.
            self.assertEqual(sentinel_solver_client.solver_cookies(""), {})

    def test_the_flat_lanes_map_is_not_used_as_a_fallback(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {"user_agent": "UA", "exit": "not-a-dict", "cookies": {"__cf_bm": "global"}}
        with self._config(), mock.patch.object(sentinel_solver_client.requests, "get", return_value=response):
            self.assertEqual(sentinel_solver_client.solver_cookies("http://exit-us-1:8080"), {})
            self.assertEqual(sentinel_solver_client.solver_user_agent(), "UA")

    def test_every_exit_is_cached_on_its_own(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {"user_agent": "UA", "exit": {"cookies": {"__cf_bm": "cleared"}}}
        with self._config(), mock.patch.object(
            sentinel_solver_client.requests, "get", return_value=response
        ) as get:
            sentinel_solver_client.solver_cookies("http://exit-a:8080")
            sentinel_solver_client.solver_cookies("http://exit-a:8080")
            sentinel_solver_client.solver_cookies("http://exit-b:8080")
        self.assertEqual(get.call_count, 2)

    def test_prepare_response_is_forwarded_without_account_material(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {"token": "solved"}
        requirements = {"prepare_token": "prepare", "turnstile": {"required": True, "dx": "dx"}}
        with self._config(), mock.patch.object(sentinel_solver_client.requests, "post", return_value=response) as post:
            sentinel_solver_client.solve_turnstile("dx", "p", requirements)
        self.assertEqual(post.call_args.kwargs["json"], {"dx": "dx", "p": "p", "requirements": requirements})


class SentinelHandshakeTests(unittest.TestCase):
    def test_prepare_finalize_uses_solver_ua_tokens_and_clears_only_restricted_cookie(self):
        api = OpenAIBackendAPI("")
        self.addCleanup(api.close)
        api.session.cookies.set("oai-sc", "restricted", domain="chatgpt.com")
        api.session.cookies.set("keep", "value", domain="chatgpt.com")
        prepare = {"prepare_token": "prepare", "proofofwork": {"required": True, "seed": "seed", "difficulty": "f"},
                   "turnstile": {"required": True, "dx": "dx"}}
        responses = [mock.Mock(status_code=200), mock.Mock(status_code=200)]
        responses[0].json.return_value = prepare
        responses[1].json.return_value = {"token": "requirements"}
        with (
            mock.patch.object(api.session, "post", side_effect=responses) as post,
            mock.patch.object(openai_backend_api, "solver_user_agent", return_value="solver-UA"),
            mock.patch.object(openai_backend_api, "build_legacy_requirements_token", return_value="p") as build,
            mock.patch.object(openai_backend_api, "build_proof_token", return_value="proof") as proof,
            mock.patch.object(openai_backend_api, "solve_turnstile", return_value="turnstile") as solve,
        ):
            result = api._get_chat_requirements()
        self.assertEqual(build.call_args.args[0], "solver-UA")
        self.assertEqual(proof.call_args.args[2], "solver-UA")
        solve.assert_called_once_with("dx", "p", prepare)
        self.assertEqual(post.call_args_list[1].kwargs["json"], {
            "prepare_token": "prepare", "proofofwork": "proof", "turnstile": "turnstile"})
        self.assertEqual(result.token, "requirements")
        self.assertIsNone(api.session.cookies.get("oai-sc"))
        self.assertEqual(api.session.cookies.get("keep"), "value")

    def test_required_challenge_without_dx_still_fails_closed(self):
        api = OpenAIBackendAPI("")
        self.addCleanup(api.close)
        response = mock.Mock(status_code=200)
        response.json.return_value = {"turnstile": {"required": True}}
        with (
            mock.patch.object(api.session, "post", return_value=response) as post,
            mock.patch.object(openai_backend_api, "solver_user_agent", return_value=""),
            mock.patch.object(openai_backend_api, "solve_turnstile", side_effect=sentinel_solver_client.SentinelSolverError("unconfigured")),
        ):
            with self.assertRaises(sentinel_solver_client.SentinelSolverError):
                api._get_chat_requirements()
        self.assertEqual(post.call_count, 1)

    def test_old_tls_profiles_are_replaced_and_custom_profile_is_preserved(self):
        api = OpenAIBackendAPI("")
        self.addCleanup(api.close)
        for old in ("chrome110", "edge101", ""):
            api.account = {"impersonate": old}
            self.assertEqual(api._build_fp()["impersonate"], "chrome146")
        api.account = {"impersonate": "chrome145"}
        self.assertEqual(api._build_fp()["impersonate"], "chrome145")

    def test_image_prepare_and_conversation_share_trace_and_current_payload(self):
        api = OpenAIBackendAPI("")
        self.addCleanup(api.close)
        requirements = ChatRequirements(token="requirements", proof_token="proof", turnstile_token="turnstile")
        response = mock.Mock(status_code=200)
        response.json.return_value = {"conduit_token": "conduit"}
        reference = {"file_id": "file-1", "width": 100, "height": 200, "file_size": 20,
                     "mime_type": "image/png", "file_name": "input.png"}
        for references in (None, [reference]):
            with self.subTest(edit=bool(references)), mock.patch.object(api.session, "post", return_value=response) as post:
                api._prepare_image_conversation("cat", requirements, "gpt-image-2")
                api._start_image_generation("cat", requirements, "conduit", "gpt-image-2", references)
            first, second = post.call_args_list
            trace = first.kwargs["headers"]["X-Oai-Turn-Trace-Id"]
            self.assertEqual(second.kwargs["headers"]["X-Oai-Turn-Trace-Id"], trace)
            for call in (first, second):
                self.assertEqual(call.kwargs["json"]["model"], "auto")
                self.assertEqual(call.kwargs["json"]["parent_message_id"], "client-created-root")
                self.assertEqual(call.kwargs["headers"]["X-OpenAI-Target-Path"],
                                 call.kwargs["headers"]["X-OpenAI-Target-Route"])
                self.assertEqual(call.kwargs["headers"]["OpenAI-Sentinel-Turnstile-Token"], "turnstile")
            message = second.kwargs["json"]["messages"][0]
            self.assertEqual(message["content"]["parts"][-1], "@创建图像 cat")
            self.assertEqual(message["metadata"]["serialization_metadata"]["custom_symbol_offsets"][0]["id"], "picture_v2")
            if references:
                self.assertEqual(message["content"]["parts"][0]["asset_pointer"], "file-service://file-1")


if __name__ == "__main__":
    unittest.main()
