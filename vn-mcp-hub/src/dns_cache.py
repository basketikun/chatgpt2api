"""DNS cache for Docker threads — monkey-patches socket.getaddrinfo.

Docker containers behind AdGuard/WireGuard DNS can fail to resolve hostnames
from worker threads (ThreadPoolExecutor). This module patches socket.getaddrinfo
at module load time so DNS resolutions are cached from the main thread before
any worker threads are spawned.

Threads still use hostnames (SSL certs remain valid) — only the underlying
DNS lookup is cached.
"""

from __future__ import annotations

import socket
import threading
import logging

logger = logging.getLogger(__name__)

_cache: dict[tuple, list] = {}
_lock = threading.Lock()
_original = socket.getaddrinfo
_patched = False


def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """Cached getaddrinfo — resolves once in main thread, returns cached from threads.

    Cache key is (host, port) only — httpx may call with different family/type/flags
    than pre_resolve(), but the DNS result is the same.
    """
    broad_key = (host, port)
    with _lock:
        if broad_key in _cache:
            return _cache[broad_key]
    result = _original(host, port, family, type, proto, flags)
    with _lock:
        _cache[broad_key] = result
    return result


def pre_resolve():
    """Patch socket.getaddrinfo and pre-resolve known hosts. Call at startup."""
    global _patched
    if _patched:
        return
    socket.getaddrinfo = _patched_getaddrinfo
    _patched = True

    hosts = [
        "vi.wikipedia.org", "en.wikipedia.org",
        "api.semanticscholar.org", "api.crossref.org",
        "api.openalex.org", "eutils.ncbi.nlm.nih.gov",
        "archive.org", "api.search.brave.com",
    ]
    for host in hosts:
        try:
            _patched_getaddrinfo(host, 443)
            logger.info("DNS cached: %s", host)
        except OSError as e:
            logger.warning("DNS pre-resolve failed: %s -> %s", host, e)


# Auto-patch on import (before any threads are spawned)
pre_resolve()


def get_ip(hostname: str) -> str:
    """Get cached IP from pre-resolved cache. Returns hostname if not cached."""
    broad_key = (hostname, 443)
    with _lock:
        if broad_key in _cache:
            result = _cache[broad_key]
            if result:
                return result[0][4][0]
    # Fallback
    try:
        info = _original(hostname, 443, socket.AF_INET)
        return info[0][4][0]
    except Exception:
        return hostname
