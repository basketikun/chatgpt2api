"""上游代理池：多个出口代理 + 账号粘性绑定。

- 池条目持久化在 ``data/proxy_pool.json``（不放进 config.json：设置页整体保存会把它覆盖掉）；
- 账号绑定写在账号自己的 ``proxy_id`` 字段上，随账号刷新/删除自然迁移/消失，本模块不保存绑定；
- 健康状态只在内存里：连续代理层失败达到阈值标记异常，后台探测连续成功才恢复（滞回，避免频繁换 IP）；
- 账号绑定的代理被禁用或异常时，用 HRW（rendezvous hash）临时借用其他代理：同一账号在故障期间
  固定借同一个，绑定本身不变；
- 本模块不依赖 account_service（避免循环引用），负载计数由调用方传入。
"""

from __future__ import annotations

import base64
import hashlib
import itertools
import json
import os
import random
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from services.config import DATA_DIR
from services.proxy_service import _is_valid_proxy_url, _redact_url_credentials, normalize_proxy_url
from utils.log import logger


PROXY_POOL_FILE = DATA_DIR / "proxy_pool.json"
PROBE_URL = "https://chatgpt.com/cdn-cgi/trace"
OAUTH_RESERVATION_TTL_SECS = 10 * 60

DEFAULT_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "probe_interval_secs": 60,
    "failure_threshold": 3,
    "recovery_successes": 2,
    "legacy_migrated": False,
}
_SETTINGS_LIMITS = {
    "probe_interval_secs": (10, 3600),
    "failure_threshold": (1, 20),
    "recovery_successes": (1, 20),
}
_DEFAULT_PORTS = {"http": 80, "https": 443, "socks5": 1080, "socks5h": 1080}
_SOURCES = {"manual", "legacy_account", "import", "subscription"}

# curl 错误码：设置了代理时，这些错误发生在与代理建连/握手阶段
_PROXY_HARD_CODES = {5, 7, 97}
_PROXY_SOFT_CODES = {35, 52, 55, 56, 60}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return "px_" + uuid.uuid4().hex[:12]


def canonical_proxy_url(url: str) -> str:
    """规范化代理 URL 作为去重键：scheme/host 小写、补默认端口，用户名密码原样保留。

    住宅代理常见同一 host:port、靠用户名区分出口 IP，所以凭据不同就是不同代理。
    无效地址返回空串。
    """
    candidate = normalize_proxy_url(url)
    if not candidate or not _is_valid_proxy_url(candidate):
        return ""
    parts = urlsplit(candidate)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not host:
        return ""
    try:
        port = parts.port or _DEFAULT_PORTS.get(scheme, 80)
    except ValueError:
        return ""
    userinfo = ""
    if "@" in parts.netloc:
        userinfo = parts.netloc.rsplit("@", 1)[0] + "@"
    host_part = f"[{host}]" if ":" in host else host
    return urlunsplit((scheme, f"{userinfo}{host_part}:{port}", "", "", ""))


def mask_proxy_url(url: str) -> str:
    """列表展示用：隐藏密码，用户名只留首尾。"""
    try:
        parts = urlsplit(str(url or ""))
    except ValueError:
        return _redact_url_credentials(url)
    if "@" not in parts.netloc:
        return str(url or "")
    host = parts.netloc.rsplit("@", 1)[1]
    username = parts.username or ""
    if len(username) > 4:
        username = f"{username[:2]}***{username[-2:]}"
    elif username:
        username = username[0] + "***"
    return f"{parts.scheme}://{username}:***@{host}"


def account_route_key(account: dict | None) -> str:
    """账号的稳定标识（HRW 借用用）：不用 access_token，它刷新后会变。"""
    account = account if isinstance(account, dict) else {}
    for key in ("user_id", "email"):
        value = str(account.get(key) or "").strip()
        if value:
            return f"{key}:{value.lower()}"
    token = str(account.get("access_token") or "").strip()
    if token:
        try:
            segment = token.split(".")[1]
            payload = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
            auth = payload.get("https://api.openai.com/auth") if isinstance(payload, dict) else None
            account_id = str((auth or {}).get("chatgpt_account_id") or "").strip() if isinstance(auth, dict) else ""
            if account_id:
                return f"chatgpt_account_id:{account_id}"
        except Exception:
            pass
        return "token:" + hashlib.sha256(token.encode("utf-8")).hexdigest()
    return ""


def _hrw_pick(key: str, entries: list[dict]) -> dict | None:
    if not entries:
        return None

    def score(entry: dict) -> int:
        digest = hashlib.sha256(f"{key}|{entry['id']}".encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big")

    return max(entries, key=score)


def classify_transport_error(exc: BaseException) -> str:
    """把 curl_cffi 异常归为 proxy / soft / neutral。

    按 curl 错误码 + 消息判断，不按异常类型（stream 路径抛的是裸 RequestException）。
    已收到响应头（response.status_code > 0）的一律 neutral：代理是通的。
    """
    code = int(getattr(exc, "code", 0) or 0)
    if not code:
        return "neutral"
    response = getattr(exc, "response", None)
    if int(getattr(response, "status_code", 0) or 0) > 0:
        return "neutral"
    message = str(exc or "")
    if code in _PROXY_HARD_CODES:
        return "proxy"
    if code == 56 and "CONNECT" in message:
        return "proxy"
    if code == 28:
        lowered = message.lower()
        if "connection timed out" in lowered or "connect aborted" in lowered or "resolving timed out" in lowered:
            return "proxy"
        if not str(getattr(response, "primary_ip", "") or ""):
            return "proxy"
        return "neutral"
    if code in _PROXY_SOFT_CODES:
        return "soft"
    return "neutral"


@dataclass
class ProxyHealth:
    state: str = "unknown"          # unknown / healthy / unhealthy；unknown 按可用处理
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_error: str | None = None
    last_error_at: str | None = None
    last_ok_at: str | None = None
    last_probe_at: str | None = None
    last_probe_ts: float = 0.0
    latency_ms: int | None = None
    exit_ip: str | None = None
    url_fingerprint: str = ""

    def public(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
            "last_ok_at": self.last_ok_at,
            "last_probe_at": self.last_probe_at,
            "latency_ms": self.latency_ms,
            "exit_ip": self.exit_ip,
        }


def _url_fingerprint(url: str) -> str:
    return hashlib.sha256(str(url or "").encode("utf-8")).hexdigest()[:16]


def _parse_trace(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in str(text or "").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            result[key.strip()] = value.strip()
    return result


def _default_probe(url: str, timeout: float) -> dict[str, Any]:
    """经代理访问 chatgpt.com 的 /cdn-cgi/trace：只要拿到 HTTP 响应就说明代理通，顺带拿出口 IP。"""
    from curl_cffi.requests import Session

    session = Session(impersonate="chrome", verify=True, proxy=url)
    started = time.perf_counter()
    try:
        response = session.get(PROBE_URL, timeout=timeout)
        latency_ms = int((time.perf_counter() - started) * 1000)
        trace = _parse_trace(response.text) if response.status_code == 200 else {}
        return {
            "ok": True,
            "status": int(response.status_code),
            "latency_ms": latency_ms,
            "error": None,
            "exit_ip": trace.get("ip") or None,
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "status": 0,
            "latency_ms": latency_ms,
            "error": _redact_url_credentials(str(exc) or exc.__class__.__name__)[:300],
            "exit_ip": None,
        }
    finally:
        session.close()


class ProxyPoolService:
    def __init__(
            self,
            store_file: Path | None = None,
            *,
            probe_func: Callable[[str, float], dict[str, Any]] | None = None,
    ) -> None:
        self._store_file = store_file
        self._probe_func = probe_func or _default_probe
        self._lock = threading.RLock()
        self._settings, self._entries = self._load()
        self._health: dict[str, ProxyHealth] = {}
        self._round_robin = itertools.count()
        self._reservations: dict[str, list[float]] = {}

    # ── 持久化 ─────────────────────────────────────────────

    def _load(self) -> tuple[dict[str, Any], list[dict]]:
        settings = dict(DEFAULT_SETTINGS)
        env_enabled = str(os.environ.get("CHATGPT2API_PROXY_POOL_ENABLED", "")).strip().lower()
        if env_enabled in {"1", "true", "yes", "on"}:
            settings["enabled"] = True
        entries: list[dict] = []
        if self._store_file is None or not self._store_file.exists():
            return settings, entries
        try:
            raw = json.loads(self._store_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning({"event": "proxy_pool_load_failed", "error": str(exc)[:200]})
            return settings, entries
        if isinstance(raw, dict):
            settings = self._normalize_settings({**settings, **(raw.get("settings") or {})})
            seen: set[str] = set()
            for item in raw.get("proxies") or []:
                entry = self._normalize_entry(item) if isinstance(item, dict) else None
                if entry is None or entry["id"] in seen:
                    continue
                seen.add(entry["id"])
                entries.append(entry)
        return settings, entries

    def _save_locked(self) -> None:
        if self._store_file is None:
            return
        self._store_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"settings": self._settings, "proxies": self._entries}
        tmp = self._store_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self._store_file)

    @staticmethod
    def _normalize_settings(raw: dict) -> dict[str, Any]:
        settings = dict(DEFAULT_SETTINGS)
        settings["enabled"] = bool(raw.get("enabled"))
        settings["legacy_migrated"] = bool(raw.get("legacy_migrated"))
        for key, (low, high) in _SETTINGS_LIMITS.items():
            try:
                value = int(raw.get(key, DEFAULT_SETTINGS[key]))
            except (TypeError, ValueError):
                value = int(DEFAULT_SETTINGS[key])
            settings[key] = max(low, min(high, value))
        return settings

    @staticmethod
    def _normalize_entry(raw: dict) -> dict | None:
        url = canonical_proxy_url(str(raw.get("url") or ""))
        if not url:
            return None
        source = str(raw.get("source") or "manual").strip()
        now = _now_iso()
        entry = {
            "id": str(raw.get("id") or _new_id()).strip(),
            "name": str(raw.get("name") or "").strip()[:64],
            "url": url,
            "enabled": bool(raw.get("enabled", True)),
            "source": source if source in _SOURCES else "manual",
            "created_at": str(raw.get("created_at") or now),
            "updated_at": str(raw.get("updated_at") or now),
        }
        subscription_id = str(raw.get("subscription_id") or "").strip()
        if subscription_id:
            # 订阅导入的节点：missing = 最近一次刷新时订阅里已没有该节点；
            # auto_disabled = 因此被自动禁用（节点回来时自动恢复，手动开关会清掉这个标记）
            entry.update({
                "subscription_id": subscription_id,
                "node_key": str(raw.get("node_key") or ""),
                "via_core": bool(raw.get("via_core")),
                "missing": bool(raw.get("missing")),
                "auto_disabled": bool(raw.get("auto_disabled")),
            })
        return entry

    # ── 设置 ───────────────────────────────────────────────

    def settings(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._settings)

    def is_enabled(self) -> bool:
        with self._lock:
            return bool(self._settings.get("enabled"))

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        allowed = {key: value for key, value in (updates or {}).items()
                   if key in {"enabled", *_SETTINGS_LIMITS} and value is not None}
        with self._lock:
            self._settings = self._normalize_settings({**self._settings, **allowed})
            self._save_locked()
            return dict(self._settings)

    def mark_legacy_migrated(self) -> None:
        with self._lock:
            if not self._settings.get("legacy_migrated"):
                self._settings["legacy_migrated"] = True
                self._save_locked()

    # ── 条目 ───────────────────────────────────────────────

    def list_entries(self) -> list[dict]:
        with self._lock:
            return [dict(entry) for entry in self._entries]

    def get_entry(self, proxy_id: str) -> dict | None:
        with self._lock:
            entry = self._find_locked(proxy_id)
            return dict(entry) if entry else None

    def has_entry(self, proxy_id: str) -> bool:
        with self._lock:
            return self._find_locked(proxy_id) is not None

    def _find_locked(self, proxy_id: str) -> dict | None:
        target = str(proxy_id or "").strip()
        if not target:
            return None
        for entry in self._entries:
            if entry["id"] == target:
                return entry
        return None

    def _find_by_url_locked(self, url: str) -> dict | None:
        for entry in self._entries:
            if entry["url"] == url:
                return entry
        return None

    def add_entries(self, urls: list[str], *, name: str = "", source: str = "manual") -> dict[str, Any]:
        added: list[dict] = []
        skipped: list[str] = []
        errors: list[dict[str, str]] = []
        cleaned = [str(item or "").strip() for item in urls or []]
        cleaned = [item for item in cleaned if item and not item.startswith("#")]
        with self._lock:
            for raw in cleaned:
                url = canonical_proxy_url(raw)
                if not url:
                    errors.append({"url": _redact_url_credentials(raw), "error": "无效的代理地址"})
                    continue
                if self._find_by_url_locked(url) is not None:
                    skipped.append(mask_proxy_url(url))
                    continue
                entry = self._normalize_entry({
                    "url": url,
                    "name": name if len(cleaned) == 1 else "",
                    "source": source,
                })
                if entry is None:
                    continue
                self._entries.append(entry)
                added.append(dict(entry))
            if added:
                self._save_locked()
        return {"added": added, "skipped": skipped, "errors": errors}

    def ensure_entry(self, url: str, *, source: str = "import") -> str:
        """按规范化 URL 找到或创建条目，返回 id；无效地址返回空串。"""
        canonical = canonical_proxy_url(url)
        if not canonical:
            return ""
        with self._lock:
            entry = self._find_by_url_locked(canonical)
            if entry is not None:
                return entry["id"]
            entry = self._normalize_entry({"url": canonical, "source": source})
            if entry is None:
                return ""
            self._entries.append(entry)
            self._save_locked()
            return entry["id"]

    def add_subscription_entry(self, url: str, *, name: str, subscription_id: str, node_key: str,
                               via_core: bool) -> tuple[dict | None, str]:
        """导入订阅节点；返回 (条目, 失败原因)。地址已在池里时不重复导入。"""
        canonical = canonical_proxy_url(url)
        if not canonical:
            return None, "无效的代理地址"
        with self._lock:
            if self._find_by_url_locked(canonical) is not None:
                return None, "该代理地址已在池中"
            entry = self._normalize_entry({
                "url": canonical,
                "name": name,
                "source": "subscription",
                "subscription_id": subscription_id,
                "node_key": node_key,
                "via_core": via_core,
            })
            if entry is None:
                return None, "无效的代理地址"
            self._entries.append(entry)
            self._save_locked()
            return dict(entry), ""

    def entries_for_subscription(self, subscription_id: str) -> list[dict]:
        with self._lock:
            return [dict(entry) for entry in self._entries if entry.get("subscription_id") == subscription_id]

    def update_entry(self, proxy_id: str, updates: dict[str, Any]) -> dict:
        """编辑名称 / URL / 启用状态，id 不变（绑定保留）。URL 无效或与其他条目重复时抛 ValueError。

        ``missing`` / ``auto_disabled`` / ``via_core`` 只供订阅刷新内部使用；手动切换启用状态会清掉 auto_disabled。
        """
        with self._lock:
            entry = self._find_locked(proxy_id)
            if entry is None:
                raise KeyError(proxy_id)
            next_entry = dict(entry)
            if updates.get("name") is not None:
                next_entry["name"] = str(updates["name"]).strip()[:64]
            if updates.get("enabled") is not None:
                next_entry["enabled"] = bool(updates["enabled"])
                if "subscription_id" in entry and updates.get("auto_disabled") is None:
                    next_entry["auto_disabled"] = False
            if "subscription_id" in entry:
                for key in ("missing", "auto_disabled", "via_core"):
                    if updates.get(key) is not None:
                        next_entry[key] = bool(updates[key])
            if updates.get("url") is not None:
                url = canonical_proxy_url(str(updates["url"]))
                if not url:
                    raise ValueError("无效的代理地址")
                other = self._find_by_url_locked(url)
                if other is not None and other["id"] != entry["id"]:
                    raise ValueError("该代理地址已存在")
                next_entry["url"] = url
            next_entry["updated_at"] = _now_iso()
            entry.update(next_entry)
            self._save_locked()
            return dict(entry)

    def delete_entry(self, proxy_id: str) -> bool:
        with self._lock:
            entry = self._find_locked(proxy_id)
            if entry is None:
                return False
            self._entries = [item for item in self._entries if item["id"] != entry["id"]]
            self._health.pop(entry["id"], None)
            self._reservations.pop(entry["id"], None)
            self._save_locked()
            return True

    # ── 健康状态 ───────────────────────────────────────────

    def _health_locked(self, entry: dict) -> ProxyHealth:
        fingerprint = _url_fingerprint(entry["url"])
        health = self._health.get(entry["id"])
        if health is None or health.url_fingerprint != fingerprint:
            # 新条目或 URL 被编辑过：健康状态从头开始
            health = ProxyHealth(url_fingerprint=fingerprint)
            self._health[entry["id"]] = health
        return health

    def health(self, proxy_id: str) -> dict[str, Any]:
        with self._lock:
            entry = self._find_locked(proxy_id)
            return self._health_locked(entry).public() if entry else ProxyHealth().public()

    def _is_usable_locked(self, entry: dict) -> bool:
        return bool(entry.get("enabled")) and self._health_locked(entry).state != "unhealthy"

    def record_success(self, proxy_id: str, *, probe: bool = False, latency_ms: int | None = None,
                       exit_ip: str | None = None) -> None:
        with self._lock:
            entry = self._find_locked(proxy_id)
            if entry is None:
                return
            health = self._health_locked(entry)
            health.last_ok_at = _now_iso()
            health.consecutive_failures = 0
            if latency_ms is not None:
                health.latency_ms = latency_ms
            if exit_ip:
                health.exit_ip = exit_ip
            if health.state == "unhealthy":
                health.consecutive_successes += 1
                if health.consecutive_successes >= int(self._settings["recovery_successes"]):
                    health.state = "healthy"
                    health.consecutive_successes = 0
                    logger.info({"event": "proxy_pool_recovered", "proxy_id": proxy_id, "probe": probe})
            else:
                health.state = "healthy"

    def record_failure(self, proxy_id: str, error: str, *, kind: str = "proxy") -> None:
        if kind == "neutral":
            return
        with self._lock:
            entry = self._find_locked(proxy_id)
            if entry is None:
                return
            health = self._health_locked(entry)
            health.consecutive_failures += 1
            health.consecutive_successes = 0
            health.last_error = _redact_url_credentials(str(error or ""))[:300]
            health.last_error_at = _now_iso()
            if health.state != "unhealthy" and health.consecutive_failures >= int(self._settings["failure_threshold"]):
                health.state = "unhealthy"
                logger.warning({
                    "event": "proxy_pool_unhealthy",
                    "proxy_id": proxy_id,
                    "proxy": mask_proxy_url(entry["url"]),
                    "error": health.last_error,
                })

    def track_session(self, session: Any, profile: Any) -> Any:
        """在 session 实例上包一层 request，把代理层失败/成功记到对应池条目。

        curl_cffi 的 get/post/put/stream 最终都走 Session.request；只统计 request() 内抛出的
        传输错误（流式传输中途断开不计）。非池出口或测试替身直接原样返回。
        """
        proxy_id = str(getattr(profile, "proxy_id", "") or "")
        original = getattr(session, "request", None)
        if not proxy_id or not callable(original):
            return session

        def tracked_request(*args: Any, **kwargs: Any) -> Any:
            try:
                response = original(*args, **kwargs)
            except Exception as exc:
                kind = classify_transport_error(exc)
                if kind != "neutral":
                    self.record_failure(proxy_id, str(exc), kind=kind)
                raise
            self.record_success(proxy_id)
            return response

        try:
            session.request = tracked_request
        except Exception:
            pass
        return session

    def probe(self, proxy_id: str, *, timeout: float = 15.0) -> dict[str, Any]:
        entry = self.get_entry(proxy_id)
        if entry is None:
            return {"ok": False, "status": 0, "latency_ms": 0, "error": "proxy not found", "exit_ip": None}
        result = self._probe_func(entry["url"], timeout)
        with self._lock:
            current = self._find_locked(proxy_id)
            if current is not None:
                health = self._health_locked(current)
                health.last_probe_at = _now_iso()
                health.last_probe_ts = time.time()
        if result.get("ok"):
            self.record_success(proxy_id, probe=True, latency_ms=result.get("latency_ms"),
                                exit_ip=result.get("exit_ip"))
        else:
            self.record_failure(proxy_id, str(result.get("error") or "probe failed"), kind="proxy")
        return result

    def probe_due(self) -> int:
        """探测到期的已启用条目；返回探测数量。"""
        with self._lock:
            interval = int(self._settings["probe_interval_secs"])
            now = time.time()
            due = [entry["id"] for entry in self._entries
                   if entry.get("enabled") and now - self._health_locked(entry).last_probe_ts >= interval]
        for proxy_id in due:
            try:
                self.probe(proxy_id)
            except Exception as exc:
                logger.warning({"event": "proxy_pool_probe_error", "proxy_id": proxy_id, "error": str(exc)[:200]})
        return len(due)

    def start_health_loop(self, stop_event: threading.Event, *, tick_secs: float = 5.0) -> threading.Thread:
        def worker() -> None:
            while not stop_event.is_set():
                try:
                    if self.is_enabled():
                        self.probe_due()
                except Exception as exc:
                    logger.warning({"event": "proxy_pool_health_loop_error", "error": str(exc)[:200]})
                stop_event.wait(tick_secs)

        thread = threading.Thread(target=worker, name="proxy-pool-health", daemon=True)
        thread.start()
        return thread

    # ── 路由 ───────────────────────────────────────────────

    def _active_reservations_locked(self) -> dict[str, int]:
        now = time.time()
        counts: dict[str, int] = {}
        for proxy_id, stamps in list(self._reservations.items()):
            alive = [stamp for stamp in stamps if now - stamp < OAUTH_RESERVATION_TTL_SECS]
            if alive:
                self._reservations[proxy_id] = alive
                counts[proxy_id] = len(alive)
            else:
                self._reservations.pop(proxy_id, None)
        return counts

    def pick_least_loaded(self, counts: dict[str, int], *, exclude: set[str] | None = None) -> str:
        """在可用（已启用且非异常）条目里选绑定数最少的；全部异常时退到已启用条目；并列随机。"""
        exclude = exclude or set()
        with self._lock:
            reservations = self._active_reservations_locked()
            candidates = [entry for entry in self._entries
                          if entry["id"] not in exclude and self._is_usable_locked(entry)]
            if not candidates:
                candidates = [entry for entry in self._entries if entry["id"] not in exclude and entry.get("enabled")]
            if not candidates:
                return ""
            loads = {entry["id"]: int(counts.get(entry["id"], 0)) + reservations.get(entry["id"], 0)
                     for entry in candidates}
            lowest = min(loads.values())
            return random.choice([proxy_id for proxy_id, load in loads.items() if load == lowest])

    def reserve(self, proxy_id: str) -> None:
        """OAuth 预分配：账号还没落库，先占一个名额，避免连续登录全落到同一个代理。"""
        with self._lock:
            if self._find_locked(proxy_id) is not None:
                self._reservations.setdefault(proxy_id, []).append(time.time())

    def release(self, proxy_id: str) -> None:
        with self._lock:
            stamps = self._reservations.get(proxy_id)
            if stamps:
                stamps.pop(0)
                if not stamps:
                    self._reservations.pop(proxy_id, None)

    def route_bound(self, proxy_id: str, route_key: str) -> tuple[dict | None, str]:
        """已绑定账号的出口：主代理可用走主代理；否则 HRW 借用；没得借仍走主代理（绝不直连）。

        返回 (条目, 路由)；主代理不存在（未绑定/悬空）或池里没有任何已启用代理时返回 (None, "")。
        """
        with self._lock:
            primary = self._find_locked(proxy_id)
            if primary is None:
                return None, ""
            if self._is_usable_locked(primary):
                return dict(primary), "bound"
            others = [entry for entry in self._entries
                      if entry["id"] != primary["id"] and self._is_usable_locked(entry)]
            borrowed = _hrw_pick(route_key or primary["id"], others)
            if borrowed is not None:
                return dict(borrowed), "borrowed"
            if primary.get("enabled"):
                return dict(primary), "bound"
            enabled_others = [entry for entry in self._entries if entry["id"] != primary["id"] and entry.get("enabled")]
            borrowed = _hrw_pick(route_key or primary["id"], enabled_others)
            if borrowed is not None:
                return dict(borrowed), "borrowed"
            return None, ""

    def route_unbound(self, route_key: str) -> tuple[dict | None, str]:
        """账号暂时没有绑定（不该常见，绑定会先发生）：按 HRW 稳定地临时挑一个。"""
        with self._lock:
            candidates = [entry for entry in self._entries if self._is_usable_locked(entry)]
            if not candidates:
                candidates = [entry for entry in self._entries if entry.get("enabled")]
            picked = _hrw_pick(route_key, candidates) if route_key else None
            if picked is None and candidates:
                picked = random.choice(candidates)
            return (dict(picked), "unbound") if picked else (None, "")

    def route_anonymous(self) -> tuple[dict | None, str]:
        """无账号流量：在可用条目里轮询。"""
        with self._lock:
            candidates = [entry for entry in self._entries if self._is_usable_locked(entry)]
            if not candidates:
                candidates = [entry for entry in self._entries if entry.get("enabled")]
            if not candidates:
                return None, ""
            return dict(candidates[next(self._round_robin) % len(candidates)]), "round_robin"

    # ── 展示 ───────────────────────────────────────────────

    def public_entry(self, entry: dict) -> dict[str, Any]:
        with self._lock:
            current = self._find_locked(entry["id"]) or entry
            health = self._health_locked(current).public()
        return {
            **dict(entry),
            "masked_url": mask_proxy_url(entry["url"]),
            "health": health,
        }


proxy_pool = ProxyPoolService(PROXY_POOL_FILE)
