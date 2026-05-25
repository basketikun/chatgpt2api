"""Regression test for the chatgpt/free/auto vision path.

Locks in two invariants that, if broken, regress the bug fixed in
commit a9162b8 ("fix(vision): keep image messages through the
payload-size truncation"):

1. `_payload_size_bytes` treats a `type:"image"` part with bytes data
   as its raw byte length — NOT the inflated `str(bytes)` form that
   would otherwise count each byte as ~4 characters.

2. `_truncate_messages` never drops a message that carries image
   content, even when the payload exceeds `_MAX_PAYLOAD_BYTES` and the
   loop has to discard older non-system messages.

Run from the repo root:
    uv run --no-project python plans/test_vision_truncation_regression.py
"""
from __future__ import annotations

import os
import sys

# Make the chatgpt2api package importable when run from repo root.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
# ConfigStore refuses to import without an auth key — supply a dummy
# one so this regression test can run without a real deployment.
os.environ.setdefault("CHATGPT2API_AUTH_KEY", "test-only-not-used")

from services.protocol.conversation import (  # noqa: E402
    _MAX_PAYLOAD_BYTES,
    _has_image_content,
    _payload_size_bytes,
    _truncate_messages,
)


def _fake_image_message(byte_len: int) -> dict:
    """Build a user message with an image part holding `byte_len` raw bytes."""
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": "Đếm số người trong ảnh"},
            {"type": "image", "data": b"\xff" * byte_len, "mime": "image/jpeg"},
        ],
    }


def test_payload_size_uses_raw_bytes() -> None:
    msg = _fake_image_message(byte_len=110_000)
    size = _payload_size_bytes([msg])
    # ~110 KB raw + a few bytes of text + 40 B overhead, NOT the ~440 KB
    # the buggy `json.dumps(..., default=str)` form would produce.
    assert 110_000 < size < 115_000, (
        f"expected ~110KB sizing, got {size}; the bytes-aware path is "
        "likely broken — see conversation.py _payload_size_bytes()"
    )


def test_truncate_preserves_image_over_cap() -> None:
    """Even a single 110KB image (over the 100KB cap on its own) must survive."""
    messages = [
        {"role": "system", "content": "you are a helpful assistant"},
        _fake_image_message(byte_len=110_000),
    ]
    result = _truncate_messages(messages)
    assert any(_has_image_content(m) for m in result), (
        "image message was dropped by _truncate_messages — this is the "
        "exact regression that produced the 'Chào bạn!' bug. See the "
        "INVARIANT in _truncate_messages docstring."
    )
    assert result[0].get("role") == "system", "system message order changed"


def test_truncate_drops_old_text_but_keeps_image() -> None:
    """When the cap is exceeded by text history, drop the text history,
    NOT the image-bearing user message."""
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "x" * 70_000},  # old text, droppable
        {"role": "assistant", "content": "ack"},
        _fake_image_message(byte_len=80_000),  # current vision request
    ]
    result = _truncate_messages(messages)
    assert any(_has_image_content(m) for m in result), "image dropped"
    text_lengths = [
        len(m["content"]) for m in result
        if m.get("role") == "user" and isinstance(m.get("content"), str)
    ]
    assert all(l < 70_000 for l in text_lengths) or not text_lengths, (
        "old large text user message was not dropped — payload still bloated"
    )


def test_short_payload_returns_unchanged() -> None:
    messages = [
        {"role": "system", "content": "short system"},
        {"role": "user", "content": "short user"},
    ]
    result = _truncate_messages(messages)
    assert result == messages, "small payload should pass through unchanged"


def main() -> None:
    tests = [
        test_payload_size_uses_raw_bytes,
        test_truncate_preserves_image_over_cap,
        test_truncate_drops_old_text_but_keeps_image,
        test_short_payload_returns_unchanged,
    ]
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as exc:
            failures.append((fn.__name__, exc))
            print(f"  FAIL  {fn.__name__}: {exc}")
    print()
    if failures:
        print(f"{len(failures)}/{len(tests)} test(s) FAILED")
        sys.exit(1)
    print(f"All {len(tests)} tests PASSED — vision truncation invariants hold")


if __name__ == "__main__":
    main()
