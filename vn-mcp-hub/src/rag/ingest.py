"""Ingest markdown files into Chroma collections.

Run inside the container before first use of kb_* MCPs:
    docker exec vn-mcp-hub python -m src.rag.ingest

Walks `data/<collection_name>/*.md`, splits each file into ~800-char chunks
with 100-char overlap, embeds them, writes to Chroma. Idempotent: re-running
upserts by deterministic ID `<source>::<chunk_index>`.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rag.ingest")

DATA_DIR = Path("/app/data")
CHROMA_DB_PATH = Path("/app/chroma_db")
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

# Collections that should be ingested. Names match `data/<name>/` folders.
COLLECTIONS = ["dien_nuoc", "y_te", "giao_duc", "ngoai_ngu", "khoa_hoc", "tu_nhien", "xa_hoi"]


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks, preferring to break at paragraph boundaries."""
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) + 2 <= size:
            buf = f"{buf}\n\n{para}" if buf else para
            continue
        if buf:
            chunks.append(buf)
        if len(para) > size:
            # Single paragraph too big: hard split.
            for i in range(0, len(para), size - overlap):
                chunks.append(para[i:i + size])
            buf = ""
        else:
            buf = para
    if buf:
        chunks.append(buf)
    return chunks


def ingest_collection(client, embed_fn, name: str) -> int:
    """Process data/<name>/*.md → upsert chunks into the named collection."""
    folder = DATA_DIR / name
    if not folder.exists():
        logger.warning("Skipping %s: folder %s does not exist", name, folder)
        return 0

    md_files = sorted(folder.glob("*.md"))
    if not md_files:
        logger.warning("Skipping %s: no .md files in %s", name, folder)
        return 0

    collection = client.get_or_create_collection(name=name, embedding_function=embed_fn)

    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []

    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        for i, chunk in enumerate(chunk_text(text)):
            ids.append(f"{md_file.name}::{i}")
            docs.append(chunk)
            metas.append({"source": md_file.name, "chunk": i})

    if not docs:
        logger.warning("No chunks produced for collection %s", name)
        return 0

    # Upsert in small batches to avoid hitting Chroma's batch limits.
    batch = 100
    for i in range(0, len(docs), batch):
        collection.upsert(
            ids=ids[i:i + batch],
            documents=docs[i:i + batch],
            metadatas=metas[i:i + batch],
        )
    logger.info("Ingested %d chunks from %d files into %s", len(docs), len(md_files), name)
    # Update collection metadata timestamp
    try:
        from src.rag.meta import touch
        touch(name, chunks=len(docs), source=f"seed/{md_files[0].name}" if len(md_files) == 1 else "seed")
    except Exception:
        pass
    return len(docs)


def main() -> int:
    try:
        import chromadb
    except ImportError as exc:
        logger.error("chromadb not installed: %s", exc)
        return 1

    from src.rag.retriever import _FastEmbedFn

    CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    embed_fn = _FastEmbedFn(EMBED_MODEL)

    total = 0
    for name in COLLECTIONS:
        total += ingest_collection(client, embed_fn, name)

    logger.info("Done. Total chunks ingested: %d", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
