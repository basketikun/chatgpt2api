from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from curl_cffi import requests

from services.proxy_service import normalize_proxy_url


PROXY_INPUT_MODES = {"single", "url", "text"}
PROXY_LEASE_SECONDS = 120
NEW_PROXY_EXPLORATION_RATIO = 0.25
AGGRESSIVE_SOURCE_MODES = {"url", "text"}
HARD_FAILURE_BUCKETS = {"socks_handshake_failed", "proxy_closed", "proxy_connect_failed", "network_timeout"}


@dataclass(frozen=True)
class ProxyPoolSelection:
    proxy: str
    source: str
    count: int
    last_error: str
    last_fetch: float
    proxy_index: int = -1
    used_cooling_proxy: bool = False
    selection_reason: str = ""


@dataclass(frozen=True)
class ProxyPoolState:
    mode: str
    source: str
    count: int
    current_proxy: str
    last_fetch: float
    last_error: str


def normalize_proxy_input_mode(value: object) -> str:
    mode = str(value or "single").strip().lower()
    return mode if mode in PROXY_INPUT_MODES else "single"


def normalize_proxy_refresh_interval(value: object) -> int:
    try:
        return max(10, int(value or 120))
    except (OverflowError, TypeError, ValueError):
        return 120


def parse_proxy_lines(text: str) -> list[str]:
    proxies: list[str] = []
    seen: set[str] = set()
    for raw_line in str(text or "").replace(",", "\n").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        proxy = normalize_proxy_url(line)
        if not _is_supported_proxy_url(proxy) or proxy in seen:
            continue
        seen.add(proxy)
        proxies.append(proxy)
    return proxies


def _is_supported_proxy_url(proxy: str) -> bool:
    parsed = urlparse(proxy)
    return parsed.scheme in {"http", "https", "socks5", "socks5h"} and bool(parsed.netloc)


def _is_supported_source_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class RegisterProxyPool:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._mode = "single"
        self._single_proxy = ""
        self._proxy_url = ""
        self._proxy_list_text = ""
        self._refresh_interval = 120
        self._proxies: list[str] = []
        self._index = 0
        self._current_proxy = ""
        self._last_fetch = 0.0
        self._last_error = ""
        self._state_file = Path(__file__).resolve().parents[2] / "data" / "register_proxy_state.json"
        self._proxy_state: dict[str, dict[str, Any]] = self._load_proxy_state()
        self._run_selection_count = 0
        self._run_new_proxy_count = 0

    def configure(
        self,
        *,
        mode: str,
        single_proxy: str,
        proxy_url: str,
        proxy_list_text: str,
        refresh_interval: int,
        fetch_now: bool = False,
    ) -> ProxyPoolState:
        normalized_mode = normalize_proxy_input_mode(mode)
        normalized_single = normalize_proxy_url(single_proxy)
        normalized_url = str(proxy_url or "").strip()
        normalized_text = str(proxy_list_text or "")
        normalized_interval = normalize_proxy_refresh_interval(refresh_interval)

        with self._lock:
            changed_source = (
                normalized_mode != self._mode
                or normalized_single != self._single_proxy
                or normalized_url != self._proxy_url
                or normalized_text != self._proxy_list_text
            )
            self._mode = normalized_mode
            self._single_proxy = normalized_single
            self._proxy_url = normalized_url
            self._proxy_list_text = normalized_text
            self._refresh_interval = normalized_interval
            self._last_error = ""
            if changed_source:
                self._index = 0
                self._current_proxy = ""
            if normalized_mode == "single":
                self._proxies = [normalized_single] if normalized_single else []
                self._last_fetch = 0.0
            elif normalized_mode == "text":
                self._proxies = parse_proxy_lines(normalized_text)
                self._last_fetch = 0.0
            elif changed_source:
                self._proxies = []
                self._last_fetch = 0.0

        if normalized_mode == "url" and fetch_now:
            self.refresh_url(force=fetch_now)
        return self.state()

    def prepare(self) -> ProxyPoolState:
        with self._lock:
            mode = self._mode
        if mode == "url":
            self.refresh_url(force=True)
        with self._lock:
            self._reset_selection_cycle_locked()
        state = self.state()
        if state.mode in {"url", "text"} and state.count == 0:
            message = state.last_error or f"no proxies available for {state.mode} proxy source"
            raise RuntimeError(message)
        return state

    def reset_selection_cycle(self) -> ProxyPoolState:
        with self._lock:
            self._reset_selection_cycle_locked()
            return self.state()

    def next_proxy(self) -> ProxyPoolSelection:
        with self._lock:
            mode = self._mode
        if mode == "url" and self._should_refresh():
            self.refresh_url(force=False)

        with self._lock:
            if self._mode == "single":
                return ProxyPoolSelection(
                    proxy=self._single_proxy,
                    source="single" if self._single_proxy else "default",
                    count=len(self._proxies),
                    last_error=self._last_error,
                    last_fetch=self._last_fetch,
                    proxy_index=0 if self._single_proxy else -1,
                    selection_reason="single" if self._single_proxy else "direct",
                )
            if not self._proxies:
                return ProxyPoolSelection(
                    proxy="",
                    source=self._mode,
                    count=0,
                    last_error=self._last_error,
                    last_fetch=self._last_fetch,
                    selection_reason="no_proxy",
                )
            proxy, proxy_index, used_cooling_proxy, selection_reason = self._next_available_proxy_locked()
            self._current_proxy = proxy
            return ProxyPoolSelection(
                proxy=proxy,
                source=self._mode,
                count=len(self._proxies),
                last_error=self._last_error,
                last_fetch=self._last_fetch,
                proxy_index=proxy_index,
                used_cooling_proxy=used_cooling_proxy,
                selection_reason=selection_reason,
            )

    def refresh_url(self, *, force: bool) -> ProxyPoolState:
        with self._lock:
            url = self._proxy_url
            if self._mode != "url":
                return self.state()
            if not force and not self._should_refresh_locked():
                return self.state()

        if not _is_supported_source_url(url):
            self._record_error("proxy_url must be a valid http or https URL")
            return self.state()

        try:
            response = requests.get(url, timeout=15, verify=False)
            response.raise_for_status()
            proxies = parse_proxy_lines(response.text)
            with self._lock:
                self._proxies = proxies
                self._index = 0
                self._last_fetch = time.time()
                self._last_error = "" if proxies else "proxy URL returned no valid proxies"
        except Exception as error:
            self._record_error(f"failed to fetch proxy URL: {error}")
        return self.state()

    def state(self) -> ProxyPoolState:
        with self._lock:
            return ProxyPoolState(
                mode=self._mode,
                source=self._mode,
                count=len(self._proxies),
                current_proxy=self._current_proxy,
                last_fetch=self._last_fetch,
                last_error=self._last_error,
            )

    def _should_refresh(self) -> bool:
        with self._lock:
            return self._should_refresh_locked()

    def _should_refresh_locked(self) -> bool:
        if self._mode != "url":
            return False
        if not self._last_fetch:
            return True
        return time.time() - self._last_fetch >= self._refresh_interval

    def _record_error(self, message: str) -> None:
        with self._lock:
            self._last_error = str(message or "").strip()

    def proxy_state_metrics(self) -> dict[str, int]:
        now = time.time()
        with self._lock:
            blacklist_count = 0
            for state in self._proxy_state.values():
                if float(state.get("blacklist_until") or 0.0) > now or int(state.get("failure_count") or 0) > 0:
                    blacklist_count += 1
            return {
                "proxy_state_count": len(self._proxy_state),
                "proxy_blacklist_count": blacklist_count,
            }

    def reset_proxy_blacklist(self) -> dict[str, int]:
        with self._lock:
            removed = len(self._proxy_state)
            self._proxy_state = {}
            self._reset_selection_cycle_locked()
            self._save_proxy_state_locked()
            return {
                "removed_proxy_state_count": removed,
                "proxy_state_count": 0,
                "proxy_blacklist_count": 0,
            }

    def record_result(
        self,
        proxy: str,
        *,
        success: bool,
        error: str = "",
        cost_seconds: float = 0.0,
        platform_authorize_ms: float = 0.0,
    ) -> dict[str, Any]:
        normalized_proxy = normalize_proxy_url(proxy)
        if not normalized_proxy:
            return {"bucket": "no_proxy", "cooldown_seconds": 0}

        now = time.time()
        bucket = classify_proxy_failure(error)
        with self._lock:
            state = self._proxy_state.setdefault(normalized_proxy, {})
            state["last_seen"] = now
            state["last_cost_seconds"] = round(float(cost_seconds or 0.0), 3)
            state["lease_until"] = 0.0
            self._update_platform_authorize_average(state, platform_authorize_ms)
            if success:
                state["success_count"] = int(state.get("success_count") or 0) + 1
                state["consecutive_failures"] = 0
                state["consecutive_bucket"] = ""
                state["consecutive_bucket_count"] = 0
                state["blacklist_until"] = 0.0
                state["blacklist_reason"] = ""
                state["last_success"] = now
                state["score"] = self._bounded_score(float(state.get("score") or 0.0) + 3.0)
                self._save_proxy_state_locked()
                return {"bucket": "success", "cooldown_seconds": 0}

            has_success = int(state.get("success_count") or 0) > 0
            state["failure_count"] = int(state.get("failure_count") or 0) + 1
            state["last_failure"] = now
            state["last_failure_bucket"] = bucket
            state["last_error"] = str(error or "")[:500]
            state["consecutive_failures"] = int(state.get("consecutive_failures") or 0) + 1
            if state.get("consecutive_bucket") == bucket:
                state["consecutive_bucket_count"] = int(state.get("consecutive_bucket_count") or 0) + 1
            else:
                state["consecutive_bucket"] = bucket
                state["consecutive_bucket_count"] = 1

            state["score"] = self._bounded_score(float(state.get("score") or 0.0) + score_delta_for_bucket(bucket, has_success=has_success))
            cooldown_seconds = proxy_cooldown_seconds(
                bucket,
                int(state.get("consecutive_bucket_count") or 1),
                has_success=has_success,
                aggressive=self._mode in AGGRESSIVE_SOURCE_MODES,
            )
            if cooldown_seconds > 0:
                state["blacklist_until"] = max(float(state.get("blacklist_until") or 0.0), now + cooldown_seconds)
                state["blacklist_reason"] = bucket
            self._save_proxy_state_locked()
            return {"bucket": bucket, "cooldown_seconds": cooldown_seconds}

    def _next_available_proxy_locked(self) -> tuple[str, int, bool, str]:
        now = time.time()
        count = len(self._proxies)
        start_index = self._index
        candidates: list[tuple[tuple[float, ...], str, int, str]] = []
        history_exists = self._has_historical_proxy_locked()
        new_proxy_allowed = not history_exists or self._new_proxy_allowed_locked()
        for offset in range(count):
            index = (start_index + offset) % count
            proxy = self._proxies[index]
            state = self._proxy_state.get(proxy) or {}
            if self._is_proxy_blocked_locked(state, now):
                continue
            reason, bucket_order = self._selection_bucket(state)
            if reason == "new_proxy" and not new_proxy_allowed:
                continue
            score = float(state.get("score") or 0.0)
            avg_ms = float(state.get("avg_platform_authorize_ms") or 0.0) or 999999999.0
            failure_count = float(int(state.get("failure_count") or 0))
            last_selected_at = float(state.get("last_selected_at") or 0.0)
            candidates.append(((bucket_order, -score, avg_ms, failure_count, last_selected_at, float(offset)), reason, index, proxy))

        if candidates:
            _, reason, index, proxy = min(candidates, key=lambda item: item[0])
            self._index = index + 1
            self._lease_proxy_locked(proxy, now)
            self._record_selection_metric_locked(reason)
            return proxy, index, False, reason

        index, proxy = self._fallback_proxy_locked(start_index, now, avoid_new_proxy=history_exists and not new_proxy_allowed)
        proxy = self._proxies[index]
        self._index = index + 1
        state = self._proxy_state.get(proxy) or {}
        used_cooling_proxy = float(state.get("blacklist_until") or 0.0) > now
        self._lease_proxy_locked(proxy, now)
        self._record_selection_metric_locked("fallback_all_blocked")
        return proxy, index, used_cooling_proxy, "fallback_all_blocked"

    def _is_proxy_blocked_locked(self, state: dict[str, Any], now: float) -> bool:
        return float(state.get("blacklist_until") or 0.0) > now or float(state.get("lease_until") or 0.0) > now

    def _selection_bucket(self, state: dict[str, Any]) -> tuple[str, float]:
        if int(state.get("success_count") or 0) > 0:
            return "historical_success", 0.0
        if int(state.get("failure_count") or 0) == 0:
            return "new_proxy", 1.0
        return "retry_after_cooldown", 2.0

    def _fallback_proxy_locked(self, start_index: int, now: float, *, avoid_new_proxy: bool) -> tuple[int, str]:
        fallback: tuple[float, int, str] | None = None
        count = len(self._proxies)
        for prefer_history in (avoid_new_proxy, False):
            for offset in range(count):
                index = (start_index + offset) % count
                proxy = self._proxies[index]
                state = self._proxy_state.get(proxy) or {}
                if prefer_history and int(state.get("success_count") or 0) <= 0:
                    continue
                blocked_until = max(float(state.get("blacklist_until") or 0.0), float(state.get("lease_until") or 0.0))
                score = float(state.get("score") or 0.0)
                candidate = (blocked_until if blocked_until > now else now, -score, index, proxy)
                if fallback is None or candidate < fallback:
                    fallback = candidate
            if fallback is not None:
                break
        if fallback is None:
            index = start_index % count
            return index, self._proxies[index]
        return int(fallback[2]), str(fallback[3])

    def _lease_proxy_locked(self, proxy: str, now: float) -> None:
        state = self._proxy_state.setdefault(proxy, {})
        state["last_seen"] = now
        state["last_selected_at"] = now
        state["lease_until"] = now + PROXY_LEASE_SECONDS
        state["score"] = float(state.get("score") or 0.0)
        self._save_proxy_state_locked()

    def _update_platform_authorize_average(self, state: dict[str, Any], platform_authorize_ms: float) -> None:
        try:
            value = float(platform_authorize_ms or 0.0)
        except (OverflowError, TypeError, ValueError):
            value = 0.0
        if value <= 0:
            return
        current = float(state.get("avg_platform_authorize_ms") or 0.0)
        state["avg_platform_authorize_ms"] = round(value if current <= 0 else current * 0.75 + value * 0.25, 1)

    def _bounded_score(self, value: float) -> float:
        return round(max(-100.0, min(100.0, value)), 3)

    def _reset_selection_cycle_locked(self) -> None:
        self._index = 0
        self._run_selection_count = 0
        self._run_new_proxy_count = 0

    def _has_historical_proxy_locked(self) -> bool:
        return any(int((self._proxy_state.get(proxy) or {}).get("success_count") or 0) > 0 for proxy in self._proxies)

    def _new_proxy_allowed_locked(self) -> bool:
        return (self._run_new_proxy_count + 1) / max(1, self._run_selection_count + 1) <= NEW_PROXY_EXPLORATION_RATIO

    def _record_selection_metric_locked(self, reason: str) -> None:
        self._run_selection_count += 1
        if reason == "new_proxy":
            self._run_new_proxy_count += 1

    def _load_proxy_state(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            proxies = data.get("proxies") if isinstance(data, dict) else None
            return proxies if isinstance(proxies, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception:
            return {}

    def _save_proxy_state_locked(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        retained = {
            proxy: state
            for proxy, state in self._proxy_state.items()
            if float(state.get("blacklist_until") or 0.0) > now
            or float(state.get("lease_until") or 0.0) > now
            or int(state.get("failure_count") or 0) > 0
            or int(state.get("success_count") or 0) > 0
        }
        self._proxy_state = dict(sorted(retained.items(), key=lambda item: float(item[1].get("last_seen") or 0.0), reverse=True)[:20000])
        payload = {"version": 1, "updated_at": now, "proxies": self._proxy_state}
        temp_file = self._state_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temp_file.replace(self._state_file)


def classify_proxy_failure(error: str) -> str:
    text = str(error or "")
    if not text:
        return "unknown"
    if "等待注册验证码超时" in text:
        return "otp_timeout"
    if "cannot complete SOCKS" in text:
        return "socks_handshake_failed"
    if "connection to proxy closed" in text or "Proxy CONNECT aborted" in text or "Connection reset by peer" in text or "Recv failure" in text:
        return "proxy_closed"
    if "Failed to connect" in text or "Could not connect to server" in text:
        return "proxy_connect_failed"
    if "Operation timed out" in text or "curl: (28)" in text:
        return "network_timeout"
    if "Cloudflare" in text or "Just a moment" in text or "cf-ray=" in text:
        return "cloudflare_403"
    return "other"


def score_delta_for_bucket(bucket: str, *, has_success: bool = False) -> float:
    if bucket == "cloudflare_403":
        return -4.0 if has_success else -8.0
    if bucket in HARD_FAILURE_BUCKETS:
        return -5.0 if has_success else -10.0
    if bucket == "other":
        return -0.5 if has_success else -1.0
    return 0.0


def proxy_cooldown_seconds(bucket: str, consecutive_bucket_count: int, *, has_success: bool = False, aggressive: bool = False) -> int:
    if bucket in HARD_FAILURE_BUCKETS:
        if aggressive and not has_success:
            return 48 * 3600
        return 24 * 3600
    if bucket == "cloudflare_403":
        if aggressive and not has_success:
            return 24 * 3600
        if consecutive_bucket_count <= 1:
            seconds = 30 * 60
        elif consecutive_bucket_count == 2:
            seconds = 6 * 3600
        else:
            seconds = 24 * 3600
        if aggressive:
            return seconds
        return max(15 * 60, seconds // 2) if has_success else seconds
    return 0
