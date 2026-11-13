"""代理订阅：拉取 Clash / V2Ray 订阅，选节点导入代理池，定时刷新。

- HTTP / SOCKS5 节点直接作为池条目；其他协议节点需要启用 mihomo 内核（可选），由内核为每个节点
  开一个固定端口，池条目是 ``http://<内核>:<端口>``；
- 订阅和内核设置保存在 ``data/proxy_subscriptions.json``；哪些节点已导入以池条目上的
  ``subscription_id`` / ``node_key`` 为准；
- 刷新只改已导入节点：参数变化只更新地址（条目 id 与账号绑定不变）；节点消失或不再可用时自动禁用
  （账号临时借用其他代理），回来时自动恢复；拉取失败不动任何条目。
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from services.config import DATA_DIR
from services.proxy_core_service import (
    ProxyCoreService,
    core_proxy_url,
    default_core_settings,
    normalize_core_settings,
    proxy_core,
)
from services.proxy_pool_service import ProxyPoolService, canonical_proxy_url, mask_proxy_url, proxy_pool
from services.proxy_service import _redact_url_credentials
from services.proxy_subscription_parser import parse_subscription, parse_userinfo
from utils.log import logger


SUBSCRIPTIONS_FILE = DATA_DIR / "proxy_subscriptions.json"
# 直接粘贴的分享链接放进一个内置的「手动」订阅：复用节点存储、内核端口与导入逻辑，但不刷新
MANUAL_SUBSCRIPTION_ID = "sub_manual"
MANUAL_SUBSCRIPTION_NAME = "手动添加的节点"
DEFAULT_USER_AGENT = "clash.meta"
DEFAULT_REFRESH_HOURS = 6
MAX_CONTENT_BYTES = 10 * 1024 * 1024
FAILED_REFRESH_RETRY_SECS = 15 * 60

Fetcher = Callable[[str, str], tuple[str, str]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mask_subscription_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return "…"
    return f"{parts.scheme}://{parts.hostname or ''}/…" if parts.scheme else "…"


def _default_fetch(url: str, user_agent: str) -> tuple[str, str]:
    """拉订阅：走全局代理（非上游流量）；返回 (内容, subscription-userinfo 头)。"""
    from curl_cffi.requests import Session

    from services.proxy_service import proxy_settings

    session = Session(**proxy_settings.build_session_kwargs(target_url=url, verify=True))
    try:
        response = session.get(url, headers={"User-Agent": user_agent or DEFAULT_USER_AGENT}, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(f"订阅服务器返回 HTTP {response.status_code}")
        content = response.content or b""
        if len(content) > MAX_CONTENT_BYTES:
            raise RuntimeError("订阅内容过大")
        return content.decode("utf-8", "replace"), str(response.headers.get("subscription-userinfo") or "")
    finally:
        session.close()


def _same_node(a: dict, b: dict) -> bool:
    """同一节点（忽略名称）：重复粘贴同一条链接时识别出来。"""
    def strip(node: dict) -> tuple:
        proxy = {key: value for key, value in (node.get("proxy") or {}).items() if key != "name"}
        return node.get("mode"), node.get("url"), json.dumps(proxy, sort_keys=True, ensure_ascii=False)

    return strip(a) == strip(b)


class ProxySubscriptionService:
    def __init__(
            self,
            store_file: Path | None,
            *,
            pool: ProxyPoolService,
            core: ProxyCoreService,
            fetcher: Fetcher | None = None,
    ) -> None:
        self._store_file = store_file
        self._pool = pool
        self._core = core
        self._fetcher = fetcher or _default_fetch
        self._lock = threading.RLock()
        self._core_settings, self._subscriptions = self._load()

    # ── 持久化 ─────────────────────────────────────────────

    def _load(self) -> tuple[dict[str, Any], list[dict]]:
        if self._store_file is None or not self._store_file.exists():
            return default_core_settings(), []
        try:
            raw = json.loads(self._store_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning({"event": "proxy_subscriptions_load_failed", "error": str(exc)[:200]})
            return default_core_settings(), []
        core = normalize_core_settings(raw.get("core") or {}) if isinstance(raw, dict) else default_core_settings()
        subscriptions = [item for item in (raw.get("subscriptions") or []) if isinstance(item, dict)] \
            if isinstance(raw, dict) else []
        return core, subscriptions

    def _save_locked(self) -> None:
        if self._store_file is None:
            return
        self._store_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._store_file.with_suffix(".json.tmp")
        payload = {"core": self._core_settings, "subscriptions": self._subscriptions}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self._store_file)

    def _find_locked(self, subscription_id: str) -> dict | None:
        for item in self._subscriptions:
            if item["id"] == subscription_id:
                return item
        return None

    # ── 内核 ───────────────────────────────────────────────

    def core_settings(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._core_settings)

    def update_core_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._core_settings = normalize_core_settings({**self._core_settings, **updates})
            self._save_locked()
            settings = dict(self._core_settings)
        # 开关或地址变了：内核节点的池地址要跟着变（关闭时自动禁用、开启时恢复）
        for subscription in self.list_subscriptions():
            self._reconcile(subscription["id"])
        if settings["enabled"]:
            self.sync_core()
        return settings

    def core_status(self) -> dict[str, Any]:
        return {"settings": self.public_core_settings(), "status": self._core.status(self.core_settings())}

    def public_core_settings(self) -> dict[str, Any]:
        settings = self.core_settings()
        settings["has_secret"] = bool(settings.pop("secret", ""))
        return settings

    def _core_nodes(self) -> list[tuple[int, dict[str, Any]]]:
        nodes: list[tuple[int, dict[str, Any]]] = []
        with self._lock:
            subscriptions = [dict(item) for item in self._subscriptions]
        for subscription in subscriptions:
            by_key = {node["name"]: node for node in subscription.get("nodes") or []}
            ports = subscription.get("ports") or {}
            for entry in self._pool.entries_for_subscription(subscription["id"]):
                node = by_key.get(entry.get("node_key"))
                port = ports.get(entry.get("node_key"))
                if entry.get("via_core") and node and node["mode"] == "core" and port:
                    nodes.append((int(port), node["proxy"]))
        return nodes

    def sync_core(self) -> dict[str, Any] | None:
        settings = self.core_settings()
        if not settings["enabled"]:
            return None
        return self._core.apply(settings, self._core_nodes())

    def core_config_text(self) -> str:
        """当前内核应有的配置文本，供对外服务订阅地址（clash 从后端拉取）。"""
        return self._core.config_text(self.core_settings(), self._core_nodes())

    def _allocate_port_locked(self, subscription: dict, node_key: str) -> int:
        ports = subscription.setdefault("ports", {})
        if node_key in ports:
            return int(ports[node_key])
        used = {int(port) for item in self._subscriptions for port in (item.get("ports") or {}).values()}
        port = int(self._core_settings["port_start"])
        while port in used:
            port += 1
        ports[node_key] = port
        return port

    def _desired_url_locked(self, subscription: dict, node: dict | None) -> tuple[str, str]:
        """节点当前应有的池地址；不可用时返回 ("", 原因)。"""
        if node is None:
            return "", "订阅中已没有该节点"
        if node["mode"] == "direct":
            return node["url"], ""
        if node["mode"] == "core":
            if not self._core_settings["enabled"]:
                return "", "需要启用 mihomo 内核"
            port = self._allocate_port_locked(subscription, node["name"])
            return core_proxy_url(self._core_settings, port), ""
        return "", node.get("reason") or "不支持的节点"

    # ── 订阅 ───────────────────────────────────────────────

    def list_subscriptions(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._subscriptions]

    def subscription_names(self) -> dict[str, str]:
        with self._lock:
            return {item["id"]: item.get("name") or _mask_subscription_url(item.get("url", ""))
                    for item in self._subscriptions}

    def public_summary(self, subscription: dict) -> dict[str, Any]:
        nodes = subscription.get("nodes") or []
        entries = self._pool.entries_for_subscription(subscription["id"])
        return {
            "id": subscription["id"],
            "kind": "manual" if subscription["id"] == MANUAL_SUBSCRIPTION_ID else "url",
            "name": subscription.get("name") or "",
            "url": subscription.get("url") or "",
            "masked_url": _mask_subscription_url(subscription.get("url") or ""),
            "user_agent": subscription.get("user_agent") or DEFAULT_USER_AGENT,
            "refresh_interval_hours": int(subscription.get("refresh_interval_hours") or 0),
            "created_at": subscription.get("created_at"),
            "last_fetched_at": subscription.get("last_fetched_at"),
            "last_error": subscription.get("last_error"),
            "userinfo": subscription.get("userinfo") or {},
            "node_count": len(nodes),
            "direct_count": sum(1 for node in nodes if node["mode"] == "direct"),
            "core_count": sum(1 for node in nodes if node["mode"] == "core"),
            "unsupported_count": sum(1 for node in nodes if node["mode"] == "unsupported"),
            "imported_count": len(entries),
            "missing_count": sum(1 for entry in entries if entry.get("missing")),
        }

    def public_detail(self, subscription_id: str) -> dict[str, Any]:
        with self._lock:
            subscription = self._find_locked(subscription_id)
            if subscription is None:
                raise KeyError(subscription_id)
            subscription = dict(subscription)
            core_enabled = bool(self._core_settings["enabled"])
        imported = {entry.get("node_key"): entry for entry in self._pool.entries_for_subscription(subscription_id)}
        nodes = []
        for node in subscription.get("nodes") or []:
            entry = imported.get(node["name"])
            reason = node.get("reason") or ""
            available = node["mode"] == "direct" or (node["mode"] == "core" and core_enabled)
            if node["mode"] == "core" and not core_enabled:
                reason = "需要启用 mihomo 内核"
            nodes.append({
                "key": node["name"],
                "name": node["name"],
                "type": node["type"],
                "server": node["server"],
                "port": node["port"],
                "mode": node["mode"],
                "available": available,
                "reason": reason,
                "masked_url": mask_proxy_url(node["url"]) if node["mode"] == "direct" else "",
                "imported": entry is not None,
                "proxy_id": entry["id"] if entry else None,
            })
        return {**self.public_summary(subscription), "nodes": nodes}

    def create(self, *, name: str, url: str, user_agent: str = "", refresh_interval_hours: int | None = None) -> dict:
        url = str(url or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("订阅地址必须是 http(s) 链接")
        subscription = {
            "id": "sub_" + uuid.uuid4().hex[:12],
            "name": str(name or "").strip()[:64],
            "url": url,
            "user_agent": str(user_agent or "").strip() or DEFAULT_USER_AGENT,
            "refresh_interval_hours": self._clamp_hours(refresh_interval_hours),
            "created_at": _now_iso(),
            "nodes": [],
            "ports": {},
        }
        with self._lock:
            self._subscriptions.append(subscription)
            self._save_locked()
        return dict(subscription)

    @staticmethod
    def _clamp_hours(value: Any) -> int:
        if value is None:
            return DEFAULT_REFRESH_HOURS
        try:
            return max(0, min(168, int(value)))
        except (TypeError, ValueError):
            return DEFAULT_REFRESH_HOURS

    def update(self, subscription_id: str, updates: dict[str, Any]) -> dict:
        with self._lock:
            subscription = self._find_locked(subscription_id)
            if subscription is None:
                raise KeyError(subscription_id)
            if updates.get("name") is not None:
                subscription["name"] = str(updates["name"]).strip()[:64]
            if updates.get("url") is not None:
                if subscription_id == MANUAL_SUBSCRIPTION_ID:
                    raise ValueError("手动添加的节点没有订阅地址")
                url = str(updates["url"]).strip()
                if not url.lower().startswith(("http://", "https://")):
                    raise ValueError("订阅地址必须是 http(s) 链接")
                subscription["url"] = url
            if updates.get("user_agent") is not None:
                subscription["user_agent"] = str(updates["user_agent"]).strip() or DEFAULT_USER_AGENT
            if updates.get("refresh_interval_hours") is not None:
                subscription["refresh_interval_hours"] = self._clamp_hours(updates["refresh_interval_hours"])
            subscription["updated_at"] = _now_iso()
            self._save_locked()
            return dict(subscription)

    def delete(self, subscription_id: str) -> list[str]:
        """删除订阅及其导入的代理，返回被删的池条目 id（调用方负责改绑账号）。"""
        with self._lock:
            subscription = self._find_locked(subscription_id)
            if subscription is None:
                raise KeyError(subscription_id)
            self._subscriptions = [item for item in self._subscriptions if item["id"] != subscription_id]
            self._save_locked()
        removed = []
        for entry in self._pool.entries_for_subscription(subscription_id):
            if self._pool.delete_entry(entry["id"]):
                removed.append(entry["id"])
        self.sync_core()
        return removed

    def on_proxy_deleted(self, entry: dict | None) -> None:
        """池条目被手动删除：释放内核端口并重载内核配置。"""
        if not entry or not entry.get("subscription_id"):
            return
        with self._lock:
            subscription = self._find_locked(entry["subscription_id"])
            if subscription is not None and entry.get("node_key") in (subscription.get("ports") or {}):
                subscription["ports"].pop(entry["node_key"], None)
                self._save_locked()
        if entry.get("via_core"):
            self.sync_core()

    def add_manual_nodes(self, links: list[str]) -> dict[str, Any]:
        """直接粘贴的分享链接：存进「手动」订阅并全部导入；同一节点重复粘贴不会重复导入。

        无法解析时抛 SubscriptionParseError；内核未启用时节点先保存，之后可在节点列表里补导入。
        """
        nodes = parse_subscription("\n".join(links))
        keys: list[str] = []
        with self._lock:
            subscription = self._find_locked(MANUAL_SUBSCRIPTION_ID)
            if subscription is None:
                subscription = {
                    "id": MANUAL_SUBSCRIPTION_ID,
                    "name": MANUAL_SUBSCRIPTION_NAME,
                    "url": "",
                    "user_agent": "",
                    "refresh_interval_hours": 0,
                    "created_at": _now_iso(),
                    "nodes": [],
                    "ports": {},
                }
                self._subscriptions.append(subscription)
            existing = subscription.setdefault("nodes", [])
            for node in nodes:
                same = next((item for item in existing if _same_node(item, node)), None)
                if same is not None:
                    keys.append(same["name"])
                    continue
                names = {item["name"] for item in existing}
                name, index = node["name"], 2
                while name in names:
                    name, index = f"{node['name']} #{index}", index + 1
                node = {**node, "name": name, "proxy": {**node["proxy"], "name": name} if node["proxy"] else {}}
                existing.append(node)
                keys.append(name)
            subscription["last_fetched_at"] = _now_iso()
            self._save_locked()
        result = self.import_nodes(MANUAL_SUBSCRIPTION_ID, keys)
        return {"nodes": len(nodes), **result}

    def refresh(self, subscription_id: str) -> dict[str, Any]:
        if subscription_id == MANUAL_SUBSCRIPTION_ID:
            return {"ok": False, "error": "手动添加的节点没有订阅地址，无需刷新"}
        with self._lock:
            subscription = self._find_locked(subscription_id)
            if subscription is None:
                raise KeyError(subscription_id)
            url, user_agent = subscription["url"], subscription.get("user_agent") or DEFAULT_USER_AGENT
            subscription["last_attempt_ts"] = time.time()
        try:
            content, userinfo_header = self._fetcher(url, user_agent)
            nodes = parse_subscription(content)
        except Exception as exc:  # 拉取失败 / SubscriptionParseError：不动任何条目
            error = _redact_url_credentials(str(exc) or exc.__class__.__name__)[:300]
            with self._lock:
                current = self._find_locked(subscription_id)
                if current is not None:
                    current["last_error"] = error
                    self._save_locked()
            logger.warning({"event": "proxy_subscription_refresh_failed", "subscription_id": subscription_id,
                            "error": error})
            return {"ok": False, "error": error}
        with self._lock:
            current = self._find_locked(subscription_id)
            if current is None:
                raise KeyError(subscription_id)
            current["nodes"] = nodes
            current["last_error"] = None
            current["last_fetched_at"] = _now_iso()
            current["userinfo"] = parse_userinfo(userinfo_header)
            self._save_locked()
        result = self._reconcile(subscription_id)
        core = self.sync_core() if result.pop("core_changed") else None
        return {"ok": True, "error": None, "nodes": len(nodes), **result, "core": core}

    def _reconcile(self, subscription_id: str) -> dict[str, Any]:
        """按最新节点列表对账已导入的池条目。"""
        updated = missing = restored = 0
        core_changed = False
        errors: list[str] = []
        with self._lock:
            subscription = self._find_locked(subscription_id)
            if subscription is None:
                return {"updated": 0, "missing": 0, "restored": 0, "errors": [], "core_changed": False}
            by_key = {node["name"]: node for node in subscription.get("nodes") or []}
            plans = []
            for entry in self._pool.entries_for_subscription(subscription_id):
                node = by_key.get(entry.get("node_key"))
                url, _reason = self._desired_url_locked(subscription, node)
                plans.append((entry, node, url))
            self._save_locked()
        for entry, node, url in plans:
            via_core = bool(node and node["mode"] == "core")
            if via_core or entry.get("via_core"):
                core_changed = True
            if not url:
                if not entry.get("missing"):
                    updates = {"missing": True}
                    if entry.get("enabled"):
                        updates.update(enabled=False, auto_disabled=True)
                    self._pool.update_entry(entry["id"], updates)
                    missing += 1
                continue
            updates: dict[str, Any] = {}
            if canonical_proxy_url(url) != entry["url"]:
                updates["url"] = url
            if via_core != bool(entry.get("via_core")):
                updates["via_core"] = via_core
            if entry.get("missing"):
                updates["missing"] = False
                if entry.get("auto_disabled") and not entry.get("enabled"):
                    updates.update(enabled=True, auto_disabled=False)
            if not updates:
                continue
            try:
                self._pool.update_entry(entry["id"], updates)
            except ValueError as exc:
                errors.append(f"{entry.get('node_key')}: {exc}")
                continue
            updated += 1 if "url" in updates else 0
            restored += 1 if "missing" in updates else 0
        return {"updated": updated, "missing": missing, "restored": restored, "errors": errors,
                "core_changed": core_changed}

    def import_nodes(self, subscription_id: str, node_keys: list[str]) -> dict[str, Any]:
        added: list[dict] = []
        skipped: list[dict[str, str]] = []
        with self._lock:
            subscription = self._find_locked(subscription_id)
            if subscription is None:
                raise KeyError(subscription_id)
            by_key = {node["name"]: node for node in subscription.get("nodes") or []}
            imported = {entry.get("node_key") for entry in self._pool.entries_for_subscription(subscription_id)}
            plans = []
            for key in dict.fromkeys(str(item) for item in node_keys or []):
                node = by_key.get(key)
                if node is None:
                    skipped.append({"key": key, "reason": "订阅中没有该节点"})
                    continue
                if key in imported:
                    skipped.append({"key": key, "reason": "已导入"})
                    continue
                url, reason = self._desired_url_locked(subscription, node)
                if not url:
                    skipped.append({"key": key, "reason": reason})
                    continue
                plans.append((node, url))
            self._save_locked()
        core_added = False
        for node, url in plans:
            via_core = node["mode"] == "core"
            entry, reason = self._pool.add_subscription_entry(
                url, name=node["name"], subscription_id=subscription_id, node_key=node["name"], via_core=via_core,
            )
            if entry is None:
                skipped.append({"key": node["name"], "reason": reason})
                continue
            added.append(entry)
            core_added = core_added or via_core
        core = self.sync_core() if core_added else None
        return {"added": added, "skipped": skipped, "core": core}

    # ── 定时刷新 ───────────────────────────────────────────

    def due_subscriptions(self, now: float | None = None) -> list[str]:
        now = time.time() if now is None else now
        due = []
        with self._lock:
            for item in self._subscriptions:
                hours = int(item.get("refresh_interval_hours") or 0)
                if hours <= 0:
                    continue
                last_attempt = float(item.get("last_attempt_ts") or 0)
                interval = hours * 3600
                if item.get("last_error"):
                    interval = min(interval, FAILED_REFRESH_RETRY_SECS)   # 失败后较快重试
                if now - last_attempt >= interval:
                    due.append(item["id"])
        return due

    def tick(self) -> None:
        for subscription_id in self.due_subscriptions():
            try:
                self.refresh(subscription_id)
            except Exception as exc:
                logger.warning({"event": "proxy_subscription_tick_error", "error": str(exc)[:200]})
        # 内核重启或首次推送失败：重新下发配置
        if self.core_settings()["enabled"] and self._core.last_apply.get("ok") is not True:
            self.sync_core()

    def start_loop(self, stop_event: threading.Event, *, tick_secs: float = 60.0) -> threading.Thread:
        def worker() -> None:
            while not stop_event.is_set():
                try:
                    self.tick()
                except Exception as exc:
                    logger.warning({"event": "proxy_subscription_loop_error", "error": str(exc)[:200]})
                stop_event.wait(tick_secs)

        thread = threading.Thread(target=worker, name="proxy-subscriptions", daemon=True)
        thread.start()
        return thread


proxy_subscriptions = ProxySubscriptionService(SUBSCRIPTIONS_FILE, pool=proxy_pool, core=proxy_core)
