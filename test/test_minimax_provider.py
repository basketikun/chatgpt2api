"""Unit tests for MiniMax provider integration."""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class TestIsMinimaxModel(unittest.TestCase):
    def setUp(self):
        from services.minimax_backend_api import is_minimax_model
        self.is_minimax_model = is_minimax_model

    def test_minimax_m27_detected(self):
        self.assertTrue(self.is_minimax_model("MiniMax-M2.7"))

    def test_minimax_m27_highspeed_detected(self):
        self.assertTrue(self.is_minimax_model("MiniMax-M2.7-highspeed"))

    def test_case_insensitive(self):
        self.assertTrue(self.is_minimax_model("minimax-m2.7"))
        self.assertTrue(self.is_minimax_model("MINIMAX-M2.7"))

    def test_non_minimax_model_rejected(self):
        self.assertFalse(self.is_minimax_model("gpt-4"))
        self.assertFalse(self.is_minimax_model("auto"))
        self.assertFalse(self.is_minimax_model("claude-3"))
        self.assertFalse(self.is_minimax_model(""))

    def test_none_rejected(self):
        self.assertFalse(self.is_minimax_model(None))


class TestMinimaxBackendAPIListModels(unittest.TestCase):
    def test_list_models_returns_correct_structure(self):
        from services.minimax_backend_api import MinimaxBackendAPI
        result = MinimaxBackendAPI.list_models()
        self.assertEqual(result["object"], "list")
        self.assertIsInstance(result["data"], list)
        model_ids = [item["id"] for item in result["data"]]
        self.assertIn("MiniMax-M2.7", model_ids)
        self.assertIn("MiniMax-M2.7-highspeed", model_ids)

    def test_list_models_owned_by_minimax(self):
        from services.minimax_backend_api import MinimaxBackendAPI
        result = MinimaxBackendAPI.list_models()
        for item in result["data"]:
            self.assertEqual(item["owned_by"], "minimax")
            self.assertEqual(item["object"], "model")


class TestMinimaxBackendAPIInit(unittest.TestCase):
    @patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key-123"})
    @patch("openai.OpenAI")
    def test_uses_env_api_key(self, mock_openai_cls):
        from importlib import reload
        import services.minimax_backend_api as mod
        reload(mod)
        mod.MinimaxBackendAPI()
        mock_openai_cls.assert_called_once_with(
            api_key="test-key-123",
            base_url="https://api.minimax.io/v1",
        )

    @patch.dict(os.environ, {
        "MINIMAX_API_KEY": "test-key",
        "MINIMAX_BASE_URL": "https://custom.minimax.io/v1",
    })
    @patch("openai.OpenAI")
    def test_uses_custom_base_url(self, mock_openai_cls):
        from importlib import reload
        import services.minimax_backend_api as mod
        reload(mod)
        mod.MinimaxBackendAPI()
        mock_openai_cls.assert_called_once_with(
            api_key="test-key",
            base_url="https://custom.minimax.io/v1",
        )


class TestMinimaxBackendAPIChatCompletions(unittest.TestCase):
    def _make_api(self):
        with patch("openai.OpenAI"):
            from services.minimax_backend_api import MinimaxBackendAPI
            api = MinimaxBackendAPI()
        return api

    def test_non_stream_passes_correct_params(self):
        api = self._make_api()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "id": "chatcmpl-test",
            "choices": [{"message": {"role": "assistant", "content": "Hello"}}],
        }
        api.client.chat.completions.create = MagicMock(return_value=mock_response)

        result = api.chat_completions(
            messages=[{"role": "user", "content": "Hi"}],
            model="MiniMax-M2.7",
            stream=False,
        )

        api.client.chat.completions.create.assert_called_once_with(
            model="MiniMax-M2.7",
            messages=[{"role": "user", "content": "Hi"}],
            temperature=1.0,
            stream=False,
        )
        self.assertIsInstance(result, dict)

    def test_temperature_is_always_1_0(self):
        """MiniMax requires temperature > 0, defaults to 1.0."""
        api = self._make_api()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"id": "chatcmpl-test", "choices": []}
        api.client.chat.completions.create = MagicMock(return_value=mock_response)

        api.chat_completions(
            messages=[{"role": "user", "content": "test"}],
            model="MiniMax-M2.7",
            stream=False,
        )

        call_kwargs = api.client.chat.completions.create.call_args[1]
        self.assertEqual(call_kwargs["temperature"], 1.0)

    def test_stream_returns_iterator(self):
        api = self._make_api()
        mock_chunk1 = MagicMock()
        mock_chunk1.model_dump.return_value = {
            "id": "chatcmpl-test",
            "choices": [{"delta": {"content": "He"}}],
        }
        mock_chunk2 = MagicMock()
        mock_chunk2.model_dump.return_value = {
            "id": "chatcmpl-test",
            "choices": [{"delta": {"content": "llo"}}],
        }

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=iter([mock_chunk1, mock_chunk2]))
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        api.client.chat.completions.create = MagicMock(return_value=mock_stream_ctx)

        result = api.chat_completions(
            messages=[{"role": "user", "content": "Hi"}],
            model="MiniMax-M2.7",
            stream=True,
        )
        chunks = list(result)
        self.assertEqual(len(chunks), 2)
        self.assertIn("id", chunks[0])


class TestMinimaxModelConstants(unittest.TestCase):
    def test_only_m27_models_exported(self):
        from services.minimax_backend_api import MINIMAX_MODELS
        self.assertIn("MiniMax-M2.7", MINIMAX_MODELS)
        self.assertIn("MiniMax-M2.7-highspeed", MINIMAX_MODELS)
        self.assertEqual(len(MINIMAX_MODELS), 2)


class TestBaseURLDefault(unittest.TestCase):
    def test_default_base_url_is_international(self):
        """Base URL must use international domain, not api.minimax.chat."""
        with patch("openai.OpenAI") as mock_openai_cls, \
             patch.dict(os.environ, {"MINIMAX_API_KEY": "key"}, clear=False):
            # Remove MINIMAX_BASE_URL so default is used
            env_copy = {k: v for k, v in os.environ.items() if k != "MINIMAX_BASE_URL"}
            with patch.dict(os.environ, env_copy, clear=True):
                from importlib import reload
                import services.minimax_backend_api as mod
                reload(mod)
                mod.MinimaxBackendAPI()
                _, kwargs = mock_openai_cls.call_args
                base_url = kwargs.get("base_url", "")
                self.assertIn("api.minimax.io", base_url)
                self.assertNotIn("api.minimax.chat", base_url)


if __name__ == "__main__":
    unittest.main()
