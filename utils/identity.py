"""The identity the whole upstream chain presents: one timezone, one offset, one date format.

The account pool is US and so is the egress, so every layer declares US Pacific. These
used to be literals scattered across several files, which is exactly how the chain ended
up contradicting itself: the conversation payload said Asia/Shanghai while the
proof-of-work fingerprint said Eastern Standard Time.

Anything that renders a time for upstream reads it from here.

The Pacific offset is computed from the US daylight-saving rule rather than through
`zoneinfo`, so it behaves the same on the container and on a Windows checkout that has no
tzdata, and so it needs no extra dependency.
"""

from __future__ import annotations

from datetime import datetime, timedelta

IDENTITY_TIMEZONE = "America/Los_Angeles"

# The web client states the offset inverted: UTC+8 is sent as -480.
_PACIFIC_STANDARD_HOURS = -8
_PACIFIC_DAYLIGHT_HOURS = -7
_LONG_NAMES = {-7: "Pacific Daylight Time", -8: "Pacific Standard Time"}


def _nth_sunday(year: int, month: int, nth: int) -> datetime:
    """Local 02:00 on the nth Sunday of a month — when US transitions happen."""
    first = datetime(year, month, 1)
    days_ahead = (6 - first.weekday()) % 7
    return first + timedelta(days=days_ahead + 7 * (nth - 1), hours=2)


def _pacific_offset_hours(now: datetime) -> int:
    """-7 while daylight saving is in force, -8 otherwise (post-2007 US rule)."""
    # DST runs from the second Sunday in March to the first Sunday in November.
    if _nth_sunday(now.year, 3, 2) <= now < _nth_sunday(now.year, 11, 1):
        return _PACIFIC_DAYLIGHT_HOURS
    return _PACIFIC_STANDARD_HOURS


def identity_timezone_offset_min(now: datetime | None = None) -> int:
    """Offset in the web client's convention, tracking daylight saving automatically."""
    moment = now or datetime.now()
    return -_pacific_offset_hours(moment) * 60


def identity_pow_date_string(now: datetime | None = None) -> str:
    """`"" + new Date` as a browser in this timezone renders it.

    e.g. `Thu Oct 15 2026 14:07:06 GMT-0700 (Pacific Daylight Time)` — the shape the
    sentinel SDK puts in its config, with the offset and long name that match the
    timezone declared everywhere else.
    """
    moment = now or datetime.now()
    hours = _pacific_offset_hours(moment)
    # The date string carries the real offset (GMT-0700); only the payload field is inverted.
    total_minutes = hours * 60
    sign = "+" if total_minutes >= 0 else "-"
    whole, remainder = divmod(abs(total_minutes), 60)
    return (
        f"{moment.strftime('%a %b %d %Y %H:%M:%S')} "
        f"GMT{sign}{whole:02d}{remainder:02d} ({_LONG_NAMES[hours]})"
    )
