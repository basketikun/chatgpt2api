"""Cloudflare R2 storage for RAG collections — online backup + n8n access.

R2 is S3-compatible, 10 GB free, no egress fees. This module uploads/downloads
ChromaDB collection data as JSON snapshot files.

- Bước 5: Hỗ trợ 2-Way Sync (Merge dữ liệu local và remote trước khi lưu lên R2),
  giải quyết hoàn toàn xung đột khi có nhiều server cài chung MCP.
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


def download_collection(collection: str) -> dict[str, Any] | None:
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


def upload_collection(collection: str) -> bool:
    """Fallback: upload trực tiếp (ghi đè). Ưu tiên dùng sync_collection_2way() hơn."""
    from src.rag.settings import should_use_cloud
    if not should_use_cloud():
        return False
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


def sync_collection_2way(collection: str) -> bool:
    """2-Way Sync giữa Local ChromaDB và R2.
    - Lấy dữ liệu trên R2 xuống (nếu có).
    - Merge với dữ liệu Local hiện tại (qua ID để tránh trùng).
    - Đẩy bản merged hoàn chỉnh lên R2 (để server khác lấy).
    - Insert những chunk từ R2 (mà local chưa có) vào local ChromaDB.
    """
    from src.rag.settings import should_use_cloud
    from src.rag.retriever import RAGRetriever

    if not should_use_cloud():
        return False

    client, bucket = _s3_client()
    if not client or not bucket:
        return False

    logger.info("Starting 2-Way Sync for %s...", collection)
    
    # 1. Lấy snapshot remote (R2) và local
    remote_snap = download_collection(collection) or {}
    remote_chunks = remote_snap.get("chunks", [])
    
    local_snap = _collection_snapshot(collection)
    local_chunks = local_snap.get("chunks", [])

    # 2. Merge qua dictionary (key là chunk id)
    merged = {}
    
    # Ưu tiên đưa remote vào trước
    for c in remote_chunks:
        cid = c.get("id")
        if cid: merged[cid] = c
        
    # Đưa local vào sau (nếu trùng id thì đè lên - thường id sinh theo thời gian nên ít trùng)
    for c in local_chunks:
        cid = c.get("id")
        if cid: merged[cid] = c

    merged_chunks = list(merged.values())
    
    # 3. Tạo snapshot mới và upload lên R2
    merged_snapshot = {
        "collection": collection,
        "count": len(merged_chunks),
        "chunks": merged_chunks,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    
    key = f"rag/{collection}.json"
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(merged_snapshot, ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("R2: 2-Way Sync Uploaded %s (%d chunks)", collection, len(merged_chunks))
    except Exception as exc:
        logger.warning("R2 2-Way Sync Upload %s failed: %s", collection, exc)
        return False

    # 4. Ingest các chunk từ remote (nếu chưa có trong local)
    retriever = RAGRetriever.get()
    if not retriever._ensure_loaded():
        return True

    try:
        col = retriever._client.get_or_create_collection(
            name=collection, embedding_function=retriever._embed_fn
        )
        
        # Lọc ra các ID từ remote mà chưa có trong local
        local_ids = {c.get("id") for c in local_chunks}
        missing_in_local = [c for c in remote_chunks if c.get("id") not in local_ids]
        
        if missing_in_local:
            ids = [c["id"] for c in missing_in_local]
            docs = [c["text"] for c in missing_in_local]
            metas = [{"source": c.get("source", "r2_sync"), "chunk": c.get("chunk", 0)} for c in missing_in_local]
            
            batch = 100
            for i in range(0, len(docs), batch):
                col.upsert(ids=ids[i:i+batch], documents=docs[i:i+batch], metadatas=metas[i:i+batch])
                
            from src.rag.meta import touch
            touch(collection, chunks=len(missing_in_local), source="r2_sync")
            logger.info("R2: 2-Way Sync Downloaded %d missing chunks to Local DB", len(missing_in_local))
            
    except Exception as exc:
        logger.warning("R2 2-Way Sync Ingest %s failed: %s", collection, exc)

    return True


def upload_all() -> dict[str, int]:
    results: dict[str, int] = {}
    if not DATA_DIR.exists():
        return results
    for folder in sorted(DATA_DIR.iterdir()):
        if not folder.is_dir():
            continue
        meta = folder / "meta.json"
        if meta.exists():
            ok = sync_collection_2way(folder.name)
            if ok:
                snapshot = _collection_snapshot(folder.name)
                results[folder.name] = snapshot.get("count", 0)
    return results


def restore_all_from_r2() -> int:
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
        resp = client.list_objects_v2(Bucket=bucket, Prefix="rag/")
        for obj in resp.get("Contents") or []:
            key = obj["Key"]
            collection = key.replace("rag/", "").replace(".json", "")
            if not collection:
                continue

            # Sử dụng 2-way sync thay vì ghi đè!
            sync_collection_2way(collection)
            total += 1
            
    except Exception as exc:
        logger.warning("R2 restore failed: %s", exc)

    return total


def get_public_url(collection: str) -> str:
    cfg = _get_r2_config()
    if not cfg:
        return ""
    return f"{cfg['endpoint']}/{cfg['bucket']}/rag/{collection}.json"
