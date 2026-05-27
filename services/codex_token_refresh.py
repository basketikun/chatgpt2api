"""
Codex OAuth token refresh — keep ChatGPT JWTs alive without manual re-login.

Mirrors the flow in 9router/open-sse/services/tokenRefresh.js#refreshCodexToken.

Flow:
    POST https://auth.openai.com/oauth/token
        Content-Type: application/x-www-form-urlencoded
        grant_type=refresh_token
        refresh_token=<refresh_token>
        client_id=<codex_client_id>
        scope=openid profile email offline_access

Response (success):
    {
        "access_token": "eyJ...",
        "refresh_token": "v1.M...",
        "expires_in": 28800,
        "id_token": "eyJ...",
        "token_type": "Bearer"
    }

Response (unrecoverable):
    {"error": "invalid_grant" | "refresh_token_reused" | "token_expired" | ...}
    -> caller must mark the account disabled and stop retrying.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from threading import Lock
from typing import Any

from curl_cffi import requests

from utils.log import logger

OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
# Public Codex CLI client_id (matches 9router PROVIDERS.codex.clientId)
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
SCOPE = "openid profile email offline_access"

UNRECOVERABLE_CODES = {
    "invalid_grant",
    "refresh_token_reused",
    "token_expired",
    "invalid_token",
    "invalid_request",
}

# Per-refresh_token mutex: prevents the rotation race where two callers
# concurrently exchange the SAME refresh_token, OpenAI rotates it, and
# one of the two access_tokens gets invalidated on first use.
#
# After acquiring the lock, callers MUST re-check account_service for a
# fresh access_token written by an earlier holder of the lock — see
# refresh_codex_token below.
_refresh_locks: dict[str, Lock] = defaultdict(Lock)
_refresh_locks_guard = Lock()
# Cap on retained locks to bound memory; pruned opportunistically when the
# guard is held. 4096 keys × ~200 B/lock = ~800 KB worst case.
_MAX_REFRESH_LOCKS = 4096

# In-process recent-refresh cache: dedupes concurrent callers on the same
# refresh_token even when the persistent store (account_service) hasn't
# been written yet. Without this, two threads could each acquire the lock
# in turn, both miss the persistence re-check, and both POST — defeating
# the dedupe goal of the mutex. Entries TTL 60s; account_service catches
# up well within that window.
_recent_refreshes: dict[str, tuple[float, dict]] = {}
_recent_lock = Lock()
_RECENT_TTL_SECONDS = 60.0


def _stash_recent(old_rt: str, result: dict) -> None:
    """Cache a fresh refresh result keyed by the old refresh_token."""
    with _recent_lock:
        now = time.time()
        # Opportunistic prune of expired entries.
        for k in list(_recent_refreshes.keys()):
            if now - _recent_refreshes[k][0] > _RECENT_TTL_SECONDS:
                del _recent_refreshes[k]
        _recent_refreshes[old_rt] = (now, result)


def _peek_recent(old_rt: str) -> dict | None:
    """Return a recently-issued result for old_rt, if still within TTL."""
    with _recent_lock:
        item = _recent_refreshes.get(old_rt)
        if item is None:
            return None
        ts, result = item
        if time.time() - ts > _RECENT_TTL_SECONDS:
            del _recent_refreshes[old_rt]
            return None
        return result


def _lock_for(refresh_token: str) -> Lock:
    """Return the per-token Lock, creating one on first use."""
    with _refresh_locks_guard:
        if len(_refresh_locks) > _MAX_REFRESH_LOCKS:
            # Drop unlocked entries; held ones stay (they'll be cleaned next time).
            for key in list(_refresh_locks.keys()):
                lock = _refresh_locks[key]
                if lock.acquire(blocking=False):
                    try:
                        _refresh_locks.pop(key, None)
                    finally:
                        lock.release()
                if len(_refresh_locks) <= _MAX_REFRESH_LOCKS // 2:
                    break
        return _refresh_locks[refresh_token]


def refresh_codex_token(refresh_token: str, device_id: str | None = None) -> dict[str, Any] | None:
    """Exchange a Codex refresh_token for a fresh access_token.

    Concurrency-safe: acquires a per-refresh_token Lock so two threads
    holding the SAME refresh_token serialize. The second holder re-reads
    account_service and returns the access_token written by the first
    holder, avoiding a duplicate OAuth call (which would invalidate one
    of the two new access_tokens via refresh-token rotation).

    Args:
        refresh_token: the refresh_token to exchange.
        device_id: stable per-account UUID. When set, sent as the
            ``X-Device-Id`` header so the request looks like a real
            persistent Codex CLI install rather than a fresh device on
            every refresh. Backed by ``account.device_id`` set in
            ``account_service._normalize_account``.

    Returns:
        On success: {"access_token": str, "refresh_token": str, "expires_in": int,
                     "expires_at": float (epoch seconds)}
        On unrecoverable failure: {"error": "unrecoverable", "code": <auth0_code>}
        On transient failure: None
    """
    if not refresh_token or not isinstance(refresh_token, str):
        return None

    lock = _lock_for(refresh_token)
    with lock:
        # Fast path: another caller within the last 60s already exchanged
        # this exact refresh_token. Return their result instead of POSTing
        # again — POSTing again would either return a duplicate (if OpenAI
        # is lenient) or invalidate the prior result (if rotation kicks in).
        recent = _peek_recent(refresh_token)
        if recent is not None:
            return recent
        # Re-check: another caller may have already refreshed this token
        # while we waited on the lock. If account_service holds an access
        # token for this refresh_token whose expiry is still > 1h away,
        # short-circuit and return that.
        try:
            from services.account_service import account_service  # avoid import cycle at module load
            existing = account_service.find_by_refresh_token(refresh_token)
        except Exception:
            existing = None
        if existing:
            cached_access = str(existing.get("access_token") or "")
            cached_exp_raw = existing.get("expires_at")
            cached_exp = 0.0
            if cached_exp_raw:
                try:
                    cached_exp = float(cached_exp_raw)
                except ValueError:
                    try:
                        from datetime import datetime
                        cached_exp = datetime.fromisoformat(str(cached_exp_raw).replace('Z', '+00:00')).timestamp()
                    except Exception:
                        pass
            if cached_access and cached_exp - time.time() > 3600:
                return {
                    "access_token": cached_access,
                    "refresh_token": refresh_token,
                    "expires_in": int(cached_exp - time.time()),
                    "expires_at": cached_exp,
                }
            # Pull device_id from the stored account if caller didn't pass one.
            if device_id is None:
                device_id = str(existing.get("device_id") or "") or None
        return _refresh_codex_token_locked(refresh_token, device_id)


def _refresh_codex_token_locked(
    refresh_token: str, device_id: str | None = None
) -> dict[str, Any] | None:
    """Inner worker: actual OAuth call. Caller MUST hold _lock_for(refresh_token)."""
    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CODEX_CLIENT_ID,
        "scope": SCOPE,
    }

    try:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        if device_id:
            # Stable per-account device identity. Real Codex CLI persists
            # a device_id; rotating it on every refresh is an abuse signal.
            headers["X-Device-Id"] = device_id
        resp = requests.post(
            OAUTH_TOKEN_URL,
            data=body,
            headers=headers,
            timeout=20,
            impersonate="chrome110",
        )
    except Exception as exc:
        logger.warning({"event": "codex_refresh_network_error", "error": str(exc)[:200]})
        return None

    if resp.status_code == 200:
        try:
            payload = resp.json()
        except Exception:
            logger.warning({"event": "codex_refresh_bad_json", "status": 200})
            return None

        access_token = str(payload.get("access_token") or "")
        new_refresh = str(payload.get("refresh_token") or refresh_token)
        expires_in = int(payload.get("expires_in") or 0)
        if not access_token:
            return None
        result = {
            "access_token": access_token,
            "refresh_token": new_refresh,
            "expires_in": expires_in,
            "expires_at": time.time() + expires_in if expires_in > 0 else 0.0,
        }
        # Cache under the OLD refresh_token (the one our caller passed in)
        # so a concurrent caller arriving on the same key gets the result
        # without POSTing again. Without this, callers serialize but each
        # still triggers an OAuth call — exactly what the rotation race
        # depends on.
        _stash_recent(refresh_token, result)
        return result

    # Non-200 — inspect error body for unrecoverable codes
    error_text = ""
    try:
        error_text = (resp.text or "")[:500]
    except Exception:
        pass

    code = None
    try:
        parsed = json.loads(error_text) if error_text else {}
        if isinstance(parsed, dict):
            err = parsed.get("error")
            if isinstance(err, str):
                code = err
            elif isinstance(err, dict):
                code = err.get("code") or err.get("error")
    except Exception:
        pass

    if code in UNRECOVERABLE_CODES:
        logger.warning({
            "event": "codex_refresh_unrecoverable",
            "status": resp.status_code,
            "code": code,
        })
        return {"error": "unrecoverable", "code": code}

    logger.warning({
        "event": "codex_refresh_transient_error",
        "status": resp.status_code,
        "body": error_text[:200],
    })
    return None
