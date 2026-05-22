"""Federated search MCP — exposes multi-source search as a standalone tool.

Registered in MOUNTS so it appears in Studio UI with source toggles.
"""

from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP("federated_search")


@mcp.tool()
def search_all(query: str, limit_per_source: int = 3) -> str:
    """Tim kiem quoc te qua nhieu search engine cung luc.

    Args:
        query: Tu khoa tim kiem.
        limit_per_source: So ket qua toi da moi nguon (1-5, mac dinh 3).

    Returns:
        Ket qua tong hop tu nhieu nguon quoc te, nhom theo nguon.
    """
    from src.search.orchestrator import federated_search as _fs, format_federated_results as _fmt
    limit_per_source = max(1, min(5, limit_per_source))
    results = _fs(query, limit_per_source)
    return _fmt(results)


@mcp.tool()
def get_search_sources() -> str:
    """Liet ke cac nguon search quoc te dang duoc su dung."""
    from src.sources_config import get_mcp
    cfg = get_mcp("federated_search")
    lines = ["**Nguon search quoc te:**", ""]
    for src, enabled in sorted(cfg.items()):
        status = "ON" if enabled else "OFF"
        lines.append(f"- {src}: {status}")
    return "\n".join(lines)
