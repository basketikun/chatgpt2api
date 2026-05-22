"""kb_hybrid.py — Module dùng chung cho Bước 3: KB-then-search hybrid.

Logic:
1. Query ChromaDB KB offline (nhanh, không cần internet)
2. Phát hiện câu hỏi cần dữ liệu live (từ khoá: mới nhất, 2024, cập nhật...)
3. Nếu cần live → gọi federated_search + MCP search song song
4. Merge kết quả KB + live → trả về đầy đủ

Dùng:
    from src.kb.hybrid_search import kb_ask

    text = kb_ask("xa_hoi", "luật pccc 2024", top_k=4)
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

# Từ khoá gợi ý cần bổ sung dữ liệu live
_LIVE_SIGNALS = [
    "mới nhất", "hiện nay", "hiện tại",
    "2024", "2025", "2026",
    "cập nhật", "gần đây", "vừa", "mới ban hành",
    "sửa đổi", "bổ sung", "quy định mới", "thay đổi",
    "hôm nay", "tuần này", "tháng này",
]

# Map collection → search queries chuyên biệt để refresh KB
COLLECTION_REFRESH_QUERIES: dict[str, list[str]] = {
    "xa_hoi": [
        "luật việt nam mới nhất {year}",
        "chính sách kinh tế việt nam {year}",
        "văn hóa xã hội việt nam {year}",
    ],
    "dien_nuoc": [
        "tiêu chuẩn điện nước việt nam {year}",
        "quy định an toàn điện {year}",
        "giá điện nước {year}",
    ],
    "y_te": [
        "hướng dẫn y tế bộ y tế {year}",
        "phác đồ điều trị cập nhật {year}",
        "chính sách bảo hiểm y tế {year}",
    ],
    "giao_duc": [
        "chương trình giáo dục phổ thông mới {year}",
        "tuyển sinh đại học {year}",
        "chính sách giáo dục {year}",
    ],
    "ngoai_ngu": [
        "thi IELTS TOEIC {year}",
        "học tiếng anh online {year}",
    ],
    "khoa_hoc": [
        "nghiên cứu khoa học việt nam {year}",
        "phát minh khoa học mới {year}",
    ],
    "tu_nhien": [
        "biến đổi khí hậu việt nam {year}",
        "thiên tai lũ lụt {year}",
        "bảo tồn động vật hoang dã {year}",
    ],
}


def _needs_live(question: str) -> bool:
    """Phát hiện câu hỏi cần bổ sung dữ liệu live."""
    q = question.lower()
    return any(kw in q for kw in _LIVE_SIGNALS)


def _search_live(question: str, extra_query: str = "", limit: int = 3) -> str:
    """Gọi federated_search để lấy dữ liệu bổ sung.
    
    Args:
        question: Câu hỏi gốc
        extra_query: Query bổ sung (vd: tên collection + năm)
        limit: Số kết quả tối đa
    """
    try:
        from src.search.orchestrator import federated_search
        query = extra_query or question
        results = federated_search(query, limit_per_source=2)
        if not results:
            return ""
        lines = ["\n\n📡 **Thông tin bổ sung từ web:**", ""]
        for r in results[:limit]:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            if title or snippet:
                line = f"• **{title}**: {snippet[:300]}"
                if url:
                    line += f"\n  *(Nguồn: {url})*"
                lines.append(line)
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("live search failed: %s", exc)
        return ""


def kb_ask(
    collection: str,
    question: str,
    top_k: int = 4,
    format_fn: Callable | None = None,
) -> str:
    """Query KB offline, tự động bổ sung live search nếu cần.

    Args:
        collection: Tên ChromaDB collection (vd: 'xa_hoi', 'dien_nuoc')
        question: Câu hỏi tiếng Việt
        top_k: Số chunks KB trả về
        format_fn: Hàm format kết quả (mặc định dùng format_hybrid_results)

    Returns:
        Chuỗi kết quả KB, có thể kèm live data nếu phát hiện cần
    """
    from src.rag.hybrid import hybrid_query, format_hybrid_results
    from datetime import datetime, timezone

    top_k = max(1, min(8, top_k))

    # Bước 1: Query KB offline (luôn chạy)
    try:
        results = hybrid_query(collection, question, top_k=top_k)
        kb_text = format_fn(results) if format_fn else format_hybrid_results(results)
    except Exception as exc:
        logger.warning("KB query %s failed: %s", collection, exc)
        kb_text = f"[Kho tri thức {collection} chưa sẵn sàng]"

    # Bước 2: Phát hiện cần live data
    if _needs_live(question):
        current_year = datetime.now(timezone.utc).year
        # Ưu tiên query chuyên biệt của collection nếu có
        refresh_queries = COLLECTION_REFRESH_QUERIES.get(collection, [])
        if refresh_queries:
            # Tìm query phù hợp nhất với câu hỏi
            live_query = refresh_queries[0].format(year=current_year)
            # Nếu câu hỏi có từ khoá cụ thể → dùng câu hỏi gốc
            if len(question) > 10:
                live_query = f"{question} {current_year}"
        else:
            live_query = f"{question} {current_year}"

        live_text = _search_live(question, extra_query=live_query, limit=3)
        if live_text:
            return f"{kb_text}{live_text}"

    return kb_text
