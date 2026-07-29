from __future__ import annotations

import json
import time
import unittest

import requests
import pytest

from test.utils import save_image

AUTH_KEY = "chatgpt2api"
BASE_URL = "http://localhost:8000"
TEXT_MODEL = "auto"
IMAGE_MODEL = "gpt-image-2"
CODEX_IMAGE_MODEL = "codex-gpt-image-2"
pytestmark = pytest.mark.live


class ResponsesTests(unittest.TestCase):
    @staticmethod
    def _iter_sse_payloads(response: requests.Response):
        for line in response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8", errors="replace")
            yield text

    def test_text_response_http(self):
        """测试 Responses 文本的非流式 HTTP 调用。"""
        response = requests.post(
            f"{BASE_URL}/v1/responses",
            headers={"Authorization": f"Bearer {AUTH_KEY}"},
            json={
                "model": TEXT_MODEL,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "你好，请简单介绍一下你自己。"},
                        ],
                    }
                ],
            },
            timeout=300,
        )
        self.assertEqual(response.status_code, 200, response.text)
        print("responses text non-stream status:")
        print(response.status_code)
        print("responses text non-stream result:")
        try:
            payload = response.json()
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            self.assertEqual(payload.get("object"), "response")
            self.assertEqual(payload.get("status"), "completed")
            self.assertTrue(isinstance(payload.get("output"), list) and payload.get("output"))
        except Exception:
            print(response.text)
            raise

    def test_text_response_stream_http(self):
        """测试 Responses 文本的流式 HTTP 调用。"""
        response = requests.post(
            f"{BASE_URL}/v1/responses",
            headers={"Authorization": f"Bearer {AUTH_KEY}"},
            json={
                "model": TEXT_MODEL,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "你好，请简单介绍一下你自己。"},
                        ],
                    }
                ],
                "stream": True,
            },
            stream=True,
            timeout=300,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(
            response.headers.get("content-type", "").startswith("text/event-stream"),
            response.headers.get("content-type", ""),
        )
        started_at = time.time()
        print("responses text stream status:")
        print(response.status_code)
        print("responses text stream chunks:")
        event_types = []
        for text in self._iter_sse_payloads(response):
            print(f"{time.time() - started_at:6.2f}s {text}")
            if not text.startswith("data:"):
                continue
            payload_text = text[5:].strip()
            if payload_text == "[DONE]":
                break
            try:
                payload = json.loads(payload_text)
            except Exception:
                continue
            event_type = str(payload.get("type") or "")
            if event_type:
                event_types.append(event_type)
        self.assertIn("response.created", event_types)
        self.assertIn("response.completed", event_types)

    def test_image_response_http(self):
        """测试 Responses 画图的非流式 HTTP 调用。"""
        response = requests.post(
            f"{BASE_URL}/v1/responses",
            headers={"Authorization": f"Bearer {AUTH_KEY}"},
            json={
                "model": IMAGE_MODEL,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "我想做一张南京城市宣传海报图。"},
                        ],
                    }
                ],
                "tools": [{"type": "image_generation"}],
            },
            timeout=300,
        )
        self.assertEqual(response.status_code, 200, response.text)
        saved_paths = []
        try:
            payload = response.json()
        except Exception:
            payload = {}
        for index, item in enumerate(payload.get("output") or [], start=1):
            if not isinstance(item, dict):
                continue
            image_b64 = str(item.get("result") or "")
            if image_b64:
                saved_paths.append(save_image(image_b64, f"responses_image_non_stream_{index}"))
        print("responses image non-stream status:")
        print(response.status_code)
        print("responses image non-stream result:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("responses image non-stream saved files:")
        for path in saved_paths:
            print(path)

    def test_image_response_stream_http(self):
        """测试 Responses 画图的流式 HTTP 调用。"""
        response = requests.post(
            f"{BASE_URL}/v1/responses",
            headers={"Authorization": f"Bearer {AUTH_KEY}"},
            json={
                "model": IMAGE_MODEL,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "我想做一张南京城市宣传海报图。"},
                        ],
                    }
                ],
                "tools": [{"type": "image_generation"}],
                "stream": True,
            },
            stream=True,
            timeout=300,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(
            response.headers.get("content-type", "").startswith("text/event-stream"),
            response.headers.get("content-type", ""),
        )
        started_at = time.time()
        saved_paths = []
        print("responses image stream status:")
        print(response.status_code)
        print("responses image stream chunks:")
        for text in self._iter_sse_payloads(response):
            print(f"{time.time() - started_at:6.2f}s {text}")
            if not text.startswith("data:"):
                continue
            payload_text = text[5:].strip()
            if payload_text == "[DONE]":
                break
            try:
                payload = json.loads(payload_text)
            except Exception:
                continue
            if payload.get("type") != "response.output_item.done":
                continue
            item = payload.get("item") or {}
            if str(item.get("type") or "") != "image_generation_call":
                continue
            image_b64 = str(item.get("result") or "")
            if image_b64:
                saved_paths.append(save_image(image_b64, f"responses_image_stream_{len(saved_paths) + 1}"))
        print("responses image stream saved files:")
        for path in saved_paths:
            print(path)

    def test_codex_image_response_http(self):
        """测试 Responses 的 codex 画图非流式 HTTP 调用。"""
        response = requests.post(
            f"{BASE_URL}/v1/responses",
            headers={"Authorization": f"Bearer {AUTH_KEY}"},
            json={
                "model": CODEX_IMAGE_MODEL,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "我想做一张南京城市宣传海报图。"},
                        ],
                    }
                ],
                "tools": [{"type": "image_generation"}],
            },
            timeout=300,
        )
        self.assertEqual(response.status_code, 200, response.text)
        saved_paths = []
        try:
            payload = response.json()
        except Exception:
            payload = {}
        for index, item in enumerate(payload.get("output") or [], start=1):
            if not isinstance(item, dict):
                continue
            image_b64 = str(item.get("result") or "")
            if image_b64:
                saved_paths.append(save_image(image_b64, f"responses_codex_image_non_stream_{index}"))
        print("responses codex image non-stream status:")
        print(response.status_code)
        print("responses codex image non-stream result:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("responses codex image non-stream saved files:")
        for path in saved_paths:
            print(path)

    def test_codex_image_response_stream_http(self):
        """测试 Responses 的 codex 画图流式 HTTP 调用。"""
        response = requests.post(
            f"{BASE_URL}/v1/responses",
            headers={"Authorization": f"Bearer {AUTH_KEY}"},
            json={
                "model": CODEX_IMAGE_MODEL,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "我想做一张南京城市宣传海报图。"},
                        ],
                    }
                ],
                "tools": [{"type": "image_generation"}],
                "stream": True,
            },
            stream=True,
            timeout=300,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(
            response.headers.get("content-type", "").startswith("text/event-stream"),
            response.headers.get("content-type", ""),
        )
        started_at = time.time()
        saved_paths = []
        print("responses codex image stream status:")
        print(response.status_code)
        print("responses codex image stream chunks:")
        for text in self._iter_sse_payloads(response):
            print(f"{time.time() - started_at:6.2f}s {text}")
            if not text.startswith("data:"):
                continue
            payload_text = text[5:].strip()
            if payload_text == "[DONE]":
                break
            try:
                payload = json.loads(payload_text)
            except Exception:
                continue
            if payload.get("type") != "response.output_item.done":
                continue
            item = payload.get("item") or {}
            if str(item.get("type") or "") != "image_generation_call":
                continue
            image_b64 = str(item.get("result") or "")
            if image_b64:
                saved_paths.append(save_image(image_b64, f"responses_codex_image_stream_{len(saved_paths) + 1}"))
        print("responses codex image stream saved files:")
        for path in saved_paths:
            print(path)


if __name__ == "__main__":
    unittest.main()
