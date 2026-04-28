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
OPENAI_IMAGE_BASE_URL = "https://ai.yunfei.best/v1"
OPENAI_IMAGE_API_KEY = "sk-q8rsQchejOfvyxHgoiX5PQKRAD8G8fh8L3F3aYlfSAhD4MJB"
PROMPT_OPTIMIZER_BASE_URL = "https://ai.yunfei.best/v1"
PROMPT_OPTIMIZER_API_KEY = "sk-m9heEruQxkNjLOWtVjM0wrz7Jk7phQAddA4Sto0DrOpCw807"
PROMPT_OPTIMIZER_MODEL = "gpt-5.4"


@dataclass(frozen=True)
class AppSettings:
    auth_key: str
    host: str
    port: int
    accounts_file: Path
    refresh_account_interval_minute: int
    openai_image_base_url: str
    openai_image_api_key: str
    openai_image_max_attempts: int
    prompt_optimizer_base_url: str
    prompt_optimizer_api_key: str
    prompt_optimizer_model: str
    images_dir: Path
    logs_dir: Path


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
    images_dir = DATA_DIR / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # 优先使用环境变量，文件配置仅作为本地/自托管回退
    raw_config: dict[str, object] = {}
    config_file = _readable_json_file(CONFIG_FILE, name="config.json")
    if config_file is not None:
        raw_config.update(_load_json_object(config_file, name="config.json"))

    auth_key = str(
        os.getenv("CHATGPT2API_AUTH_KEY")
        or raw_config.get("auth-key")
        or ""
    ).strip()

    if not auth_key:
        raise ValueError(
            "❌ auth-key 未设置！\n"
            "请按以下任意一种方式解决：\n"
            "1. 在 Render 的 Environment 变量中添加：\n"
            "   CHATGPT2API_AUTH_KEY = your_real_auth_key\n"
            "2. 或者在 config.json 中填写：\n"
            '   "auth-key": "your_real_auth_key"'
        )

    refresh_account_interval_minute = cast(
        int, raw_config.get("refresh_account_interval_minute", 60)
    )

    openai_image_base_url = OPENAI_IMAGE_BASE_URL
    openai_image_api_key = OPENAI_IMAGE_API_KEY
    openai_image_max_attempts = max(
        1,
        min(20, int(raw_config.get("openai_image_max_attempts") or os.getenv("CHATGPT2API_OPENAI_IMAGE_MAX_ATTEMPTS") or 8)),
    )
    prompt_optimizer_base_url = str(
        os.getenv("CHATGPT2API_PROMPT_OPTIMIZER_BASE_URL")
        or raw_config.get("prompt_optimizer_base_url")
        or PROMPT_OPTIMIZER_BASE_URL
    ).strip()
    prompt_optimizer_api_key = str(
        os.getenv("CHATGPT2API_PROMPT_OPTIMIZER_API_KEY")
        or raw_config.get("prompt_optimizer_api_key")
        or PROMPT_OPTIMIZER_API_KEY
    ).strip()
    prompt_optimizer_model = str(
        os.getenv("CHATGPT2API_PROMPT_OPTIMIZER_MODEL")
        or raw_config.get("prompt_optimizer_model")
        or PROMPT_OPTIMIZER_MODEL
    ).strip()

    return AppSettings(
        auth_key=auth_key,
        host="0.0.0.0",
        port=8000,
        accounts_file=DATA_DIR / "accounts.json",
        refresh_account_interval_minute=refresh_account_interval_minute,
        openai_image_base_url=openai_image_base_url,
        openai_image_api_key=openai_image_api_key,
        openai_image_max_attempts=openai_image_max_attempts,
        prompt_optimizer_base_url=prompt_optimizer_base_url,
        prompt_optimizer_api_key=prompt_optimizer_api_key,
        prompt_optimizer_model=prompt_optimizer_model,
        images_dir=images_dir,
        logs_dir=logs_dir,
    )


config = _load_settings()
