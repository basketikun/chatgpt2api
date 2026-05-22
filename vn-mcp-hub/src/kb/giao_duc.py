"""kb_giao_duc — kho tri thức giáo dục

RAG-backed: Chroma collection 'giao_duc'.
Hybrid: KB offline + live search khi cần dữ liệu hiện tại.
"""

from __future__ import annotations

from fastmcp import FastMCP
from src.rag.retriever import RAGRetriever
from src.kb.hybrid_search import kb_ask

mcp = FastMCP("kb_giao_duc")
COLLECTION = "giao_duc"


@mcp.tool()
def ask_giao_duc(question: str, top_k: int = 4) -> str:
    """Hỏi đáp về giáo dục, phương pháp học tập, chương trình học.

    Tự động bổ sung dữ liệu live nếu câu hỏi liên quan đến thông tin hiện tại.

    Args:
        question: Câu hỏi tiếng Việt.
        top_k: Số đoạn tài liệu liên quan trả về (1-8, mặc định 4).

    Returns:
        Thông tin từ kho tri thức, kết hợp dữ liệu live nếu cần thiết.
    """
    return kb_ask(COLLECTION, question, top_k=top_k)


@mcp.tool()
def list_topics() -> str:
    """Liệt kê chủ đề trong kho giao_duc."""
    from pathlib import Path
    folder = Path(f"/app/data/{COLLECTION}")
    if not folder.exists():
        return "Kho tri thức chưa được seed."
    files = sorted(folder.glob("*.md"))
    if not files:
        return "Kho tri thức rỗng."
    lines = ["**Chủ đề:**", ""]
    lines.extend(f"- {f.stem}" for f in files)
    return "\n".join(lines)


@mcp.tool()
def get_topic_status() -> str:
    """Kiểm tra Chroma collection giao_duc."""
    stats = RAGRetriever.get().collection_stats(COLLECTION)
    if not stats.get("available"):
        return "Collection chua khoi tao."
    count = stats.get("count", 0)
    if count == 0:
        return "Collection rong."
    return f"Collection '{COLLECTION}' co {count} chunks."
