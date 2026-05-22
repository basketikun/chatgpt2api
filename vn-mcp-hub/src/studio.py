"""Studio — create and manage dynamic KB MCPs at runtime.

Adds a lightweight web UI at /studio so users can upload markdown files and
get a new RAG-backed MCP server without writing code or rebuilding the image.

Dynamic MCPs are persisted to data/studio/dynamic.json so they survive
container restarts (when data/ is a mounted volume).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from src.rag.hybrid import hybrid_query, format_hybrid_results
from src.rag.retriever import RAGRetriever

logger = logging.getLogger(__name__)

STUDIO_DIR = Path("/app/data/studio")
REGISTRY_FILE = STUDIO_DIR / "dynamic.json"

# ── Registry helpers ──────────────────────────────────────────────────────────


def _read_registry() -> list[dict[str, Any]]:
    if not REGISTRY_FILE.exists():
        return []
    try:
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_registry(entries: list[dict[str, Any]]) -> None:
    STUDIO_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── Collection management ────────────────────────────────────────────────────


def _ingest_kb(name: str) -> int:
    """Index studio/<name>/content.md into Chroma collection <name>."""
    from src.rag.ingest import chunk_text

    retriever = RAGRetriever.get()
    if not retriever._ensure_loaded():
        return 0

    content_file = STUDIO_DIR / name / "content.md"
    if not content_file.exists():
        return 0

    text = content_file.read_text(encoding="utf-8")
    chunks = chunk_text(text)
    if not chunks:
        return 0

    col = retriever._client.get_or_create_collection(
        name=name, embedding_function=retriever._embed_fn
    )
    ids = [f"{name}::{i}" for i in range(len(chunks))]
    metas = [{"source": f"studio/{name}/content.md", "chunk": i} for i in range(len(chunks))]

    batch = 100
    for i in range(0, len(chunks), batch):
        col.upsert(ids=ids[i:i + batch], documents=chunks[i:i + batch], metadatas=metas[i:i + batch])

    # Update metadata
    try:
        from src.rag.meta import touch
        touch(name, chunks=len(chunks), source="studio_ingest")
    except Exception:
        pass

    return len(chunks)


def _delete_collection(name: str) -> bool:
    import chromadb
    retriever = RAGRetriever.get()
    if not retriever._ensure_loaded():
        return False
    try:
        retriever._client.delete_collection(name)
        retriever._collections.pop(name, None)
        return True
    except Exception:
        return False


# ── Public API ────────────────────────────────────────────────────────────────


def list_dynamic_mcps() -> list[dict[str, Any]]:
    entries = _read_registry()
    for e in entries:
        stats = RAGRetriever.get().collection_stats(e["name"])
        e["chunks"] = stats.get("count", 0) if stats.get("available") else 0
    return entries


def create_kb(name: str, label: str, markdown_content: str) -> dict[str, Any]:
    errors: list[str] = []

    # Validate name
    name = name.strip().lower().replace(" ", "_")
    if not name or not name.replace("_", "").isalnum():
        errors.append("Tên chỉ được dùng chữ, số và gạch dưới")
    if len(name) > 30:
        errors.append("Tên tối đa 30 ký tự")
    if not label.strip():
        label = name
    if not markdown_content.strip():
        errors.append("Nội dung markdown trống")
    if errors:
        return {"ok": False, "errors": errors}

    # Check duplicate
    entries = _read_registry()
    if any(e["name"] == name for e in entries):
        return {"ok": False, "errors": [f"KB '{name}' đã tồn tại. Xóa trước khi tạo lại."]}

    # Save markdown
    kb_dir = STUDIO_DIR / name
    kb_dir.mkdir(parents=True, exist_ok=True)
    (kb_dir / "content.md").write_text(markdown_content, encoding="utf-8")

    # Ingest
    chunks = _ingest_kb(name)

    # Create meta.json with default settings
    from src.rag.meta import write_meta
    write_meta(name, {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "update_interval_hours": 720,
        "auto_update": False,
        "chunks_count": chunks,
        "sources": ["studio_ingest"],
    })

    # Trigger R2 sync (if configured)
    try:
        from src.rag.cloud import sync_collection_2way
        sync_collection_2way(name)
        logger.info("Studio: R2 synced new KB '%s'", name)
    except Exception as exc:
        logger.info("Studio: R2 sync skipped for '%s': %s", name, exc)

    # Register
    entry = {
        "name": name,
        "label": label.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "chunks": chunks,
    }
    entries.append(entry)
    _write_registry(entries)

    logger.info("Studio: created KB '%s' (%d chunks)", name, chunks)
    return {"ok": True, "name": name, "label": label.strip(), "chunks": chunks}


def delete_kb(name: str) -> dict[str, Any]:
    entries = _read_registry()
    filtered = [e for e in entries if e["name"] != name]
    if len(filtered) == len(entries):
        return {"ok": False, "error": f"KB '{name}' không tồn tại"}

    _write_registry(filtered)
    _delete_collection(name)

    # Remove files
    kb_dir = STUDIO_DIR / name
    if kb_dir.exists():
        import shutil
        shutil.rmtree(kb_dir, ignore_errors=True)

    logger.info("Studio: deleted KB '%s'", name)
    return {"ok": True, "name": name}


def make_dynamic_mcp(name: str, label: str) -> FastMCP:
    """Create a FastMCP instance for a dynamic KB."""
    mcp = FastMCP(name)

    def ask_fn(question: str, top_k: int = 4) -> str:
        top_k = max(1, min(8, top_k))
        results = hybrid_query(name, question, top_k=top_k)
        return format_hybrid_results(results)
    ask_fn.__name__ = f"ask_{name}"
    ask_fn.__doc__ = f"Hỏi đáp về {label}.\n\n    Trả về các đoạn tài liệu phù hợp từ kho {label}."
    mcp.tool()(ask_fn)

    def list_fn() -> str:
        content = STUDIO_DIR / name / "content.md"
        if not content.exists():
            return "Kho trống."
        lines = [f"**Chủ đề {label}:**", "", f"- {content.stem}"]
        return "\n".join(lines)
    list_fn.__name__ = f"list_topics_{name}"
    list_fn.__doc__ = f"Liệt kê chủ đề trong kho {label}."
    mcp.tool()(list_fn)

    def status_fn() -> str:
        stats = RAGRetriever.get().collection_stats(name)
        if not stats.get("available"):
            return "Collection chưa khởi tạo."
        return f"Collection '{name}' có {stats.get('count', 0)} chunks."
    status_fn.__name__ = f"get_status_{name}"
    status_fn.__doc__ = "Kiểm tra trạng thái Chroma collection."
    mcp.tool()(status_fn)

    return mcp


def load_dynamic_mcps() -> list[tuple[str, FastMCP]]:
    """Return list of (name, FastMCP) for all registered dynamic KBs."""
    entries = _read_registry()
    result: list[tuple[str, FastMCP]] = []
    for entry in entries:
        try:
            mcp = make_dynamic_mcp(entry["name"], entry.get("label", entry["name"]))
            result.append((entry["name"], mcp))
        except Exception as exc:
            logger.warning("Studio: failed to load dynamic MCP '%s': %s", entry.get("name"), exc)
    return result
