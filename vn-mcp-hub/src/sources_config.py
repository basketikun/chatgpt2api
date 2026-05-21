"""Per-MCP source toggle config — reads/writes data/studio/sources.json.

Each MCP can have multiple sub-sources (RSS feeds, APIs, search backends).
Users toggle them on/off in Studio UI. MCPs read this config at runtime
to skip disabled sources — no restart needed.

Default: all sources ON for all MCPs. Only MCPs that the user has customized
appear in sources.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SOURCES_FILE = Path("/app/data/studio/sources.json")

# ── Default source definitions per MCP ──────────────────────────────────────

DEFAULTS: dict[str, dict[str, bool]] = {
    "vn_news": {
        "vnexpress": True,
        "tuoitre": True,
        "thanhnien": True,
        "dantri": True,
        "bbc_news": True,
        "google_news": True,
    },
    "vn_weather": {
        "open_meteo": True,
        "accuweather": False,   # needs API key
        "nws": True,            # US National Weather Service, free
        "wttr": True,
    },
    "federated_search": {
        "ddg": True,
        "wikipedia": True,
        "brave": False,         # needs API key
        "semantic_scholar": True,
        "crossref": True,
        "pubmed": True,
        "openalex": True,
        "internet_archive": True,
    },
    "kb_dien_nuoc":  {"chroma_rag": True, "web_fallback": True},
    "kb_y_te":       {"chroma_rag": True, "pubmed_api": True, "web_fallback": True},
    "kb_giao_duc":   {"chroma_rag": True, "web_fallback": True},
    "kb_ngoai_ngu":  {"chroma_rag": True, "web_fallback": True},
    "kb_khoa_hoc":   {"chroma_rag": True, "web_fallback": True},
    "kb_tu_nhien":   {"chroma_rag": True, "web_fallback": True},
    "kb_xa_hoi":     {"chroma_rag": True, "web_fallback": True},
    "kb_sach":       {"chroma_rag": True, "web_fallback": True},
}

# Help text for sources that need user action (API key, setup, etc.)
SOURCE_HELP: dict[str, dict[str, str]] = {
    "vn_weather": {
        "accuweather": "Cần ACCUWEATHER_API_KEY. Đăng ký free 50 calls/ngày tại developer.accuweather.com",
    },
    "federated_search": {
        "brave": "Cần BRAVE_API_KEY. Đăng ký free 2000 queries/tháng tại brave.com/search/api",
        "mojeek": "Cần MOJEEK_API_KEY. Đăng ký free tier tại mojeek.com/search/api",
        "semantic_scholar": "Nhập SEMANTIC_SCHOLAR_API_KEY (không bắt buộc) từ api.semanticscholar.org để tránh lỗi 429 (Rate Limit).",
    },
    "vn_news": {
        "google_news": "Google News RSS có thể bị chặn ở một số quốc gia. Dùng VPN nếu cần.",
    },
}

# Map source key to env var name for API keys
SOURCE_ENV_MAP = {
    "accuweather": "ACCUWEATHER_API_KEY",
    "brave": "BRAVE_API_KEY",
    "mojeek": "MOJEEK_API_KEY",
    "semantic_scholar": "SEMANTIC_SCHOLAR_API_KEY",
}


def _read() -> dict[str, dict[str, bool]]:
    if not SOURCES_FILE.exists():
        return {}
    try:
        return json.loads(SOURCES_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _write(data: dict[str, dict[str, bool]]) -> None:
    SOURCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    SOURCES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_all() -> dict[str, dict[str, bool]]:
    """Return all MCP source configs, merged with defaults."""
    stored = _read()
    result: dict[str, dict[str, bool]] = {}
    for mcp, sources in DEFAULTS.items():
        result[mcp] = dict(sources)
        if mcp in stored:
            result[mcp].update(stored[mcp])
    return result


def get_all_with_help() -> dict:
    """Return sources + help text for Studio UI."""
    sources = get_all()
    keys = _read_keys()
    result: dict = {}
    for mcp, srcs in sources.items():
        items: dict = {}
        for name, enabled in srcs.items():
            env_var = SOURCE_ENV_MAP.get(name, "")
            items[name] = {
                "enabled": enabled,
                "help": (SOURCE_HELP.get(mcp, {}).get(name, "")),
                "needs_key": bool(env_var),
                "has_key": bool(get_api_key(name)),
            }
        result[mcp] = items
    return result


def _read_keys() -> dict[str, str]:
    kf = Path("/app/data/studio/api_keys.json")
    if not kf.exists():
        return {}
    return json.loads(kf.read_text(encoding="utf-8")) or {}


def _write_keys(keys: dict[str, str]) -> None:
    kf = Path("/app/data/studio/api_keys.json")
    kf.parent.mkdir(parents=True, exist_ok=True)
    kf.write_text(json.dumps(keys, ensure_ascii=False, indent=2), encoding="utf-8")


def get_api_key(source_key: str) -> str:
    """Get API key for a source. Checks env var first, then local keys file."""
    import os
    env_var = SOURCE_ENV_MAP.get(source_key, "")
    if env_var:
        val = os.environ.get(env_var, "")
        if val:
            return val
    try:
        return _read_keys().get(source_key, "")
    except Exception:
        return ""


def save_api_key(source_key: str, api_key: str) -> bool:
    """Save an API key for a source."""
    keys = _read_keys()
    keys[source_key] = api_key
    _write_keys(keys)
    return True


def get_mcp(mcp_name: str) -> dict[str, bool]:
    """Return source config for one MCP, merged with defaults."""
    defaults = DEFAULTS.get(mcp_name, {})
    stored = _read().get(mcp_name, {})
    return {**defaults, **stored}


def is_enabled(mcp_name: str, source_name: str) -> bool:
    """Check if a specific source is enabled for a MCP."""
    return get_mcp(mcp_name).get(source_name, True)


def set_source(mcp_name: str, source_name: str, enabled: bool) -> dict[str, bool]:
    """Toggle one source. Returns updated config for that MCP."""
    stored = _read()
    if mcp_name not in stored:
        stored[mcp_name] = {}
    stored[mcp_name][source_name] = enabled
    # Clean up: remove keys that match defaults (keep file small)
    defaults = DEFAULTS.get(mcp_name, {})
    clean = {}
    for k, v in stored[mcp_name].items():
        if v != defaults.get(k):
            clean[k] = v
    if clean:
        stored[mcp_name] = clean
    else:
        stored.pop(mcp_name, None)
    _write(stored)
    logger.info("Source toggled: %s.%s = %s", mcp_name, source_name, enabled)
    return get_mcp(mcp_name)
