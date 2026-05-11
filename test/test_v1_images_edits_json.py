from __future__ import annotations

import base64
import os
import unittest
from unittest import mock

os.environ.setdefault("CHATGPT2API_AUTH_KEY", "chatgpt2api")

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.ai as ai_module

AUTH_HEADERS = {"Authorization": "Bearer chatgpt2api"}
PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(b"fake-png").decode("ascii")
JPEG_DATA_URL = "data:image/jpeg;base64," + base64.b64encode(b"fake-jpeg").decode("ascii")


class ImageEditsJsonApiTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def fake_handle(payload):
            self.calls.append(payload)
            return {"created": 1, "data": [{"b64_json": "ZmFrZQ=="}]}

        self.handle_patcher = mock.patch.object(ai_module.openai_v1_image_edit, "handle", fake_handle)
        self.filter_patcher = mock.patch.object(ai_module, "filter_or_log", mock.AsyncMock())
        self.handle_patcher.start()
        self.filter_patcher.start()
        self.addCleanup(self.handle_patcher.stop)
        self.addCleanup(self.filter_patcher.stop)

        app = FastAPI()
        app.include_router(ai_module.create_router())
        self.client = TestClient(app)

    def test_json_model_omitted_uses_existing_default_logic(self):
        response = self.client.post(
            "/v1/images/edits",
            headers=AUTH_HEADERS,
            json={"prompt": "未传 model", "image": PNG_DATA_URL},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.calls[0]["model"], "gpt-image-2")

    def test_json_model_is_not_overwritten_when_provided(self):
        response = self.client.post(
            "/v1/images/edits",
            headers=AUTH_HEADERS,
            json={"model": "codex-gpt-image-2", "prompt": "保留 model", "image": PNG_DATA_URL},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.calls[0]["model"], "codex-gpt-image-2")

    def test_image_edit_accepts_json_image_url(self):
        response = self.client.post(
            "/v1/images/edits",
            headers=AUTH_HEADERS,
            json={
                "model": "gpt-image-2",
                "prompt": "把图片改成夜景风格",
                "n": 1,
                "size": "1024x1536",
                "response_format": "b64_json",
                "images": [{"image_url": PNG_DATA_URL}],
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = self.calls[0]
        self.assertEqual(payload["prompt"], "把图片改成夜景风格")
        self.assertEqual(payload["model"], "gpt-image-2")
        self.assertEqual(payload["n"], 1)
        self.assertEqual(payload["size"], "1024x1536")
        self.assertEqual(payload["response_format"], "b64_json")
        self.assertEqual(payload["images"], [(b"fake-png", "image_1.png", "image/png")])

    def test_image_edit_accepts_json_multiple_images_and_b64_json(self):
        response = self.client.post(
            "/v1/images/edits",
            headers=AUTH_HEADERS,
            json={
                "prompt": "把两张图合成海报",
                "images": [
                    PNG_DATA_URL,
                    {"b64_json": base64.b64encode(b"raw-jpeg").decode("ascii"), "mime_type": "image/jpeg", "filename": "two.jpg"},
                    {"image_url": {"url": JPEG_DATA_URL}},
                ],
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        images = self.calls[0]["images"]
        self.assertEqual(images[0], (b"fake-png", "image_1.png", "image/png"))
        self.assertEqual(images[1], (b"raw-jpeg", "two.jpg", "image/jpeg"))
        self.assertEqual(images[2], (b"fake-jpeg", "image_3.jpg", "image/jpeg"))

    def test_image_edit_keeps_multipart_multiple_image_fields(self):
        response = self.client.post(
            "/v1/images/edits",
            headers=AUTH_HEADERS,
            data={"prompt": "multipart 多图仍然可用", "model": "gpt-image-2", "n": "1"},
            files=[
                ("image", ("one.png", b"one", "image/png")),
                ("image", ("two.jpg", b"two", "image/jpeg")),
                ("image[]", ("three.webp", b"three", "image/webp")),
            ],
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.calls[0]["images"], [
            (b"one", "one.png", "image/png"),
            (b"two", "two.jpg", "image/jpeg"),
            (b"three", "three.webp", "image/webp"),
        ])

    def test_image_edit_rejects_json_without_image(self):
        response = self.client.post("/v1/images/edits", headers=AUTH_HEADERS, json={"prompt": "缺少图片"})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("image file is required", response.text)

    def test_image_edit_rejects_remote_json_url(self):
        response = self.client.post(
            "/v1/images/edits",
            headers=AUTH_HEADERS,
            json={"prompt": "不允许远程拉图", "images": [{"image_url": "https://example.com/a.png"}]},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("remote image URLs are not supported", response.text)

    def test_image_edit_rejects_json_n_out_of_range(self):
        response = self.client.post(
            "/v1/images/edits",
            headers=AUTH_HEADERS,
            json={"prompt": "n 越界", "n": 5, "image": PNG_DATA_URL},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertFalse(self.calls)


if __name__ == "__main__":
    unittest.main()
