"""可选的 mihomo（Clash.Meta）内核：把 ss / vmess / trojan 等节点转成本地 HTTP 代理端口。

每个导入的节点一个 mixed 监听端口（``proxy: <节点>``），端口固定不变，代理池条目就是
``http://<listen_host>:<端口>``——节点参数随订阅更新也不会改变条目地址，账号绑定不受影响。
配置写到 ``data/mihomo/config.yaml``（mihomo 容器挂载这个目录，重启后仍是最新配置），
再通过 mihomo 的 REST API 热加载。
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from services.config import DATA_DIR
from utils.log import logger


CORE_CONFIG_DIR = DATA_DIR / "mihomo"
CONTROLLER_LISTEN = "0.0.0.0:9090"

DEFAULT_CORE_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "api_url": "http://proxy-core:9090",
    "secret": "",
    "listen_host": "proxy-core",
    "port_start": 20000,
}


def default_core_settings() -> dict[str, Any]:
    """首次使用时从环境变量取默认值（compose 里配置），之后以保存的设置为准。"""
    settings = dict(DEFAULT_CORE_SETTINGS)
    env_map = {
        "enabled": "CHATGPT2API_PROXY_CORE_ENABLED",
        "api_url": "CHATGPT2API_PROXY_CORE_API",
        "secret": "CHATGPT2API_PROXY_CORE_SECRET",
        "listen_host": "CHATGPT2API_PROXY_CORE_LISTEN_HOST",
        "port_start": "CHATGPT2API_PROXY_CORE_PORT_START",
    }
    for key, env in env_map.items():
        value = os.environ.get(env)
        if value is None or value == "":
            continue
        settings[key] = value.strip().lower() in {"1", "true", "yes", "on"} if key == "enabled" else value.strip()
    return normalize_core_settings(settings)


def normalize_core_settings(raw: dict[str, Any]) -> dict[str, Any]:
    settings = {**DEFAULT_CORE_SETTINGS, **{k: v for k, v in (raw or {}).items() if k in DEFAULT_CORE_SETTINGS}}
    settings["enabled"] = bool(settings["enabled"])
    settings["api_url"] = str(settings["api_url"] or DEFAULT_CORE_SETTINGS["api_url"]).strip().rstrip("/")
    settings["secret"] = str(settings["secret"] or "").strip()
    settings["listen_host"] = str(settings["listen_host"] or DEFAULT_CORE_SETTINGS["listen_host"]).strip()
    try:
        port_start = int(settings["port_start"])
    except (TypeError, ValueError):
        port_start = int(DEFAULT_CORE_SETTINGS["port_start"])
    settings["port_start"] = max(1024, min(64000, port_start))
    return settings


def core_proxy_url(settings: dict[str, Any], port: int) -> str:
    host = settings["listen_host"]
    host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"http://{host}:{port}"


def build_core_config(settings: dict[str, Any], nodes: list[tuple[int, dict[str, Any]]]) -> dict[str, Any]:
    """nodes: [(端口, mihomo 节点配置)]。节点在配置里统一改名为 ``p<端口>``，避免跨订阅重名。"""
    proxies: list[dict[str, Any]] = []
    listeners: list[dict[str, Any]] = []
    for port, proxy in sorted(nodes, key=lambda item: item[0]):
        name = f"p{port}"
        proxies.append({**proxy, "name": name})
        listeners.append({
            "name": f"in-{port}",
            "type": "mixed",
            "port": port,
            "listen": "0.0.0.0",
            "udp": False,
            "users": [],
            "proxy": name,
        })
    config: dict[str, Any] = {
        "log-level": "warning",
        "ipv6": True,
        "mode": "rule",
        "allow-lan": True,
        "external-controller": CONTROLLER_LISTEN,
        "proxies": proxies,
        "listeners": listeners,
        # 只有监听器上的流量会进来，且都直接交给指定节点；兜底拒绝，不让内核当成通用代理
        "rules": ["MATCH,REJECT"],
    }
    if settings.get("secret"):
        config["secret"] = settings["secret"]
    return config


class ProxyCoreService:
    def __init__(self, config_dir: Path | None = CORE_CONFIG_DIR, *, opener=None) -> None:
        self._config_dir = config_dir
        self._opener = opener or urllib.request.urlopen
        self._lock = threading.Lock()
        self.last_apply: dict[str, Any] = {"ok": None, "error": None}

    def _request(self, settings: dict[str, Any], method: str, path: str, body: dict | None = None,
                 timeout: float = 10) -> tuple[int, bytes]:
        headers = {"Content-Type": "application/json"}
        if settings.get("secret"):
            headers["Authorization"] = f"Bearer {settings['secret']}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(settings["api_url"] + path, data=data, headers=headers, method=method)
        # 内核在内网，绕过环境里的 HTTP 代理
        with self._opener(request, timeout=timeout) as response:
            return int(getattr(response, "status", 200)), response.read()

    @staticmethod
    def config_text(settings: dict[str, Any], nodes: list[tuple[int, dict[str, Any]]]) -> str:
        """生成的 mihomo 配置文本（供热加载 / 写盘 / 对外服务订阅地址共用）。"""
        return yaml.safe_dump(build_core_config(settings, nodes), allow_unicode=True, sort_keys=False)

    def status(self, settings: dict[str, Any]) -> dict[str, Any]:
        if not settings.get("enabled"):
            return {"enabled": False, "ok": False, "version": None, "error": None, "last_apply": self.last_apply}
        try:
            _status, body = self._request(settings, "GET", "/version", timeout=5)
            version = json.loads(body.decode("utf-8") or "{}").get("version")
            return {"enabled": True, "ok": True, "version": version, "error": None, "last_apply": self.last_apply}
        except Exception as exc:
            return {"enabled": True, "ok": False, "version": None, "error": _describe(exc),
                    "last_apply": self.last_apply}

    def apply(self, settings: dict[str, Any], nodes: list[tuple[int, dict[str, Any]]]) -> dict[str, Any]:
        """写配置文件并热加载；内核不可达时文件仍会写入，内核下次启动即生效。"""
        text = self.config_text(settings, nodes)
        with self._lock:
            if self._config_dir is not None:
                try:
                    self._config_dir.mkdir(parents=True, exist_ok=True)
                    tmp = self._config_dir / "config.yaml.tmp"
                    tmp.write_text(text, encoding="utf-8")
                    tmp.replace(self._config_dir / "config.yaml")
                except Exception as exc:
                    logger.warning({"event": "proxy_core_write_failed", "error": str(exc)[:200]})
            try:
                self._request(settings, "PUT", "/configs?force=true", {"path": "", "payload": text}, timeout=30)
                self.last_apply = {"ok": True, "error": None, "nodes": len(nodes)}
            except Exception as exc:
                self.last_apply = {"ok": False, "error": _describe(exc), "nodes": len(nodes)}
                logger.warning({"event": "proxy_core_apply_failed", "error": self.last_apply["error"]})
            return dict(self.last_apply)


def _describe(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            detail = ""
        return f"HTTP {exc.code} {detail}".strip()
    return str(exc)[:300] or exc.__class__.__name__


def _no_proxy_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open


proxy_core = ProxyCoreService(opener=_no_proxy_opener())
