"""Deciding whether the page's turnstile module actually produced a token.

Kept free of any browser dependency so it can be unit-tested from the main service's
virtualenv, which does not have Playwright.

This check is what stops a silently useless handshake from travelling on. Every failure
the module can report is a string that is obviously not a token, and upstream answers a
bad token with a disguised `404 {"detail": "Model not found"}` - which reads as an
account or quota problem and sends you looking in the wrong place.
"""

from __future__ import annotations

import base64
import re

# The module shares the frontend's 500ms budget and reports the step count on timeout.
VM_TIMEOUT_MARK = "turnstile VM timed out"

_ERROR_SHAPE = re.compile(r"^\d+: ")


def validate_turnstile_token(token: str, seed: str) -> str:
    """Return why the token is unusable, or "" when it looks like a real one."""
    if not token:
        return "the page's turnstile module returned an empty token"
    if token == seed:
        # The seed is echoed back when the module's own cache is consulted instead of
        # running the challenge program - the exact shape of a broken WeakMap hook.
        return "the page's turnstile module echoed the seed back; the challenge never ran"
    if token.isdigit():
        return f"{VM_TIMEOUT_MARK} after {token} steps"
    try:
        decoded = base64.b64decode(token + "===", validate=False).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        decoded = ""
    if _ERROR_SHAPE.match(decoded):
        return f"the page's turnstile module failed: {decoded[:160]}"
    return ""


def is_retryable_solve_error(error: str) -> bool:
    """Only a cold-page timeout is worth re-running; anything else is a real failure."""
    return VM_TIMEOUT_MARK in str(error or "")
