"""Background scheduler that periodically refreshes the /v1/models cache.

The existing cache invalidates on:
  • Config hash change (provider on/off, profile rename, ...)
  • TTL expiry (24h)
  • Explicit ?refresh=true call

That covers user-initiated refreshes but leaves a long gap when nobody
hits /v1/models in between — the catalogue can drift relative to what
the upstream providers actually serve (Gemini Web renames `2.5 Pro` to
`3 Pro`, chatgpt.com adds a new `gpt-5.x` slug, the Codex pool exposes
a new model). This scheduler proactively re-fetches every
`SCAN_INTERVAL_SECONDS` so the cache stays warm with the live list
even when the API is idle.

Cheap: each scan is one in-process call to `list_models(force_refresh=True)`
which fans out to provider fetchers in a thread pool, persists to disk,
and returns. No additional outbound traffic beyond what a manual
refresh would do.
"""
from __future__ import annotations

import random
import threading
import time

from utils.log import logger

# Refresh every 6h, ±30 min jitter so the same minute isn't pounded on
# every restart-aligned 24h boundary. Aligns with jwt_refresh_scheduler's
# beat to make activity easy to read in logs.
SCAN_INTERVAL_SECONDS = 6 * 3600
SCAN_INTERVAL_JITTER_SECONDS = 30 * 60
# Initial delay so other startup work (MCP tool discovery, account
# warmup) lands first — the upstream picker fetches can be slow.
INITIAL_DELAY_SECONDS = 90

_started = False


def _refresh_once() -> None:
    """Force-refresh the models cache. Heavy lifting lives in
    `list_models(force_refresh=True)` itself; we just call it."""
    # Import lazily so this module doesn't pull the whole protocol stack
    # at process import time.
    from services.protocol.openai_v1_models import list_models
    t0 = time.time()
    try:
        result = list_models(force_refresh=True, apply_filter=False)
        count = len((result or {}).get("data") or [])
        logger.info({
            "event": "models_refresh_done",
            "count": count,
            "took_s": round(time.time() - t0, 2),
        })
    except Exception as exc:
        logger.warning({"event": "models_refresh_error", "error": str(exc)[:200]})


def _scheduler_loop() -> None:
    # Initial delay so warm-up doesn't compete with first user traffic.
    time.sleep(INITIAL_DELAY_SECONDS)
    while True:
        _refresh_once()
        jitter = random.uniform(-SCAN_INTERVAL_JITTER_SECONDS, SCAN_INTERVAL_JITTER_SECONDS)
        time.sleep(max(300, SCAN_INTERVAL_SECONDS + jitter))


def start() -> None:
    """Start the background refresh thread (idempotent)."""
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(
        target=_scheduler_loop, daemon=True, name="models-refresh-scheduler",
    )
    t.start()
    logger.info({
        "event": "models_refresh_scheduler_started",
        "interval_h": SCAN_INTERVAL_SECONDS / 3600,
        "initial_delay_s": INITIAL_DELAY_SECONDS,
    })
