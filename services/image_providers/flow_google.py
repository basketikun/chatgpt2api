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
    "auto": "NARWHAL",
    "": "NARWHAL",
    "banana-pro": "NANO_BANANA_PRO",
    "nano-banana-pro": "NANO_BANANA_PRO",
    "imagen-4": "IMAGEN_4",
    "imagen4": "IMAGEN_4",
    "imagen": "IMAGEN_4",
}

_ASPECT_FROM_SIZE: dict[tuple[int, int], str] = {
    (1024, 1024): "IMAGE_ASPECT_RATIO_SQUARE",
    (1792, 1024): "IMAGE_ASPECT_RATIO_LANDSCAPE",
    (1024, 1792): "IMAGE_ASPECT_RATIO_PORTRAIT",
    (1280, 896):  "IMAGE_ASPECT_RATIO_LANDSCAPE",
    (896, 1280):  "IMAGE_ASPECT_RATIO_PORTRAIT",
}


def _resolve_model(model: str) -> str:
    """Map a 'flow/<alias>' model string to the Flow imageModelName."""
    raw = (model or "").strip().lower()
    if raw.startswith("flow/"):
        raw = raw[len("flow/"):]
    return _MODEL_ALIASES.get(raw, raw.upper() if raw else "NARWHAL")


def _resolve_aspect(size: str | None) -> str:
    if not size:
        return "IMAGE_ASPECT_RATIO_LANDSCAPE"
    if size in {"square", "1:1", "1024x1024"}:
        return "IMAGE_ASPECT_RATIO_SQUARE"
    if size in {"portrait", "9:16", "3:4", "1024x1792", "896x1280"}:
        return "IMAGE_ASPECT_RATIO_PORTRAIT"
    if size in {"landscape", "16:9", "4:3", "1792x1024", "1280x896"}:
        return "IMAGE_ASPECT_RATIO_LANDSCAPE"
    # Try WxH
    try:
        w, h = (int(x) for x in size.split("x"))
        if w == h:
            return "IMAGE_ASPECT_RATIO_SQUARE"
        return "IMAGE_ASPECT_RATIO_LANDSCAPE" if w > h else "IMAGE_ASPECT_RATIO_PORTRAIT"
    except (TypeError, ValueError):
        return "IMAGE_ASPECT_RATIO_LANDSCAPE"


# ── Account pool (in-process state) ───────────────────────────────────────

_pool_lock = threading.Lock()
# Account state by composite key (profile + project) so we don't collide
# across accounts that happen to share a profile.
_account_state: dict[str, dict[str, float]] = {}
# Round-robin cursor per provider config snapshot.
_rotation_index: dict[str, int] = {}

# How long to skip an account after a quota / 429 error.
_QUOTA_COOLDOWN_S = 3600.0


def _account_key(account: dict[str, Any]) -> str:
    return f"{account.get('profile', '')}::{account.get('project_id', '')}"


def _pool_config() -> dict[str, Any]:
    providers = config.data.get("providers") or {}
    cfg = providers.get("flow") or {}
    return cfg if isinstance(cfg, dict) else {}


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
    """Pick the next healthy account, skipping ones in cooldown."""
    accounts = _accounts()
    if not accounts:
        return None
    exclude = exclude or set()
    now = time.time()
    with _pool_lock:
        for offset in range(len(accounts)):
            idx = (_rotation_index.get("flow", 0) + offset) % len(accounts)
            acc = accounts[idx]
            key = _account_key(acc)
            if key in exclude:
                continue
            state = _account_state.get(key, {})
            cooldown_until = state.get("cooldown_until", 0)
            if cooldown_until and now < cooldown_until:
                continue
            _rotation_index["flow"] = (idx + 1) % len(accounts)
            return acc
        # All in cooldown — return the LEAST recently failed one anyway
        return accounts[_rotation_index.get("flow", 0) % len(accounts)]


def _mark_quota_exhausted(account: dict[str, Any]) -> None:
    with _pool_lock:
        key = _account_key(account)
        _account_state.setdefault(key, {})["cooldown_until"] = time.time() + _QUOTA_COOLDOWN_S
    logger.warning({"event": "flow_account_cooldown", "account": account.get("label"),
                    "cooldown_s": _QUOTA_COOLDOWN_S})


# ── Adapter ──────────────────────────────────────────────────────────────

class FlowImageAdapter(BaseImageAdapter):
    """OpenAI-image-compatible adapter that calls the captcha-solver Flow endpoint."""

    no_auth = False

    def get_key_count(self, credentials: dict[str, Any] | None) -> int:
        """Tell the dispatch layer how many accounts to retry across."""
        return max(1, len(_accounts()))

    def _current_account(self, key_try: int) -> dict[str, Any] | None:
        accounts = _accounts()
        if not accounts:
            return None
        # Re-derive index from key_try so each retry picks a different acct.
        idx = (_rotation_index.get("flow", 0) + key_try) % len(accounts)
        with _pool_lock:
            _rotation_index["flow"] = (idx + 1) % len(accounts)
        return accounts[idx]

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
        account = self._current_account(key_try)
        if credentials is not None and account is not None:
            credentials["_flow_account"] = account
        return f"{base}/v1/google/flow/generate-image"

    def build_body(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        prompt = str(body.get("prompt") or "")
        size = body.get("size") or "1792x1024"
        flow_model = _resolve_model(model)
        aspect = _resolve_aspect(str(size) if size else None)
        # Caller passes credentials separately, but build_body has no access
        # to them — the account choice lives on credentials, looked up via
        # build_headers right after. We add account here too if available.
        return {
            "prompt": prompt,
            "aspect_ratio": aspect,
            "model": flow_model,
            # binary mode for inline base64; the dispatch layer expects raw
            # JPEG/PNG and will base64-encode it.
            "return_binary": True,
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
