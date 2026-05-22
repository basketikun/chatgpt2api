"""MCP Validator — test an MCP server URL before adding it to the hub.

Calls initialize + tools/list to verify the server works and returns
tool descriptions so the user knows what the MCP can do.
"""

from __future__ import annotations

import json, logging
from typing import Any
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


def validate_mcp(url: str, api_key: str = "") -> dict[str, Any]:
    """Test an MCP server URL. Returns validation result.

    Returns:
        {ok, name, version, tools_count, tools[], errors[]}
        tools: [{name, description}]
    """
    errors: list[str] = []
    tools: list[dict[str, str]] = []
    name = ""
    version = ""

    session_id = None

    def _call(method: str, params: dict | None = None) -> dict | None:
        nonlocal session_id
        body = {"jsonrpc": "2.0", "id": "1", "method": method}
        if params:
            body["params"] = params
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if session_id:
            headers["mcp-session-id"] = session_id
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            sid = resp.getheader("mcp-session-id")
            if sid:
                session_id = sid
            raw = resp.read().decode()
            for line in raw.split("\n"):
                if line.startswith("data: "):
                    d = json.loads(line[6:])
                    if d.get("id") != "server-error":
                        return d
        except urllib.error.HTTPError as e:
            sid = e.getheader("mcp-session-id")
            if sid:
                session_id = sid
            raw = e.read().decode()
            for line in raw.split("\n"):
                if line.startswith("data: "):
                    d = json.loads(line[6:])
                    return d
            errors.append(f"HTTP {e.code}: {raw[:200]}")
        except Exception as e:
            errors.append(f"Connection error: {e}")
        return None

    # Step 1: Initialize
    init = _call("initialize", {
        "protocolVersion": "0.1.0",
        "capabilities": {},
        "clientInfo": {"name": "vn-mcp-hub-validator", "version": "1.0"},
    })
    if not init:
        return {"ok": False, "errors": errors or ["Could not initialize MCP server"], "tools": []}

    result = init.get("result", {})
    name = result.get("serverInfo", {}).get("name", "")
    version = result.get("serverInfo", {}).get("version", "")
    if not name:
        name = url.rstrip("/").split("/")[-2] or "unknown"

    # Step 2: List tools
    tools_resp = _call("tools/list")
    if tools_resp:
        for t in tools_resp.get("result", {}).get("tools", []):
            tools.append({
                "name": t.get("name", ""),
                "description": (t.get("description") or "")[:200],
            })

    return {
        "ok": True,
        "name": name,
        "version": version,
        "tools_count": len(tools),
        "tools": tools,
        "errors": errors,
    }
