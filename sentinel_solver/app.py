"""Sentinel solver service: keeps a headless Chromium on chatgpt.com and computes Turnstile tokens.

Since 2026-10-14 the chatgpt.com conversation endpoint only accepts a Turnstile
token that was produced inside a real chatgpt.com page; a pure Python/Node
emulation is rejected. The main service does not bundle a browser, so it calls
this one over HTTP.

`vm.js` is a port of the two isomorphic VMs in the chatgpt.com frontend bundle
(the challenge program is served as an obfuscated instruction list and has to run
against the real `window`/`document`). It follows the implementation in
MEIZU16/chatgpt2api's `sentinel_solver/` (MIT), kept byte-identical so it can be
re-synced against the frontend bundle when OpenAI changes the instruction set.

Environment:
- SENTINEL_SOLVER_KEY: when set, requests must send `Authorization: Bearer <key>`
- SENTINEL_SOLVER_PROXY: outbound proxy for the browser, should match the main service egress
- SENTINEL_SOLVER_USER_AGENT: optional, defaults to a Linux Chrome UA built from the bundled Chromium
- SENTINEL_SOLVER_TIMEZONE: optional page timezone (e.g. Asia/Shanghai), should match the egress IP
- SENTINEL_SOLVER_REFRESH_SECONDS: how often the page is reopened, default 1800
- SENTINEL_SOLVER_HEADLESS: default true, set false to debug
- PORT: listen port, default 8080
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import hmac
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright_stealth import Stealth
from pydantic import BaseModel

from turnstile_result import is_retryable_solve_error, validate_turnstile_token

CHATGPT_URL = "https://chatgpt.com/"
CHALLENGE_TITLES = ("请稍候", "Just a moment", "Attention Required")
VM_SCRIPT = (Path(__file__).parent / "vm.js").read_text(encoding="utf-8")
BASE_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
"""

# Preferred path: load OpenAI's own turnstile chunk from this very page and let it
# compute the token against the real environment. A hand-ported VM has to track
# whatever the frontend does next; calling the shipped module does not.
#
# The chunk is content-hashed and changes on every deploy, so it is discovered at
# solve time instead of being pinned. See `_WALK_TURNSTILE_ASSET`.
_PINNED_ASSET = "/unauth-mweb/assets/turnstile-DykPLDEM.js"
_WALK_TURNSTILE_ASSET = """
async (maxChunks) => {
  // Match the module specifier and resolve it against the chunk that declares it —
  // the raw path in the bundle is relative ("./turnstile-<hash>.js") and would
  // otherwise be resolved against the wrong base.
  const target = /["'`]((?:\\.{0,2}\\/)?[A-Za-z0-9_./-]*\\/turnstile-[A-Za-z0-9_-]+\\.js)["'`]/;
  const specifier = /["'`]((?:\\.{0,2}\\/)?[A-Za-z0-9_./-]+\\.js)["'`]/g;
  const seen = new Set();
  const queue = [];
  const push = (url) => {
    if (!url || seen.has(url) || !url.startsWith(location.origin)) return;
    seen.add(url);
    queue.push(url);
  };
  // The turnstile chunk hangs off the sentinel subsystem, and a plain breadth-first
  // walk drowns in unrelated chunks first, so prefer sentinel-shaped URLs. This only
  // reorders the search: if nothing matches, the full walk still runs.
  const preferred = /sentinel|prewarm|turnstile/i;
  const shift = () => {
    const index = queue.findIndex((url) => preferred.test(url));
    return queue.splice(index === -1 ? 0 : index, 1)[0];
  };
  document.querySelectorAll('script[src], link[href]').forEach((node) => {
    const raw = node.src || node.href;
    if (raw && raw.split('?')[0].endsWith('.js')) push(new URL(raw, location.href).href);
  });
  // The document names most chunks through preload links rather than script tags, and
  // the live DOM can be missing some of them, so also read the raw HTML for both.
  try {
    const html = await (await fetch(location.href)).text();
    const refs = /(?:src|href)=["']([^"']+\\.js)["']/g;
    let ref;
    while ((ref = refs.exec(html)) !== null) push(new URL(ref[1], location.href).href);
  } catch (error) {}
  let fetched = 0;
  while (queue.length && fetched < maxChunks) {
    const url = shift();
    fetched++;
    let text;
    try {
      text = await (await fetch(url)).text();
    } catch (error) {
      continue;
    }
    const hit = text.match(target);
    if (hit) return { asset: new URL(hit[1], url).pathname, scanned: fetched };
    let match;
    specifier.lastIndex = 0;
    while ((match = specifier.exec(text)) !== null) {
      push(new URL(match[1], url).href);
    }
  }
  return { asset: null, scanned: fetched };
}
"""
_SOLVE_VIA_SDK = """
async ([requirements, key, asset]) => {
  try {
    const mod = await import(asset);
    const turnstile = mod.turnstile || (mod.default && mod.default.turnstile);
    if (!turnstile || typeof turnstile.getEnforcementToken !== 'function') {
      return 'ERR:getEnforcementToken missing';
    }
    // The seed map and token cache share the requirements key. Leave the cache
    // untouched, or the SDK returns the seed without running the challenge.
    const cache = turnstile.tokenCache;
    const original = WeakMap.prototype.get;
    WeakMap.prototype.get = function (target) {
      if (this === cache) return original.call(this, target);
      return target === requirements ? key : original.call(this, target);
    };
    let token;
    try {
      token = await turnstile.getEnforcementToken(requirements);
    } finally {
      WeakMap.prototype.get = original;
    }
    return String(token === undefined || token === null ? '' : token);
  } catch (error) {
    return 'ERR:' + String(error).slice(0, 300);
  }
}
"""
_SOLVE_VIA_VM = "([dx, p]) => window.__sentinelVM.turnstile(dx, p)"
_BROWSER_FETCH = """
async ([method, url, headers, body]) => {
  try {
    const resp = await fetch(url, { method, headers: headers || {}, body: body || undefined,
                                   redirect: 'error', signal: AbortSignal.timeout(30000) });
    const text = await resp.text();
    const out = {};
    resp.headers.forEach((value, key) => { out[key] = value; });
    return { status: resp.status, headers: out, text };
  } catch (error) {
    return { status: 0, headers: {}, text: 'ERR:' + String(error).slice(0, 400) };
  }
}
"""

SOLVER_KEY = os.getenv("SENTINEL_SOLVER_KEY", "").strip()
PROXY = os.getenv("SENTINEL_SOLVER_PROXY", "").strip()
USER_AGENT = os.getenv("SENTINEL_SOLVER_USER_AGENT", "").strip()
TIMEZONE = os.getenv("SENTINEL_SOLVER_TIMEZONE", "").strip()
REFRESH_SECONDS = max(60, int(os.getenv("SENTINEL_SOLVER_REFRESH_SECONDS", "1800")))
HEADLESS = os.getenv("SENTINEL_SOLVER_HEADLESS", "true").strip().lower() not in {"0", "false", "no"}
# Turnstile runs on a 500ms budget in the frontend and reports the step count on
# timeout, so a slow solve is not an error there. SO gets a real deadline.
# The ported VM inside vm.js keeps the frontend's own 500ms turnstile budget and
# 60s SO budget. The page's own module may need to fetch/parse on first use, so it
# gets room here.
ASSET_WALK_MAX_CHUNKS = 80
SDK_SOLVE_TIMEOUT_MS = 120000
SDK_SOLVE_ATTEMPTS = 3
READY_TIMEOUT_SECONDS = 60


# Per-exit lanes: one browser context per pool exit so the challenge is solved from the
# same IP the business request uses. LRU-capped, idle-reaped.
MAX_LANES = max(0, int(os.getenv("SENTINEL_SOLVER_MAX_LANES", "8")))
LANE_IDLE_SECS = max(60, int(os.getenv("SENTINEL_SOLVER_LANE_IDLE_SECS", "1800")))
# Playwright's per-context proxy takes server + optional username/password and handles
# proxy auth itself, so an authenticated exit needs no local relay.
_PROXY_SCHEME_MAP = {"socks5h": "socks5", "https": "http"}


def _lane_proxy_spec(proxy: str) -> dict[str, str]:
    """Turn a pool proxy URL into Playwright's per-context proxy argument.

    Playwright accepts ``{server, username, password}`` natively, so anonymous and
    authenticated exits both collapse to one dict. The returned ``server`` is the
    stable lane key.
    """
    raw = str(proxy or "").strip()
    if not raw:
        return {}
    if "://" not in raw:
        raw = "http://" + raw
    from urllib.parse import urlsplit

    parts = urlsplit(raw)
    scheme = (parts.scheme or "http").lower()
    host = parts.hostname or ""
    if not host:
        return {}
    host = f"[{host}]" if ":" in host else host
    netloc = f"{host}:{parts.port}" if parts.port else host
    spec = {"server": f"{_PROXY_SCHEME_MAP.get(scheme, scheme)}://{netloc}"}
    if parts.username:
        from urllib.parse import unquote
        spec["username"] = unquote(parts.username)
        spec["password"] = unquote(parts.password or "")
    return spec
class _Lane:
    """One Cloudflare-cleared chatgpt.com page bound to one egress proxy.

    The challenge program ties its proof to the browser context that solved it, so each
    pool exit gets its own context; the empty-key lane is the default egress.
    """

    def __init__(self, solver: "SolverPage", key: str, proxy_spec: dict[str, str]) -> None:
        self._solver = solver
        self.key = key
        self.proxy_spec = proxy_spec
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._opened_at = 0.0
        self._lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._turnstile_asset = ""
        self.cookies: dict[str, str] = {}
        self.last_error = ""
        self.last_used = time.monotonic()

    async def close(self) -> None:
        async with self._lock:
            await self._close_locked()

    async def _close_locked(self) -> None:
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:  # noqa: BLE001
                pass
        self._context = None
        self._page = None
        # A closed context takes its cookies with it, so stop reporting them.
        self.cookies = {}

    async def page(self) -> Page:
        async with self._lock:
            stale = self._page is None or time.monotonic() - self._opened_at > REFRESH_SECONDS
            if not stale and not await self._is_ready(self._page):
                stale = True
            if stale:
                await self._reopen()
            self.last_used = time.monotonic()
            return self._page

    async def invalidate(self) -> None:
        async with self._lock:
            self._opened_at = 0.0

    async def _reopen(self) -> None:
        await self._close_locked()
        context_kwargs: dict[str, object] = {
            "locale": "zh-CN",
            "viewport": {"width": 1280, "height": 800},
            "user_agent": self._solver.user_agent,
        }
        if self.proxy_spec:
            context_kwargs["proxy"] = self.proxy_spec
        if TIMEZONE:
            context_kwargs["timezone_id"] = TIMEZONE
        context = await self._solver._browser.new_context(**context_kwargs)
        # page.evaluate has no per-call timeout, so widen the context default; the
        # page's own module can take a moment on first use.
        context.set_default_timeout(SDK_SOLVE_TIMEOUT_MS)
        await context.add_init_script(BASE_INIT_SCRIPT)
        await context.add_init_script(VM_SCRIPT)
        await Stealth().apply_stealth_async(context)
        page = await context.new_page()
        await page.goto(CHATGPT_URL, wait_until="domcontentloaded", timeout=60000)
        deadline = time.monotonic() + READY_TIMEOUT_SECONDS
        while not await self._is_ready(page):
            if time.monotonic() > deadline:
                title = await page.title()
                await context.close()
                raise RuntimeError(
                    f"chatgpt.com page not ready (title={title!r}), likely stuck on a Cloudflare challenge"
                )
            await asyncio.sleep(1)
        self._context = context
        self._page = page
        self._opened_at = time.monotonic()
        self.last_error = ""
        await self._capture_cookies()
        label = f" (proxy={self.proxy_spec['server']})" if self.proxy_spec else ""
        print(f"[sentinel-solver] chatgpt.com page ready{label}: {await page.title()!r}", flush=True)

    async def _capture_cookies(self) -> None:
        """Record the chatgpt.com cookies this cleared page holds (see `exit_status`).

        Cloudflare scores some endpoints per client rather than per request: the
        same curl_cffi fingerprint gets a persistent 403 challenge on
        `/backend-api/sentinel/chat-requirements/prepare` without these cookies and
        is let through with them. Retrying does not substitute for them. The main
        service syncs them onto its own session for this lane's egress only.
        """
        self.cookies = {}
        if self._context is None:
            return
        try:
            jar = await self._context.cookies("https://chatgpt.com")
        except Exception as exc:  # noqa: BLE001
            print(f"[sentinel-solver] cookie capture failed: {exc}", flush=True)
            return
        self.cookies = {
            str(item.get("name")): str(item.get("value"))
            for item in jar
            if item.get("name") and item.get("value")
        }
        if self.cookies:
            print(f"[sentinel-solver] captured cookies: {', '.join(sorted(self.cookies))}", flush=True)

    @staticmethod
    async def _is_ready(page: Page | None) -> bool:
        if page is None or page.is_closed():
            return False
        try:
            title = await page.title()
            if any(marker in title for marker in CHALLENGE_TITLES):
                return False
            return await page.evaluate(
                "location.hostname === 'chatgpt.com' && typeof window.__sentinelVM === 'object'"
            )
        except Exception:  # noqa: BLE001
            return False

    async def turnstile_asset(self) -> str:
        """Locate chatgpt.com's own turnstile chunk.

        The file name is content-hashed and changes on every deploy, so walk the
        page's module graph for it. The pinned path is only a last resort, and the
        import that follows will fail loudly if it has gone stale.
        """
        if self._turnstile_asset:
            return self._turnstile_asset
        try:
            found = await self.evaluate(_WALK_TURNSTILE_ASSET, ASSET_WALK_MAX_CHUNKS) or {}
            asset = str((found or {}).get("asset") or "")
            scanned = (found or {}).get("scanned")
            if asset:
                self._turnstile_asset = asset
                print(f"[sentinel-solver] turnstile asset discovered: {asset} (after {scanned} chunks)", flush=True)
                return self._turnstile_asset
            print(f"[sentinel-solver] turnstile asset not referenced in {scanned} chunks", flush=True)
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
        print(f"[sentinel-solver] turnstile asset discovery fell back to {_PINNED_ASSET}", flush=True)
        self._turnstile_asset = _PINNED_ASSET
        return self._turnstile_asset

    async def solve_turnstile(self, requirements: dict[str, Any] | None, dx: str, p: str) -> tuple[bool, str]:
        """Solve via the page's own turnstile module, falling back to the ported VM."""
        if requirements:
            error = ""
            for attempt in range(1, SDK_SOLVE_ATTEMPTS + 1):
                asset = await self.turnstile_asset()
                try:
                    raw = str(await self.evaluate(_SOLVE_VIA_SDK, [requirements, p, asset]) or "")
                except Exception as exc:  # noqa: BLE001
                    error = str(exc)
                    break
                if raw.startswith("ERR:"):
                    error = raw[4:]
                    break
                error = validate_turnstile_token(raw, p)
                if not error:
                    return True, raw
                # Only a cold-page timeout is worth retrying; anything else is a real
                # failure and re-running it just wastes the caller's budget.
                if not is_retryable_solve_error(error) or attempt == SDK_SOLVE_ATTEMPTS:
                    break
                print(f"[sentinel-solver] {error} (attempt {attempt}/{SDK_SOLVE_ATTEMPTS})", flush=True)
            self.last_error = error[:300]
            print(f"[sentinel-solver] SDK solve failed: {error[:300]}", flush=True)
            # Drop the cached asset and page so the next attempt re-discovers both.
            self._turnstile_asset = ""
            await self.invalidate()
        if not dx:
            return False, self.last_error or "no dx and no requirements supplied"
        result = str(await self.evaluate(_SOLVE_VIA_VM, [dx, p]) or "")
        if result.startswith("ERR:"):
            return False, result[4:]
        error = validate_turnstile_token(result, p)
        return (False, error) if error else (True, result)

    async def clearance(self) -> dict[str, object]:
        """Cookies the challenge-cleared page holds, plus the user agent that earned them.

        Cloudflare binds its clearance to the client that solved the challenge, so the
        caller has to replay both the cookies and this UA, from the same egress.
        """
        page = await self.page()
        cookies = await self._context.cookies("https://chatgpt.com/")
        return {
            "user_agent": self._solver.user_agent,
            "page_url": CHATGPT_URL,
            "cookies": [
                {
                    "name": str(item.get("name") or ""),
                    "value": str(item.get("value") or ""),
                    "domain": str(item.get("domain") or ""),
                    "path": str(item.get("path") or "/"),
                }
                for item in cookies
                if item.get("name")
            ],
        }

    async def evaluate(self, expression: str, arg: object) -> object:
        """Run in the page, reopening once if the page turned out to be dead."""
        for attempt in range(2):
            page = await self.page()
            try:
                return await page.evaluate(expression, arg)
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
                if attempt:
                    raise
                await self.invalidate()
        raise RuntimeError("unreachable")

    async def browser_request(self, method: str, url: str, headers: dict[str, str], body: str) -> dict[str, object]:
        """Run a same-origin request through the page so it carries the browser identity.

        Headers that ``fetch`` forbids (Sec-*, User-Agent, Cookie, Origin, Referer,
        Host, Content-Length, ...) are dropped here rather than passed to the browser;
        those are owned by the page itself and a mismatch there is exactly what trips
        the fingerprint check.
        """
        exact_forbidden = {
            "user-agent", "cookie", "cookie2", "origin", "referer", "host",
            "content-length", "connection", "keep-alive", "te", "trailer",
            "transfer-encoding", "upgrade", "via", "date", "expect", "dnt",
            "accept", "accept-language", "accept-charset", "accept-encoding",
        }
        prefix_forbidden = ("sec-", "proxy-", "access-control-")
        allowed: dict[str, str] = {}
        for key, value in (headers or {}).items():
            name = str(key or "").strip().lower()
            if not name or name in exact_forbidden or name.startswith(prefix_forbidden):
                continue
            allowed[key] = str(value)
        async with self._request_lock:
            try:
                result = await self.evaluate(_BROWSER_FETCH, [method, url, allowed, body])
            finally:
                if self._context is not None:
                    await self._context.clear_cookies(name="oai-sc")
        return result if isinstance(result, dict) else {"status": 0, "headers": {}, "text": str(result)}

    def status(self) -> dict[str, object]:
        return {
            "ready": self._page is not None and not self._page.is_closed(),
            "proxy": self.proxy_spec.get("server"),
            "page_age_seconds": int(time.monotonic() - self._opened_at) if self._opened_at else None,
            "last_used_seconds_ago": int(time.monotonic() - self.last_used),
            "last_error": self.last_error or None,
            # Cookies the cleared page holds (mainly Cloudflare's __cf_bm / _cfuvid and
            # oai-did). They are bound to the IP that earned them, so they are reported
            # per lane and callers must take their own exit's set: see `exit_status`.
            "cookies": dict(self.cookies),
        }


class SolverPage:
    """Keeps one Cloudflare-cleared chatgpt.com page per egress lane, reopening them when stale."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._lanes: dict[str, _Lane] = {}
        self._lanes_lock = asyncio.Lock()
        self.user_agent = USER_AGENT
        self.last_error = ""

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        launch_kwargs = {
            "headless": HEADLESS,
            # channel="chromium" uses full Chromium's new headless mode; the default
            # headless shell cannot clear the Cloudflare challenge.
            "channel": "chromium",
            "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"],
        }
        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        if not self.user_agent:
            major = self._browser.version.split(".")[0]
            self.user_agent = (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
            )
        try:
            await (await self._lane("")).page()
        except Exception as exc:  # noqa: BLE001
            # A page that cannot open yet is not fatal; the first request retries.
            self.last_error = str(exc)
            print(f"[sentinel-solver] initial page open failed: {exc}", flush=True)

    async def stop(self) -> None:
        async with self._lanes_lock:
            lanes = list(self._lanes.values())
            self._lanes.clear()
        for lane in lanes:
            await lane.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    async def _lane(self, proxy: str) -> _Lane:
        spec = _lane_proxy_spec(proxy)
        key = self._lane_key(spec)
        now = time.monotonic()
        to_close: list[_Lane] = []
        async with self._lanes_lock:
            for lane_key, lane in list(self._lanes.items()):
                if lane_key and now - lane.last_used > LANE_IDLE_SECS:
                    del self._lanes[lane_key]
                    to_close.append(lane)
            lane = self._lanes.get(key)
            if lane is None:
                if MAX_LANES and len(self._lanes) >= MAX_LANES:
                    victim = min(
                        (l for k, l in self._lanes.items() if k),
                        key=lambda l: l.last_used,
                        default=None,
                    )
                    if victim is not None:
                        del self._lanes[victim.key]
                        to_close.append(victim)
                lane = _Lane(self, key, spec)
                self._lanes[key] = lane
        for stale in to_close:
            await stale.close()
        return lane

    @staticmethod
    def _lane_key(spec: dict[str, str]) -> str:
        """Stable lane key for a Playwright proxy spec, "" for the default egress.

        Credentials are part of the key: residential pools commonly share one
        host:port and distinguish exits by username, so dropping them would make one
        exit's cookies look like another's.
        """
        if not spec:
            return ""
        return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()

    async def exit_status(self, proxy: str) -> dict[str, object]:
        """Cookies the warmed lane for `proxy` holds, plus whether that lane is open.

        The caller must pass its own egress. Cloudflare binds these cookies to the IP
        that earned them, so another exit's set does nothing for this request, and the
        default lane here is the solver's own egress rather than the caller's. An empty
        `cookies` just means that exit has not been used yet: the caller has nothing to
        attach, which is not an error.

        Read-only by design, so a health probe never warms, evicts or reopens a lane.
        """
        key = self._lane_key(_lane_proxy_spec(proxy))
        if not key:
            return {"lane": None, "warmed": False, "cookies": {}}
        async with self._lanes_lock:
            lane = self._lanes.get(key)
            if lane is None:
                return {"lane": key, "warmed": False, "cookies": {}}
            return {"lane": key, "warmed": bool(lane.status()["ready"]), "cookies": dict(lane.cookies)}

    async def solve_turnstile(
        self, requirements: dict[str, Any] | None, dx: str, p: str, proxy: str = ""
    ) -> tuple[bool, str]:
        lane = await self._lane(proxy)
        async with lane._request_lock:
            return await lane.solve_turnstile(requirements, dx, p)

    async def clearance(self) -> dict[str, object]:
        return await (await self._lane("")).clearance()

    async def evaluate(self, expression: str, arg: object) -> object:
        return await (await self._lane("")).evaluate(expression, arg)

    async def browser_request(
        self, method: str, url: str, headers: dict[str, str], body: str, proxy: str = ""
    ) -> dict[str, object]:
        lane = await self._lane(proxy)
        return await lane.browser_request(method, url, headers, body)

    def status(self) -> dict[str, object]:
        return {
            "ready": self._browser is not None,
            "browser_version": self._browser.version if self._browser else None,
            "user_agent": self.user_agent,
            "timezone": TIMEZONE or None,
            "last_error": self.last_error or None,
            "lanes": {key: lane.status() for key, lane in self._lanes.items()},
        }


solver = SolverPage()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await solver.start()
    yield
    await solver.stop()


app = FastAPI(title="chatgpt2api sentinel solver", lifespan=lifespan)


class TurnstileRequest(BaseModel):
    proxy: str = ""
    p: str
    dx: str = ""
    # The full `/chat-requirements/prepare` response: pure challenge material
    # (prepare token, dx, proof-of-work seed, SO handle). No account token,
    # cookie or user prompt is ever sent here.
    requirements: dict[str, Any] | None = None


class SORequest(BaseModel):
    collector_dx: str
    snapshot_dx: str
    p: str


class BrowserRequest(BaseModel):
    proxy: str = ""
    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = {}
    body: str = ""


def require_key(authorization: str | None) -> None:
    if not SOLVER_KEY:
        return
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, SOLVER_KEY):
        raise HTTPException(status_code=401, detail="invalid solver key")


@app.get("/health")
async def health(proxy: str = "") -> dict[str, object]:
    """Solver status, plus the asked-for exit's cookies when `proxy` names one.

    `?proxy=<pool exit>` is how the main service picks up the cookies its own egress
    earned (see `SolverPage.exit_status`). The plain `/health` reports every lane's
    cookies for inspection but never merges them into one set, because a merged set
    would silently attach another exit's cookies to this request.
    """
    status = solver.status()
    if proxy.strip():
        status["exit"] = await solver.exit_status(proxy)
    return status


@app.post("/v1/turnstile")
async def solve_turnstile(body: TurnstileRequest, authorization: str | None = Header(default=None)) -> dict[str, str]:
    require_key(authorization)
    try:
        ok, token = await solver.solve_turnstile(body.requirements, body.dx, body.p, body.proxy)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"turnstile solve failed: {exc}") from exc
    if not ok:
        raise HTTPException(status_code=503, detail=f"turnstile solve failed: {token[:300]}")
    return {"token": token}


@app.post("/v1/request")
async def browser_request(body: BrowserRequest, authorization: str | None = Header(default=None)) -> dict[str, object]:
    require_key(authorization)
    target = urlsplit(body.url)
    routes = {
        "/backend-api/me": "GET",
        "/backend-api/conversation/init": "POST",
        "/backend-api/accounts/check/v4-2023-04-27": "GET",
        **{f"/{base}/sentinel/chat-requirements/{step}": "POST"
           for base in ("backend-api", "backend-anon") for step in ("prepare", "finalize")},
    }
    if (target.scheme != "https" or target.netloc != "chatgpt.com" or target.fragment
            or routes.get(target.path) != body.method.upper()):
        raise HTTPException(status_code=400, detail="browser request URL is not allowed")
    forbidden = {
        "user-agent", "cookie", "cookie2", "origin", "referer", "host", "content-length",
        "connection", "keep-alive", "te", "trailer", "transfer-encoding", "upgrade", "via",
        "date", "expect", "dnt", "accept", "accept-language", "accept-charset", "accept-encoding",
    }
    prefix_forbidden = ("sec-", "proxy-", "access-control-")
    headers = {}
    for key, value in (body.headers or {}).items():
        name = str(key or "").strip().lower()
        if name and name not in forbidden and not name.startswith(prefix_forbidden):
            headers[str(key)] = str(value)
    try:
        result = await solver.browser_request(body.method.upper(), body.url, headers, body.body, body.proxy)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"browser request failed: {exc}") from exc
    return result if isinstance(result, dict) else {"status": 0, "headers": {}, "text": str(result)}


@app.post("/v1/so")
async def solve_so(body: SORequest, authorization: str | None = Header(default=None)) -> dict[str, str]:
    require_key(authorization)
    try:
        token = await solver.evaluate(
            "([c, s, p]) => window.__sentinelVM.so(c, s, p)", [body.collector_dx, body.snapshot_dx, body.p]
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"so solve failed: {exc}") from exc
    return {"token": str(token or "")}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")), access_log=False)
