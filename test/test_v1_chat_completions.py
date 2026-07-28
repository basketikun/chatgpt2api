from __future__ import annotations

import json
import time
import unittest

import requests
import pytest

from utils.helper import save_images_from_text

AUTH_KEY = "chatgpt2api"
BASE_URL = "http://localhost:8000"
pytestmark = pytest.mark.live


class ChatCompletionsTests(unittest.TestCase):
    def test_text_completion_http(self):
        """测试文本对话的非流式 HTTP 调用。"""
        response = requests.post(
            f"{BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {AUTH_KEY}"},
            json={
                "model": "auto",
                "messages": [
                    {"role": "user", "content": "你好。"},
                    {"role": "assistant", "content": "你好，我可以帮助你处理文本和图片相关请求。"},
                    {"role": "user", "content": "那你再简单介绍一下你自己。"},
                ],
            },
            timeout=300,
        )
        print("text non-stream status:")
        print(response.status_code)
        print("text non-stream result:")
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))

    def test_text_completion_stream_http(self):
        """测试文本对话的流式 HTTP 调用。"""
        response = requests.post(
            f"{BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {AUTH_KEY}"},
            json={
                "model": "auto",
                "stream": True,
                "messages": [
                    {"role": "user", "content": "你好。"},
                    {"role": "assistant", "content": "你好，我的名字是Claude。"},
                    {"role": "user", "content": "那你再简单介绍一下你自己，比如你的名字是什么。"},
                ],
            },
            stream=True,
            timeout=300,
        )
        print("text stream status:")
        print(response.status_code)
        print("text stream result:")
        for line in response.iter_lines():
            if line:
                print(line.decode("utf-8", errors="replace"))

    def test_image_completion_http(self):
        """测试图片对话的非流式 HTTP 调用。"""
        response = requests.post(
            f"{BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {AUTH_KEY}"},
            json={
                "model": "gpt-image-2",
                "messages": [
                    {"role": "user", "content": "我想做一张南京城市宣传海报图。"},
                ],
                "n": 1,
            },
            timeout=300,
        )
        payload = response.json()
        content = str((((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""))
        saved_paths = save_images_from_text(content, "chat_completions_image_non_stream")
        print("image non-stream status:")
        print(response.status_code)
        print("image non-stream saved files:")
        for path in saved_paths:
            print(path)

    def test_image_completion_stream_http(self):
        """测试图片对话的流式 HTTP 调用。"""
        response = requests.post(
            f"{BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {AUTH_KEY}"},
            json={
                "model": "gpt-image-2",
                "stream": True,
                "messages": [
                    {"role": "user", "content": "我想做一张南京城市宣传海报图。"},
                ],
                "n": 1,
            },
            stream=True,
            timeout=300,
        )
        parts: list[str] = []
        started_at = time.time()
        print("image stream status:")
        print(response.status_code)
        print("image stream chunks:")
        for line in response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8", errors="replace")
            print(f"{time.time() - started_at:6.2f}s {text}")
            if not text.startswith("data:"):
                continue
            payload = text[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except Exception:
                continue
            delta = ((chunk.get("choices") or [{}])[0].get("delta") or {})
            content = str(delta.get("content") or "")
            if content:
                parts.append(content)
        saved_paths = save_images_from_text("".join(parts), "chat_completions_image_stream")
        print("image stream saved files:")
        for path in saved_paths:
            print(path)
