"""RAG retriever — query Chroma vector DB for kb_* MCPs.

Each knowledge base lives in its own Chroma collection (e.g. "dien_nuoc").
The retriever loads a single embedding model once and reuses it across all
collections. First query against a collection opens it lazily.

Uses fastembed (ONNX runtime, ~200MB) instead of sentence-transformers
(torch, ~3GB) to keep the Docker image under 5GB.

Designed to fail soft: if Chroma can't initialise (missing model, missing
data dir), `query()` returns an empty list instead of raising — the kb_*
MCPs surface a friendly error to the LLM rather than crashing the hub.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# All collections share one persist dir; ingest.py writes here too.
CHROMA_DB_PATH = Path("/app/chroma_db")

# Light, multilingual model — good enough for VN + EN technical content.
# fastembed downloads this to its cache on first use (~120MB).
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Default top-k chunks returned per query. Tuned to fit ~2000 tokens.
DEFAULT_TOP_K = 4


class _FastEmbedFn:
    """Custom ChromaDB embedding function backed by fastembed (ONNX, no torch)."""

    def __init__(self, model_name: str = EMBED_MODEL) -> None:
        self._model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self._model_name)

    def __call__(self, input: list[str]) -> list[list[float]]:
        self._load()
        return [e.tolist() for e in self._model.embed(input)]

    def embed_documents(self, *args, **kwargs) -> list[list[float]]:
        """ChromaDB v0.5+ batch embedding. Handles various call signatures."""
        docs = args[0] if args else kwargs.get("texts", kwargs.get("input", []))
        if isinstance(docs, str):
            docs = [docs]
        self._load()
        try:
            return [e.tolist() for e in self._model.embed(docs)]
        except Exception:
            return [e.tolist() for e in self._model.embed(list(docs))]

    def embed_query(self, *args, **kwargs) -> list[list[float]]:
        """ChromaDB v0.5+ single-query embedding. Returns List[List[float]]."""
        query_text = ""
        if args:
            q = args[0]
            if isinstance(q, list) and q:
                query_text = str(q[0])
            elif isinstance(q, str):
                query_text = q
        if not query_text:
            query_text = str(kwargs.get("text", "") or kwargs.get("input", "") or "")
            if isinstance(query_text, list):
                query_text = str(query_text[0]) if query_text else ""
        if not query_text:
            return [[0.0] * 384]
        self._load()
        result = list(self._model.embed([query_text]))
        return [result[0].tolist()] if result else [[0.0] * 384]

    def name(self) -> str:
        return self._model_name


class RAGRetriever:
    """Singleton-ish retriever shared by all kb_* MCPs.

    Lazy: doesn't load the embedding model until the first query, so the
    hub starts fast even if RAG is never used.
    """

    _instance: "RAGRetriever | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._client = None
        self._embed_fn = None
        self._collections: dict[str, Any] = {}

    @classmethod
    def get(cls) -> "RAGRetriever":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _ensure_loaded(self) -> bool:
        """Load Chroma client + embedding model on first use. Returns False on failure."""
        if self._client is not None:
            return True
        try:
            import chromadb

            self._client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
            self._embed_fn = _FastEmbedFn(EMBED_MODEL)
            logger.info("RAG: chroma + fastembed loaded from %s", CHROMA_DB_PATH)
            return True
        except Exception as exc:
            logger.error("RAG: failed to load chroma/embeddings: %s", exc)
            return False

    def _get_collection(self, name: str):
        if name in self._collections:
            return self._collections[name]
        if not self._ensure_loaded():
            return None
        try:
            col = self._client.get_or_create_collection(
                name=name,
                embedding_function=self._embed_fn,
            )
            self._collections[name] = col
            return col
        except Exception as exc:
            logger.error("RAG: get_or_create_collection(%s) failed: %s", name, exc)
            return None

    def query(self, collection: str, text: str, top_k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
        """Return top-k matching chunks as a list of {text, source, score}."""
        col = self._get_collection(collection)
        if col is None:
            return []
        try:
            res = col.query(query_texts=[text], n_results=top_k)
        except Exception as exc:
            logger.warning("RAG: query(%s) failed: %s", collection, exc)
            return []

        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        logger.info("RAG query(%s): '%s' -> %d docs, distances=%s",
                    collection, text[:50], len(docs),
                    [round(d, 3) if d else None for d in dists[:3]] if dists else [])
        out: list[dict[str, Any]] = []
        for i, doc in enumerate(docs):
            meta = metas[i] if i < len(metas) else {}
            dist = dists[i] if i < len(dists) else None
            out.append({
                "text": doc,
                "source": (meta or {}).get("source", "unknown"),
                "score": 1.0 - float(dist) if dist is not None else None,
            })
        return out

    def collection_stats(self, collection: str) -> dict[str, Any]:
        """Useful for admin/debug — returns document count, etc."""
        col = self._get_collection(collection)
        if col is None:
            return {"available": False}
        try:
            count = col.count()
        except Exception:
            count = -1
        return {"available": True, "count": count}


def query(collection: str, text: str, top_k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
    """Module-level shortcut so kb_* MCPs can `from src.rag.retriever import query`."""
    return RAGRetriever.get().query(collection, text, top_k)


def format_results(results: list[dict[str, Any]]) -> str:
    """Convert hits into a markdown block ready to feed back to the LLM."""
    if not results:
        return "Không tìm thấy thông tin liên quan trong kho tri thức."
    lines = []
    for i, r in enumerate(results, 1):
        src = r.get("source") or "unknown"
        text = (r.get("text") or "").strip()
        if len(text) > 1500:
            text = text[:1500] + "…"
        lines.append(f"## Kết quả {i} — nguồn: `{src}`\n\n{text}")
    return "\n\n---\n\n".join(lines)
