"""One identity across the whole chain: payload, offset, PoW fingerprint, solver page.

These live in one module for a reason. The chain previously contradicted itself - the
conversation payload declared Asia/Shanghai while the proof-of-work fingerprint declared
Eastern Standard Time, and the solver page declared a third value - and a mismatch like
that is exactly what the sentinel handshake and Cloudflare score against. The invariant is
asserted here because upstream reports a disagreement as an intermittent 403 or a
disguised 404, which no single request can attribute.
"""

from __future__ import annotations

import re
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from services.openai_backend_api import OpenAIBackendAPI
from utils.identity import IDENTITY_TIMEZONE, identity_pow_date_string, identity_timezone_offset_min

REPO = Path(__file__).resolve().parent.parent
DST = datetime(2026, 10, 15, 14, 7, 6)      # Pacific daylight time
STANDARD = datetime(2026, 1, 15, 12, 0, 0)  # Pacific standard time


def ok_response(payload: dict | None = None) -> mock.Mock:
    response = mock.Mock(status_code=200)
    response.json.return_value = payload if payload is not None else {}
    return response


class IdentityHelpersTests(unittest.TestCase):
    def test_offset_follows_daylight_saving(self):
        self.assertEqual(identity_timezone_offset_min(DST), 420)
        self.assertEqual(identity_timezone_offset_min(STANDARD), 480)

    def test_pow_date_names_the_zone_and_carries_the_real_gmt_offset(self):
        self.assertEqual(identity_pow_date_string(DST), "Thu Oct 15 2026 14:07:06 GMT-0700 (Pacific Daylight Time)")
        self.assertEqual(identity_pow_date_string(STANDARD), "Thu Jan 15 2026 12:00:00 GMT-0800 (Pacific Standard Time)")

    def test_pow_date_offset_is_the_inverse_of_the_payload_offset(self):
        for moment in (DST, STANDARD):
            payload_offset = identity_timezone_offset_min(moment)
            match = re.search(r"GMT([+-])(\d{2})(\d{2})", identity_pow_date_string(moment))
            self.assertIsNotNone(match, "the date string must carry a GMT offset")
            sign = -1 if match.group(1) == "-" else 1
            date_offset_min = sign * (int(match.group(2)) * 60 + int(match.group(3)))
            # The payload field is inverted, so the real offset is its negation.
            self.assertEqual(date_offset_min, -payload_offset)


class RequestPayloadIdentityTests(unittest.TestCase):
    """The requests we actually send must all declare the same place."""

    def setUp(self):
        self.api = OpenAIBackendAPI("")

    def capture(self, call, payload: dict | None = None):
        """Run `call` with the session stubbed out, returning (url, request body)."""
        seen: dict[str, object] = {}

        def fake_request(url, **kwargs):  # noqa: ANN001
            seen["url"] = url
            seen["json"] = kwargs.get("json")
            return ok_response(payload)

        with mock.patch.object(self.api.session, "post", side_effect=fake_request), \
                mock.patch.object(self.api.session, "get", side_effect=fake_request):
            call()
        return seen

    def test_both_chat_targets_declare_the_identity_timezone(self):
        self.api.access_token = "token"
        self.assertEqual(self.api._chat_target(), ("/backend-api/conversation", IDENTITY_TIMEZONE))
        self.api.access_token = ""
        self.assertEqual(self.api._chat_target(), ("/backend-anon/conversation", IDENTITY_TIMEZONE))

    def test_text_conversation_payload(self):
        payload = self.api._conversation_payload([{"role": "user", "content": "hi"}], "auto", IDENTITY_TIMEZONE, None)
        self.assertEqual(payload["timezone"], IDENTITY_TIMEZONE)
        self.assertEqual(payload["timezone_offset_min"], identity_timezone_offset_min())

    def test_image_prepare_payload(self):
        seen = self.capture(lambda: self.api._prepare_image_conversation("cat", mock.Mock(token=""), "gpt-image-2.5"),
                            payload={"conduit_token": "x"})
        self.assertEqual(seen["json"]["timezone"], IDENTITY_TIMEZONE)
        self.assertEqual(seen["json"]["timezone_offset_min"], identity_timezone_offset_min())

    def test_image_conversation_payload(self):
        seen = self.capture(lambda: self.api._start_image_generation("cat", mock.Mock(token=""), "conduit", "gpt-image-2.5"))
        self.assertEqual(seen["json"]["timezone"], IDENTITY_TIMEZONE)
        self.assertEqual(seen["json"]["timezone_offset_min"], identity_timezone_offset_min())

    def test_conversation_init_payload(self):
        seen = self.capture(lambda: self.api._get_conversation_init(), payload={"ok": True})
        self.assertEqual(seen["json"]["timezone_offset_min"], identity_timezone_offset_min())

    def test_account_check_query_string(self):
        seen = self.capture(lambda: self.api._get_default_account(), payload={"accounts": {}})
        self.assertIn(f"timezone_offset_min={identity_timezone_offset_min()}", str(seen["url"]))


class NoHardcodedTimezoneTests(unittest.TestCase):
    """A literal that survived in one file is how the chain drifted apart before."""

    LITERALS = ("Asia/Shanghai", '"-480"', "timezone_offset_min=-480", "GMT-0500", "Eastern Standard Time")
    # `utils/identity.py` documents the old values it replaced. `sub2api_service.py` talks
    # to a third-party sub2api admin API whose own `timezone` query param is a different
    # service's convention, not part of the chatgpt.com sentinel chain this guard protects.
    ALLOWED = {"utils/identity.py", "services/sub2api_service.py"}

    def test_no_module_hardcodes_a_timezone(self):
        offenders = []
        for folder in ("services", "utils", "api"):
            for path in sorted((REPO / folder).rglob("*.py")):
                relative = path.relative_to(REPO).as_posix()
                if relative in self.ALLOWED:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                for literal in self.LITERALS:
                    if literal in text:
                        offenders.append(f"{relative}: {literal}")
        self.assertEqual(offenders, [], f"hardcoded timezone literals: {offenders}")

    def test_the_solver_page_uses_the_same_timezone(self):
        manifest = (REPO / "k8s" / "chatgpt2api-k3s.yaml").read_text(encoding="utf-8")
        match = re.search(r"- name: SENTINEL_SOLVER_TIMEZONE\s*\n\s*value: (\S+)", manifest)
        self.assertIsNotNone(match, "SENTINEL_SOLVER_TIMEZONE missing from the solver deployment")
        self.assertEqual(match.group(1), IDENTITY_TIMEZONE)


if __name__ == "__main__":
    unittest.main()
