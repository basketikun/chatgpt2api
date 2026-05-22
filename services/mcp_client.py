"""MCP Client — connects to MCP servers, fetches tools, proxies tool calls.

Used by the chat completion handler to inject MCP tools into LLM requests
and relay tool calls back to the MCP server.

Session management: each unique (url, api_key) pair gets one persistent
client that reuses the MCP session across requests.
"""

from __future__ import annotations

import json, logging, threading, time
from typing import Any
import urllib.request
import urllib.error

from services.config import config
from utils.log import logger


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

    def _call(self, method: str, params: dict | None = None) -> dict | None:
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
            resp = urllib.request.urlopen(req, timeout=15)
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

    def ensure_connected(self) -> bool:
        """Initialize session if not connected. Returns True on success."""
        now = time.time()
        # Fast path check for session validity (5 min TTL)
        if self.session_id and (now - self._last_init) < 300:
            return True

        with self._lock:
            if self.session_id and (now - self._last_init) < 300:
                return True

            init = self._call("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "chatgpt2api", "version": "1.0"},
            })
            if not init:
                self.session_id = None
                return False

            # Send initialized notification (required by MCP spec)
            self._call("notifications/initialized")

            self.server_name = init.get("result", {}).get("serverInfo", {}).get("name", "")
            # Fetch tools
            tools_resp = self._call("tools/list")
            if tools_resp:
                self.tools = tools_resp.get("result", {}).get("tools", [])
            self._last_init = now
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
        result = self._call("tools/call", {"name": name, "arguments": arguments})
        if not result:
            return None
        content = result.get("result", {}).get("content", [])
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        return "\n".join(texts) if texts else json.dumps(content, ensure_ascii=False)


# ── Global session pool ─────────────────────────────────────────────────────

_sessions: dict[str, MCPSession] = {}
_sessions_lock = threading.Lock()


def _session_key(url: str, api_key: str) -> str:
    return f"{url}::{api_key[:8] if api_key else 'noauth'}"


def get_enabled_mcp_tools() -> list[dict[str, Any]]:
    """Collect OpenAI-format tools from all enabled MCP servers in config."""
    installed = config.data.get("mcp_servers") or []
    if isinstance(installed, dict):
        installed = list(installed.values())
    if not isinstance(installed, list) or not installed:

    logger.info({"event": "mcp_debug_v2", "total": len(installed),
                 "enabled_count": sum(1 for i in installed if i.get("enabled", True)),
                 "urls": [i.get("url", "")[:60] for i in installed[:3]]})

    all_tools: list[dict[str, Any]] = []
    for info in installed:
        if not info.get("enabled", True):
            continue
        url = info.get("url", "")
        api_key = str(info.get("api_key") or "")
        if not url:
            continue
        key = _session_key(url, api_key)
        with _sessions_lock:
            if key not in _sessions:
                _sessions[key] = MCPSession(url, api_key)
            session = _sessions[key]
        try:
            tools = session.get_tools()
            all_tools.extend(tools)
            logger.info({"event": "mcp_tools_loaded", "name": info.get("name", "unknown"), "count": len(tools)})
        except Exception as exc:
            logger.warning({"event": "mcp_session_failed", "name": info.get("name", "unknown"), "error": str(exc)})
    return all_tools


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
