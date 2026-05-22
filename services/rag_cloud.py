"""Cloudflare R2 storage for RAG collections — online backup + n8n access.

R2 is S3-compatible, 10 GB free, no egress fees. This module uploads/downloads
ChromaDB collection data as JSON snapshot files that n8n and other HTTP clients
can read directly (no Python/chromadb required on the reading side).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path("/app/data")


def _get_r2_config() -> dict[str, str] | None:
    """Read R2 credentials from vn-mcp-hub's local config (data/studio/r2.json)."""
    try:
        import json
        r2_file = Path("/app/data/studio/r2.json")
        if not r2_file.exists():
            return None
        r2 = json.loads(r2_file.read_text(encoding="utf-8"))
        endpoint = str(r2.get("endpoint") or "")
        access_key = str(r2.get("access_key_id") or "")
        secret_key = str(r2.get("secret_access_key") or "")
        bucket = str(r2.get("bucket") or "vn-mcp-hub-rag")
        if not endpoint or not access_key or not secret_key:
            return None
        return {"endpoint": endpoint.rstrip("/"), "access_key": access_key,
                "secret_key": secret_key, "bucket": bucket}
    except Exception:
        return None


def _s3_client():
    """Create boto3 S3 client for R2. Returns None if not configured."""
    cfg = _get_r2_config()
    if not cfg:
        return None, None
    try:
        import boto3
        client = boto3.client(
            "s3",
            endpoint_url=cfg["endpoint"],
            aws_access_key_id=cfg["access_key"],
            aws_secret_access_key=cfg["secret_key"],
        )
        return client, cfg["bucket"]
    except ImportError:
        logger.warning("boto3 not installed — R2 storage disabled")
        return None, None
    except Exception as exc:
        logger.warning("R2 client init failed: %s", exc)
        return None, None


def _collection_snapshot(collection: str) -> dict[str, Any]:
    """Build a JSON-serializable snapshot of a ChromaDB collection."""
    from src.rag.retriever import RAGRetriever
    retriever = RAGRetriever.get()
    if not retriever._ensure_loaded():
        return {"collection": collection, "error": "Chroma not loaded", "chunks": []}

    col = retriever._get_collection(collection)
    if col is None or col.count() == 0:
        return {"collection": collection, "chunks": [], "count": 0}

    try:
        data = col.get()
        chunks = []
        for i, doc in enumerate(data.get("documents") or []):
            meta = (data.get("metadatas") or [{}])[i] if i < len(data.get("metadatas") or []) else {}
            chunk_id = (data.get("ids") or [""])[i] if i < len(data.get("ids") or []) else ""
            chunks.append({"id": chunk_id, "text": doc, "source": meta.get("source", ""), "chunk": meta.get("chunk", i)})
        return {
            "collection": collection,
            "count": len(chunks),
            "chunks": chunks,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.warning("Snapshot %s failed: %s", collection, exc)
        return {"collection": collection, "error": str(exc), "chunks": []}


def upload_collection(collection: str) -> bool:
    """Upload one collection to R2 as JSON."""
    client, bucket = _s3_client()
    if not client or not bucket:
        return False
    snapshot = _collection_snapshot(collection)
    key = f"rag/{collection}.json"
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("R2: uploaded %s (%d chunks)", collection, snapshot.get("count", 0))
        return True
    except Exception as exc:
        logger.warning("R2 upload %s failed: %s", collection, exc)
        return False


def download_collection(collection: str) -> dict[str, Any] | None:
    """Download collection snapshot from R2. Returns None if not found."""
    client, bucket = _s3_client()
    if not client or not bucket:
        return None
    key = f"rag/{collection}.json"
    try:
        resp = client.get_object(Bucket=bucket, Key=key)
        return json.loads(resp["Body"].read().decode("utf-8"))
    except Exception as exc:
        logger.debug("R2 download %s: %s", collection, exc)
        return None


def upload_all() -> dict[str, int]:
    """Upload all collections to R2. Returns {collection: chunks}."""
    results: dict[str, int] = {}
    if not DATA_DIR.exists():
        return results
    for folder in sorted(DATA_DIR.iterdir()):
        if not folder.is_dir():
            continue
        meta = folder / "meta.json"
        if meta.exists():
            ok = upload_collection(folder.name)
            if ok:
                snapshot = _collection_snapshot(folder.name)
                results[folder.name] = snapshot.get("count", 0)
    return results


def restore_all_from_r2() -> int:
    """Download ALL collections from R2 and ingest into Chroma. Idempotent.

    Call this at startup after R2 is configured. Pulls the latest snapshot
    for every collection and upserts into the local Chroma DB.

    Returns total chunks restored.
    """
    client, bucket = _s3_client()
    if not client or not bucket:
        return 0

    from src.rag.ingest import chunk_text
    from src.rag.retriever import RAGRetriever
    from src.rag.meta import touch

    retriever = RAGRetriever.get()
    if not retriever._ensure_loaded():
        return 0

    total = 0
    try:
        # List all rag/*.json objects in R2
        resp = client.list_objects_v2(Bucket=bucket, Prefix="rag/")
        for obj in resp.get("Contents") or []:
            key = obj["Key"]
            collection = key.replace("rag/", "").replace(".json", "")
            if not collection:
                continue

            snapshot = download_collection(collection)
            if not snapshot:
                continue

            chunks = snapshot.get("chunks") or []
            if not chunks:
                continue

            col = retriever._client.get_or_create_collection(
                name=collection, embedding_function=retriever._embed_fn
            )
            ids = [c.get("id", f"r2_restore::{i}") for i, c in enumerate(chunks)]
            docs = [c.get("text", "") for c in chunks]
            metas = [{"source": c.get("source", "r2"), "chunk": c.get("chunk", i)} for i, c in enumerate(chunks)]

            batch = 100
            for i in range(0, len(docs), batch):
                col.upsert(ids=ids[i:i+batch], documents=docs[i:i+batch], metadatas=metas[i:i+batch])

            touch(collection, chunks=len(chunks), source="r2_restore")
            total += len(chunks)
            logger.info("R2: restored %s (%d chunks)", collection, len(chunks))
    except Exception as exc:
        logger.warning("R2 restore failed: %s", exc)

    return total


def get_public_url(collection: str) -> str:
    """Return the public URL for a collection JSON on R2."""
    cfg = _get_r2_config()
    if not cfg:
        return ""
    return f"{cfg['endpoint']}/{cfg['bucket']}/rag/{collection}.json"
