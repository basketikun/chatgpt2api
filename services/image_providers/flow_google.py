"""Google Labs Flow image adapter — proxies to the captcha-solver service.

Flow runs only behind a real browser (Patchright + Chrome on Xvfb) because
its UI is heavily client-side. We can't talk to Google's Flow endpoint
directly from a Python HTTP client — Cloudflare-style heuristics + a
required reCAPTCHA Enterprise token reject any non-browser caller. So we
delegate to the captcha-solver microservice which keeps a logged-in
Chromium session per Google account ("profile") and drives the Flow UI
on our behalf.

Provider config (config.json):

    "providers": {
        "flow": {
            "enabled": true,
            "captcha_solver_url": "http://172.16.10.38:8010",
            "captcha_solver_api_key": "<bearer key>",
            "accounts": [
                {"profile": "google-fx",   "project_id": "54468d77-...."},
                {"profile": "google-fx-2", "project_id": "8a9bc1de-...."}
            ]
        }
    }

Each account is its own browser profile + Flow project. Adapter rotates
round-robin; on quota/rate errors we mark an account "cooldown" for an
hour and prefer the next one. Add new accounts by sending the captcha-
solver a manual-login session with a new profile name and signing in.

Model aliases (case-insensitive, matches the Flow UI labels):

    flow/banana-2     → NARWHAL          (Nano Banana 2)
    flow/banana       → NARWHAL          (alias)
    flow/auto         → NARWHAL          (default)
    flow/banana-pro   → NANO_BANANA_PRO  (Nano Banana Pro)
    flow/imagen-4     → IMAGEN_4         (Imagen 4)

Anything else after `flow/` is forwarded verbatim as the imageModelName,
so future models work without code changes.
"""

from __future__ import annotations

import base64
import threading
import time
from typing import Any

from curl_cffi import requests

from services.config import config
from services.image_providers._base import BaseImageAdapter, now_sec
from utils.log import logger


_MODEL_ALIASES = {
    "banana": "NARWHAL",
    "banana-2": "NARWHAL",
    "narwhal": "NARWHAL",
    # `auto` and empty fall through to the strongest model so users get
    # Nano Banana Pro out of the box without having to know the alias.
    "auto": "NANO_BANANA_PRO",
    "": "NANO_BANANA_PRO",
    "best": "NANO_BANANA_PRO",
    "banana-pro": "NANO_BANANA_PRO",
    "nano-banana-pro": "NANO_BANANA_PRO",
    # Flow's API enum is IMAGEN_3_5 even though the UI labels it "Imagen 4".
    # Captured request body confirms. captcha-solver maps either form to
    # the real enum, so any of these aliases works.
    "imagen-4": "IMAGEN_3_5",
    "imagen4": "IMAGEN_3_5",
    "imagen": "IMAGEN_3_5",
    "imagen-3-5": "IMAGEN_3_5",
    "imagen3_5": "IMAGEN_3_5",
}

# All Flow models we expose. Used by list_models() so the chatgpt2api UI
# dropdown shows the same options the Flow website does.
FLOW_MODELS = [
    {"id": "flow/banana-pro", "label": "Nano Banana Pro",   "internal": "NANO_BANANA_PRO"},
    {"id": "flow/banana-2",   "label": "Nano Banana 2",     "internal": "NARWHAL"},
    {"id": "flow/imagen-4",   "label": "Imagen 4",          "internal": "IMAGEN_4"},
    {"id": "flow/auto",       "label": "Auto (Pro)",        "internal": "NANO_BANANA_PRO"},
]

_ASPECT_FROM_SIZE: dict[tuple[int, int], str] = {
    (1024, 1024): "IMAGE_ASPECT_RATIO_SQUARE",
    (1792, 1024): "IMAGE_ASPECT_RATIO_LANDSCAPE",
    (1024, 1792): "IMAGE_ASPECT_RATIO_PORTRAIT",
    (1280, 896):  "IMAGE_ASPECT_RATIO_LANDSCAPE",
    (896, 1280):  "IMAGE_ASPECT_RATIO_PORTRAIT",
}

# Friendly aspect strings ("16:9", "4:3", ...) → Flow API constant.
_ASPECT_FROM_LABEL: dict[str, str] = {
    "16:9":     "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "4:3":      "IMAGE_ASPECT_RATIO_LANDSCAPE_4_3",
    "1:1":      "IMAGE_ASPECT_RATIO_SQUARE",
    "square":   "IMAGE_ASPECT_RATIO_SQUARE",
    "3:4":      "IMAGE_ASPECT_RATIO_PORTRAIT_3_4",
    "9:16":     "IMAGE_ASPECT_RATIO_PORTRAIT",
    "portrait": "IMAGE_ASPECT_RATIO_PORTRAIT",
    "landscape": "IMAGE_ASPECT_RATIO_LANDSCAPE",
}


def _resolve_model(model: str) -> str:
    """Map a 'flow/<alias>' model string to the Flow imageModelName."""
    raw = (model or "").strip().lower()
    if raw.startswith("flow/"):
        raw = raw[len("flow/"):]
    # Default to the strongest model when no alias is given.
    return _MODEL_ALIASES.get(raw, raw.upper() if raw else "NANO_BANANA_PRO")


def _resolve_aspect(size: str | None) -> str:
    """Convert size string OR aspect label to Flow's IMAGE_ASPECT_RATIO_*.

    Accepts: "16:9", "4:3", "1:1", "3:4", "9:16", "1024x1024" (WxH),
    "landscape" / "portrait" / "square". Default is 16:9 landscape.
    """
    if not size:
        return "IMAGE_ASPECT_RATIO_LANDSCAPE"
    s = str(size).strip().lower()
    if s in _ASPECT_FROM_LABEL:
        return _ASPECT_FROM_LABEL[s]
    if "x" in s:
        try:
            w, h = (int(x) for x in s.split("x"))
            mapped = _ASPECT_FROM_SIZE.get((w, h))
            if mapped:
                return mapped
            if w == h:
                return "IMAGE_ASPECT_RATIO_SQUARE"
            return "IMAGE_ASPECT_RATIO_LANDSCAPE" if w > h else "IMAGE_ASPECT_RATIO_PORTRAIT"
        except (TypeError, ValueError):
            pass
    return "IMAGE_ASPECT_RATIO_LANDSCAPE"


# ── Account pool (in-process state) ───────────────────────────────────────
#
# Selection model: STRICT PRIORITY (Main → Backup → Spare 1 → …).
# Account at index 0 (Main) is always tried first. We only fall through
# to index 1 (Backup) when Main is in cooldown OR was already-tried in
# this request. Same for index 2, 3, etc.
#
# Cooldown auto-resets when the timer expires — the account silently
# re-enters the pool at its priority slot. No manual unlock needed.

_pool_lock = threading.Lock()
# Account state by composite key (profile + project) so we don't collide
# across accounts that happen to share a profile.
_account_state: dict[str, dict[str, float]] = {}

# Default cooldown when no explicit config — 1 hour (Flow Pro quota
# typically resets hourly). Override via providers.flow.cooldown_seconds.
_DEFAULT_COOLDOWN_S = 3600.0


def _account_key(account: dict[str, Any]) -> str:
    return f"{account.get('profile', '')}::{account.get('project_id', '')}"


def _pool_config() -> dict[str, Any]:
    providers = config.data.get("providers") or {}
    cfg = providers.get("flow") or {}
    return cfg if isinstance(cfg, dict) else {}


def _cooldown_seconds() -> float:
    """Cooldown after a 429 / quota error, in seconds.

    Reads providers.flow.cooldown_seconds from the live config so admins
    can tune it per environment via the Settings → Flow card."""
    cfg = _pool_config()
    raw = cfg.get("cooldown_seconds")
    try:
        val = float(raw)
        if val > 0:
            return val
    except (TypeError, ValueError):
        pass
    return _DEFAULT_COOLDOWN_S


def _accounts() -> list[dict[str, Any]]:
    cfg = _pool_config()
    raw = cfg.get("accounts") or []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for a in raw:
        if isinstance(a, dict) and a.get("project_id"):
            out.append({
                "profile": str(a.get("profile") or "google-fx"),
                "project_id": str(a["project_id"]),
                "label": str(a.get("label") or a.get("name") or a.get("profile") or "google-fx"),
            })
    return out


def _next_account(exclude: set[str] | None = None) -> dict[str, Any] | None:
    """Pick the highest-priority healthy account.

    Strict priority: index 0 (Main) is always tried first. We only move
    on to index 1 (Backup) when index 0 is in cooldown OR `exclude` (the
    caller already tried it in this request and got a quota error).
    """
    accounts = _accounts()
    if not accounts:
        return None
    exclude = exclude or set()
    now = time.time()
    with _pool_lock:
        for idx in range(len(accounts)):
            acc = accounts[idx]
            key = _account_key(acc)
            if key in exclude:
                continue
            state = _account_state.get(key, {})
            cooldown_until = state.get("cooldown_until", 0)
            if cooldown_until and now < cooldown_until:
                continue
            return acc
        # All accounts are in cooldown OR excluded — the pool is fully
        # exhausted. Return None so the dispatcher reports a clear
        # error to the caller (rather than silently picking a dead one).
        return None


def _mark_quota_exhausted(account: dict[str, Any]) -> None:
    cooldown_s = _cooldown_seconds()
    with _pool_lock:
        key = _account_key(account)
        _account_state.setdefault(key, {})["cooldown_until"] = time.time() + cooldown_s
    logger.warning({"event": "flow_account_cooldown", "account": account.get("label"),
                    "cooldown_s": cooldown_s})


# ── Adapter ──────────────────────────────────────────────────────────────

class FlowImageAdapter(BaseImageAdapter):
    """OpenAI-image-compatible adapter that calls the captcha-solver Flow endpoint."""

    no_auth = False

    def get_key_count(self, credentials: dict[str, Any] | None) -> int:
        """Tell the dispatch layer how many accounts to retry across."""
        return max(1, len(_accounts()))

    # Track which account each request has tried so retries skip dead ones.
    # Keyed by Python object id of the credentials dict (one per request).
    _tried_by_req: dict[int, set[str]] = {}

    def _current_account(
        self,
        key_try: int,
        credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Strict-priority pick. On retry, exclude the account from the
        previous try so the dispatcher actually rotates to the next
        priority slot instead of looping on the same dead Main."""
        req_key = id(credentials) if credentials is not None else 0
        excluded = self._tried_by_req.setdefault(req_key, set())
        # Always ask the pool for the next healthy account, excluding
        # already-tried ones in this request. Priority order is enforced
        # by _next_account itself.
        acc = _next_account(exclude=excluded)
        if acc:
            excluded.add(_account_key(acc))
        # GC: requests with >10 tries are likely going nowhere — drop state
        # so we don't accumulate dict entries from ids of stale objects.
        if len(excluded) > 10:
            self._tried_by_req.pop(req_key, None)
        return acc

    def build_url(
        self,
        model: str,
        credentials: dict[str, Any] | None,
        key_try: int = 0,
    ) -> str:
        cfg = _pool_config()
        base = str(cfg.get("captcha_solver_url") or "").rstrip("/")
        if not base:
            raise RuntimeError(
                "flow provider missing captcha_solver_url in config.providers.flow"
            )
        # Stash the chosen account on the credentials dict so build_body
        # can read it without re-rotating.
        account = self._current_account(key_try, credentials=credentials)
        if credentials is not None and account is not None:
            credentials["_flow_account"] = account
        return f"{base}/v1/google/flow/generate-image"

    def build_body(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        """Build the captcha-solver Flow request.

        Accepts standard OpenAI image params (`size`, `n`, `model`) plus
        a few Flow-specific overrides via `extra_body` so HA/n8n callers
        can pick aspect ratio / model / count without learning the Flow
        constants:

            "extra_body": {
                "aspect_ratio": "16:9",       # or "4:3" / "1:1" / "3:4" / "9:16"
                "flow_model":   "banana-pro", # alias from _MODEL_ALIASES
                "count":        1             # 1-4
            }

        Defaults: 16:9 landscape, Nano Banana Pro, 1 image.
        """
        prompt = str(body.get("prompt") or "")
        extra = body.get("extra_body") or {}
        if not isinstance(extra, dict):
            extra = {}

        # Aspect: prefer explicit extra_body.aspect_ratio, else fall back to
        # standard OpenAI `size` (defaults to landscape 16:9).
        aspect_in = extra.get("aspect_ratio") or extra.get("aspect") or body.get("size")
        aspect = _resolve_aspect(str(aspect_in) if aspect_in else None)

        # Model: extra_body.flow_model wins over the top-level model (since
        # callers using OpenAI clients often hard-code model="flow/auto"
        # but still want to override per-call from HA).
        model_in = extra.get("flow_model") or extra.get("model") or model
        flow_model = _resolve_model(str(model_in))

        # Count: extra_body.count or OpenAI `n`, clamped 1-4.
        count_in = extra.get("count") or extra.get("n") or body.get("n") or 1
        try:
            count = max(1, min(4, int(count_in)))
        except (TypeError, ValueError):
            count = 1

        return {
            "prompt": prompt,
            "aspect_ratio": aspect,
            "model": flow_model,
            "count": count,
            # binary mode returns the FIRST image's bytes; for count > 1 the
            # rest are in the JSON manifest. Set False if you want all URLs.
            "return_binary": count == 1,
            "timeout": 180,
            "headless": False,
        }

    def build_headers(
        self,
        credentials: dict[str, Any] | None,
        request_body: dict[str, Any],
        model: str,
        body: dict[str, Any],
    ) -> dict[str, str]:
        cfg = _pool_config()
        api_key = str(cfg.get("captcha_solver_api_key") or "")
        account = (credentials or {}).get("_flow_account") or _next_account()
        if account:
            request_body["project_id"] = account["project_id"]
            request_body["profile"] = account["profile"]
            logger.info({"event": "flow_account_chosen",
                         "label": account.get("label"),
                         "profile": account["profile"]})
        else:
            raise RuntimeError(
                "no Google Flow accounts configured. "
                "Add at least one under providers.flow.accounts."
            )
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def parse_response(self, response: Any) -> dict[str, Any] | None:
        """Capture binary image body + quota errors before the generic
        dispatcher takes over (it would treat a 502 as fatal but here a
        quota 502 just means rotate to the next account)."""
        if not hasattr(response, "status_code"):
            return None
        if response.status_code >= 400:
            text = ""
            try:
                text = response.text[:600]
            except Exception:
                pass
            lower = text.lower()
            # Common Flow quota / rate signals.
            if (
                "quota" in lower
                or "rate" in lower
                or "usage_limit" in lower
                or response.status_code == 429
            ):
                # The credentials carry the account we just used.
                account = (
                    (response.request._flow_account if hasattr(response.request, "_flow_account") else None)
                    if hasattr(response, "request") else None
                )
                if account:
                    _mark_quota_exhausted(account)
                raise RuntimeError(f"flow quota/rate: HTTP {response.status_code}: {text[:200]}")
            return None
        ct = (response.headers.get("content-type") or "").lower()
        if ct.startswith("image/"):
            return {
                "data": [{
                    "b64_json": base64.b64encode(response.content).decode("ascii"),
                    "_mime": ct,
                    "_flow_meta": {
                        "model": response.headers.get("x-flow-model"),
                        "seed": response.headers.get("x-flow-seed"),
                        "id": response.headers.get("x-flow-image-id"),
                        "elapsed_ms": response.headers.get("x-flow-elapsed-ms"),
                    },
                }],
            }
        # Fallback: JSON response with URL list (when binary mode disabled).
        try:
            payload = response.json()
        except Exception:
            return None
        images = payload.get("images") or []
        if not images:
            return {"data": []}
        data: list[dict[str, Any]] = []
        for im in images:
            url = im.get("url")
            if not url:
                continue
            try:
                r2 = requests.get(url, timeout=30)
                r2.raise_for_status()
                data.append({
                    "b64_json": base64.b64encode(r2.content).decode("ascii"),
                    "_mime": r2.headers.get("content-type", "image/jpeg"),
                    "_flow_meta": im,
                })
            except Exception as exc:
                logger.warning({"event": "flow_download_failed", "url": url[:120], "error": str(exc)})
        return {"data": data}

    def normalize(self, parsed: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        data = parsed.get("data") or []
        return {"created": now_sec(), "data": data}

    def test_connection(self, credentials: dict[str, Any] | None = None) -> bool:
        cfg = _pool_config()
        base = str(cfg.get("captcha_solver_url") or "").rstrip("/")
        if not base:
            return False
        try:
            r = requests.get(f"{base}/health", timeout=5)
            return r.status_code == 200
        except Exception:
            return False


flow_image_adapter = FlowImageAdapter()
