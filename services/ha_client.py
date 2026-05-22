"""Home Assistant REST API client via Long-Lived Access Token.

Fetches entity states and calls services so the LLM can see and control
the smart home directly, without needing the HA voice pipeline.
"""

from __future__ import annotations

import json, logging, time, threading
from typing import Any
import urllib.request

from services.config import config
from utils.log import logger

# ── Module-level state cache ────────────────────────────────────────────────
_state_cache: list[dict] = []
_state_cache_ts: float = 0.0
_context_cache: str = ""          # Pre-computed context string
_context_cache_ts: float = 0.0
_state_cache_lock = threading.Lock()
_CACHE_TTL = 60  # seconds (configurable via home_assistant.refresh_interval)


def _get_cache_ttl() -> int:
    """Get refresh interval from HA settings, default 60s."""
    try:
        ha = config.data.get("home_assistant") or {}
        return int(ha.get("refresh_interval", 60))
    except Exception:
        return 60


def _get_ha_config() -> dict[str, str] | None:
    ha = config.data.get("home_assistant") or {}
    url = str(ha.get("url") or "").strip().rstrip("/")
    token = str(ha.get("token") or "").strip()
    if not url or not token:
        return None
    return {"url": url, "token": token}


def get_states(use_cache: bool = True) -> list[dict[str, Any]]:
    """Fetch all entity states from HA. Cache respects configurable TTL."""
    global _state_cache, _state_cache_ts
    ttl = _get_cache_ttl()
    now = time.time()
    if use_cache and _state_cache and (now - _state_cache_ts) < ttl:
        return _state_cache
    cfg = _get_ha_config()
    if not cfg:
        return []
    try:
        req = urllib.request.Request(
            f"{cfg['url']}/api/states",
            headers={"Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/json"},
        )
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        with _state_cache_lock:
            _state_cache = data
            _state_cache_ts = now
        return data
    except Exception as exc:
        logger.warning({"event": "ha_states_failed", "error": str(exc)})
        return _state_cache or []  # return stale cache on error


def get_state(entity_id: str) -> dict[str, Any] | None:
    """Fetch a single entity's state."""
    cfg = _get_ha_config()
    if not cfg:
        return None
    try:
        req = urllib.request.Request(
            f"{cfg['url']}/api/states/{entity_id}",
            headers={"Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/json"},
        )
        return json.loads(urllib.request.urlopen(req, timeout=10).read())
    except Exception as exc:
        logger.debug({"event": "ha_state_failed", "entity": entity_id, "error": str(exc)})
        return None


def call_service(domain: str, service: str, data: dict[str, Any] | None = None) -> bool:
    """Call an HA service (e.g., light.turn_on). Passes full data dict as payload."""
    cfg = _get_ha_config()
    if not cfg:
        return False
    try:
        payload = data or {}
        body = json.dumps(payload)
        req = urllib.request.Request(
            f"{cfg['url']}/api/services/{domain}/{service}",
            data=body.encode(),
            headers={"Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
        # Invalidate cache after any write operation
        global _state_cache_ts
        _state_cache_ts = 0.0
        return True
    except Exception as exc:
        logger.warning({"event": "ha_service_failed", "domain": domain, "service": service, "error": str(exc)})
        return False


# All domains shown to AI — users interact by friendly_name, not entity_id
# Limit per domain keeps token count reasonable even for large setups
_CONTEXT_DOMAINS = [
    "light", "switch", "climate", "cover", "lock", "fan", "media_player",
    "sensor", "binary_sensor", "input_boolean", "input_number", "input_select",
    "scene", "script", "automation", "vacuum", "camera",
]
# Max entities per domain shown in context (keep token count low)
_MAX_PER_DOMAIN = 20


def format_states_context() -> str:
    """Format HA entities as compact summary — cached until TTL expires.

    First call fetches all states once and pre-computes the context string.
    Subsequent calls within TTL return cached string instantly (no processing).
    """
    global _context_cache, _context_cache_ts
    ttl = _get_cache_ttl()
    now = time.time()
    if _context_cache and (now - _context_cache_ts) < ttl:
        return _context_cache

    states = get_states(use_cache=False)  # Force fresh fetch
    if not states:
        return ""

    by_domain: dict[str, list[dict]] = {}
    for s in states:
        eid = s.get("entity_id", "")
        domain = eid.split(".")[0] if "." in eid else ""
        if domain in _CONTEXT_DOMAINS:
            by_domain.setdefault(domain, []).append(s)

    if not by_domain:
        return ""

    actionable_domains = {"light", "switch", "climate", "cover", "lock", "fan", "media_player"}
    lines = [
        "## Smart Home — Live State",
        f"Tổng: {len(states)} thiết bị. Dùng `ha_search_entities` để tìm theo tên.",
        f"Dữ liệu cập nhật mỗi {ttl}s. Các thiết bị điều khiển:",
        "",
    ]

    for domain in _CONTEXT_DOMAINS:
        entities = by_domain.get(domain)
        if not entities:
            continue
        if domain in actionable_domains:
            shown = entities[:_MAX_PER_DOMAIN]
            lines.append(f"[{domain}] ({len(entities)} total)")
            for s in shown:
                eid = s.get("entity_id", "")
                state = s.get("state", "")
                name = s.get("attributes", {}).get("friendly_name", "")
                label = f"{name} ({eid})" if name else eid
                lines.append(f"  {label}: {state}")
        else:
            names = []
            for s in entities[:_MAX_PER_DOMAIN]:
                name = s.get("attributes", {}).get("friendly_name", "")
                if name:
                    names.append(name)
            preview = ", ".join(names[:10])
            lines.append(f"[{domain}] ({len(entities)}): {preview}...")

    lines.append("")
    lines.append("Dùng `ha_search_entities` để tìm thiết bị KHÔNG có trong danh sách trên.")

    _context_cache = "\n".join(lines)
    _context_cache_ts = now
    return _context_cache

    return "\n".join(lines)


# Smart home keywords for detecting HA-relevant queries
_HA_KEYWORDS = (
    "đèn", "quạt", "máy lạnh", "điều hòa", "cửa", "khóa", "rèm",
    "bật", "tắt", "mở", "đóng", "trạng thái", "nhiệt độ", "độ ẩm",
    "cảm biến", "công tắc", "ổ cắm", "thiết bị", "nhà",
    "phòng", "bếp", "tắm", "ngủ", "khách", "ban công",
    "light", "switch", "sensor", "climate", "cover", "lock",
)


def _is_ha_query(messages: list[dict[str, Any]]) -> bool:
    """Heuristic: is the last user message asking about smart home devices?"""
    for m in reversed(messages):
        if m.get("role") == "user":
            text = str(m.get("content") or "").lower()
            return any(kw in text for kw in _HA_KEYWORDS)
    return False


def inject_ha_context(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inject HA entity registry as a system message — only for HA-related queries."""
    if not _is_ha_query(messages):
        return messages

    ctx = format_states_context()
    if not ctx:
        return messages

    result = list(messages)
    insert_pos = len(result)
    for i in range(len(result) - 1, -1, -1):
        if result[i].get("role") == "user":
            insert_pos = i
            break
    result.insert(insert_pos, {"role": "system", "content": ctx})
    logger.info({"event": "ha_context_injected", "chars": len(ctx)})
    return result


def get_ha_tools() -> list[dict[str, Any]]:
    """Return OpenAI-format tools for HA control (get state, call service)."""
    cfg = _get_ha_config()
    if not cfg:
        return []
    return [
        {
            "type": "function",
            "function": {
                "name": "ha_get_state",
                "description": "Lấy trạng thái 1 thiết bị Home Assistant theo entity_id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Entity ID (vd: light.ban_cong, sensor.nhiet_do)"}
                    },
                    "required": ["entity_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ha_search_entities",
                "description": "Tìm kiếm entity_id của thiết bị Home Assistant dựa vào tên hoặc từ khóa (vd: 'đèn', 'phòng ngủ', 'nhiệt độ'). Rất hữu ích khi không biết chính xác entity_id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Từ khóa tìm kiếm (vd: đèn ban công)"}
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ha_call_service",
                "description": "Gọi Home Assistant service để điều khiển thiết bị (bật/tắt đèn, khóa cửa, v.v.)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "domain": {"type": "string", "description": "Domain: light, switch, lock, climate, cover..."},
                        "service": {"type": "string", "description": "Service: turn_on, turn_off, toggle, lock, unlock..."},
                        "entity_id": {"type": "string", "description": "Entity ID đầy đủ (vd: light.ban_cong)"},
                    },
                    "required": ["domain", "service", "entity_id"],
                },
            },
        },
    ]


def execute_ha_tool(tool_name: str, arguments: dict[str, Any]) -> str | None:
    """Execute an HA tool and return result text."""
    if tool_name == "ha_get_state":
        eid = arguments.get("entity_id", "")
        state = get_state(eid)
        if state is None:
            return f"Không tìm thấy thiết bị '{eid}'"
        return json.dumps(state, ensure_ascii=False, indent=2)
    elif tool_name == "ha_search_entities":
        query = arguments.get("query", "").lower()
        states = get_states()
        matches = []
        for s in states:
            eid = s.get("entity_id", "").lower()
            name = s.get("attributes", {}).get("friendly_name", "").lower()
            if query in eid or query in name:
                matches.append(f"- {s.get('attributes', {}).get('friendly_name', '')} ({s.get('entity_id', '')}): {s.get('state', '')}")
        if not matches:
            return f"Không tìm thấy thiết bị nào khớp với '{query}'"
        return f"Các thiết bị tìm thấy (từ khóa '{query}'):\n" + "\n".join(matches[:20])
    elif tool_name == "ha_call_service":
        domain = arguments.get("domain", "")
        service = arguments.get("service", "")
        entity_id = arguments.get("entity_id", "")
        ok = call_service(domain, service, {"entity_id": entity_id})
        return f"Đã gọi {domain}.{service} cho {entity_id}" if ok else f"Lỗi gọi {domain}.{service}"
    return None
