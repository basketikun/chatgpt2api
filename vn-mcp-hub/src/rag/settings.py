"""RAG lifecycle settings — sync interval, storage mode.

Stored in data/studio/settings.json. Read at runtime so changes take effect
without restart (scheduler re-reads on each cycle).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SETTINGS_FILE = Path("/app/data/studio/settings.json")

DEFAULTS = {
    "sync_interval_minutes": 360,     # 6 hours between R2 syncs
    "storage_mode": "local",          # "local" | "cloud" | "both"
    "auto_update_interval_hours": 1,  # scheduler check frequency
    "api_base_url": "http://chatgpt2api:3030/v1",
    "ai_model": "cx/auto",
    "api_key": "AnhNhi@0610",
    "telegram_bot_token": "",         # Telegram Bot token for 2-way chat
    "telegram_chat_ids": [],          # Allowed Telegram chat IDs (empty=allow all)
    "telegram_ai_model": "",          # AI model for Telegram (empty=use default)
    "telegram_webhook_url": "",       # Public webhook URL for Telegram
    "telegram_system_prompt": "",     # Custom system prompt for Telegram bot

    # ── KB auto-refresh defaults (used when a collection's own meta.json
    # doesn't set them). Match meta.py defaults.
    "refresh_interval_days": 90,     # how often the scheduler force-refreshes
    "soft_notify_days": 60,          # add "you may want to refresh" hint after this
    # Time-of-day window (local server time) when the scheduler is allowed
    # to run AI synthesis. Set start == end to allow any time. Useful for
    # restricting heavy work to overnight (e.g. 0 → 5).
    "refresh_window_start_hour": 0,  # inclusive (0-23)
    "refresh_window_end_hour": 0,    # exclusive (0-23); 0==0 means "any time"
}


def get_refresh_window() -> tuple[int, int]:
    """Return (start_hour, end_hour). end_hour is exclusive. (0,0) means
    "any time of day is allowed"."""
    s = read()
    try:
        start = int(s.get("refresh_window_start_hour", 0)) % 24
        end = int(s.get("refresh_window_end_hour", 0)) % 24
    except (TypeError, ValueError):
        start, end = 0, 0
    return start, end


def is_within_refresh_window(now=None) -> bool:
    """True if `now` falls inside the configured refresh window."""
    from datetime import datetime
    start, end = get_refresh_window()
    if start == end:
        return True  # any time allowed
    hour = (now or datetime.now()).hour
    if start < end:
        return start <= hour < end
    # window wraps midnight (e.g. 22 → 5)
    return hour >= start or hour < end


def get_default_refresh_interval_hours() -> int:
    s = read()
    try:
        return max(1, int(s.get("refresh_interval_days", 90))) * 24
    except (TypeError, ValueError):
        return 90 * 24


def get_default_soft_notify_days() -> int:
    s = read()
    try:
        return max(1, int(s.get("soft_notify_days", 60)))
    except (TypeError, ValueError):
        return 60


def read() -> dict:
    if not SETTINGS_FILE.exists():
        return dict(DEFAULTS)
    try:
        stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return {**DEFAULTS, **stored}
    except Exception:
        return dict(DEFAULTS)


def write(data: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_sync_interval_minutes() -> int:
    return int(read().get("sync_interval_minutes", 360))


def get_storage_mode() -> str:
    return str(read().get("storage_mode", "local"))


def should_use_cloud() -> bool:
    return get_storage_mode() in ("cloud", "both")


def should_use_local() -> bool:
    return get_storage_mode() in ("local", "both")
