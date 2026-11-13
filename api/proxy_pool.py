from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.support import require_admin
from services.account_service import account_service
from services.proxy_pool_service import account_route_key, proxy_pool
from services.proxy_subscription_parser import SubscriptionParseError, split_share_links
from services.proxy_subscription_service import proxy_subscriptions


class ProxyPoolSettingsRequest(BaseModel):
    enabled: bool | None = None
    probe_interval_secs: int | None = None
    failure_threshold: int | None = None
    recovery_successes: int | None = None


class ProxyPoolAddRequest(BaseModel):
    urls: list[str] = Field(default_factory=list)
    name: str = ""


class ProxyPoolUpdateRequest(BaseModel):
    name: str | None = None
    url: str | None = None
    enabled: bool | None = None


class SubscriptionCreateRequest(BaseModel):
    name: str = ""
    url: str = ""
    user_agent: str = ""
    refresh_interval_hours: int | None = None


class SubscriptionUpdateRequest(BaseModel):
    name: str | None = None
    url: str | None = None
    user_agent: str | None = None
    refresh_interval_hours: int | None = None


class SubscriptionImportRequest(BaseModel):
    node_keys: list[str] = Field(default_factory=list)


class ProxyCoreUpdateRequest(BaseModel):
    enabled: bool | None = None
    api_url: str | None = None
    secret: str | None = None
    listen_host: str | None = None
    port_start: int | None = None


def build_pool_payload() -> dict:
    """池设置 + 条目（健康状态、绑定数、借用数）+ 汇总。"""
    entries = proxy_pool.list_entries()
    entry_ids = {entry["id"] for entry in entries}
    pool_enabled = proxy_pool.is_enabled()
    bound: dict[str, int] = {}
    borrowing: dict[str, int] = {}
    borrowed_out: dict[str, int] = {}
    unbound = 0
    for account in account_service.proxy_binding_snapshot():
        proxy_id = account["proxy_id"]
        if proxy_id not in entry_ids:
            unbound += 1
            continue
        bound[proxy_id] = bound.get(proxy_id, 0) + 1
        if not pool_enabled:
            continue
        entry, route = proxy_pool.route_bound(proxy_id, account_route_key(account))
        if entry is not None and route == "borrowed":
            borrowing[entry["id"]] = borrowing.get(entry["id"], 0) + 1
            borrowed_out[proxy_id] = borrowed_out.get(proxy_id, 0) + 1

    subscription_names = proxy_subscriptions.subscription_names()
    items = []
    for entry in entries:
        item = proxy_pool.public_entry(entry)
        if entry.get("subscription_id"):
            item["subscription_name"] = subscription_names.get(entry["subscription_id"], "")
        item["bound_count"] = bound.get(entry["id"], 0)
        item["borrowing_count"] = borrowing.get(entry["id"], 0)
        item["borrowed_out_count"] = borrowed_out.get(entry["id"], 0)
        items.append(item)
    healthy = sum(1 for item in items if item["health"]["state"] == "healthy")
    unhealthy = sum(1 for item in items if item["health"]["state"] == "unhealthy")
    settings = proxy_pool.settings()
    settings.pop("legacy_migrated", None)
    return {
        "settings": settings,
        "items": items,
        "summary": {
            "total": len(items),
            "enabled": sum(1 for item in items if item["enabled"]),
            "healthy": healthy,
            "unhealthy": unhealthy,
            "bound_accounts": sum(bound.values()),
            "unbound_accounts": unbound,
        },
    }


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/proxy/pool")
    async def get_proxy_pool(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return await run_in_threadpool(build_pool_payload)

    @router.post("/api/proxy/pool/settings")
    async def update_proxy_pool_settings(body: ProxyPoolSettingsRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)

        def apply() -> dict:
            was_enabled = proxy_pool.is_enabled()
            proxy_pool.update_settings(body.model_dump(exclude_none=True))
            extra: dict = {}
            if proxy_pool.is_enabled() and not was_enabled:
                # 开启时：旧账号代理迁进池，再给未绑定账号均分
                extra = account_service.activate_proxy_pool()
            return {**build_pool_payload(), **extra}

        return await run_in_threadpool(apply)

    @router.post("/api/proxy/pool")
    async def add_proxy_pool_entries(body: ProxyPoolAddRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        urls = [line for item in body.urls for line in str(item or "").splitlines()]
        if not any(url.strip() for url in urls):
            raise HTTPException(status_code=400, detail={"error": "请至少填写一个代理地址"})

        def apply() -> dict:
            # vmess:// 等分享链接走订阅解析（需要 mihomo 内核），普通 http/socks 地址直接入池
            plain, shares = split_share_links(urls)
            result = proxy_pool.add_entries(plain, name=body.name) if plain else {"added": [], "skipped": [], "errors": []}
            added, skipped, errors = len(result["added"]), len(result["skipped"]), list(result["errors"])
            core_apply = None
            if shares:
                try:
                    manual = proxy_subscriptions.add_manual_nodes(shares)
                except SubscriptionParseError as exc:
                    errors.append({"url": f"{len(shares)} 条分享链接", "error": str(exc)})
                else:
                    added += len(manual["added"])
                    core_apply = manual["core"]
                    for item in manual["skipped"]:
                        if item["reason"] == "已导入":
                            skipped += 1
                        else:
                            errors.append({"url": item["key"], "error": item["reason"]})
            assigned = account_service.bind_unbound_accounts() if added else 0
            return {
                **build_pool_payload(),
                "added": added,
                "skipped": skipped,
                "errors": errors,
                "assigned": assigned,
                "core_apply": core_apply,
            }

        return await run_in_threadpool(apply)

    @router.post("/api/proxy/pool/{proxy_id}/test")
    async def test_proxy_pool_entry(proxy_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        if not proxy_pool.has_entry(proxy_id):
            raise HTTPException(status_code=404, detail={"error": "代理不存在"})
        result = await run_in_threadpool(proxy_pool.probe, proxy_id)
        return {**await run_in_threadpool(build_pool_payload), "result": result}

    @router.post("/api/proxy/pool/{proxy_id}")
    async def update_proxy_pool_entry(
            proxy_id: str,
            body: ProxyPoolUpdateRequest,
            authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)

        def apply() -> dict:
            current = proxy_pool.get_entry(proxy_id)
            if current is None:
                raise HTTPException(status_code=404, detail={"error": "代理不存在"})
            if body.url is not None and current.get("subscription_id") and current["url"] != body.url.strip():
                raise HTTPException(status_code=400, detail={"error": "订阅导入的代理地址由订阅维护，不能手动修改"})
            try:
                item = proxy_pool.update_entry(proxy_id, body.model_dump(exclude_none=True))
            except KeyError as exc:
                raise HTTPException(status_code=404, detail={"error": "代理不存在"}) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
            # 之前全部代理都被禁用时可能有账号没分到，重新启用后补上（已绑定的不动）
            account_service.bind_unbound_accounts()
            return {**build_pool_payload(), "item": proxy_pool.public_entry(item)}

        return await run_in_threadpool(apply)

    @router.delete("/api/proxy/pool/{proxy_id}")
    async def delete_proxy_pool_entry(proxy_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)

        def apply() -> dict:
            entry = proxy_pool.get_entry(proxy_id)
            if entry is None or not proxy_pool.delete_entry(proxy_id):
                raise HTTPException(status_code=404, detail={"error": "代理不存在"})
            # 粘性只在删除时打破：原账号逐个改绑到当前最少的代理
            reassigned = account_service.reassign_proxy_bindings(proxy_id)
            proxy_subscriptions.on_proxy_deleted(entry)
            return {**build_pool_payload(), "reassigned": reassigned}

        return await run_in_threadpool(apply)

    # ── 订阅 ───────────────────────────────────────────────

    def subscriptions_payload() -> dict:
        return {
            "items": [proxy_subscriptions.public_summary(item) for item in proxy_subscriptions.list_subscriptions()],
            "core": proxy_subscriptions.core_status(),
        }

    def subscription_detail(subscription_id: str) -> dict:
        try:
            return proxy_subscriptions.public_detail(subscription_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"error": "订阅不存在"}) from exc

    @router.get("/api/proxy/subscriptions")
    async def list_subscriptions(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return await run_in_threadpool(subscriptions_payload)

    @router.post("/api/proxy/subscriptions")
    async def create_subscription(body: SubscriptionCreateRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)

        def apply() -> dict:
            try:
                created = proxy_subscriptions.create(
                    name=body.name, url=body.url, user_agent=body.user_agent,
                    refresh_interval_hours=body.refresh_interval_hours,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
            result = proxy_subscriptions.refresh(created["id"])
            return {**subscriptions_payload(), "item": subscription_detail(created["id"]), "result": result}

        return await run_in_threadpool(apply)

    @router.get("/api/proxy/subscriptions/{subscription_id}")
    async def get_subscription(subscription_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return {"item": await run_in_threadpool(subscription_detail, subscription_id)}

    @router.post("/api/proxy/subscriptions/{subscription_id}")
    async def update_subscription(
            subscription_id: str,
            body: SubscriptionUpdateRequest,
            authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)

        def apply() -> dict:
            try:
                proxy_subscriptions.update(subscription_id, body.model_dump(exclude_none=True))
            except KeyError as exc:
                raise HTTPException(status_code=404, detail={"error": "订阅不存在"}) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
            return {**subscriptions_payload(), "item": subscription_detail(subscription_id)}

        return await run_in_threadpool(apply)

    @router.post("/api/proxy/subscriptions/{subscription_id}/refresh")
    async def refresh_subscription(subscription_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)

        def apply() -> dict:
            try:
                result = proxy_subscriptions.refresh(subscription_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail={"error": "订阅不存在"}) from exc
            return {**subscriptions_payload(), "item": subscription_detail(subscription_id), "result": result}

        return await run_in_threadpool(apply)

    @router.post("/api/proxy/subscriptions/{subscription_id}/import")
    async def import_subscription_nodes(
            subscription_id: str,
            body: SubscriptionImportRequest,
            authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)

        def apply() -> dict:
            try:
                result = proxy_subscriptions.import_nodes(subscription_id, body.node_keys)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail={"error": "订阅不存在"}) from exc
            assigned = account_service.bind_unbound_accounts() if result["added"] else 0
            return {
                **subscriptions_payload(),
                "item": subscription_detail(subscription_id),
                "added": len(result["added"]),
                "skipped": result["skipped"],
                "core_apply": result["core"],
                "assigned": assigned,
            }

        return await run_in_threadpool(apply)

    @router.delete("/api/proxy/subscriptions/{subscription_id}")
    async def delete_subscription(subscription_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)

        def apply() -> dict:
            try:
                removed = proxy_subscriptions.delete(subscription_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail={"error": "订阅不存在"}) from exc
            reassigned = sum(account_service.reassign_proxy_bindings(proxy_id) for proxy_id in removed)
            return {**subscriptions_payload(), "removed_proxies": len(removed), "reassigned": reassigned}

        return await run_in_threadpool(apply)

    # ── mihomo 内核（可选） ────────────────────────────────

    @router.get("/api/proxy/core")
    async def get_proxy_core(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return await run_in_threadpool(proxy_subscriptions.core_status)

    @router.post("/api/proxy/core")
    async def update_proxy_core(body: ProxyCoreUpdateRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)

        def apply() -> dict:
            proxy_subscriptions.update_core_settings(body.model_dump(exclude_none=True))
            # 内核开关会让对应条目恢复/禁用，可能有账号需要补分配
            account_service.bind_unbound_accounts()
            return proxy_subscriptions.core_status()

        return await run_in_threadpool(apply)

    @router.get("/api/proxy/core/config")
    async def get_proxy_core_config(authorization: str | None = Header(default=None)):
        """对外服务的 mihomo 配置（订阅地址）：clash-egress pod 从后端拉取这份配置启动。"""
        require_admin(authorization)
        text = await run_in_threadpool(proxy_subscriptions.core_config_text)
        return Response(content=text, media_type="application/yaml")

    return router
