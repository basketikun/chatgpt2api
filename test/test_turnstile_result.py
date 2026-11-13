"""The solver must not hand upstream a value that is not a turnstile token.

This is the check that was missing when the WeakMap hook swallowed the module's own
cache: the challenge program never ran, the seed came straight back, and upstream
answered with a disguised `404 {"detail": "Model not found"}` - which reads as an account
or quota problem and sends you looking in the wrong place.
"""

from __future__ import annotations

import base64
import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent.parent / "sentinel_solver" / "turnstile_result.py"
_spec = importlib.util.spec_from_file_location("turnstile_result", MODULE_PATH)
turnstile_result = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(turnstile_result)

validate = turnstile_result.validate_turnstile_token
retryable = turnstile_result.is_retryable_solve_error

SEED = "gAAAAACsome-requirements-token"
REAL_TOKEN = "QxIcBBYJGRQCEm1kDGpsUV9x"


class ValidateTurnstileTokenTests(unittest.TestCase):
    def test_a_plausible_token_is_accepted(self):
        self.assertEqual(validate(REAL_TOKEN, SEED), "")

    def test_empty_token_is_rejected(self):
        self.assertIn("empty", validate("", SEED))

    def test_the_seed_echoed_back_is_rejected(self):
        # Exactly what a WeakMap hook that does not skip tokenCache produces.
        message = validate(SEED, SEED)
        self.assertIn("echoed the seed back", message)
        self.assertIn("never ran", message)

    def test_a_step_count_means_the_vm_timed_out(self):
        message = validate("147", SEED)
        self.assertIn(turnstile_result.VM_TIMEOUT_MARK, message)
        self.assertTrue(retryable(message))

    def test_a_vm_error_is_not_retryable(self):
        encoded = base64.b64encode(b"42: TypeError: x is not a function").decode()
        message = validate(encoded, SEED)
        self.assertIn("failed", message)
        self.assertFalse(retryable(message))

    def test_only_a_timeout_is_retryable(self):
        self.assertFalse(retryable(validate(REAL_TOKEN, SEED)))
        self.assertFalse(retryable(validate(SEED, SEED)))
        self.assertFalse(retryable(""))


if __name__ == "__main__":
    unittest.main()
