from __future__ import annotations

import re

from fastapi import APIRouter, Header, HTTPException, Path, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from api.support import require_admin
from services.invoice_service import InvoiceServiceError, invoice_service


NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
}


def _raise_service_error(exc: InvoiceServiceError) -> None:
    headers = dict(NO_STORE_HEADERS)
    if exc.retry_after and re.fullmatch(r"\d{1,7}", exc.retry_after):
        headers["Retry-After"] = exc.retry_after
    raise HTTPException(status_code=exc.status_code, detail={"error": exc.code}, headers=headers) from None


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/invoices/accounts")
    async def list_invoice_accounts(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return JSONResponse(
            {"items": invoice_service.list_account_options()},
            headers=NO_STORE_HEADERS,
        )

    @router.get("/api/invoices/{account_id}")
    async def list_invoices(
        account_id: str = Path(min_length=1, max_length=128),
        limit: int = Query(default=20, ge=1, le=100),
        cursor: str = Query(default="", max_length=2048),
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        try:
            payload = await run_in_threadpool(invoice_service.list_invoices, account_id, limit, cursor)
        except InvoiceServiceError as exc:
            _raise_service_error(exc)
        return JSONResponse(payload, headers=NO_STORE_HEADERS)

    return router
