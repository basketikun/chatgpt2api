"""The browser identity we advertise must describe the client the TLS profile emulates.

This is a deterministic guard on purpose. The mismatch it catches (a chrome146 TLS
fingerprint carrying Edge 143 headers) shows up upstream only as an intermittent
Cloudflare challenge, which cannot be measured reliably request by request — so the
invariant is asserted here instead.
"""

from __future__ import annotations

import re
import unittest
from unittest import mock

from services import openai_backend_api as backend
from services.openai_backend_api import OpenAIBackendAPI


class FingerprintConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.api = OpenAIBackendAPI("")
        self.addCleanup(self.api.close)
        self.headers = self.api.session.headers

    def ua_version(self) -> str:
        match = re.search(r"Chrome/(\d+)\.", self.headers["User-Agent"])
        self.assertIsNotNone(match, "user agent must name a Chrome version")
        return match.group(1)

    def profile_version(self) -> str:
        match = re.match(r"chrome(\d+)$", self.api.fp["impersonate"])
        self.assertIsNotNone(match, f"unexpected impersonate profile {self.api.fp['impersonate']!r}")
        return match.group(1)

    def test_user_agent_version_matches_the_tls_profile(self):
        self.assertEqual(self.ua_version(), self.profile_version())

    def test_client_hint_versions_match_the_user_agent(self):
        version = self.ua_version()
        sec_ch_ua = self.headers["Sec-Ch-Ua"]
        self.assertIn(f'"Chromium";v="{version}"', sec_ch_ua)
        self.assertIn(f'"Google Chrome";v="{version}"', sec_ch_ua)
        self.assertEqual(self.headers["Sec-Ch-Ua-Full-Version"], f'"{version}.0.0.0"')
        self.assertIn(f'"Chromium";v="{version}.0.0.0"', self.headers["Sec-Ch-Ua-Full-Version-List"])

    def test_the_identity_does_not_mix_browser_brands(self):
        # The bug this guards: an Edge identity on top of a Chrome TLS profile.
        for name in ("User-Agent", "Sec-Ch-Ua", "Sec-Ch-Ua-Full-Version-List"):
            value = self.headers[name]
            self.assertNotIn("Edg/", value)
            self.assertNotIn("Microsoft Edge", value)
            self.assertNotIn("Edge", value)
        self.assertNotIn("Edg/", backend.FINGERPRINT_UA)
        self.assertNotIn("Microsoft Edge", backend.FINGERPRINT_SEC_CH_UA)

    def test_the_platform_reported_by_the_hints_matches_the_user_agent(self):
        self.assertIn("Windows NT", self.headers["User-Agent"])
        self.assertEqual(self.headers["Sec-Ch-Ua-Platform"], '"Windows"')

    def test_legacy_profiles_are_replaced_rather_than_used(self):
        for legacy in backend.LEGACY_IMPERSONATES:
            self.assertNotEqual(self.api.fp["impersonate"], legacy)

    def test_a_stored_legacy_fingerprint_is_upgraded(self):
        # Accounts that carry an old fp must not keep an edge101 profile.
        with self._cached_account({"fp": {"impersonate": "edge101"}}):
            api = OpenAIBackendAPI("test-token")
            self.addCleanup(api.close)
            self.assertEqual(api.fp["impersonate"], backend.DEFAULT_IMPERSONATE)
            self.assertEqual(api.fp["user-agent"], backend.FINGERPRINT_UA)

    class _cached_account:  # noqa: N801 - small helper, used as a context manager
        def __init__(self, account: dict):
            self.account = account

        def __enter__(self):
            self._patch = mock.patch.object(backend.account_service, "get_account", return_value=self.account)
            self._patch.start()

        def __exit__(self, *exc):
            self._patch.stop()


if __name__ == "__main__":
    unittest.main()
