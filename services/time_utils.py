from __future__ import annotations

from datetime import UTC, datetime


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def utc_timestamp_iso(value: float) -> str:
    return datetime.fromtimestamp(value, tz=UTC).isoformat().replace("+00:00", "Z")
