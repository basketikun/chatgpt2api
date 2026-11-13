"""代理订阅解析：Clash / mihomo YAML、V2Ray（base64 或明文 URI 列表）。

输出统一的节点描述：
- ``mode == "direct"``：HTTP / SOCKS5 节点，curl_cffi 和 Chrome 能直接用，``url`` 即代理地址；
- ``mode == "core"``：ss / vmess / vless / trojan 等，需要 mihomo 内核转成本地端口，``proxy`` 是
  mihomo 格式的节点配置；
- ``mode == "unsupported"``：解析不了或内核也不支持，``reason`` 说明原因。
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

import yaml


# mihomo 支持的出站类型（direct / reject 这类内置出站不算节点）
CORE_TYPES = {
    "ss", "ssr", "vmess", "vless", "trojan", "hysteria", "hysteria2", "tuic", "wireguard",
    "snell", "anytls", "mieru", "ssh", "socks5", "http",
}
_SKIP_TYPES = {"direct", "reject", "reject-drop", "pass", "dns", "compatible"}


class SubscriptionParseError(ValueError):
    pass


def _b64decode(text: str) -> str:
    raw = "".join(str(text or "").split())
    raw = raw.replace("-", "+").replace("_", "/")
    raw += "=" * (-len(raw) % 4)
    return base64.b64decode(raw, validate=False).decode("utf-8")


def _try_b64decode(text: str) -> str | None:
    try:
        return _b64decode(text)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


def _port(value: Any) -> int:
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        return 0
    return port if 0 < port < 65536 else 0


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _first(query: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        values = query.get(key)
        if values and values[0]:
            return values[0]
    return ""


def _node(name: str, proxy: dict[str, Any] | None, *, mode: str, url: str = "", reason: str = "",
          type_: str = "", server: str = "", port: int = 0) -> dict[str, Any]:
    return {
        "name": name,
        "type": type_ or str((proxy or {}).get("type") or ""),
        "server": server or str((proxy or {}).get("server") or ""),
        "port": port or _port((proxy or {}).get("port")),
        "mode": mode,
        "url": url,
        "reason": reason,
        "proxy": proxy or {},
    }


def _direct_url(scheme: str, server: str, port: int, username: str = "", password: str = "") -> str:
    host = f"[{server}]" if ":" in server and not server.startswith("[") else server
    userinfo = ""
    if username or password:
        userinfo = f"{quote(username, safe='')}:{quote(password, safe='')}@"
    return f"{scheme}://{userinfo}{host}:{port}"


def node_from_clash(proxy: dict[str, Any]) -> dict[str, Any] | None:
    """Clash 节点：HTTP / SOCKS5 直连可用，其余交给内核；节点配置原样保留。"""
    type_ = str(proxy.get("type") or "").strip().lower()
    name = str(proxy.get("name") or "").strip()
    if not type_ or type_ in _SKIP_TYPES:
        return None
    server = str(proxy.get("server") or "").strip()
    port = _port(proxy.get("port"))
    if not name:
        name = f"{type_}://{server}:{port}"
    proxy = {**proxy, "name": name}
    if not server or not port:
        return _node(name, proxy, mode="unsupported", reason="缺少服务器地址或端口")
    username = str(proxy.get("username") or "")
    password = str(proxy.get("password") or "")
    if type_ == "http" and not proxy.get("headers"):
        scheme = "https" if proxy.get("tls") else "http"
        if scheme == "https" and proxy.get("skip-cert-verify"):
            # 证书校验关不掉（curl / Chrome 都会校验），交给内核
            return _node(name, proxy, mode="core")
        return _node(name, proxy, mode="direct", url=_direct_url(scheme, server, port, username, password))
    if type_ == "socks5" and not proxy.get("tls"):
        return _node(name, proxy, mode="direct", url=_direct_url("socks5h", server, port, username, password))
    if type_ in CORE_TYPES:
        return _node(name, proxy, mode="core")
    return _node(name, proxy, mode="unsupported", reason=f"不支持的节点类型 {type_}")


# ── V2Ray 分享链接 → mihomo 节点 ───────────────────────────────────────


def _transport_opts(proxy: dict[str, Any], network: str, path: str, host: str, service_name: str = "") -> None:
    network = (network or "tcp").lower()
    if network in {"", "tcp", "none"}:
        return
    proxy["network"] = network
    if network == "ws":
        opts: dict[str, Any] = {}
        if path:
            opts["path"] = path
        if host:
            opts["headers"] = {"Host": host}
        if opts:
            proxy["ws-opts"] = opts
    elif network == "grpc":
        proxy["grpc-opts"] = {"grpc-service-name": service_name or path}
    elif network in {"h2", "http"}:
        proxy["network"] = "h2" if network == "h2" else "http"
        opts = {}
        if path:
            opts["path"] = path if network == "h2" else [path]
        if host:
            opts["host"] = [host]
        if opts:
            proxy["h2-opts" if network == "h2" else "http-opts"] = opts
    elif network in {"httpupgrade", "xhttp"}:
        opts = {}
        if path:
            opts["path"] = path
        if host:
            opts["host"] = host
        proxy[f"{network}-opts"] = opts


def _parse_vmess(uri: str) -> dict[str, Any]:
    payload = uri[len("vmess://"):]
    decoded = _try_b64decode(payload.split("#", 1)[0])
    if not decoded:
        raise SubscriptionParseError("vmess 链接不是 base64 JSON")
    data = json.loads(decoded)
    name = str(data.get("ps") or "").strip()
    server = str(data.get("add") or "").strip()
    port = _port(data.get("port"))
    proxy: dict[str, Any] = {
        "name": name or f"vmess://{server}:{port}",
        "type": "vmess",
        "server": server,
        "port": port,
        "uuid": str(data.get("id") or ""),
        "alterId": int(data.get("aid") or 0),
        "cipher": str(data.get("scy") or "auto"),
        "udp": True,
    }
    if str(data.get("tls") or "").lower() == "tls":
        proxy["tls"] = True
        sni = str(data.get("sni") or data.get("host") or "")
        if sni:
            proxy["servername"] = sni
        if data.get("fp"):
            proxy["client-fingerprint"] = str(data["fp"])
        if data.get("alpn"):
            proxy["alpn"] = [item for item in str(data["alpn"]).split(",") if item]
        if _truthy(data.get("insecure") or data.get("allowInsecure")):
            proxy["skip-cert-verify"] = True
    network = str(data.get("net") or "tcp").lower()
    if network == "tcp" and str(data.get("type") or "").lower() == "http":
        # tcp + HTTP 伪装头
        proxy["network"] = "http"
        opts: dict[str, Any] = {"path": [str(data.get("path") or "/")]}
        if data.get("host"):
            opts["headers"] = {"Host": [item for item in str(data["host"]).split(",") if item]}
        proxy["http-opts"] = opts
    else:
        _transport_opts(proxy, network, str(data.get("path") or ""), str(data.get("host") or ""))
    return proxy


def _split_uri(uri: str) -> tuple[Any, dict[str, list[str]], str]:
    parts = urlsplit(uri)
    return parts, parse_qs(parts.query), unquote(parts.fragment or "").strip()


def _parse_vless_or_trojan(uri: str, type_: str) -> dict[str, Any]:
    parts, query, name = _split_uri(uri)
    server, port = parts.hostname or "", _port(parts.port)
    secret = unquote(parts.username or "")
    proxy: dict[str, Any] = {"name": name or f"{type_}://{server}:{port}", "type": type_, "server": server,
                             "port": port, "udp": True}
    if type_ == "vless":
        proxy["uuid"] = secret
        flow = _first(query, "flow")
        if flow:
            proxy["flow"] = flow
    else:
        proxy["password"] = secret
    security = _first(query, "security").lower()
    sni = _first(query, "sni", "peer", "servername")
    if type_ == "trojan" or security in {"tls", "reality", "xtls"}:
        if type_ == "vless":
            proxy["tls"] = True
        if sni:
            proxy["servername" if type_ == "vless" else "sni"] = sni
    if security == "reality":
        proxy["reality-opts"] = {"public-key": _first(query, "pbk"), "short-id": _first(query, "sid")}
    fingerprint = _first(query, "fp")
    if fingerprint:
        proxy["client-fingerprint"] = fingerprint
    if _truthy(_first(query, "allowInsecure", "insecure", "allow_insecure")):
        proxy["skip-cert-verify"] = True
    alpn = _first(query, "alpn")
    if alpn:
        proxy["alpn"] = [item for item in alpn.split(",") if item]
    _transport_opts(proxy, _first(query, "type"), _first(query, "path"), _first(query, "host"),
                    _first(query, "serviceName"))
    return proxy


def _parse_ss(uri: str) -> dict[str, Any]:
    body = uri[len("ss://"):]
    body, _, fragment = body.partition("#")
    name = unquote(fragment).strip()
    body, _, query_text = body.partition("?")
    body = body.rstrip("/")
    if "@" not in body:
        # 旧格式：ss://base64(method:password@host:port)
        decoded = _try_b64decode(body)
        if not decoded or "@" not in decoded:
            raise SubscriptionParseError("无法解析 ss 链接")
        body = decoded
        userinfo, _, hostport = body.rpartition("@")
    else:
        userinfo, _, hostport = body.rpartition("@")
        userinfo = unquote(userinfo)
        if ":" not in userinfo:
            userinfo = _try_b64decode(userinfo) or userinfo
    method, _, password = userinfo.partition(":")
    parts = urlsplit(f"//{hostport}")
    server, port = parts.hostname or "", _port(parts.port)
    proxy: dict[str, Any] = {"name": name or f"ss://{server}:{port}", "type": "ss", "server": server, "port": port,
                             "cipher": method, "password": password, "udp": True}
    plugin = _first(parse_qs(query_text), "plugin")
    if plugin:
        plugin_name, *options = unquote(plugin).split(";")
        opts = dict(item.split("=", 1) if "=" in item else (item, "true") for item in options if item)
        if plugin_name in {"obfs-local", "simple-obfs"}:
            proxy["plugin"] = "obfs"
            proxy["plugin-opts"] = {"mode": opts.get("obfs", "http"), "host": opts.get("obfs-host", "")}
        elif plugin_name == "v2ray-plugin":
            proxy["plugin"] = "v2ray-plugin"
            proxy["plugin-opts"] = {"mode": opts.get("mode", "websocket"), "tls": "tls" in opts,
                                    "host": opts.get("host", ""), "path": opts.get("path", "/")}
        else:
            raise SubscriptionParseError(f"不支持的 ss 插件 {plugin_name}")
    return proxy


def _parse_hysteria2(uri: str) -> dict[str, Any]:
    parts, query, name = _split_uri(uri)
    server, port = parts.hostname or "", _port(parts.port)
    password = unquote(parts.username or "")
    if parts.password:
        password = f"{password}:{unquote(parts.password)}"
    proxy: dict[str, Any] = {"name": name or f"hysteria2://{server}:{port}", "type": "hysteria2",
                             "server": server, "port": port, "password": password, "udp": True}
    sni = _first(query, "sni", "peer")
    if sni:
        proxy["sni"] = sni
    if _truthy(_first(query, "insecure", "allowInsecure")):
        proxy["skip-cert-verify"] = True
    obfs = _first(query, "obfs")
    if obfs:
        proxy["obfs"] = obfs
        proxy["obfs-password"] = _first(query, "obfs-password")
    ports = _first(query, "mport")
    if ports:
        proxy["ports"] = ports
    return proxy


def _parse_tuic(uri: str) -> dict[str, Any]:
    parts, query, name = _split_uri(uri)
    server, port = parts.hostname or "", _port(parts.port)
    proxy: dict[str, Any] = {"name": name or f"tuic://{server}:{port}", "type": "tuic", "server": server,
                             "port": port, "uuid": unquote(parts.username or ""),
                             "password": unquote(parts.password or ""), "udp": True}
    sni = _first(query, "sni")
    if sni:
        proxy["sni"] = sni
    alpn = _first(query, "alpn")
    if alpn:
        proxy["alpn"] = [item for item in alpn.split(",") if item]
    congestion = _first(query, "congestion_control", "congestion-controller")
    if congestion:
        proxy["congestion-controller"] = congestion
    if _truthy(_first(query, "allow_insecure", "insecure", "allowInsecure")):
        proxy["skip-cert-verify"] = True
    return proxy


def _parse_socks_or_http(uri: str) -> dict[str, Any]:
    parts, _query, name = _split_uri(uri)
    scheme = parts.scheme.lower()
    server, port = parts.hostname or "", _port(parts.port)
    username, password = unquote(parts.username or ""), unquote(parts.password or "")
    if username and not parts.password:
        # v2rayN：socks://base64(user:pass)@host:port
        decoded = _try_b64decode(username)
        if decoded and ":" in decoded:
            username, _, password = decoded.partition(":")
    type_ = "http" if scheme in {"http", "https"} else "socks5"
    proxy: dict[str, Any] = {"name": name or f"{scheme}://{server}:{port}", "type": type_,
                             "server": server, "port": port}
    if username or password:
        proxy["username"] = username
        proxy["password"] = password
    if scheme == "https":
        proxy["tls"] = True
    return proxy


_URI_PARSERS = {
    "vmess": _parse_vmess,
    "vless": lambda uri: _parse_vless_or_trojan(uri, "vless"),
    "trojan": lambda uri: _parse_vless_or_trojan(uri, "trojan"),
    "ss": _parse_ss,
    "hysteria2": _parse_hysteria2,
    "hy2": _parse_hysteria2,
    "tuic": _parse_tuic,
    "socks": _parse_socks_or_http,
    "socks5": _parse_socks_or_http,
    "socks5h": _parse_socks_or_http,
    "http": _parse_socks_or_http,
    "https": _parse_socks_or_http,
}


def node_from_uri(uri: str) -> dict[str, Any] | None:
    uri = uri.strip()
    if "://" not in uri:
        return None
    scheme = uri.split("://", 1)[0].lower()
    parser = _URI_PARSERS.get(scheme)
    if parser is None:
        fragment = unquote(uri.split("#", 1)[1]).strip() if "#" in uri else ""
        return _node(fragment or uri[:60], None, mode="unsupported", type_=scheme,
                     reason=f"不支持的分享链接类型 {scheme}://")
    try:
        proxy = parser(uri)
    except Exception as exc:
        fragment = unquote(uri.split("#", 1)[1]).strip() if "#" in uri else ""
        return _node(fragment or f"{scheme}://…", None, mode="unsupported", type_=scheme,
                     reason=f"解析失败：{str(exc)[:80]}")
    return node_from_clash(proxy)


# 粘贴到「批量添加」里时走订阅解析的分享链接；http(s) / socks5(h) 仍按普通代理地址处理
SHARE_LINK_SCHEMES = {"vmess", "vless", "trojan", "ss", "ssr", "hysteria2", "hy2", "tuic", "socks"}


def split_share_links(lines: list[str]) -> tuple[list[str], list[str]]:
    """把批量输入拆成 (普通代理地址, 分享链接)；整行 base64 的订阅内容会展开成分享链接。"""
    plain: list[str] = []
    shares: list[str] = []
    for raw in lines:
        line = str(raw or "").strip()
        if not line or line.startswith("#"):
            continue
        if "://" in line:
            scheme = line.split("://", 1)[0].lower()
            (shares if scheme in SHARE_LINK_SCHEMES else plain).append(line)
            continue
        decoded = _try_b64decode(line) if len(line) > 16 and " " not in line and ":" not in line else None
        if decoded and "://" in decoded:
            shares.extend(item.strip() for item in decoded.splitlines() if item.strip())
        else:
            plain.append(line)
    return plain, shares


def _looks_like_clash(text: str) -> bool:
    return "proxies:" in text


def parse_subscription(content: str) -> list[dict[str, Any]]:
    """解析订阅内容，返回节点列表（名称去重）；内容无法识别时抛 SubscriptionParseError。"""
    text = str(content or "").strip().lstrip("﻿")
    if not text:
        raise SubscriptionParseError("订阅内容为空")
    nodes: list[dict[str, Any]] = []
    if _looks_like_clash(text):
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise SubscriptionParseError(f"Clash 配置解析失败：{str(exc)[:120]}") from exc
        proxies = data.get("proxies") if isinstance(data, dict) else None
        if not isinstance(proxies, list):
            raise SubscriptionParseError("Clash 配置里没有 proxies 列表")
        nodes = [node for item in proxies if isinstance(item, dict) and (node := node_from_clash(item))]
    else:
        lines_text = text if "://" in text else (_try_b64decode(text) or "")
        if "://" not in lines_text:
            raise SubscriptionParseError("无法识别的订阅格式（既不是 Clash 配置，也不是分享链接列表）")
        nodes = [node for line in lines_text.splitlines() if (node := node_from_uri(line))]
    if not nodes:
        raise SubscriptionParseError("订阅里没有节点")
    return _dedupe_names(nodes)


def _dedupe_names(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, int] = {}
    for node in nodes:
        base = node["name"]
        count = seen.get(base, 0)
        seen[base] = count + 1
        if count:
            node["name"] = f"{base} #{count + 1}"
            if node["proxy"]:
                node["proxy"] = {**node["proxy"], "name": node["name"]}
    return nodes


def parse_userinfo(header: str) -> dict[str, int]:
    """subscription-userinfo: upload=..; download=..; total=..; expire=.."""
    result: dict[str, int] = {}
    for part in str(header or "").split(";"):
        key, _, value = part.strip().partition("=")
        if key in {"upload", "download", "total", "expire"}:
            try:
                result[key] = int(float(value))
            except ValueError:
                continue
    return result
