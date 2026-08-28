from __future__ import annotations

import unittest

from services.openai_backend_api import OpenAIBackendAPI


class OpenAIBackendAccountInfoTests(unittest.TestCase):
    def test_get_user_info_exposes_authoritative_subscription_renewal(self) -> None:
        backend = OpenAIBackendAPI.__new__(OpenAIBackendAPI)
        backend.access_token = "token"
        backend._get_me = lambda: {"email": "pro@example.com", "id": "user_test"}
        backend._get_conversation_init = lambda: {
            "limits_progress": [{"feature_name": "image_gen", "remaining": 7}],
            "default_model_slug": "gpt-test",
        }
        backend._get_default_account = lambda: (
            {"plan_type": "Pro"},
            {
                "has_active_subscription": True,
                "subscription_plan": "chatgptpro",
                "billing_period": "monthly",
                "renews_at": "2026-09-05T08:06:08+00:00",
                "cancels_at": None,
                "subscription_id": "must-not-leak",
            },
        )

        result = backend.get_user_info()

        self.assertEqual(result["renews_at"], "2026-09-05T08:06:08+00:00")
        self.assertEqual(result["billing_period"], "monthly")
        self.assertEqual(result["subscription_plan"], "chatgptpro")
        self.assertTrue(result["has_active_subscription"])
        self.assertIsNone(result["cancels_at"])
        self.assertNotIn("subscription_id", result)

    def test_get_user_info_preserves_unknown_renewal_as_none(self) -> None:
        backend = OpenAIBackendAPI.__new__(OpenAIBackendAPI)
        backend.access_token = "token"
        backend._get_me = lambda: {"email": "free@example.com", "id": "user_free"}
        backend._get_conversation_init = lambda: {"limits_progress": []}
        backend._get_default_account = lambda: ({"plan_type": "free"}, {})

        result = backend.get_user_info()

        self.assertIsNone(result["has_active_subscription"])
        self.assertIsNone(result["renews_at"])
        self.assertIsNone(result["billing_period"])
        self.assertIsNone(result["cancels_at"])


if __name__ == "__main__":
    unittest.main()
