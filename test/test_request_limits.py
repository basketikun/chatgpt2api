from __future__ import annotations

from unittest import IsolatedAsyncioTestCase

from fastapi import HTTPException

from api.image_inputs import (
    MAX_IMAGE_UPLOAD_BYTES,
    MAX_IMAGE_REQUEST_BYTES,
    MAX_IMAGE_UPLOAD_COUNT,
    read_image_sources,
)


class ImageUploadLimitTests(IsolatedAsyncioTestCase):
    async def test_per_file_upload_limit_is_rejected(self) -> None:
        oversized = (b"x" * (MAX_IMAGE_UPLOAD_BYTES + 1), "image.png", "image/png")

        with self.assertRaises(HTTPException) as context:
            await read_image_sources([oversized])

        self.assertEqual(context.exception.status_code, 413)

    async def test_excessive_upload_count_is_rejected(self) -> None:
        sources = [(b"x", "image.png", "image/png") for _ in range(MAX_IMAGE_UPLOAD_COUNT + 1)]

        with self.assertRaises(HTTPException) as context:
            await read_image_sources(sources)

        self.assertEqual(context.exception.status_code, 413)

    async def test_total_upload_size_is_bounded(self) -> None:
        chunk = b"x" * MAX_IMAGE_UPLOAD_BYTES
        sources = [
            (chunk, "image.png", "image/png"),
            (chunk, "image.png", "image/png"),
            (b"y" * (MAX_IMAGE_REQUEST_BYTES - 2 * MAX_IMAGE_UPLOAD_BYTES + 1), "image.png", "image/png"),
        ]

        with self.assertRaises(HTTPException) as context:
            await read_image_sources(sources)

        self.assertEqual(context.exception.status_code, 413)
