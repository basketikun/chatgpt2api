import threading
import unittest

from services.config import config
from services.protocol.conversation import _remove_image_conversation_later


class FakeBackend:
    def __init__(self) -> None:
        self.called = threading.Event()

    def delete_conversation(self, conversation_id: str) -> dict:
        self.called.set()
        return {}


class RemoveImageConversationGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = dict(config.data)

    def tearDown(self) -> None:
        config.data = self._saved

    def _removed(self, *, after_result: bool, always: bool, success: bool) -> bool:
        config.data = dict(
            self._saved,
            image_remove_conversation_after_result=after_result,
            image_remove_conversation_always=always,
        )
        backend = FakeBackend()
        _remove_image_conversation_later(backend, "conv-1", success=success)
        return backend.called.wait(2.0)

    def test_both_off_never_removes(self) -> None:
        self.assertFalse(self._removed(after_result=False, always=False, success=True))
        self.assertFalse(self._removed(after_result=False, always=False, success=False))

    def test_after_result_only_removes_on_success(self) -> None:
        self.assertTrue(self._removed(after_result=True, always=False, success=True))
        self.assertFalse(self._removed(after_result=True, always=False, success=False))

    def test_always_removes_regardless_of_success(self) -> None:
        self.assertTrue(self._removed(after_result=False, always=True, success=True))
        self.assertTrue(self._removed(after_result=False, always=True, success=False))

    def test_empty_conversation_id_is_noop(self) -> None:
        config.data = dict(self._saved, image_remove_conversation_always=True)
        backend = FakeBackend()
        _remove_image_conversation_later(backend, "", success=False)
        self.assertFalse(backend.called.wait(0.2))

    def test_retained_workbench_conversation_is_never_removed(self) -> None:
        config.data = dict(self._saved, image_remove_conversation_always=True)
        backend = FakeBackend()
        _remove_image_conversation_later(
            backend,
            "conv-1",
            success=True,
            retain_conversation=True,
        )
        self.assertFalse(backend.called.wait(0.2))


if __name__ == "__main__":
    unittest.main()
