"""MCP Client — connects to MCP servers, fetches tools, proxies tool calls.

Used by the chat completion handler to inject MCP tools into LLM requests
and relay tool calls back to the MCP server.

Session management: each unique (url, api_key) pair gets one persistent
client that reuses the MCP session across requests.

Performance:
- Per-session circuit breaker: a failed init is remembered for 60s so we
  don't retry a dead MCP on every chat request (saves 15s × N every time).
- Module-level tools cache: `get_enabled_mcp_tools()` is called multiple
  times per chat (inject + tool-result loop). Cache the merged list for
  30s so we don't iterate 20+ servers on each call.
- Parallel discovery: tools/list across all enabled MCP servers runs in
  a thread pool, so total cold-start time is max(server) not sum(servers).
"""

from __future__ import annotations

import json, logging, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
import urllib.request
import urllib.error

from services.config import config
from utils.log import logger


# Per-call HTTP timeouts (seconds).
_INIT_TIMEOUT = 5      # initialize / tools/list — keep short so dead MCPs don't block chat
_NOTIFY_TIMEOUT = 2    # fire-and-forget notification
_TOOL_CALL_TIMEOUT = 30  # actual tool execution — user-visible work, allow longer

# Circuit breaker: after a failed init, skip this MCP for this long.
_FAILURE_COOLDOWN = 60.0

# After this many consecutive failures, lengthen the cooldown exponentially so
# permanently dead servers stop costing us a probe every minute.
_MAX_FAST_RETRIES = 3
_LONG_COOLDOWN = 1800.0  # 30 min


class MCPSession:
    """One connected MCP server session. Auto-reconnects on expiry."""

    def __init__(self, url: str, api_key: str = "") -> None:
        self.url = url
        self.api_key = api_key
        self.session_id: str | None = None
        self.server_name: str = ""
        self.tools: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._last_init = 0.0
        # Circuit breaker state
        self._last_failure = 0.0
        self._failure_count = 0

    def _call(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict | None:
        body = {"jsonrpc": "2.0", "id": "1", "method": method}
        if params:
            body["params"] = params
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=timeout if timeout is not None else _INIT_TIMEOUT)
            sid = resp.getheader("mcp-session-id")
            if sid:
                self.session_id = sid
            # Read response - FastMCP can return plain JSON or SSE
            raw = resp.read().decode('utf-8', errors='ignore')
            # Try SSE format first
            for line in raw.split("\n"):
                line = line.strip()
                if line.startswith("data: "):
                    try:
                        d = json.loads(line[6:])
                        if d.get("id") != "server-error":
                            return d
                    except json.JSONDecodeError:
                        pass
            # Try plain JSON format (FastMCP Streamable HTTP)
            try:
                d = json.loads(raw)
                if isinstance(d, dict) and d.get("id") != "server-error":
                    return d
            except json.JSONDecodeError:
                pass
        except urllib.error.HTTPError as e:
            sid = e.getheader("mcp-session-id")
            if sid:
                self.session_id = sid
            raw = e.read().decode()
            # Try SSE format
            for line in raw.split("\n"):
                line = line.strip()
                if line.startswith("data: "):
                    try:
                        return json.loads(line[6:])
                    except json.JSONDecodeError:
                        pass
            # Try plain JSON format
            try:
                d = json.loads(raw)
                if isinstance(d, dict):
                    return d
            except json.JSONDecodeError:
                pass
        except Exception as exc:
            logger.warning({"event": "mcp_call_failed", "url": self.url, "error": str(exc)})
        return None

    def _current_cooldown(self) -> float:
        """Cooldown grows after repeated failures so a permanently dead MCP
        only costs us a probe every 30 min instead of every minute."""
        if self._failure_count >= _MAX_FAST_RETRIES:
            return _LONG_COOLDOWN
        return _FAILURE_COOLDOWN

    def ensure_connected(self) -> bool:
        """Initialize session if not connected. Returns True on success.

        Circuit-breaker: if a previous init failed within the cooldown window,
        return False immediately so a single dead MCP can't add 15s × N to
        every chat request. Repeated failures lengthen the cooldown.
        """
        now = time.time()
        # Fast path check for session validity (5 min TTL)
        if self.session_id and (now - self._last_init) < 300:
            return True

        # Circuit breaker: don't retry a dead MCP within current cooldown
        if self._last_failure and (now - self._last_failure) < self._current_cooldown():
            return False

        with self._lock:
            now = time.time()
            if self.session_id and (now - self._last_init) < 300:
                return True
            if self._last_failure and (now - self._last_failure) < self._current_cooldown():
                return False

            init = self._call("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "chatgpt2api", "version": "1.0"},
            }, timeout=_INIT_TIMEOUT)
            if not init:
                self.session_id = None
                self._last_failure = now
                self._failure_count += 1
                return False

            # Send initialized notification (fire-and-forget, short timeout)
            try:
                self._call("notifications/initialized", timeout=_NOTIFY_TIMEOUT)
            except Exception:
                pass

            self.server_name = init.get("result", {}).get("serverInfo", {}).get("name", "")
            # Fetch tools
            tools_resp = self._call("tools/list", timeout=_INIT_TIMEOUT)
            if tools_resp:
                self.tools = tools_resp.get("result", {}).get("tools", [])
            self._last_init = now
            self._last_failure = 0.0
            self._failure_count = 0
            return True

    def get_tools(self) -> list[dict[str, Any]]:
        """Return OpenAI-format tools list for injection into chat completions."""
        if not self.ensure_connected():
            return []
        openai_tools: list[dict[str, Any]] = []
        for t in self.tools:
            name = t.get("name", "")
            desc = t.get("description", "")
            schema = t.get("inputSchema", {"type": "object", "properties": {}})
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": schema,
                },
            })
        return openai_tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str | None:
        """Call an MCP tool and return the text result."""
        if not self.ensure_connected():
            return None
        result = self._call("tools/call", {"name": name, "arguments": arguments}, timeout=_TOOL_CALL_TIMEOUT)
        if not result:
            return None
        content = result.get("result", {}).get("content", [])
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        return "\n".join(texts) if texts else json.dumps(content, ensure_ascii=False)


# ── Global session pool ─────────────────────────────────────────────────────

_sessions: dict[str, MCPSession] = {}
_sessions_lock = threading.Lock()

# Tools cache: shared across the request pipeline so we don't iterate 20+
# servers three times per chat completion. The tool schemas almost never
# change at runtime — bump to 15 min so the first request after the previous
# 5-min TTL doesn't pay a 2.5s re-discovery cost (visible in chat traces).
# A new MCP server appearing in config still triggers an immediate re-probe
# via invalidate_tools_cache().
_TOOLS_CACHE_TTL = 900.0
_tools_cache: list[dict[str, Any]] | None = None
_tools_cache_ts: float = 0.0
_tools_cache_signature: str = ""
_tools_cache_lock = threading.Lock()

# Concurrency for parallel MCP probing
_PROBE_WORKERS = 16


def _session_key(url: str, api_key: str) -> str:
    return f"{url}::{api_key[:8] if api_key else 'noauth'}"


def _enabled_signature(installed: list[dict]) -> str:
    """A short string that changes whenever the enabled-MCP set changes,
    so we invalidate the cache on config edits."""
    parts = []
    for info in installed:
        if not info.get("enabled", True):
            continue
        url = info.get("url", "") or ""
        if not url:
            continue
        api_key = str(info.get("api_key") or "")
        parts.append(f"{url}|{bool(api_key)}")
    return ";".join(sorted(parts))


def _collect_tools_one(info: dict) -> tuple[str, list[dict[str, Any]]]:
    """Worker: probe one MCP and return (name, tools)."""
    url = info.get("url", "")
    api_key = str(info.get("api_key") or "")
    if not url:
        return info.get("name", "unknown"), []
    key = _session_key(url, api_key)
    with _sessions_lock:
        if key not in _sessions:
            _sessions[key] = MCPSession(url, api_key)
        session = _sessions[key]
    try:
        return info.get("name", "unknown"), session.get_tools()
    except Exception as exc:
        logger.warning({"event": "mcp_session_failed", "name": info.get("name", "unknown"), "error": str(exc)})
        return info.get("name", "unknown"), []


def get_enabled_mcp_tools() -> list[dict[str, Any]]:
    """Collect OpenAI-format tools from all enabled MCP servers in config.

    Cached for _TOOLS_CACHE_TTL seconds and discovered in parallel across
    servers. A single dead MCP (circuit-broken) costs ~0ms; a healthy MCP
    only pays the one-time cold-start cost.
    """
    global _tools_cache, _tools_cache_ts, _tools_cache_signature

    installed = config.data.get("mcp_servers") or []
    if isinstance(installed, dict):
        installed = list(installed.values())
    if not isinstance(installed, list) or not installed:
        return []

    enabled = [i for i in installed if i.get("enabled", True) and i.get("url")]
    signature = _enabled_signature(enabled)
    now = time.time()

    # Fast path: cache hit
    if (
        _tools_cache is not None
        and signature == _tools_cache_signature
        and (now - _tools_cache_ts) < _TOOLS_CACHE_TTL
    ):
        return list(_tools_cache)

    with _tools_cache_lock:
        now = time.time()
        if (
            _tools_cache is not None
            and signature == _tools_cache_signature
            and (now - _tools_cache_ts) < _TOOLS_CACHE_TTL
        ):
            return list(_tools_cache)

        logger.info({
            "event": "mcp_debug_v2",
            "total": len(installed),
            "enabled_count": len(enabled),
            "urls": [i.get("url", "")[:60] for i in enabled[:3]],
        })

        # Probe all enabled MCPs in parallel.
        seen_names: set[str] = set()
        all_tools: list[dict[str, Any]] = []
        workers = min(_PROBE_WORKERS, max(1, len(enabled)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_collect_tools_one, info): info for info in enabled}
            for fut in as_completed(futures):
                info = futures[fut]
                try:
                    name, tools = fut.result()
                except Exception as exc:
                    logger.warning({"event": "mcp_session_failed", "name": info.get("name", "unknown"), "error": str(exc)})
                    continue
                for t in tools:
                    fname = t.get("function", {}).get("name", "")
                    if fname and fname not in seen_names:
                        seen_names.add(fname)
                        all_tools.append(t)
                logger.info({"event": "mcp_tools_loaded", "name": name, "count": len(tools)})

        _tools_cache = all_tools
        _tools_cache_ts = now
        _tools_cache_signature = signature
        return list(all_tools)


def invalidate_tools_cache() -> None:
    """Force `get_enabled_mcp_tools()` to re-probe on its next call.

    Call this after editing the MCP server list (install / uninstall / toggle).
    """
    global _tools_cache, _tools_cache_ts, _tools_cache_signature
    with _tools_cache_lock:
        _tools_cache = None
        _tools_cache_ts = 0.0
        _tools_cache_signature = ""


def prewarm_tools_cache() -> None:
    """Fire-and-forget background prewarm so the first chat request doesn't
    pay the cold-start probe cost. Safe to call multiple times.
    """
    def _run() -> None:
        try:
            get_enabled_mcp_tools()
        except Exception as exc:
            logger.warning({"event": "mcp_prewarm_failed", "error": str(exc)})
    threading.Thread(target=_run, daemon=True, name="mcp-prewarm").start()


def call_mcp_tool(tool_name: str, arguments: dict[str, Any], server_id: str = "") -> str | None:
    """Find which MCP session owns this tool and call it.

    Args:
        tool_name: Ten MCP tool can goi (vi du: 'search_web', 'get_news')
        arguments: Tham so truyen vao tool
        server_id: (Optional) ID cua MCP server cu the trong config (vi du: 'vn_search').
                   Neu cung cap, se goi thang server nay thay vi tim kiem toan bo.
    """
    installed = config.data.get("mcp_servers") or []
    if isinstance(installed, dict):
        installed = list(installed.values())
    if not isinstance(installed, list):
        return None

    def _try_call(info: dict) -> str | None:
        if not info.get("enabled", True):
            return None
        url = info.get("url", "")
        api_key = str(info.get("api_key") or "")
        if not url:
            return None
        key = _session_key(url, api_key)
        with _sessions_lock:
            if key not in _sessions:
                _sessions[key] = MCPSession(url, api_key)
            session = _sessions[key]
        if not session.ensure_connected():
            return None
        # Neu co server_id cu the: goi tool khong can kiem tra ten tool trong tool list
        # (vi IntentRouter da biet chinh xac tool nao dung cho server nay)
        if server_id:
            return session.call_tool(tool_name, arguments)
        # Khong co server_id: tim tool theo ten nhu cu
        for t in session.tools:
            if t.get("name") == tool_name:
                result = session.call_tool(tool_name, arguments)
                if result is not None:
                    return result
        return None

    # Neu co server_id: chi goi server do
    if server_id:
        for info in installed:
            # Match theo id field hoac theo url chua server_id
            info_id = str(info.get("id") or info.get("name", "")).lower()
            if info_id == server_id.lower() or server_id.lower() in info.get("url", "").lower():
                result = _try_call(info)
                if result is not None:
                    return result
        return None

    # Khong co server_id: duyet tat ca nhu cu
    for info in installed:
        result = _try_call(info)
        if result is not None:
            return result
    return None
