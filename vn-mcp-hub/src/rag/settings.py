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
}


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
