"""VN MCP Hub — entry point.

Mounts 16 custom MCP servers under one FastAPI app on port 8005.

Each MCP exposes its own JSON-RPC endpoint at /<name>/mcp using the
Streamable HTTP transport. chatgpt2api connects to these endpoints
exactly like any other public HTTP MCP.

URLs (replace <host> with your server IP and <port> with mapped host port):
- VN core:        http://<host>:<port>/vn_weather/mcp
                  http://<host>:<port>/vn_news/mcp
                  http://<host>:<port>/vn_currency/mcp
                  http://<host>:<port>/vn_lunar/mcp
- VN extended:    http://<host>:<port>/vn_search/mcp
                  http://<host>:<port>/vn_law/mcp
                  http://<host>:<port>/vn_phat_nguoi/mcp
                  http://<host>:<port>/vn_stock/mcp
- General:        http://<host>:<port>/youtube/mcp
                  http://<host>:<port>/wikipedia/mcp
                  http://<host>:<port>/arxiv/mcp
- Knowledge:      http://<host>:<port>/kb_dien_nuoc/mcp
                  http://<host>:<port>/kb_y_te/mcp
                  http://<host>:<port>/kb_giao_duc/mcp
                  http://<host>:<port>/kb_ngoai_ngu/mcp
- HA helper:      http://<host>:<port>/ha_helper/mcp
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager, AsyncExitStack
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vn-mcp-hub")


# MCP app instances collected during mount — their lifespans are entered
# in the parent FastAPI lifespan so FastMCP's session manager initializes.
_mcp_sub_apps: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting VN MCP Hub on port 8005")
    async with AsyncExitStack() as stack:
        for _mcp_app in _mcp_sub_apps:
            if hasattr(_mcp_app, "lifespan"):
                try:
                    await stack.enter_async_context(_mcp_app.lifespan(_mcp_app))
                except Exception:
                    pass
        # Auto-ingest synchronously before yielding
        if not os.environ.get("SKIP_AUTO_INGEST"):
            try:
                from src.rag import ingest
                ingest.main()
            except Exception as exc:
                logger.warning("Auto-ingest failed (non-fatal): %s", exc)
        # Restore RAG data from R2 (if configured) — pulls latest KB collections
        try:
            from src.rag.cloud import restore_all_from_r2
            restored = restore_all_from_r2()
            if restored > 0:
                logger.info("R2: restored %d chunks from cloud", restored)
        except Exception as exc:
            logger.warning("R2 restore failed (non-fatal): %s", exc)
        # Start background auto-update scheduler
        _scheduler_stop = None
        try:
            from src.rag.scheduler import start_scheduler
            _scheduler_stop = start_scheduler()
        except Exception as exc:
            logger.warning("Scheduler failed to start: %s", exc)
        yield
        if _scheduler_stop is not None:
            _scheduler_stop.set()
    logger.info("Shutting down VN MCP Hub")


def create_app() -> FastAPI:
    """Build the parent FastAPI app with all 16 MCPs mounted as sub-apps."""
    app = FastAPI(
        title="VN MCP Hub",
        version="0.1.0",
        description="16 custom MCP servers for Vietnamese chatgpt2api users",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def index():
        mcps = []
        for name, _ in MOUNTS:
            label, desc, *rest = MCP_LABELS.get(name, (name, "", ""))
            cat = rest[0] if rest else "general"
            mcps.append({"id": name, "label": label, "description": desc,
                         "category": cat, "url": f"/{name}/mcp"})
        return JSONResponse({
            "name": "VN MCP Hub",
            "version": "0.1.0",
            "mcps": [name for name, _ in MOUNTS],
            "mcp_details": mcps,
            "endpoint_pattern": "/<name>/mcp",
        })

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # ── Studio endpoints ────────────────────────────────────────────────
    from src.studio_html import STUDIO_HTML

    @app.get("/studio")
    async def studio_page():
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=STUDIO_HTML)

    @app.get("/api/studio/mcps")
    async def studio_list_mcps():
        try:
            from src.studio import list_dynamic_mcps as _ldm
            dynamic = _ldm()
        except Exception:
            dynamic = []
        all_mcps = []
        for name, _ in MOUNTS:
            all_mcps.append({"name": name, "builtin": True})
        for d in dynamic:
            all_mcps.append({**d, "builtin": False})
        return {"mcps": all_mcps}

    @app.post("/api/studio/kb")
    async def studio_create_kb(request: Request):
        try:
            body = await request.json()
            from src.studio import create_kb as _create
            return _create(
                name=str(body.get("name", "")),
                label=str(body.get("label", "")),
                markdown_content=str(body.get("content", "")),
            )
        except Exception as exc:
            return {"ok": False, "errors": [str(exc)]}

    @app.get("/api/studio/sources")
    async def studio_get_sources():
        """Return per-MCP source toggle config with help text."""
        from src.sources_config import get_all_with_help
        return {"sources": get_all_with_help()}

    @app.post("/api/studio/sources/{mcp_name}")
    async def studio_toggle_source(mcp_name: str, request: Request):
        """Toggle one source for a MCP. Body: {source_name: true/false}"""
        body = await request.json()
        from src.sources_config import set_source as _set
        for src, enabled in (body or {}).items():
            if isinstance(src, str) and isinstance(enabled, bool):
                return {"ok": True, "mcp": mcp_name, "sources": _set(mcp_name, src, enabled)}
        return {"ok": False, "error": "Invalid body"}

    @app.get("/api/studio/collection/{name}/meta")
    async def studio_collection_meta(name: str):
        """Get collection metadata (timestamp, interval, auto_update)."""
        from src.rag.meta import read_meta, get_age_str
        meta = read_meta(name)
        return {"name": name, "meta": meta, "age": get_age_str(name)}

    @app.get("/api/rag/export/{collection}")
    async def rag_export(collection: str):
        """Export a Chroma collection as JSON (for n8n, external apps)."""
        from src.rag.meta import read_meta
        from src.rag.retriever import RAGRetriever
        retriever = RAGRetriever.get()
        if not retriever._ensure_loaded():
            return {"error": "Chroma not loaded"}
        col = retriever._get_collection(collection)
        if col is None or col.count() == 0:
            return {"collection": collection, "chunks": [], "count": 0}
        data = col.get()
        chunks = []
        for i, doc in enumerate(data.get("documents") or []):
            meta = (data.get("metadatas") or [{}])[i]
            chunks.append({"id": (data.get("ids") or [""])[i], "text": doc,
                          "source": (meta or {}).get("source", "")})
        meta = read_meta(collection)
        return {"collection": collection, "count": len(chunks),
                "last_updated": meta.get("last_updated"), "chunks": chunks}

    @app.post("/api/rag/upload/{collection}")
    async def rag_upload_r2(collection: str):
        """Upload a collection to Cloudflare R2."""
        from src.rag.cloud import upload_collection
        ok = upload_collection(collection)
        return {"ok": ok, "collection": collection}

    @app.post("/api/rag/refresh/{collection}")
    async def rag_force_refresh(collection: str):
        """Force manual AI refresh for a specific collection."""
        from src.rag.scheduler import _run_refresh, _get_refresh_queries
        from src.rag.meta import read_meta, touch
        import threading
        
        def _do_refresh():
            meta = read_meta(collection)
            queries = _get_refresh_queries(collection, meta)
            total = _run_refresh(collection, queries)
            if total > 0:
                from datetime import datetime, timezone
                touch(collection, chunks=total, source=f"manual_ai/{datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
                try:
                    from src.rag.cloud import sync_collection_2way
                    sync_collection_2way(collection)
                except Exception:
                    pass

        threading.Thread(target=_do_refresh, daemon=True).start()
        return {"ok": True, "message": "Dang chay ngam qua trinh AI tong hop..."}

    @app.get("/api/rag/models")
    async def rag_get_models():
        """Fetch available models from the configured API Base URL."""
        from src.rag.settings import read as read_settings
        import urllib.request
        import json
        
        settings = read_settings()
        base_url = settings.get("api_base_url", "http://chatgpt2api:3030/v1").rstrip("/")
        api_key = settings.get("api_key", "AnhNhi@0610")
        
        url = f"{base_url}/models"
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read().decode())
            models = [m["id"] for m in data.get("data", []) if "id" in m]
            return {"ok": True, "models": models}
        except Exception as e:
            return {"ok": False, "error": str(e), "models": ["cx/auto", "chatgpt/auto"]}

    from fastapi import UploadFile, File, Form
    import urllib.request
    from bs4 import BeautifulSoup
    from pypdf import PdfReader
    import io

    @app.post("/api/studio/analyze_source")
    async def studio_analyze_source(
        file: UploadFile = File(None),
        url: str = Form(None)
    ):
        """Read a file or URL, extract text, and use AI to synthesize it into Markdown for RAG."""
        try:
            raw_text = ""
            if url:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                resp = urllib.request.urlopen(req, timeout=10)
                html = resp.read().decode("utf-8", errors="ignore")
                soup = BeautifulSoup(html, "html.parser")
                raw_text = soup.get_text(separator="\n", strip=True)
            elif file:
                content = await file.read()
                filename = file.filename.lower()
                if filename.endswith(".pdf"):
                    reader = PdfReader(io.BytesIO(content))
                    for page in reader.pages:
                        text = page.extract_text()
                        if text:
                            raw_text += text + "\n"
                else:
                    raw_text = content.decode("utf-8", errors="ignore")
            
            if not raw_text.strip():
                return {"ok": False, "error": "Khong the trich xuat van ban tu nguon."}
            
            from src.rag.scheduler import _synthesize_with_ai
            title_hint = file.filename if file else url
            query = f"Phân tích, chắt lọc kiến thức và trình bày lại nội dung từ nguồn ({title_hint}) thành bài viết Markdown chi tiết"
            
            raw_text = raw_text[:50000] 
            
            import logging
            logger = logging.getLogger("vn-mcp-hub")
            logger.info("Analyzing source: %s, extracted length: %d", title_hint, len(raw_text))
            
            synthesized = _synthesize_with_ai(query, raw_text)
            if not synthesized or len(synthesized) < 50:
                return {"ok": False, "error": "AI khong the tong hop hoac van ban qua ngan."}
            
            return {"ok": True, "markdown": synthesized}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @app.post("/api/rag/curate/{collection}")
    async def rag_curate(collection: str, request: Request):
        """Add curated content to a RAG collection + upload to R2.

        Body: {title, text, source}
        - Splits text into chunks, ingests into Chroma, uploads to R2.
        """
        from src.rag.ingest import chunk_text
        from src.rag.retriever import RAGRetriever
        from src.rag.meta import touch
        from src.rag.cloud import upload_collection

        body = await request.json()
        title = str(body.get("title") or "")
        text = str(body.get("text") or "")
        source = str(body.get("source") or "curated")

        if not text.strip():
            return {"ok": False, "error": "No text provided"}

        chunks = chunk_text(f"# {title}\n\n{text}" if title else text)
        if not chunks:
            return {"ok": False, "error": "No chunks produced"}

        retriever = RAGRetriever.get()
        if not retriever._ensure_loaded():
            return {"ok": False, "error": "Chroma not loaded"}

        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        col = retriever._client.get_or_create_collection(
            name=collection, embedding_function=retriever._embed_fn
        )
        ids = [f"curated::{ts}::{i}" for i in range(len(chunks))]
        metas = [{"source": source, "chunk": i} for i in range(len(chunks))]
        batch = 100
        for i in range(0, len(chunks), batch):
            col.upsert(ids=ids[i:i+batch], documents=chunks[i:i+batch], metadatas=metas[i:i+batch])

        touch(collection, chunks=len(chunks), source=f"curated/{source}")

        # Upload to R2
        r2_ok = upload_collection(collection)

        return {"ok": True, "collection": collection, "chunks_added": len(chunks), "r2_uploaded": r2_ok}

    @app.get("/api/studio/settings")
    async def studio_get_settings():
        """Get RAG lifecycle settings (sync interval, storage mode)."""
        from src.rag.settings import read as _read_settings
        return _read_settings()

    @app.post("/api/studio/settings")
    async def studio_save_settings(request: Request):
        """Save RAG lifecycle settings."""
        from src.rag.settings import write as _write_settings
        body = await request.json()
        _write_settings(body)
        return {"ok": True}

    @app.post("/api/studio/key/{source_key}")
    async def studio_save_key(source_key: str, request: Request):
        """Save an API key for a source. Body: {api_key: '...'}"""
        from src.sources_config import save_api_key
        body = await request.json()
        key = str(body.get("api_key") or "").strip()
        ok = save_api_key(source_key, key)
        return {"ok": ok, "source": source_key}

    @app.post("/api/studio/validate-mcp")
    async def studio_validate_mcp(request: Request):
        """Test an MCP server URL. Body: {url, api_key?}"""
        from src.mcp_validator import validate_mcp
        body = await request.json()
        url = str(body.get("url") or "").strip()
        api_key = str(body.get("api_key") or "").strip()
        if not url:
            return {"ok": False, "errors": ["URL is required"]}
        return validate_mcp(url, api_key)

    @app.get("/api/studio/external-mcps")
    async def studio_list_external():
        """List external MCPs from registry."""
        import json
        reg = Path("/app/data/studio/external_mcps.json")
        if reg.exists():
            return {"mcps": json.loads(reg.read_text(encoding="utf-8")) or []}
        return {"mcps": []}

    @app.post("/api/studio/external-mcp")
    async def studio_add_external(request: Request):
        """Add an external MCP. Body: {name, url, description, api_key?}"""
        import json
        body = await request.json()
        name = str(body.get("name") or "").strip()
        url = str(body.get("url") or "").strip()
        desc = str(body.get("description") or "").strip()
        api_key = str(body.get("api_key") or "").strip()
        if not name or not url:
            return {"ok": False, "errors": ["Name and URL are required"]}

        reg = Path("/app/data/studio/external_mcps.json")
        reg.parent.mkdir(parents=True, exist_ok=True)
        entries = json.loads(reg.read_text(encoding="utf-8")) if reg.exists() else []
        if any(e["name"] == name for e in entries):
            return {"ok": False, "errors": [f"MCP '{name}' already exists"]}
        entries.append({"name": name, "url": url, "description": desc, "api_key": api_key,
                        "added_at": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()})
        reg.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "name": name}

    @app.delete("/api/studio/external-mcp/{name}")
    async def studio_delete_external(name: str):
        """Remove an external MCP."""
        import json
        reg = Path("/app/data/studio/external_mcps.json")
        if not reg.exists():
            return {"ok": True}
        entries = json.loads(reg.read_text(encoding="utf-8")) or []
        entries = [e for e in entries if e["name"] != name]
        reg.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}

    @app.get("/api/studio/r2")
    async def studio_get_r2():
        """Get R2 config (masked secret)."""
        import json
        r2_file = Path("/app/data/studio/r2.json")
        if r2_file.exists():
            cfg = json.loads(r2_file.read_text(encoding="utf-8"))
            if cfg.get("secret_access_key"):
                cfg["secret_access_key"] = "****" + cfg["secret_access_key"][-4:]
            return {"configured": True, "config": cfg}
        return {"configured": False, "config": {}}

    @app.post("/api/studio/r2")
    async def studio_save_r2(request: Request):
        """Save R2 credentials. Body: {endpoint, access_key_id, secret_access_key, bucket}"""
        import json
        body = await request.json()
        r2_file = Path("/app/data/studio/r2.json")
        r2_file.parent.mkdir(parents=True, exist_ok=True)
        cfg = {
            "endpoint": str(body.get("endpoint") or "").strip(),
            "access_key_id": str(body.get("access_key_id") or "").strip(),
            "secret_access_key": str(body.get("secret_access_key") or "").strip(),
            "bucket": str(body.get("bucket") or "vn-mcp-hub-rag").strip(),
        }
        r2_file.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}

    @app.get("/api/rag/list")
    async def rag_list():
        """List all RAG collections with metadata."""
        from src.rag.meta import read_meta, get_age_str
        from pathlib import Path
        data_dir = Path("/app/data")
        result = []
        if data_dir.exists():
            for folder in sorted(data_dir.iterdir()):
                if folder.is_dir() and (folder / "meta.json").exists():
                    meta = read_meta(folder.name)
                    result.append({"name": folder.name, "chunks": meta.get("chunks_count", 0),
                                   "last_updated": meta.get("last_updated"),
                                   "age": get_age_str(folder.name),
                                   "auto_update": meta.get("auto_update", False)})
        return {"collections": result}

    @app.post("/api/studio/collection/{name}/settings")
    async def studio_collection_settings(name: str, request: Request):
        """Update collection settings. Body: {update_interval_hours, auto_update}"""
        from src.rag.meta import read_meta, write_meta
        body = await request.json()
        meta = read_meta(name)
        if "update_interval_hours" in body:
            meta["update_interval_hours"] = int(body["update_interval_hours"])
        if "auto_update" in body:
            meta["auto_update"] = bool(body["auto_update"])
        write_meta(name, meta)
        return {"ok": True, "name": name, "meta": meta}

    @app.delete("/api/studio/kb/{name}")
    async def studio_delete_kb(name: str):
        from src.studio import delete_kb as _delete
        return _delete(name)

    _mount_mcps(app)
    _mount_dynamic_mcps(app)
    return app


MCP_LABELS = {
    "vn_weather": ("Thời tiết VN", "Thời tiết 63 tỉnh thành, 4 nguồn (Open-Meteo, AccuWeather, NWS, wttr)", "weather"),
    "vn_news": ("Tin tức VN", "Tin mới nhất từ VnExpress, Tuổi Trẻ, Thanh Niên, Dân Trí, BBC, Google News", "news"),
    "vn_currency": ("Tỷ giá & Vàng", "Tỷ giá Vietcombank, giá vàng SJC, ngoại tệ", "finance"),
    "vn_lunar": ("Lịch Âm", "Đổi dương sang âm, can chi, ngày hoàng đạo", "vn_other"),
    "vn_search": ("Tìm kiếm Web", "Tìm web qua DuckDuckGo, hỗ trợ tiếng Việt", "search"),
    "vn_law": ("Tra cứu Luật", "Văn bản pháp luật Việt Nam từ thuvienphapluat.vn", "search"),
    "vn_phat_nguoi": ("Phạt nguội", "Tra cứu phạt nguội xe từ csgt.vn", "vn_other"),
    "vn_stock": ("Cổ phiếu VN", "Giá cổ phiếu, VN-Index, HNX từ VNDirect", "finance"),
    "youtube": ("YouTube Transcript", "Lấy transcript video YouTube, hỗ trợ tiếng Việt", "general"),
    "wikipedia": ("Wikipedia", "Bách khoa toàn thư đa ngôn ngữ (mặc định tiếng Việt)", "search"),
    "arxiv": ("arXiv Paper", "Tìm paper khoa học trên arXiv", "search"),
    "kb_dien_nuoc": ("Kho Điện Nước", "Kiến thức điện, nước, điều hòa, chiller (MCB, MCCB...)", "knowledge"),
    "kb_y_te": ("Kho Y Tế", "Y tế cơ bản, sơ cứu, bệnh thường gặp", "knowledge"),
    "kb_giao_duc": ("Kho Giáo Dục", "Chương trình giáo dục VN, phương pháp học tập", "knowledge"),
    "kb_ngoai_ngu": ("Kho Ngoại Ngữ", "Từ điển, dịch thuật, ngữ pháp, luyện phát âm", "knowledge"),
    "kb_khoa_hoc": ("Kho Khoa Học", "Vật lý, hóa học, sinh học, toán cơ bản", "knowledge"),
    "kb_tu_nhien": ("Kho Tự Nhiên", "Động vật, thực vật, hệ sinh thái, khí hậu, địa lý VN", "knowledge"),
    "kb_xa_hoi": ("Kho Xã Hội", "Lịch sử VN, văn hóa, kinh tế, chính trị, 54 dân tộc", "knowledge"),
    "ha_helper": ("HA Helper", "Giờ hoàng đạo, gợi ý ngữ pháp lệnh Home Assistant", "ha"),
    "federated_search": ("Multi-Search", "Tìm kiếm đồng thời 9 nguồn quốc tế (DDG, Brave, PubMed...)", "search"),
}

MOUNTS = [
    ("vn_weather", "src.vn.weather"),
    ("vn_news", "src.vn.news"),
    ("vn_currency", "src.vn.currency"),
    ("vn_lunar", "src.vn.lunar"),
    ("vn_search", "src.vn.search"),
    ("vn_law", "src.vn.law"),
    ("vn_phat_nguoi", "src.vn.phat_nguoi"),
    ("vn_stock", "src.vn.stock"),
    ("youtube", "src.general.youtube"),
    ("wikipedia", "src.general.wikipedia"),
    ("arxiv", "src.general.arxiv"),
    ("kb_dien_nuoc", "src.kb.dien_nuoc"),
    ("kb_y_te", "src.kb.y_te"),
    ("kb_giao_duc", "src.kb.giao_duc"),
    ("kb_ngoai_ngu", "src.kb.ngoai_ngu"),
    ("kb_khoa_hoc", "src.kb.khoa_hoc"),
    ("kb_tu_nhien", "src.kb.tu_nhien"),
    ("kb_xa_hoi", "src.kb.xa_hoi"),
    ("ha_helper", "src.ha.helper"),
    ("federated_search", "src.search.orchestrator_mcp"),
]


def _get_http_app(mcp):
    """Return the MCP's ASGI app, compatible with fastmcp 2.x and 3.x."""
    if hasattr(mcp, "http_app"):
        return mcp.http_app()  # fastmcp >= 3.0
    return mcp.streamable_http_app()  # fastmcp 2.x


def _mount_mcps(app: FastAPI) -> None:
    """Import each MCP module and mount its FastMCP HTTP app under /<name>/mcp.

    Failures during import are logged but do not abort startup — partial hub
    is better than no hub. Modules that haven't been written yet (during
    incremental build) simply skip.
    """
    for name, module_path in MOUNTS:
        try:
            module = __import__(module_path, fromlist=["mcp"])
            mcp_instance = getattr(module, "mcp", None)
            if mcp_instance is None:
                logger.warning("Module %s has no 'mcp' attribute, skipping", module_path)
                continue
            sub_app = _get_http_app(mcp_instance)
            _mcp_sub_apps.append(sub_app)
            app.mount(f"/{name}", sub_app)
            logger.info("Mounted %s at /%s/mcp", module_path, name)
        except ImportError as exc:
            logger.warning("Skipping %s (not built yet): %s", module_path, exc)
        except Exception as exc:
            logger.error("Failed to mount %s: %s", module_path, exc, exc_info=True)


def _mount_dynamic_mcps(app: FastAPI) -> None:
    """Mount studio-created dynamic KB MCPs from data/studio/dynamic.json."""
    try:
        from src.studio import load_dynamic_mcps
        for name, mcp in load_dynamic_mcps():
            try:
                sub_app = _get_http_app(mcp)
                _mcp_sub_apps.append(sub_app)
                app.mount(f"/{name}", sub_app)
                logger.info("Studio: mounted dynamic MCP at /%s/mcp", name)
            except Exception as exc:
                logger.warning("Studio: failed to mount dynamic MCP '%s': %s", name, exc)
    except Exception as exc:
        logger.warning("Studio: load_dynamic_mcps failed: %s", exc)


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8005,
        log_level="info",
        reload=False,
    )
