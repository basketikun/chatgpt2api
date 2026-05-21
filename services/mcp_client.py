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
            raw = resp.read().decode()
            for line in raw.split("\n"):
                if line.startswith("data: "):
                    d = json.loads(line[6:])
                    if d.get("id") != "server-error":
                        return d
        except urllib.error.HTTPError as e:
            sid = e.getheader("mcp-session-id")
            if sid:
                self.session_id = sid
            raw = e.read().decode()
            for line in raw.split("\n"):
                if line.startswith("data: "):
                    return json.loads(line[6:])
        except Exception as exc:
            logger.warning({"event": "mcp_call_failed", "url": self.url, "error": str(exc)})
        return None

    def ensure_connected(self) -> bool:
        """Initialize session if not connected. Returns True on success."""
        now = time.time()
        if self.session_id and (now - self._last_init) < 300:
            return True
        with self._lock:
            if self.session_id and (now - self._last_init) < 300:
                return True
            init = self._call("initialize", {
                "protocolVersion": "0.1.0",
                "capabilities": {},
                "clientInfo": {"name": "chatgpt2api", "version": "1.0"},
            })
            if not init:
                self.session_id = None
                return False
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
        installed = installed.values()
    if not isinstance(installed, list):
        return []

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


def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> str | None:
    """Find which MCP session owns this tool and call it."""
    installed = config.data.get("mcp_servers") or []
    if isinstance(installed, dict):
        installed = installed.values()
    if not isinstance(installed, list):
        return None
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
        # Check if this session has the tool
        if not session.ensure_connected():
            continue
        for t in session.tools:
            if t.get("name") == tool_name:
                result = session.call_tool(tool_name, arguments)
                if result is not None:
                    return result
    return None
