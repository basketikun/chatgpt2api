from __future__ import annotations

import unittest

from services.openai_backend_api import _is_content_policy_error


class ContentPolicyKeywordTests(unittest.TestCase):
    """内容政策关键词匹配，用例文本均取自线上真实回复。"""

    def test_matches_chinese_moderation_message(self) -> None:
        text = "非常抱歉，生成的图片可能违反了我们的内容政策。如果你认为此判断有误，请重试或修改提示语。"
        self.assertTrue(_is_content_policy_error(text))

    def test_matches_observed_english_refusals_with_curly_apostrophe(self) -> None:
        # 线上 4 条轮询超时会话里上游返回的原文，弯引号为 U+2019
        texts = [
            "Sorry, I can’t help create or edit an image of a real person to make them topless or nude.",
            "Sorry, I can’t help create a nude or sexually explicit image of a real person.",
            "Sorry, I can’t help create or edit an image to make a real person appear nude or unclothed.",
            "Sorry, I can’t help create nude or sexually explicit edits of a real person in an image.",
        ]
        for text in texts:
            with self.subTest(text=text):
                self.assertTrue(_is_content_policy_error(text))

    def test_matches_english_refusal_with_straight_apostrophe(self) -> None:
        self.assertTrue(_is_content_policy_error("Sorry, I can't help with that request."))

    def test_ignores_plain_text_and_empty(self) -> None:
        self.assertFalse(_is_content_policy_error("Here is the image you asked for."))
        self.assertFalse(_is_content_policy_error(""))


if __name__ == "__main__":
    unittest.main()
