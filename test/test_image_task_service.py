from __future__ import annotations

import json
import tempfile
import time
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from services.image_task_service import ImageTaskService, _authoritative_image_failure


OWNER = {"id": "owner-1", "name": "Owner", "role": "admin"}
OTHER_OWNER = {"id": "owner-2", "name": "Other", "role": "user"}


def wait_for_task(service: ImageTaskService, identity: dict[str, object], task_id: str, status: str, timeout: float = 2.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        result = service.list_tasks(identity, [task_id])
        last = (result.get("items") or [None])[0]
        if last and last.get("status") == status:
            return last
        time.sleep(0.02)
    raise AssertionError(f"task {task_id} did not reach {status}, last={last}")


class ImageTaskServiceTests(unittest.TestCase):
    def test_image_task_creates_an_independent_session_on_the_bound_account(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            captured = {}

            def handler(payload):
                captured.update(payload)
                return {
                    "data": [{"url": "http://example.test/image.png"}],
                    "_provider_binding_id": "cb_account_a",
                    "_provider_account_identity": "account_opaque_a",
                    "_conversation_id": "conversation-1",
                    "_parent_message_id": "message-2",
                }

            service = self.make_service(Path(tmp_dir) / "image_tasks.json", handler)
            service.submit_generation(
                OWNER,
                client_task_id="bound-task",
                prompt="continue",
                model="gpt-image-2",
                size=None,
                base_url="http://local.test",
                provider_binding_id="cb_account_a",
                provider_account_identity="account_opaque_a",
                client_conversation_id="workbench-conversation-1",
                retain_conversation=True,
            )

            task = wait_for_task(service, OWNER, "bound-task", "success")

            self.assertEqual(captured["provider_binding_id"], "cb_account_a")
            self.assertEqual(captured["provider_account_identity"], "account_opaque_a")
            self.assertEqual(captured["client_conversation_id"], "workbench-conversation-1")
            self.assertEqual(captured["conversation_id"], "")
            self.assertEqual(captured["parent_message_id"], "")
            self.assertTrue(captured["retain_conversation"])
            self.assertEqual(task["provider_binding_id"], "cb_account_a")
            self.assertEqual(task["provider_account_identity"], "account_opaque_a")
            self.assertEqual(task["client_conversation_id"], "workbench-conversation-1")
            self.assertEqual(task["image_session_id"], "conversation-1")
            self.assertEqual(task["image_session_parent_id"], "message-2")
            self.assertNotIn("conversation_id", task)
            self.assertNotIn("parent_message_id", task)

    def make_service(self, path: Path, handler=None) -> ImageTaskService:
        return ImageTaskService(
            path,
            generation_handler=handler or (lambda _payload: {"data": [{"url": "http://example.test/image.png"}]}),
            edit_handler=handler or (lambda _payload: {"data": [{"url": "http://example.test/edit.png"}]}),
            retention_days_getter=lambda: 30,
        )

    def test_duplicate_submit_uses_existing_task(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            calls = 0

            def handler(_payload):
                nonlocal calls
                calls += 1
                time.sleep(0.05)
                return {"data": [{"url": "http://example.test/image.png"}]}

            service = self.make_service(Path(tmp_dir) / "image_tasks.json", handler)
            first = service.submit_generation(
                OWNER,
                client_task_id="task-1",
                prompt="cat",
                model="gpt-image-2",
                size=None,
                base_url="http://local.test",
            )
            second = service.submit_generation(
                OWNER,
                client_task_id="task-1",
                prompt="cat",
                model="gpt-image-2",
                size=None,
                base_url="http://local.test",
            )

            self.assertEqual(first["id"], "task-1")
            self.assertEqual(second["id"], "task-1")
            task = wait_for_task(service, OWNER, "task-1", "success")
            self.assertEqual(task["data"][0]["url"], "http://example.test/image.png")
            self.assertEqual(calls, 1)

    def test_duplicate_task_id_with_changed_request_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self.make_service(Path(tmp_dir) / "image_tasks.json")
            service.submit_generation(
                OWNER,
                client_task_id="task-immutable",
                prompt="cat",
                model="gpt-image-2",
                size=None,
            )

            with self.assertRaisesRegex(ValueError, "different immutable request"):
                service.submit_generation(
                    OWNER,
                    client_task_id="task-immutable",
                    prompt="dog",
                    model="gpt-image-2",
                    size=None,
                )
            wait_for_task(service, OWNER, "task-immutable", "success")

    def test_unknown_resume_uses_the_same_bound_account_and_session(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            error = RuntimeError("ChatGPT 生图超时")
            error.code = "CONVERSATION_OUTCOME_UNKNOWN"
            error.provider_binding_id = "cb_account_a"
            error.provider_account_identity = "account_opaque_a"
            error.conversation_id = "conversation-1"
            error.parent_message_id = "message-1"

            def handler(_payload):
                raise error

            service = self.make_service(Path(tmp_dir) / "image_tasks.json", handler)
            service.submit_generation(
                OWNER,
                client_task_id="unknown-task",
                prompt="cat",
                model="gpt-image-2",
                size=None,
                provider_binding_id="cb_account_a",
                provider_account_identity="account_opaque_a",
                client_conversation_id="workbench-conversation-1",
                retain_conversation=True,
            )
            wait_for_task(service, OWNER, "unknown-task", "error")

            class FakeBackend:
                def __init__(self, access_token=None, proxy_url=None):
                    self.access_token = access_token

                def _poll_image_results(self, conversation_id, timeout):
                    self.poll = (conversation_id, timeout)
                    return ["file-1"], []

                def _get_conversation(self, _conversation_id):
                    return {"current_node": "assistant-1", "mapping": {"assistant-1": {"message": {"status": "in_progress"}}}}

                def resolve_conversation_image_urls(self, conversation_id, file_ids, sediment_ids, poll=False):
                    return ["https://provider.example/image.png"]

                def download_image_bytes(self, _urls):
                    return [b"image-bytes"]

                def get_conversation_parent_message_id(self, _conversation_id):
                    return "message-2"

                def close(self):
                    return None

            with (
                mock.patch("services.account_service.account_service.get_bound_account_identity", return_value="account_opaque_a"),
                mock.patch("services.account_service.account_service.acquire_bound_image_access_token", return_value="bound-token") as acquire,
                mock.patch("services.account_service.account_service.conversation_binding_lock", return_value=nullcontext()) as binding_lock,
                mock.patch("services.account_service.account_service.release_image_slot") as release,
                mock.patch("services.openai_backend_api.OpenAIBackendAPI", FakeBackend),
                mock.patch("services.protocol.conversation.format_image_result", return_value={"data": [{"url": "http://content-provider/images/result.png"}]}),
            ):
                resumed = service.resume_poll(OWNER, "unknown-task", 30, "http://content-provider")
                self.assertIn(resumed["status"], {"running", "success"}, resumed)
                task = wait_for_task(service, OWNER, "unknown-task", "success")
                deadline = time.time() + 1
                while not release.called and time.time() < deadline:
                    time.sleep(0.01)

            acquire.assert_called_once_with("cb_account_a", image_model="gpt-image-2")
            binding_lock.assert_called_once_with("cb_account_a", "workbench-conversation-1")
            release.assert_called_once_with("bound-token")
            self.assertEqual(task["image_session_id"], "conversation-1")
            self.assertEqual(task["image_session_parent_id"], "message-2")
            self.assertEqual(task["data"], [{"url": "http://content-provider/images/result.png"}])

    def test_authoritative_finished_image_failure_is_terminal(self):
        document = {
            "current_node": "assistant-1",
            "mapping": {
                "assistant-1": {
                    "message": {
                        "author": {"role": "assistant"},
                        "status": "finished_successfully",
                        "end_turn": True,
                        "content": {
                            "content_type": "text",
                            "parts": ["Something went wrong while generating your image. Sorry about that."],
                        },
                    }
                }
            },
        }
        self.assertEqual(
            _authoritative_image_failure(document),
            "Something went wrong while generating your image. Sorry about that.",
        )
        document["mapping"]["assistant-1"]["message"]["status"] = "in_progress"
        self.assertEqual(_authoritative_image_failure(document), "")

    def test_unknown_resume_maps_authoritative_finished_failure_to_terminal_code(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            error = RuntimeError("ChatGPT 生图超时")
            error.code = "CONVERSATION_OUTCOME_UNKNOWN"
            error.provider_binding_id = "cb_account_a"
            error.provider_account_identity = "account_opaque_a"
            error.conversation_id = "conversation-1"
            error.parent_message_id = "message-1"

            service = self.make_service(Path(tmp_dir) / "image_tasks.json", lambda _payload: (_ for _ in ()).throw(error))
            service.submit_generation(
                OWNER,
                client_task_id="terminal-no-image-task",
                prompt="cat",
                model="gpt-image-2",
                size=None,
                provider_binding_id="cb_account_a",
                provider_account_identity="account_opaque_a",
                client_conversation_id="workbench-conversation-1",
                retain_conversation=True,
            )
            wait_for_task(service, OWNER, "terminal-no-image-task", "error")

            class FakeBackend:
                def __init__(self, access_token=None, proxy_url=None):
                    self.access_token = access_token

                def _get_conversation(self, _conversation_id):
                    return {
                        "current_node": "assistant-1",
                        "mapping": {
                            "assistant-1": {
                                "message": {
                                    "author": {"role": "assistant"},
                                    "status": "finished_successfully",
                                    "end_turn": True,
                                    "content": {
                                        "content_type": "text",
                                        "parts": ["Something went wrong while generating your image. Sorry about that."],
                                    },
                                }
                            }
                        },
                    }

                def close(self):
                    return None

            with (
                mock.patch("services.account_service.account_service.get_bound_account_identity", return_value="account_opaque_a"),
                mock.patch("services.account_service.account_service.acquire_bound_image_access_token", return_value="bound-token"),
                mock.patch("services.account_service.account_service.conversation_binding_lock", return_value=nullcontext()),
                mock.patch("services.account_service.account_service.release_image_slot"),
                mock.patch("services.openai_backend_api.OpenAIBackendAPI", FakeBackend),
            ):
                resumed = service.resume_poll(OWNER, "terminal-no-image-task", 30, "http://content-provider")
                self.assertIn(resumed["status"], {"running", "error"}, resumed)
                task = wait_for_task(service, OWNER, "terminal-no-image-task", "error")

            self.assertEqual(task["error_code"], "NO_IMAGE_GENERATED")

    def test_different_owner_cannot_query_task(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self.make_service(Path(tmp_dir) / "image_tasks.json")
            service.submit_generation(
                OWNER,
                client_task_id="private-task",
                prompt="cat",
                model="gpt-image-2",
                size=None,
                base_url="http://local.test",
            )

            wait_for_task(service, OWNER, "private-task", "success")
            result = service.list_tasks(OTHER_OWNER, ["private-task"])

            self.assertEqual(result["items"], [])
            self.assertEqual(result["missing_ids"], ["private-task"])

    def test_success_task_persists_to_new_service_instance(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "image_tasks.json"
            service = self.make_service(path)
            service.submit_generation(
                OWNER,
                client_task_id="persisted-task",
                prompt="cat",
                model="gpt-image-2",
                size=None,
                base_url="http://local.test",
            )
            wait_for_task(service, OWNER, "persisted-task", "success")

            reloaded = self.make_service(path)
            result = reloaded.list_tasks(OWNER, ["persisted-task"])

            self.assertEqual(result["missing_ids"], [])
            self.assertEqual(result["items"][0]["status"], "success")
            self.assertEqual(result["items"][0]["data"][0]["url"], "http://example.test/image.png")

    def test_startup_marks_unfinished_tasks_as_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "image_tasks.json"
            path.write_text(
                json.dumps(
                    {
                        "tasks": [
                            {
                                "id": "queued-task",
                                "owner_id": "owner-1",
                                "status": "queued",
                                "mode": "generate",
                                "model": "gpt-image-2",
                                "created_at": "2099-01-01 00:00:00",
                                "updated_at": "2099-01-01 00:00:00",
                            },
                            {
                                "id": "running-task",
                                "owner_id": "owner-1",
                                "status": "running",
                                "mode": "generate",
                                "model": "gpt-image-2",
                                "created_at": "2099-01-01 00:00:00",
                                "updated_at": "2099-01-01 00:00:00",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            service = self.make_service(path)
            result = service.list_tasks(OWNER, ["queued-task", "running-task"])

            self.assertEqual([item["status"] for item in result["items"]], ["error", "error"])
            self.assertTrue(all("已中断" in item.get("error", "") for item in result["items"]))
            self.assertTrue(
                all(
                    item.get("error_code") == "CONVERSATION_OUTCOME_UNKNOWN"
                    for item in result["items"]
                )
            )


if __name__ == "__main__":
    unittest.main()
