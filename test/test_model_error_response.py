from __future__ import annotations

import json
import unittest
from unittest import mock

from services.log_service import LoggedCall
from services.model_service import ModelUnavailableError


class ModelErrorResponseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.call = LoggedCall(
            {"id": "test", "name": "test", "role": "user"},
            "/v1/responses",
            "missing-model",
            "Responses",
        )

    async def test_unavailable_model_is_a_client_error(self) -> None:
        def handler():
            raise ModelUnavailableError("missing-model")

        with mock.patch.object(self.call, "log"):
            response = await self.call.run(handler)

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"]["type"], "invalid_request_error")
        self.assertEqual(payload["error"]["code"], "model_not_available")
        self.assertEqual(payload["error"]["param"], "model")

    async def test_stream_setup_uses_the_same_model_error(self) -> None:
        def events():
            raise ModelUnavailableError("missing-model")
            yield

        with mock.patch.object(self.call, "log"):
            response = await self.call.run(events)

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"]["code"], "model_not_available")


if __name__ == "__main__":
    unittest.main()
