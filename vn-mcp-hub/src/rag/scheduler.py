"""Background auto-update scheduler — periodically checks collections.

- Bước 4: Tự động refresh KB, dùng AI (ChatGPT) tổng hợp nội dung trước khi lưu.
- Bước 5: Sync R2 an toàn cho 2 server cài chung (Merge trước khi upload).

Performance note: each refresh issues an LLM synthesis call that takes
30-80 s through chatgpt2api's codex pool. With the previous defaults
(check every hour, no spacing) a single tick could fire 14 synthesis
calls back-to-back (7 collections × 2 queries) and saturate the codex
pool for ~10 minutes, making interactive HA / Telegram requests crawl.
We now:
  - check once a day (env override RAG_SCHEDULER_INTERVAL_SEC)
  - sleep RAG_REFRESH_COOLDOWN_SEC between consecutive synthesis calls
  - skip the loop entirely when RAG_SCHEDULER_DISABLED=1
"""

from __future__ import annotations

import logging
import os
import time
import threading
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


# How often the loop wakes up to check for stale collections. 24 h means
# each KB refreshes at most once a day — well within Wikipedia / law /
# news update cadence and easy on the codex pool.
CHECK_INTERVAL_SEC = _env_int("RAG_SCHEDULER_INTERVAL_SEC", 86400)
# Pause between two synthesis calls so a multi-collection refresh doesn't
# saturate chatgpt2api's codex slots.
REFRESH_COOLDOWN_SEC = _env_int("RAG_REFRESH_COOLDOWN_SEC", 60)
# Hard kill switch — set to 1 if you want to run refreshes only via the
# manual /api/rag/refresh/{collection} endpoint.
SCHEDULER_DISABLED = os.environ.get("RAG_SCHEDULER_DISABLED", "").lower() in {"1", "true", "yes"}

DEFAULT_REFRESH_QUERIES: dict[str, list[str]] = {
    "xa_hoi": [
        "luật việt nam mới nhất {year}",
        "chính sách kinh tế xã hội việt nam {year}",
    ],
    "dien_nuoc": [
        "tiêu chuẩn kỹ thuật điện nước việt nam {year}",
        "quy định an toàn điện việt nam {year}",
    ],
    "y_te": [
        "hướng dẫn y tế bộ y tế việt nam {year}",
        "phác đồ điều trị cập nhật {year}",
    ],
    "giao_duc": [
        "chương trình giáo dục phổ thông mới {year}",
        "chính sách tuyển sinh đại học {year}",
    ],
    "ngoai_ngu": [
        "chứng chỉ ngoại ngữ quốc tế cấu trúc mới {year}",
    ],
    "khoa_hoc": [
        "phát minh khoa học công nghệ mới {year}",
    ],
    "tu_nhien": [
        "biến đổi khí hậu thiên tai việt nam {year}",
        "bảo vệ môi trường sinh thái {year}",
    ],
}


def _get_refresh_queries(collection: str, meta: dict) -> list[str]:
    year = datetime.now(timezone.utc).year
    custom_queries = meta.get("refresh_queries")
    if isinstance(custom_queries, list) and custom_queries:
        return [q.format(year=year) for q in custom_queries]
    defaults = DEFAULT_REFRESH_QUERIES.get(collection)
    if defaults:
        return [q.format(year=year) for q in defaults]
    return [f"{collection} cập nhật mới nhất {year}"]


def _synthesize_with_ai(query: str, raw_text: str) -> str:
    """Gọi chatgpt2api (cổng 3030) để AI tổng hợp kiến thức từ kết quả search."""
    from src.rag.settings import read as read_settings
    settings = read_settings()
    api_key = settings.get("api_key", "AnhNhi@0610")
    ai_model = settings.get("ai_model", "cx/auto")
    base_url = settings.get("api_base_url", "http://chatgpt2api:3030/v1").rstrip("/")

    url = f"{base_url}/chat/completions"

    prompt = f"""Bạn là một chuyên gia tổng hợp tri thức (Knowledge Base).
Dựa vào các kết quả tìm kiếm web thô dưới đây, hãy tổng hợp thành một bài viết Markdown chi tiết, mạch lạc, có cấu trúc rõ ràng (dùng Heading 2, 3, bullet points).
Bài viết cần tập trung vào chủ đề: "{query}".

LOẠI BỎ các thông tin rác, quảng cáo, không liên quan.
CHỈ TRẢ VỀ nội dung bài viết, không thêm lời chào hỏi.

=== THÔNG TIN TÌM KIẾM THÔ ===
{raw_text}
"""

    payload = {
        "model": ai_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read().decode())
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if content:
            logger.info("AI synthesis OK: %d chars for query '%s'", len(content), query[:60])
        else:
            logger.warning("AI synthesis returned empty content for query '%s', response keys: %s",
                         query[:60], list(data.keys()))
        return content.strip()
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode()[:500]
        except Exception:
            pass
        logger.error("AI synthesis HTTP %d for '%s': %s", exc.code, query[:60], body)
        return ""
    except urllib.error.URLError as exc:
        logger.error("AI synthesis connection failed for '%s': %s", query[:60], exc.reason)
        return ""
    except Exception as exc:
        logger.error("AI synthesis unexpected error for '%s': %s (%s)", query[:60], exc, type(exc).__name__)
        return ""


def _run_refresh(collection: str, queries: list[str]) -> int:
    from src.rag.ingest import chunk_text
    from src.rag.retriever import RAGRetriever
    from src.search.orchestrator import federated_search

    retriever = RAGRetriever.get()
    if not retriever._ensure_loaded():
        return 0

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_chunks: list[str] = []

    for query in queries:
        try:
            results = federated_search(query, limit_per_source=3)
            if not results:
                continue

            raw_lines = []
            for r in results[:10]:
                title, snippet, url = r.get("title", ""), r.get("snippet", ""), r.get("url", "")
                if title or snippet:
                    raw_lines.append(f"Title: {title}\nSnippet: {snippet}\nURL: {url}\n---")
            
            raw_text = "\n".join(raw_lines)
            
            # ĐƯA QUA AI TỔNG HỢP!
            logger.info("AI is synthesizing knowledge for query: %s", query)
            synthesized = _synthesize_with_ai(query, raw_text)
            
            if not synthesized or len(synthesized) < 100:
                logger.warning("AI synthesis too short or failed, fallback to raw text")
                synthesized = f"# Cập nhật: {query}\n\n" + raw_text

            # Gắn metadata tiêu đề
            final_text = f"# AI Tổng hợp: {query} ({date_str})\n\n{synthesized}"
            chunks = chunk_text(final_text)
            all_chunks.extend(chunks)
            logger.info("Refresh %s query '%s': %d chunks generated", collection, query[:50], len(chunks))

        except Exception as exc:
            logger.warning("Refresh %s query failed: %s", collection, exc)

    if not all_chunks:
        return 0

    try:
        col = retriever._client.get_or_create_collection(
            name=collection, embedding_function=retriever._embed_fn
        )
        ts = datetime.now(timezone.utc).strftime("%H%M%S")
        ids = [f"auto_ai::{date_str}_{ts}::{i}" for i in range(len(all_chunks))]
        metas_list = [{"source": f"auto_ai/{date_str}", "chunk": i} for i in range(len(all_chunks))]

        batch = 100
        for i in range(0, len(all_chunks), batch):
            col.upsert(
                ids=ids[i:i + batch],
                documents=all_chunks[i:i + batch],
                metadatas=metas_list[i:i + batch],
            )
        return len(all_chunks)
    except Exception as exc:
        logger.warning("Refresh %s ingest failed: %s", collection, exc)
        return 0


def _scheduler_loop(stop_event: threading.Event) -> None:
    logger.info("AI Auto-update scheduler started (check every %ds)", CHECK_INTERVAL_SEC)
    
    # Chạy ngay lần đầu tiên khi khởi động
    try:
        _check_all_collections()
    except Exception as exc:
        logger.warning("Scheduler init check failed: %s", exc)

    tick = 0
    while not stop_event.wait(CHECK_INTERVAL_SEC):
        tick += 1
        try:
            _check_all_collections()
        except Exception as exc:
            logger.warning("Scheduler check failed: %s", exc)
            
        try:
            from src.rag.settings import get_sync_interval_minutes
            sync_ticks = max(1, (get_sync_interval_minutes() * 60) // CHECK_INTERVAL_SEC)
        except Exception:
            sync_ticks = 6
            
        if tick % sync_ticks == 0:
            try:
                from src.rag.cloud import restore_all_from_r2
                n = restore_all_from_r2()
                if n > 0:
                    logger.info("Scheduler: 2-Way Synced %d chunks from R2", n)
            except Exception as exc:
                logger.debug("R2 sync skipped: %s", exc)
    logger.info("Auto-update scheduler stopped")


def _check_all_collections() -> None:
    from src.rag.meta import read_meta, is_stale, touch
    from src.rag.settings import is_within_refresh_window, get_refresh_window
    from pathlib import Path

    data_dir = Path("/app/data")
    if not data_dir.exists():
        return

    # Honour the global "refresh allowed only between X-Y hours" setting.
    # When the user restricts heavy work to overnight (e.g. 0-5h) we
    # silently skip the cycle if it fires outside that window.
    if not is_within_refresh_window():
        start, end = get_refresh_window()
        logger.info("Scheduler skipped: outside refresh window %02d:00-%02d:00", start, end)
        return

    refreshed_any = False
    for folder in sorted(data_dir.iterdir()):
        if not folder.is_dir():
            continue
        meta = read_meta(folder.name)
        if not meta.get("auto_update"):
            continue
        stale, msg = is_stale(folder.name)
        if not stale:
            continue

        # Spread synthesis calls so we don't slam the codex pool. The
        # first stale collection of the cycle goes immediately; every one
        # after that waits REFRESH_COOLDOWN_SEC.
        if refreshed_any and REFRESH_COOLDOWN_SEC > 0:
            logger.info("Scheduler: cooldown %ds before next refresh", REFRESH_COOLDOWN_SEC)
            time.sleep(REFRESH_COOLDOWN_SEC)

        logger.info("Scheduler: %s is stale (%s), auto-refreshing with AI...", folder.name, msg)
        try:
            queries = _get_refresh_queries(folder.name, meta)
            total_chunks = _run_refresh(folder.name, queries)
            refreshed_any = True

            if total_chunks > 0:
                touch(folder.name, chunks=total_chunks, source=f"auto_ai/{datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
                logger.info("Scheduler: %s — refreshed %d chunks", folder.name, total_chunks)

                # TRIGGER R2 2-WAY SYNC NGAY LẬP TỨC
                try:
                    from src.rag.cloud import sync_collection_2way
                    sync_collection_2way(folder.name)
                    logger.info("Scheduler: %s — 2-Way Synced to R2", folder.name)
                except Exception as exc:
                    logger.warning("R2 sync failed after refresh: %s", exc)
            else:
                logger.info("Scheduler: %s — no new chunks", folder.name)

        except Exception as exc:
            logger.warning("Scheduler: %s auto-refresh failed: %s", folder.name, exc)


def start_scheduler() -> threading.Event:
    stop = threading.Event()
    if SCHEDULER_DISABLED:
        logger.info("RAG scheduler disabled via RAG_SCHEDULER_DISABLED env")
        return stop
    t = threading.Thread(target=_scheduler_loop, args=(stop,), daemon=True, name="rag-scheduler")
    t.start()
    return stop
