"""kb_ngoai_ngu — kho tri thức ngoại ngữ

RAG-backed: Chroma collection 'ngoai_ngu'.
Hybrid: KB offline + live search khi cần dữ liệu hiện tại.
"""

from __future__ import annotations

from fastmcp import FastMCP
from src.rag.retriever import RAGRetriever
from src.kb.hybrid_search import kb_ask

mcp = FastMCP("kb_ngoai_ngu")
COLLECTION = "ngoai_ngu"


@mcp.tool()
def ask_ngoai_ngu(question: str, top_k: int = 4) -> str:
    """Hỏi đáp về ngoại ngữ, ngữ pháp, từ điển, luyện thi.

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
    """Liệt kê chủ đề trong kho ngoai_ngu."""
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
    """Kiểm tra Chroma collection ngoai_ngu."""
    stats = RAGRetriever.get().collection_stats(COLLECTION)
    if not stats.get("available"):
        return "Collection chua khoi tao."
    count = stats.get("count", 0)
    if count == 0:
        return "Collection rong."
    return f"Collection '{COLLECTION}' co {count} chunks."
