"""Client for the sentinel solver service (`sentinel_solver/`).

Since 2026-10-14 chatgpt.com only accepts a Turnstile token that was computed
inside a real chatgpt.com page. A pure-Python or Node emulation of the challenge
is rejected, and an incomplete handshake does not surface as 403: the
conversation endpoint answers a disguised `404 {"detail": "Model not found"}`.
The solver keeps a headless Chromium on that page and computes the token for us.

The JSON browser route forwards account Authorization to the trusted solver.
Conversation prompts and streaming responses continue to use the main service.

Cloudflare also scores some paths per client rather than per request, so this module
hands back the cookies the cleared page holds alongside its user agent
(`solver_identity`), keyed by the egress that earned them. The backend adopts them on
its session before the first upstream call; see `_apply_solver_cookies`.
"""

from __future__ import annotations

import threading
import time

from curl_cffi import requests

from services.config import config
from utils.log import logger

SOLVER_TIMEOUT_SECONDS = 20
# Solving waits on the page's own module, which can take a moment on a cold page.
SOLVER_SOLVE_TIMEOUT_SECONDS = 60
HEALTH_CACHE_SECONDS = 600
# A failed health probe is cached briefly too, so a solver that is down does not
# get probed once per request, per exit.
HEALTH_FAILURE_CACHE_SECONDS = 30

_health_lock = threading.Lock()
# Caches one `/health` answer per egress, because the interesting half of it (the
# cleared page's cookies) is bound to the exit that earned it and every session has to
# be handed its own set. Keyed by (solver url, egress), so a reconfigured solver or a
# different exit never reads another's entry.
_health_cache: dict[tuple[str, str], dict[str, object]] = {}


class SentinelSolverError(RuntimeError):
    """The solver is unconfigured or could not produce a Turnstile token."""


def _solver_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.sentinel_solver_key:
        headers["Authorization"] = f"Bearer {config.sentinel_solver_key}"
    return headers


def _health(proxy: str = "") -> dict[str, object]:
    """Cached `/health` for one egress, or {} when the solver is unset or unreachable.

    A non-empty `proxy` asks the solver about that exit specifically and gets back its
    captured cookies; without one only the browser-wide user agent is meaningful.
    """
    base_url = config.sentinel_solver_url
    if not base_url:
        return {}
    exit_key = str(proxy or "").strip()
    cache_key = (base_url, exit_key)
    with _health_lock:
        now = time.monotonic()
        for key in [k for k, entry in _health_cache.items() if now >= float(entry["expires_at"])]:
            del _health_cache[key]
        cached = _health_cache.get(cache_key)
        if cached is not None:
            return dict(cached)
        payload: dict[str, object] = {}
        request_kwargs: dict[str, object] = {}
        if exit_key:
            request_kwargs["params"] = {"proxy": exit_key}
        try:
            response = requests.get(
                f"{base_url}/health",
                headers=_solver_headers(),
                timeout=SOLVER_TIMEOUT_SECONDS,
                **request_kwargs,
            )
            if response.status_code == 200:
                body = response.json() or {}
                if isinstance(body, dict):
                    payload = body
        except Exception as exc:  # noqa: BLE001
            logger.warning({"event": "sentinel_solver_health_error", "error": str(exc)})
        user_agent = str(payload.get("user_agent") or "")
        exit_info = payload.get("exit") if isinstance(payload.get("exit"), dict) else {}
        cookies = {
            str(name): str(value)
            for name, value in (exit_info.get("cookies") or {}).items()
            if name and value
        }
        ttl = HEALTH_CACHE_SECONDS if user_agent else HEALTH_FAILURE_CACHE_SECONDS
        _health_cache[cache_key] = {
            "user_agent": user_agent,
            "cookies": cookies,
            "warmed": bool(exit_info.get("warmed")),
            "expires_at": now + ttl,
        }
        return dict(_health_cache[cache_key])


def solver_identity(proxy: str = "") -> tuple[str, dict[str, str]]:
    """The solver page's (user_agent, cookies) for `proxy`, or ("", {}) when unavailable.

    One cached `/health` call answers both halves, but they belong together for a
    reason: the cookies are bound to the egress that earned them, so pass the session's
    own exit. A `__cf_bm` from another exit does nothing for this request, and the
    solver's own default egress is not ours, so an unnamed exit gets no cookies at all
    rather than somebody else's.

    - UA: the requirements/proof tokens embed it and it has to match the browser that
      solved the challenge; otherwise the conversation endpoint answers
      `404 {"detail": "Model not found"}`.
    - cookies: mainly Cloudflare's `__cf_bm` / `_cfuvid`. Cloudflare scores some paths
      (sentinel/chat-requirements) per client: a bare curl_cffi request is challenged
      persistently without them and is let through with them.
    """
    health = _health(proxy)
    return str(health.get("user_agent") or ""), dict(health.get("cookies") or {})


def solver_user_agent() -> str:
    """User agent of the page that computes the Turnstile token, or "" when unset."""
    return solver_identity()[0]


def solver_cookies(proxy: str = "") -> dict[str, str]:
    """Cookies the cleared solver page holds for `proxy` (Cloudflare per-path checks)."""
    return solver_identity(proxy)[1]


def solve_turnstile(dx: str, p: str, requirements: dict | None = None, proxy: str = "") -> str:
    """Solve the Turnstile challenge.

    `dx` comes from the prepare response and `p` is the requirements token we sent.
    `requirements` is the whole prepare response — passing it lets the solver call
    the page's own turnstile module instead of emulating the challenge, which is
    the only thing that currently produces an accepted token. It is pure challenge
    material: no account token, cookie or user prompt is involved.

    Fails closed: without a solved token the conversation request would come back
    as a disguised 404 and burn the whole retry budget, so an unsolvable challenge
    is raised here instead.
    """
    base_url = config.sentinel_solver_url
    if not base_url:
        raise SentinelSolverError(
            "sentinel solver is not configured (CHATGPT2API_SENTINEL_SOLVER_URL / config.json sentinel_solver_url)"
        )
    body: dict[str, object] = {"dx": dx, "p": p}
    if requirements:
        body["requirements"] = requirements
    if proxy:
        body["proxy"] = proxy
    try:
        response = requests.post(
            f"{base_url}/v1/turnstile",
            headers=_solver_headers(),
            json=body,
            timeout=SOLVER_SOLVE_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning({"event": "sentinel_solver_error", "error": str(exc)})
        raise SentinelSolverError(f"sentinel solver request failed: {exc}") from exc

    if response.status_code != 200:
        logger.warning({
            "event": "sentinel_solver_failed",
            "status": response.status_code,
            "body": str(response.text or "")[:200],
        })
        raise SentinelSolverError(
            f"sentinel solver returned HTTP {response.status_code}: {str(response.text or '')[:200]}"
        )

    token = str((response.json() or {}).get("token") or "")
    if not token:
        raise SentinelSolverError("sentinel solver returned an empty turnstile token")
    return token


def browser_request(method: str, url: str, headers: dict[str, str] | None = None, body: str = "", proxy: str = "") -> dict:
    """Run a JSON request through the solver's real Chromium page."""
    base_url = config.sentinel_solver_url
    if not base_url:
        raise SentinelSolverError("sentinel solver is not configured")
    try:
        response = requests.post(
            f"{base_url}/v1/request", headers=_solver_headers(),
            json={"method": method, "url": url, "headers": headers or {}, "body": body, **({"proxy": proxy} if proxy else {})},
            timeout=SOLVER_SOLVE_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        raise SentinelSolverError(f"sentinel browser request failed: {exc}") from exc
    if response.status_code != 200:
        raise SentinelSolverError(f"sentinel browser request returned HTTP {response.status_code}")
    try:
        data = response.json()
        if (not isinstance(data, dict) or type(data.get("status")) is not int
                or not 0 <= data["status"] <= 599 or not isinstance(data.get("headers"), dict)
                or not isinstance(data.get("text"), str)):
            raise ValueError("invalid browser response")
        return data
    except (TypeError, ValueError) as exc:
        raise SentinelSolverError("invalid sentinel browser response") from exc
