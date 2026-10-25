from __future__ import annotations

import unittest
from unittest import mock

from services.config import config
from services.protocol import conversation
from services.protocol.conversation import ConversationRequest, ImageGenerationError, ImageOutput


class ImageModelMappingTests(unittest.TestCase):
    def run_request(self, request, settings):
        output = ImageOutput(kind="result", model="codex-gpt-image-2", index=1, total=request.n)
        with mock.patch.dict(config.data, settings, clear=True), mock.patch.object(
            conversation, "_generate_single_image", return_value=[output]
        ) as generate:
            outputs = list(conversation.stream_image_outputs_with_pool(request))
        return generate, outputs

    def test_maps_edit_request_without_mutating_original_or_losing_options(self):
        request = ConversationRequest(
            model="gpt-image-2", prompt="edit this image", images=["reference-image"],
            size="1536x1024", quality="high", response_format="url",
            base_url="https://example.test", progress_callback=mock.Mock(),
        )
        generate, outputs = self.run_request(request, {
            "image_model_mapping": {"gpt-image-2": " codex-gpt-image-2 "}
        })
        routed = generate.call_args.args[0]
        self.assertEqual(routed.model, "codex-gpt-image-2")
        self.assertEqual(request.model, "gpt-image-2")
        self.assertIsNot(routed, request)
        for name, value in vars(request).items():
            if name != "model":
                self.assertEqual(getattr(routed, name), value)
        self.assertEqual(len(outputs), 1)

    def test_absent_or_unmatched_mapping_preserves_request(self):
        for settings in ({}, {"image_model_mapping": {"auto": "codex-gpt-image-2"}}):
            with self.subTest(settings=settings):
                request = ConversationRequest(model="gpt-image-2", prompt="draw")
                generate, _ = self.run_request(request, settings)
                self.assertIs(generate.call_args.args[0], request)

    def test_malformed_or_empty_mapping_is_ignored(self):
        for mapping in (None, [], "codex-gpt-image-2", {"gpt-image-2": None},
                        {"gpt-image-2": 42}, {"gpt-image-2": "  "}):
            with self.subTest(mapping=mapping):
                request = ConversationRequest(model="gpt-image-2")
                generate, _ = self.run_request(request, {"image_model_mapping": mapping})
                self.assertIs(generate.call_args.args[0], request)

    def test_mapping_is_applied_once(self):
        generate, _ = self.run_request(ConversationRequest(model="gpt-image-2"), {
            "image_model_mapping": {
                "gpt-image-2": "codex-gpt-image-2", "codex-gpt-image-2": "gpt-image-2"
            }
        })
        self.assertEqual(generate.call_args.args[0].model, "codex-gpt-image-2")

    def test_unsupported_target_fails_before_generation(self):
        with self.assertRaises(ImageGenerationError):
            self.run_request(ConversationRequest(model="gpt-image-2"), {
                "image_model_mapping": {"gpt-image-2": "invalid-image-model"}
            })

    def test_serial_batch_uses_mapped_model_for_every_image(self):
        generate, outputs = self.run_request(ConversationRequest(model="gpt-image-2", n=3), {
            "image_model_mapping": {"gpt-image-2": "codex-gpt-image-2"},
            "image_parallel_generation": False,
        })
        self.assertEqual(len(outputs), 3)
        self.assertEqual([call.args[1:] for call in generate.call_args_list], [(1, 3), (2, 3), (3, 3)])
        self.assertTrue(all(call.args[0].model == "codex-gpt-image-2" for call in generate.call_args_list))

    def test_parallel_batch_uses_mapped_model_for_every_image(self):
        generate, outputs = self.run_request(ConversationRequest(model="gpt-image-2", n=3), {
            "image_model_mapping": {"gpt-image-2": "codex-gpt-image-2"},
            "image_parallel_generation": True,
        })
        self.assertEqual(len(outputs), 3)
        self.assertEqual(generate.call_count, 3)
        self.assertTrue(all(call.args[0].model == "codex-gpt-image-2" for call in generate.call_args_list))


if __name__ == "__main__":
    unittest.main()
