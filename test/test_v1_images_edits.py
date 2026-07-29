from __future__ import annotations

import json
import time
import unittest
from pathlib import Path

import requests
import pytest

from test.utils import save_image
from utils.log import logger

AUTH_KEY = "chatgpt2api"
BASE_URL = "http://localhost:8000"
pytestmark = pytest.mark.live
ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"


def load_asset_bytes(name: str) -> bytes:
    return (ASSETS_DIR / name).read_bytes()


def summarize_chunk(chunk: dict[str, object]) -> dict[str, object]:
    data = chunk.get("data")
    data_items = data if isinstance(data, list) else []
    return {
        "object": chunk.get("object"),
        "index": chunk.get("index"),
        "total": chunk.get("total"),
        "created": chunk.get("created"),
        "finish_reason": chunk.get("finish_reason"),
        "progress_text": chunk.get("progress_text"),
        "upstream_event_type": chunk.get("upstream_event_type"),
        "data_count": len(data_items),
        "has_b64_json": any(isinstance(item, dict) and bool(item.get("b64_json")) for item in data_items),
    }


class ImageEditsTests(unittest.TestCase):
    def test_image_edit_http(self):
        """测试图片编辑的非流式 HTTP 调用。"""
        response = requests.post(
            f"{BASE_URL}/v1/images/edits",
            headers={"Authorization": f"Bearer {AUTH_KEY}"},
            data={
                "model": "gpt-image-2",
                "prompt": "参考输入图片，保持人物主体和二次元插画风格不变，让女孩怀里抱着一只可爱的小猫，画面自然协调。",
                "n": "1",
                "response_format": "b64_json",
            },
            files={"image": ("chery_studio.png", load_asset_bytes("chery_studio.png"), "image/png")},
            timeout=300,
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        saved_paths = []
        for index, item in enumerate(payload.get("data") or [], start=1):
            b64_json = str((item or {}).get("b64_json") or "")
            if b64_json:
                saved_paths.append(save_image(b64_json, f"images_edits_non_stream_{index}"))
        self.assertGreater(len(saved_paths), 0, "非流式接口未输出图片。")
        logger.info({
            "event": "test_images_edits_non_stream_done",
            "status_code": response.status_code,
            "created": payload.get("created"),
            "saved_paths": [str(path) for path in saved_paths],
            "image_count": len(saved_paths),
        })

    def test_image_edit_stream_http(self):
        """测试图片编辑的流式 HTTP 调用。"""
        response = requests.post(
            f"{BASE_URL}/v1/images/edits",
            headers={"Authorization": f"Bearer {AUTH_KEY}"},
            data={
                "model": "gpt-image-2",
                "prompt": "请提取两张输入界面截图中的 6 个任务，并把这 6 个任务整合排版到同一张图里，做成一张清晰的中文任务总览海报，标题明确，六个任务分区展示，版面整洁。",
                "n": "1",
                "response_format": "b64_json",
                "stream": "true",
            },
            files=[
                ("image", ("image.png", load_asset_bytes("image.png"), "image/png")),
                ("image", ("image_edit.png", load_asset_bytes("image_edit.png"), "image/png")),
            ],
            stream=True,
            timeout=300,
        )
        image_items: list[dict[str, object]] = []
        stream_errors: list[dict[str, object]] = []
        started_at = time.time()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(
            response.headers.get("content-type", "").startswith("text/event-stream"),
            response.headers.get("content-type", ""),
        )
        logger.info({
            "event": "test_images_edits_stream_start",
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
        })
        try:
            for line in response.iter_lines():
                if not line:
                    continue
                text = line.decode("utf-8", errors="replace")
                if not text.startswith("data:"):
                    continue
                payload = text[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except Exception:
                    continue
                elapsed = time.time() - started_at
                if isinstance(chunk.get("error"), dict):
                    stream_errors.append(chunk["error"])
                logger.info({
                    "event": "test_images_edits_stream_chunk",
                    "elapsed_seconds": round(elapsed, 2),
                    "chunk": summarize_chunk(chunk),
                })
                data = chunk.get("data")
                if isinstance(data, list):
                    image_items.extend(item for item in data if isinstance(item, dict))
        finally:
            response.close()

        saved_paths = []
        for index, item in enumerate(image_items, start=1):
            b64_json = str(item.get("b64_json") or "")
            if b64_json:
                saved_paths.append(save_image(b64_json, f"images_edits_stream_{index}"))
        self.assertFalse(stream_errors, f"流式接口返回错误: {stream_errors}")
        self.assertGreater(len(saved_paths), 0, "流式接口未输出图片。")
        logger.info({
            "event": "test_images_edits_stream_done",
            "saved_paths": [str(path) for path in saved_paths],
            "image_count": len(saved_paths),
        })


if __name__ == "__main__":
    unittest.main()
