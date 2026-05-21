"""DNS cache for Wikipedia lookups — resolves hostnames in main thread.

Docker containers with AdGuard/WireGuard DNS can fail to resolve
hostnames from worker threads (ThreadPoolExecutor). This module
pre-resolves known hosts at import time so the orchestrator threads
don't need to do DNS lookups.
"""

from __future__ import annotations

import socket
import time
import logging

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, str]] = {}
_TTL = 300  # 5 minutes


def get_ip(hostname: str) -> str:
    """Resolve hostname to IP. Returns hostname unchanged on failure."""
    now = time.time()
    if hostname in _cache:
        ts, ip = _cache[hostname]
        if now - ts < _TTL:
            return ip
    try:
        info = socket.getaddrinfo(hostname, 443, socket.AF_INET)
        ip = info[0][4][0]
        _cache[hostname] = (now, ip)
        logger.info("DNS: %s -> %s", hostname, ip)
        return ip
    except Exception as exc:
        logger.debug("DNS: %s failed: %s", hostname, exc)
        return hostname  # Fall back to hostname


# Pre-resolve common hosts at import time (main thread)
_PRELOAD = ["vi.wikipedia.org", "en.wikipedia.org", "api.semanticscholar.org",
            "api.crossref.org", "api.openalex.org", "api.pubmed.gov",
            "archive.org", "api.search.brave.com"]
for _host in _PRELOAD:
    get_ip(_host)
