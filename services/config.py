from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "config.json"


@dataclass(frozen=True)
class AppSettings:
    auth_key: str
    host: str
    port: int
    accounts_file: Path
    proxy_url: str | None
    refresh_account_interval_minute: int


def _readable_json_file(path: Path, *, name: str) -> Path | None:
    if not path.exists():
        return None
    if path.is_dir():
        print(
            f"Warning: {name} at '{path}' is a directory, ignoring it and falling back to other configuration sources.",
            file=sys.stderr,
        )
        return None
    return path


def _load_json_object(path: Path, *, name: str) -> dict[str, object]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"{name} must be a JSON object")
    return loaded


def _load_settings() -> AppSettings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    raw_config: dict[str, object] = {}
    config_file = _readable_json_file(CONFIG_FILE, name="config.json")
    if config_file is not None:
        raw_config.update(_load_json_object(config_file, name="config.json"))

    auth_key = str(os.getenv("CHATGPT2API_AUTH_KEY") or raw_config.get("auth-key") or "").strip()
    if not auth_key:
        raise ValueError(
            "auth-key 未设置。\n"
            "请在环境变量 CHATGPT2API_AUTH_KEY 中设置，或在 config.json 中提供 auth-key。"
        )

    proxy_url = str(os.getenv("CHATGPT2API_PROXY_URL") or raw_config.get("proxy-url") or "").strip() or None
    refresh_account_interval_minute = cast(int, raw_config.get("refresh_account_interval_minute", 5))

    return AppSettings(
        auth_key=auth_key,
        host="0.0.0.0",
        port=8000,
        accounts_file=DATA_DIR / "accounts.json",
        proxy_url=proxy_url,
        refresh_account_interval_minute=refresh_account_interval_minute,
    )


config = _load_settings()
