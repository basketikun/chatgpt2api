"""Background auto-update scheduler — periodically checks collections.

Runs in a daemon thread started from the FastAPI lifespan. Every hour it
checks each collection's metadata. If auto_update is enabled and the data
is past its update interval, the scheduler triggers a federated search,
splits results into chunks, and ingests them into Chroma.
"""

from __future__ import annotations

import logging
import time
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SEC = 3600   # 1 hour between checks


def _scheduler_loop(stop_event: threading.Event) -> None:
    logger.info("Auto-update scheduler started (check every %ds)", CHECK_INTERVAL_SEC)
    tick = 0
    while not stop_event.wait(CHECK_INTERVAL_SEC):
        tick += 1
        try:
            _check_all_collections()
        except Exception as exc:
            logger.warning("Scheduler check failed: %s", exc)
        # Sync from R2 at configured interval (other instances may have updated)
        try:
            from src.rag.settings import get_sync_interval_minutes
            sync_interval = get_sync_interval_minutes()
            sync_ticks = max(1, (sync_interval * 60) // CHECK_INTERVAL_SEC)
        except Exception:
            sync_ticks = 6
        if tick % sync_ticks == 0:
            try:
                from src.rag.cloud import restore_all_from_r2
                n = restore_all_from_r2()
                if n > 0:
                    logger.info("Scheduler: synced %d chunks from R2", n)
            except Exception as exc:
                logger.debug("R2 sync skipped: %s", exc)
    logger.info("Auto-update scheduler stopped")


def _check_all_collections() -> None:
    from src.rag.meta import read_meta, is_stale, touch
    from src.rag.ingest import chunk_text
    from src.rag.retriever import RAGRetriever

    # Scan data/ for collections with meta.json
    from pathlib import Path
    data_dir = Path("/app/data")
    if not data_dir.exists():
        return

    for folder in sorted(data_dir.iterdir()):
        if not folder.is_dir():
            continue
        meta = read_meta(folder.name)
        if not meta.get("auto_update"):
            continue

        stale, msg = is_stale(folder.name)
        if not stale:
            continue

        logger.info("Scheduler: %s is stale (%s), auto-updating...", folder.name, msg)
        try:
            # Search for fresh content
            from src.search.orchestrator import federated_search as _fs
            query = f"{folder.name} cập nhật mới nhất {datetime.now(timezone.utc).strftime('%Y-%m')}"
            results = _fs(query, limit_per_source=3)
            if not results:
                logger.info("Scheduler: %s — no search results, skipping", folder.name)
                continue

            # Build a markdown document from search results
            lines = [f"# Auto-update: {folder.name} — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC\n"]
            for r in results[:10]:
                lines.append(f"## {r.get('title', '')}\n{r.get('snippet', '')}\n{r.get('url', '')}\n")
            text = "\n".join(lines)

            # Chunk and ingest
            chunks = chunk_text(text)
            if not chunks:
                continue

            retriever = RAGRetriever.get()
            if not retriever._ensure_loaded():
                continue

            col = retriever._client.get_or_create_collection(
                name=folder.name, embedding_function=retriever._embed_fn
            )
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            ids = [f"auto_update::{date_str}::{i}" for i in range(len(chunks))]
            docs = chunks
            metas = [{"source": f"auto_update/{date_str}", "chunk": i} for i in range(len(chunks))]

            batch = 100
            for i in range(0, len(chunks), batch):
                col.upsert(ids=ids[i:i + batch], documents=docs[i:i + batch], metadatas=metas[i:i + batch])

            touch(folder.name, chunks=len(chunks), source=f"auto_update/{date_str}")
            logger.info("Scheduler: %s — ingested %d chunks", folder.name, len(chunks))
            # Upload to R2 (non-blocking, best effort)
            try:
                from src.rag.cloud import upload_collection
                upload_collection(folder.name)
            except Exception:
                pass
        except Exception as exc:
            logger.warning("Scheduler: %s auto-update failed: %s", folder.name, exc)


def start_scheduler() -> threading.Event:
    """Start the background auto-update thread. Returns stop event."""
    stop = threading.Event()
    t = threading.Thread(target=_scheduler_loop, args=(stop,), daemon=True, name="rag-scheduler")
    t.start()
    return stop
