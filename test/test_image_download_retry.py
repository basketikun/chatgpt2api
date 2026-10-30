import unittest
from unittest import mock

from services.openai_backend_api import OpenAIBackendAPI
from utils.helper import UpstreamHTTPError


class FakeResponse:
    """模拟 curl_cffi 响应，只提供 ensure_ok 和下载逻辑用到的字段。"""

    def __init__(self, status_code: int, content: bytes = b"", text: str = "") -> None:
        self.status_code = status_code
        self.content = content
        self.text = text
        self.headers: dict[str, str] = {}

    def json(self):
        raise ValueError("not json")


class FakeSession:
    """按预设序列依次返回响应或抛出异常，并记录调用次数。"""

    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _backend(outcomes) -> OpenAIBackendAPI:
    backend = OpenAIBackendAPI.__new__(OpenAIBackendAPI)
    backend.session = FakeSession(outcomes)
    return backend


class ImageDownloadRetryTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch("services.openai_backend_api.time.sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def test_success_first_try_no_retry(self) -> None:
        backend = _backend([FakeResponse(200, b"img")])
        self.assertEqual(backend.download_image_bytes(["u"]), [b"img"])
        self.assertEqual(backend.session.calls, 1)
        self.sleep.assert_not_called()

    def test_503_then_success(self) -> None:
        backend = _backend([FakeResponse(503, text="upstream connect error"), FakeResponse(200, b"img")])
        self.assertEqual(backend.download_image_bytes(["u"]), [b"img"])
        self.assertEqual(backend.session.calls, 2)
        self.sleep.assert_called_once_with(1.0)

    def test_connection_error_then_success(self) -> None:
        backend = _backend([ConnectionError("curl: (7) Connection refused"), FakeResponse(200, b"img")])
        self.assertEqual(backend.download_image_bytes(["u"]), [b"img"])
        self.assertEqual(backend.session.calls, 2)

    def test_exhausted_raises_last_error_with_backoff(self) -> None:
        backend = _backend([
            FakeResponse(503, text="first"),
            FakeResponse(502, text="second"),
            FakeResponse(503, text="third"),
        ])
        with self.assertRaises(UpstreamHTTPError) as ctx:
            backend.download_image_bytes(["u"])
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.body, "third")
        self.assertEqual(backend.session.calls, 3)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [1.0, 2.0])

    def test_dedup_and_multiple_urls(self) -> None:
        backend = _backend([FakeResponse(200, b"a"), FakeResponse(503), FakeResponse(200, b"a"), FakeResponse(200, b"b")])
        self.assertEqual(backend.download_image_bytes(["u1", "u2", "u3"]), [b"a", b"b"])
        self.assertEqual(backend.session.calls, 4)


if __name__ == "__main__":
    unittest.main()
