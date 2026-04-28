from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


class UserManagementAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "users.db"
        self.old_user_db = os.environ.get("CHATGPT2API_USER_DATABASE_URL")
        self.old_jwt_secret = os.environ.get("JWT_SECRET")
        os.environ["CHATGPT2API_USER_DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["JWT_SECRET"] = "unit-test-secret-with-at-least-32-bytes"

        for module_name in list(sys.modules):
            if (
                module_name.startswith("api.")
                or module_name.startswith("services.user")
                or module_name in {"api", "services.auth_service"}
            ):
                sys.modules.pop(module_name, None)

        app_module = importlib.import_module("api.app")
        self.client = TestClient(app_module.create_app())

    def tearDown(self) -> None:
        service_module = sys.modules.get("services.user_service")
        service = getattr(service_module, "user_service", None)
        engine = getattr(service, "engine", None)
        if engine is not None:
            engine.dispose()
        if self.old_user_db is None:
            os.environ.pop("CHATGPT2API_USER_DATABASE_URL", None)
        else:
            os.environ["CHATGPT2API_USER_DATABASE_URL"] = self.old_user_db
        if self.old_jwt_secret is None:
            os.environ.pop("JWT_SECRET", None)
        else:
            os.environ["JWT_SECRET"] = self.old_jwt_secret
        self.tmp.cleanup()

    def create_admin(self) -> str:
        response = self.client.post(
            "/api/setup/admin",
            json={"email": "admin@example.com", "password": "AdminPass123!"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        return str(payload["token"])

    def auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_setup_creates_first_admin_once_and_jwt_authenticates(self) -> None:
        status = self.client.get("/api/setup/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["requires_setup"], True)

        token = self.create_admin()

        status = self.client.get("/api/setup/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["requires_setup"], False)

        second = self.client.post(
            "/api/setup/admin",
            json={"email": "other@example.com", "password": "AdminPass123!"},
        )
        self.assertEqual(second.status_code, 409)

        me = self.client.get("/api/auth/me", headers=self.auth_headers(token))
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["user"]["email"], "admin@example.com")
        self.assertEqual(me.json()["user"]["role"], "admin")

    def test_register_consumes_invitation_and_applies_promo_code(self) -> None:
        admin_token = self.create_admin()
        headers = self.auth_headers(admin_token)
        settings = self.client.patch(
            "/api/admin/auth-settings",
            headers=headers,
            json={
                "email_verification_enabled": False,
                "invitation_required": True,
                "promo_codes_enabled": True,
                "default_image_quota": 0,
            },
        )
        self.assertEqual(settings.status_code, 200, settings.text)

        invite_response = self.client.post(
            "/api/admin/redeem-codes/generate",
            headers=headers,
            json={"type": "invitation", "count": 1},
        )
        self.assertEqual(invite_response.status_code, 200, invite_response.text)
        invitation_code = invite_response.json()["codes"][0]["code"]

        promo_response = self.client.post(
            "/api/admin/promo-codes",
            headers=headers,
            json={"code": "WELCOME", "image_quota": 3, "max_uses": 1},
        )
        self.assertEqual(promo_response.status_code, 200, promo_response.text)

        register = self.client.post(
            "/api/auth/register",
            json={
                "email": "user@example.com",
                "password": "UserPass123!",
                "invitation_code": invitation_code,
                "promo_code": "WELCOME",
            },
        )
        self.assertEqual(register.status_code, 200, register.text)
        self.assertEqual(register.json()["user"]["image_quota"], 3)

        reused = self.client.post(
            "/api/auth/register",
            json={
                "email": "second@example.com",
                "password": "UserPass123!",
                "invitation_code": invitation_code,
                "promo_code": "WELCOME",
            },
        )
        self.assertEqual(reused.status_code, 400)

    def test_image_quota_is_reserved_settled_and_text_requests_do_not_deduct(self) -> None:
        admin_token = self.create_admin()
        created = self.client.post(
            "/api/admin/users",
            headers=self.auth_headers(admin_token),
            json={
                "email": "artist@example.com",
                "password": "UserPass123!",
                "role": "user",
                "enabled": True,
                "image_quota": 1,
                "image_concurrency": 1,
            },
        )
        self.assertEqual(created.status_code, 200, created.text)

        login = self.client.post(
            "/api/auth/login",
            json={"email": "artist@example.com", "password": "UserPass123!"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        user_token = login.json()["token"]
        headers = self.auth_headers(user_token)

        with patch(
            "api.ai.openai_v1_image_generations.handle",
            return_value={"created": 1, "data": [{"b64_json": "abc"}]},
        ):
            first = self.client.post(
                "/v1/images/generations",
                headers=headers,
                json={"prompt": "draw", "model": "gpt-image-2", "n": 1},
            )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).json()["user"]["image_quota"], 0)

        with patch(
            "api.ai.openai_v1_chat_complete.handle",
            return_value={"id": "chatcmpl-test", "choices": [{"message": {"content": "ok"}}]},
        ):
            text = self.client.post(
                "/v1/chat/completions",
                headers=headers,
                json={"model": "gpt-5", "messages": [{"role": "user", "content": "hello"}]},
            )
        self.assertEqual(text.status_code, 200, text.text)
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).json()["user"]["image_quota"], 0)

        second = self.client.post(
            "/v1/images/generations",
            headers=headers,
            json={"prompt": "draw again", "model": "gpt-image-2", "n": 1},
        )
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["error"]["code"], "insufficient_quota")

    def test_failed_image_request_refunds_reserved_quota(self) -> None:
        admin_token = self.create_admin()
        self.client.post(
            "/api/admin/users",
            headers=self.auth_headers(admin_token),
            json={
                "email": "refund@example.com",
                "password": "UserPass123!",
                "role": "user",
                "enabled": True,
                "image_quota": 1,
                "image_concurrency": 1,
            },
        )
        login = self.client.post(
            "/api/auth/login",
            json={"email": "refund@example.com", "password": "UserPass123!"},
        )
        headers = self.auth_headers(login.json()["token"])

        with patch("api.ai.openai_v1_image_generations.handle", side_effect=RuntimeError("upstream failed")):
            response = self.client.post(
                "/v1/images/generations",
                headers=headers,
                json={"prompt": "draw", "model": "gpt-image-2", "n": 1},
            )
        self.assertEqual(response.status_code, 502, response.text)
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).json()["user"]["image_quota"], 1)

    def test_redeem_codes_add_image_quota_and_concurrency_once(self) -> None:
        admin_token = self.create_admin()
        user = self.client.post(
            "/api/admin/users",
            headers=self.auth_headers(admin_token),
            json={
                "email": "redeem@example.com",
                "password": "UserPass123!",
                "role": "user",
                "enabled": True,
                "image_quota": 0,
                "image_concurrency": 1,
            },
        )
        self.assertEqual(user.status_code, 200, user.text)
        login = self.client.post(
            "/api/auth/login",
            json={"email": "redeem@example.com", "password": "UserPass123!"},
        )
        headers = self.auth_headers(login.json()["token"])

        quota_code = self.client.post(
            "/api/admin/redeem-codes/generate",
            headers=self.auth_headers(admin_token),
            json={"type": "image_quota", "value": 5, "count": 1},
        ).json()["codes"][0]["code"]
        concurrency_code = self.client.post(
            "/api/admin/redeem-codes/generate",
            headers=self.auth_headers(admin_token),
            json={"type": "concurrency", "value": 2, "count": 1},
        ).json()["codes"][0]["code"]

        quota = self.client.post("/api/redeem", headers=headers, json={"code": quota_code})
        self.assertEqual(quota.status_code, 200, quota.text)
        concurrency = self.client.post("/api/redeem", headers=headers, json={"code": concurrency_code})
        self.assertEqual(concurrency.status_code, 200, concurrency.text)

        me = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me.json()["user"]["image_quota"], 5)
        self.assertEqual(me.json()["user"]["image_concurrency"], 3)

        reused = self.client.post("/api/redeem", headers=headers, json={"code": quota_code})
        self.assertEqual(reused.status_code, 400)


if __name__ == "__main__":
    unittest.main()
