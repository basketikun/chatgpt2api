"""HTTP client for the cloak-bridge Node service.

The captcha-solver normally drives `patchright` (a stealth Playwright fork)
directly from Python. Patchright's stealth patches are good enough for
most flows but Cloudflare Turnstile, ChatGPT signup, and some Google
endpoints have started flagging it on heavily-trafficked datacenter IPs.
CloakBrowser adds a second layer of stealth (different fingerprint
patches), so we keep both available and pick the one most likely to win
for a given target.

This module is a thin async wrapper around `cloak-bridge/server.js` — a
Node HTTP service that owns the cloakbrowser process. We talk to it via
JSON HTTP instead of bundling Node into every Python call path.

Wire:
    POST /launch                 → ensure profile context exists
    POST /navigate               → page.goto
    POST /get_html               → page.content
    POST /get_text               → page.innerText (optional selector)
    POST /click                  → page.click
    POST /type                   → page.fill
    POST /evaluate               → page.evaluate
    POST /wait_for_selector      → page.waitForSelector
    POST /screenshot             → page.screenshot (returns base64 png)
    POST /cookies                → browser.cookies (per-profile)
    POST /close                  → close & evict the profile
    GET  /health                 → liveness probe

Usage:
    from .cloak_client import cloak

    async with cloak.session("chatgpt") as page:
        await page.navigate("https://chatgpt.com/")
        html = await page.get_html()
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)


def _default_url() -> str:
    """Resolve the cloak-bridge URL from the environment.

    Docker compose typically runs cloak-bridge on the same container with
    supervisord, so localhost:8011 is the default. A dedicated sidecar
    container can override via CLOAK_BRIDGE_URL.
    """
    return os.environ.get("CLOAK_BRIDGE_URL", "http://127.0.0.1:8011").rstrip("/")


class CloakBridgeError(RuntimeError):
    """Raised when the bridge returns ok=false or HTTP errors."""


class CloakPage:
    """High-level helpers bound to a (profile, pageId) pair on the bridge."""

    def __init__(self, client: "CloakClient", profile: str, page_id: str = "default") -> None:
        self._client = client
        self.profile = profile
        self.page_id = page_id

    async def navigate(self, url: str, *, timeout: float = 30.0, wait_until: str = "domcontentloaded") -> str:
        data = await self._client._post(
            "/navigate",
            {
                "profile": self.profile,
                "pageId": self.page_id,
                "url": url,
                "timeout": int(timeout * 1000),
                "waitUntil": wait_until,
            },
        )
        return str(data.get("url") or "")

    async def get_html(self) -> str:
        data = await self._client._post(
            "/get_html", {"profile": self.profile, "pageId": self.page_id}
        )
        return str(data.get("html") or "")

    async def get_text(self, selector: str | None = None) -> str:
        payload: dict[str, Any] = {"profile": self.profile, "pageId": self.page_id}
        if selector:
            payload["selector"] = selector
        data = await self._client._post("/get_text", payload)
        return str(data.get("text") or "")

    async def click(self, selector: str, *, timeout: float = 10.0) -> None:
        await self._client._post(
            "/click",
            {
                "profile": self.profile,
                "pageId": self.page_id,
                "selector": selector,
                "timeout": int(timeout * 1000),
            },
        )

    async def fill(self, selector: str, text: str, *, timeout: float = 10.0) -> None:
        await self._client._post(
            "/type",
            {
                "profile": self.profile,
                "pageId": self.page_id,
                "selector": selector,
                "text": text,
                "timeout": int(timeout * 1000),
            },
        )

    async def evaluate(self, script: str) -> Any:
        data = await self._client._post(
            "/evaluate",
            {"profile": self.profile, "pageId": self.page_id, "script": script},
        )
        return data.get("result")

    async def wait_for_selector(self, selector: str, *, timeout: float = 30.0, state: str = "visible") -> None:
        await self._client._post(
            "/wait_for_selector",
            {
                "profile": self.profile,
                "pageId": self.page_id,
                "selector": selector,
                "timeout": int(timeout * 1000),
                "state": state,
            },
        )

    async def screenshot(self, *, full_page: bool = True) -> bytes:
        import base64

        data = await self._client._post(
            "/screenshot",
            {"profile": self.profile, "pageId": self.page_id, "fullPage": full_page},
        )
        return base64.b64decode(str(data.get("png_b64") or ""))


class CloakClient:
    """Async client for the cloak-bridge HTTP service."""

    def __init__(self, base_url: str | None = None, *, request_timeout: float = 60.0) -> None:
        self.base_url = (base_url or _default_url()).rstrip("/")
        self._timeout = request_timeout
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        client = await self._ensure_client()
        resp = await client.post(f"{self.base_url}{path}", json=payload)
        try:
            data = resp.json()
        except Exception as exc:
            raise CloakBridgeError(
                f"non-JSON response from cloak-bridge {path}: HTTP {resp.status_code} {resp.text[:200]}"
            ) from exc
        if resp.status_code >= 400 or not data.get("ok", True):
            raise CloakBridgeError(
                f"cloak-bridge {path} failed: {data.get('error') or f'HTTP {resp.status_code}'}"
            )
        return data

    async def health(self) -> bool:
        try:
            client = await self._ensure_client()
            resp = await client.get(f"{self.base_url}/health")
            return resp.status_code == 200 and resp.json().get("ok") is True
        except Exception as exc:
            logger.warning("cloak-bridge health check failed: %s", exc)
            return False

    async def launch(self, profile: str = "default") -> None:
        await self._post("/launch", {"profile": profile})

    async def cookies(self, profile: str = "default") -> list[dict[str, Any]]:
        data = await self._post("/cookies", {"profile": profile})
        cookies = data.get("cookies") or []
        return list(cookies) if isinstance(cookies, list) else []

    async def close_profile(self, profile: str) -> bool:
        try:
            data = await self._post("/close", {"profile": profile})
            return bool(data.get("ok"))
        except CloakBridgeError:
            return False

    def page(self, profile: str = "default", page_id: str = "default") -> CloakPage:
        return CloakPage(self, profile=profile, page_id=page_id)

    @asynccontextmanager
    async def session(self, profile: str = "default", page_id: str = "default") -> AsyncIterator[CloakPage]:
        """Convenience: ensure context is launched, yield a page, keep
        the context alive on exit (cookies persist for the next call).
        """
        await self.launch(profile)
        yield self.page(profile, page_id)


cloak = CloakClient()


def is_enabled() -> bool:
    """Feature flag: read CLOAK_BROWSER_ENABLED at call time (so a runtime
    env change can flip behaviour without restarting the captcha-solver).
    """
    return os.environ.get("CLOAK_BROWSER_ENABLED", "0").strip().lower() in {
        "1", "true", "yes", "on",
    }
