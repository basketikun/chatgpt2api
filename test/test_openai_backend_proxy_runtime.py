import unittest
from types import SimpleNamespace
from unittest import mock

from api import image_inputs
from services import openai_backend_api
from services.proxy_service import ClearanceBundle
from utils import helper


class OpenAIBackendProxyRuntimeTests(unittest.TestCase):
    def test_chatgpt_session_opts_into_upstream_proxy_runtime(self) -> None:
        session = mock.MagicMock()
        session.headers = {}
        session_kwargs = {"proxy": "http://runtime-proxy.test:8118"}

        with (
            mock.patch.object(openai_backend_api.account_service, "get_account", return_value={}),
            mock.patch.object(
                openai_backend_api.proxy_settings,
                "build_session_kwargs",
                return_value=session_kwargs,
            ) as build_session_kwargs,
            mock.patch.object(openai_backend_api.requests, "Session", return_value=session) as session_factory,
        ):
            backend = openai_backend_api.OpenAIBackendAPI("test-access-token")

        build_session_kwargs.assert_called_once_with(
            account={},
            upstream=True,
            impersonate=backend.fp["impersonate"],
            verify=True,
        )
        session_factory.assert_called_once_with(**session_kwargs)
        self.assertEqual(session.headers["Authorization"], "Bearer test-access-token")

    def test_chatgpt_session_warms_and_applies_flaresolverr_clearance(self) -> None:
        session = mock.MagicMock()
        session.headers = {}
        profile = SimpleNamespace(
            clearance_enabled=True,
            clearance={"warm_up_on_start": True},
        )
        bundle = ClearanceBundle(
            target_host="chatgpt.com",
            proxy_url="http://runtime-proxy.test:8118",
            cookies={"cf_clearance": "test-clearance"},
            user_agent="FlareSolverr test UA",
        )

        with (
            mock.patch.object(openai_backend_api.account_service, "get_account", return_value={}),
            mock.patch.object(openai_backend_api.proxy_settings, "build_session_kwargs", return_value={}),
            mock.patch.object(openai_backend_api.proxy_settings, "get_profile", return_value=profile),
            mock.patch.object(
                openai_backend_api.proxy_settings,
                "refresh_clearance",
                return_value=bundle,
            ) as refresh_clearance,
            mock.patch.object(openai_backend_api.requests, "Session", return_value=session),
        ):
            backend = openai_backend_api.OpenAIBackendAPI("test-access-token")

        refresh_clearance.assert_called_once_with(
            target_url="https://chatgpt.com",
            account={},
            force=False,
            upstream=True,
        )
        self.assertEqual(backend.user_agent, bundle.user_agent)
        self.assertEqual(session.headers["User-Agent"], bundle.user_agent)
        session.cookies.set.assert_called_once_with(
            "cf_clearance",
            "test-clearance",
            domain=".chatgpt.com",
        )

    def test_chatgpt_headers_apply_cached_clearance(self) -> None:
        session = mock.MagicMock()
        session.headers = {"User-Agent": "Caller UA"}

        with (
            mock.patch.object(openai_backend_api.account_service, "get_account", return_value={}),
            mock.patch.object(openai_backend_api.proxy_settings, "build_session_kwargs", return_value={}),
            mock.patch.object(openai_backend_api.requests, "Session", return_value=session),
        ):
            backend = openai_backend_api.OpenAIBackendAPI("test-access-token")

        with mock.patch.object(
            openai_backend_api.proxy_settings,
            "build_headers",
            return_value={"Cookie": "cf_clearance=test-clearance"},
        ) as build_headers:
            headers = backend._headers("/backend-api/conversation")

        self.assertEqual(headers, {"Cookie": "cf_clearance=test-clearance"})
        build_headers.assert_called_once()
        call = build_headers.call_args.kwargs
        self.assertEqual(call["target_url"], "https://chatgpt.com/backend-api/conversation")
        self.assertEqual(call["account"], {})
        self.assertTrue(call["upstream"])
        self.assertEqual(call["headers"]["Authorization"], "Bearer test-access-token")
        self.assertEqual(call["headers"]["X-OpenAI-Target-Path"], "/backend-api/conversation")
        self.assertEqual(call["headers"]["X-OpenAI-Target-Route"], "/backend-api/conversation")

    def test_remote_image_inputs_use_resource_proxy_runtime(self) -> None:
        response = SimpleNamespace(
            status_code=200,
            headers={"content-type": "image/png"},
            content=b"test-image",
        )

        for module, loader in (
            (image_inputs, image_inputs._download_image_url),
            (helper, helper._decode_message_image_url),
        ):
            with self.subTest(module=module.__name__), (
                mock.patch.object(module.proxy_settings, "build_session_kwargs", return_value={})
            ) as build_session_kwargs, mock.patch.object(module.requests, "get", return_value=response):
                self.assertIsNotNone(loader("https://assets.example.test/image.png"))

            build_session_kwargs.assert_called_once_with(resource=True, upstream=True)


if __name__ == "__main__":
    unittest.main()
