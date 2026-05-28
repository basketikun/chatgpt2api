"""
Usage Snapshot Poller — proactive rate-limit monitoring like codext.

Ported from codext codex-rs/tui/src/chatwidget/rate_limits.rs:
  - Background polling every 15s for rate-limit snapshots
  - Warning thresholds: 75%, 90%, 95% usage
  - Parse x-codex-primary-reset-at and x-codex-secondary-reset-at headers
  - Identify 5h/daily/weekly/monthly window labels
  - Track primary and secondary usage windows

Also integrates with the existing codext codex-rs/chatgpt/src/chatgpt_client.rs
pattern: GET requests to ChatGPT backend API with Codex auth headers.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from utils.log import logger

# Polling interval (matches codext's RATE_LIMIT_REFRESH_INTERVAL_SECS)
POLL_INTERVAL_SECONDS = 15

# Warning thresholds — mirrors codext's RATE_LIMIT_WARNING_THRESHOLDS
WARNING_THRESHOLDS = [75.0, 90.0, 95.0]

# Window duration labels — mirrors codext's get_limits_duration()
WINDOW_5H_MINUTES = 5 * 60
WINDOW_DAILY_MINUTES = 24 * 60
WINDOW_WEEKLY_MINUTES = 7 * 24 * 60
WINDOW_MONTHLY_MINUTES = 30 * 24 * 60

# Account fetch timeout (codext uses 2s for git, 60s for connectors)
FETCH_TIMEOUT_SECONDS = 15


@dataclass
class UsageWindow:
    """A single usage window (primary or secondary)."""
    used_percent: float = 0.0
    remaining_percent: float = 100.0
    window_duration_mins: int | None = None
    window_label: str = "usage"
    resets_at: str = ""  # ISO timestamp or unix
    resets_in_seconds: int = 0


@dataclass
class AccountUsageSnapshot:
    """Full usage snapshot for one account — mirrors codext's RateLimitSnapshot."""
    account_id: str = ""
    account_email: str = ""
    plan_type: str = ""  # Plus/Team/Pro/Free
    primary: UsageWindow | None = None
    secondary: UsageWindow | None = None
    has_quota: bool = True
    rate_limit_reached: bool = False
    fetched_at: float = field(default_factory=time.time)
    fetch_error: str = ""


class UsageSnapshotPoller:
    """Proactive rate-limit polling service.

    Ports codext's background poll loop:
    - Every 15s fetches usage for all active accounts
    - Parses Codex/chatgpt.com rate-limit headers
    - Tracks warning thresholds (75/90/95%)
    - Emits events when thresholds crossed
    - Provides snapshot data for status display
    """

    def __init__(self):
        self._lock = threading.Lock()
        # {account_id: AccountUsageSnapshot}
        self._snapshots: dict[str, AccountUsageSnapshot] = {}
        # Track which thresholds we've already warned about per account
        # {account_id: {window_key: last_warned_threshold}}
        self._warned_thresholds: dict[str, dict[str, float]] = {}
        # Track last known account emails for identity change detection
        self._last_accounts: set[str] = set()
        # Callbacks
        self._on_quota_recovered_callbacks: list[callable] = []
        self._on_warning_callbacks: list[callable] = []
        self._on_limit_reached_callbacks: list[callable] = []
        # Background task handle
        self._task: asyncio.Task | None = None
        self._running = False

    # ── Public API ──────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info({"event": "usage_poller_started", "interval_s": POLL_INTERVAL_SECONDS})

    async def stop(self) -> None:
        """Stop the background polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def get_snapshot(self, account_id: str) -> AccountUsageSnapshot | None:
        """Get the latest snapshot for an account."""
        with self._lock:
            return self._snapshots.get(account_id)

    def get_all_snapshots(self) -> dict[str, AccountUsageSnapshot]:
        """Get all current snapshots (for status display)."""
        with self._lock:
            return dict(self._snapshots)

    def has_any_quota_available(self) -> bool:
        """Check if any account has quota remaining (like codext's
        rate_limit_snapshot_has_available_quota)."""
        with self._lock:
            for snap in self._snapshots.values():
                if snap.has_quota and not snap.rate_limit_reached:
                    return True
            return False

    def get_accounts_near_limit(self, threshold: float = 90.0) -> list[dict]:
        """Get accounts approaching rate limit (>threshold% used)."""
        with self._lock:
            near = []
            for aid, snap in self._snapshots.items():
                primary_pct = snap.primary.used_percent if snap.primary else 0
                secondary_pct = snap.secondary.used_percent if snap.secondary else 0
                if primary_pct >= threshold or secondary_pct >= threshold:
                    near.append({
                        "account_id": aid,
                        "email": snap.account_email,
                        "primary_used_pct": primary_pct,
                        "secondary_used_pct": secondary_pct,
                        "plan": snap.plan_type,
                    })
            return near

    def on_snapshot(self, callback: callable) -> None:
        """Register callback(account_id, snapshot) for each poll cycle."""
        self._on_quota_recovered_callbacks.append(callback)

    def on_warning(self, callback: callable) -> None:
        """Register callback(account_id, warning_text, threshold) for threshold crossings."""
        self._on_warning_callbacks.append(callback)

    def on_limit_reached(self, callback: callable) -> None:
        """Register callback(account_id, snapshot) when 100% usage reached."""
        self._on_limit_reached_callbacks.append(callback)

    # ── Internal ──────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        """Main polling loop — mirrors codext's start_rate_limit_poller()."""
        while self._running:
            try:
                await self._fetch_all_accounts()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception({"event": "usage_poller_cycle_error"})
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _fetch_all_accounts(self) -> None:
        """Fetch usage snapshots for all active accounts."""
        try:
            from services.account_service import account_service
        except Exception:
            return

        accounts = account_service.list_accounts()
        current_ids = set()

        for account in accounts:
            access_token = str(account.get("access_token") or "")
            if not access_token:
                continue
            account_id = access_token[:40]  # Use token prefix as key
            current_ids.add(account_id)

            # Check account change detection
            with self._lock:
                if account_id not in self._snapshots:
                    self._snapshots[account_id] = AccountUsageSnapshot(
                        account_id=account_id,
                        account_email=str(account.get("email") or "")[:80],
                        plan_type=str(account.get("plan") or account.get("type") or ""),
                    )

            # Fetch usage in thread pool (curl_cffi is sync)
            try:
                snapshot = await asyncio.to_thread(
                    self._fetch_account_usage, access_token
                )
            except Exception as exc:
                snapshot = AccountUsageSnapshot(
                    account_id=account_id,
                    fetch_error=str(exc)[:200],
                )

            with self._lock:
                old_snap = self._snapshots.get(account_id)
                self._snapshots[account_id] = snapshot
                # Detect quota recovery
                if old_snap and old_snap.rate_limit_reached and not snapshot.rate_limit_reached:
                    for cb in self._on_quota_recovered_callbacks:
                        try:
                            cb(account_id, snapshot)
                        except Exception:
                            pass
                # Check warnings
                self._check_warnings(account_id, snapshot)

        # Detect account changes (removals)
        with self._lock:
            removed = self._last_accounts - current_ids
            for rid in removed:
                self._snapshots.pop(rid, None)
                self._warned_thresholds.pop(rid, None)
            self._last_accounts = current_ids

    def _fetch_account_usage(self, access_token: str) -> AccountUsageSnapshot:
        """Fetch usage data for a single account via chatgpt.com backend API.

        Ported from codext chatgpt_client.rs pattern:
        GET {chatgpt_base_url}/backend-api/sentinel/chat-requirements
        with OAI-Product-Sku: codex header.
        """
        snap = AccountUsageSnapshot(account_id=access_token[:40])
        try:
            from curl_cffi import requests
            import uuid

            headers = {
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "Mozilla/5.0",
                "OAI-Device-Id": str(uuid.uuid4()),
                "Content-Type": "application/json",
            }

            # Use the sentinel endpoint which returns quota info
            resp = requests.post(
                "https://chatgpt.com/backend-api/sentinel/chat-requirements",
                headers=headers,
                json={"p": "", "conversation_mode": {"kind": "chat"}},
                timeout=FETCH_TIMEOUT_SECONDS,
                impersonate="chrome110",
            )

            if resp.status_code == 200:
                snap.has_quota = True
                # Parse rate-limit headers (codext-style)
                self._parse_rate_limit_headers(snap, dict(resp.headers))
            elif resp.status_code == 401:
                snap.has_quota = False
                snap.fetch_error = "unauthorized"
            elif resp.status_code == 429:
                snap.has_quota = False
                snap.rate_limit_reached = True
                self._parse_rate_limit_headers(snap, dict(resp.headers))
                snap.fetch_error = "rate_limited"
            else:
                snap.fetch_error = f"http_{resp.status_code}"

        except Exception as exc:
            snap.fetch_error = str(exc)[:200]

        snap.fetched_at = time.time()
        return snap

    def _parse_rate_limit_headers(
        self, snap: AccountUsageSnapshot, headers: dict
    ) -> None:
        """Parse Codex rate-limit headers into structured usage windows.

        Headers (from codext's observed behavior):
        - x-codex-primary-used-percent: 85
        - x-codex-primary-reset-at: unix timestamp
        - x-codex-secondary-used-percent: 45
        - x-codex-secondary-reset-at: unix timestamp
        - x-codex-plan-type: plus / team / pro
        """
        try:
            primary_pct_str = headers.get("x-codex-primary-used-percent", "")
            if primary_pct_str:
                pct = float(primary_pct_str)
                reset_at = headers.get("x-codex-primary-reset-at", "")
                reset_iso = ""
                reset_secs = 0
                if reset_at and reset_at.strip().isdigit():
                    try:
                        from datetime import datetime, timezone
                        reset_ts = int(reset_at)
                        reset_iso = datetime.fromtimestamp(reset_ts, tz=timezone.utc).isoformat()
                        reset_secs = max(0, reset_ts - int(time.time()))
                    except (ValueError, OSError):
                        pass
                window_mins = self._guess_window_minutes(reset_secs)
                snap.primary = UsageWindow(
                    used_percent=pct,
                    remaining_percent=max(0, 100.0 - pct),
                    window_duration_mins=window_mins,
                    window_label=self._window_label(window_mins),
                    resets_at=reset_iso,
                    resets_in_seconds=reset_secs,
                )
                if pct >= 100.0:
                    snap.rate_limit_reached = True
        except (ValueError, TypeError):
            pass

        try:
            secondary_pct_str = headers.get("x-codex-secondary-used-percent", "")
            if secondary_pct_str:
                pct = float(secondary_pct_str)
                reset_at = headers.get("x-codex-secondary-reset-at", "")
                reset_iso = ""
                reset_secs = 0
                if reset_at and reset_at.strip().isdigit():
                    try:
                        from datetime import datetime, timezone
                        reset_ts = int(reset_at)
                        reset_iso = datetime.fromtimestamp(reset_ts, tz=timezone.utc).isoformat()
                        reset_secs = max(0, reset_ts - int(time.time()))
                    except (ValueError, OSError):
                        pass
                window_mins = self._guess_window_minutes(reset_secs)
                snap.secondary = UsageWindow(
                    used_percent=pct,
                    remaining_percent=max(0, 100.0 - pct),
                    window_duration_mins=window_mins,
                    window_label=self._window_label(window_mins),
                    resets_at=reset_iso,
                    resets_in_seconds=reset_secs,
                )
        except (ValueError, TypeError):
            pass

        # Parse plan type
        plan = headers.get("x-codex-plan-type", "")
        if plan:
            snap.plan_type = plan

        # Parse account email if available
        email = headers.get("x-codex-account-email", "")
        if email:
            snap.account_email = email

    @staticmethod
    def _guess_window_minutes(reset_seconds: int) -> int | None:
        """Guess the window duration from reset time.

        Mirrors codext's get_limits_duration() pattern.
        """
        if reset_seconds <= 0:
            return None
        # Approximate window matching (within 5% tolerance, like codext)
        mins = reset_seconds // 60
        candidates = [
            (WINDOW_5H_MINUTES, 0.05),
            (WINDOW_DAILY_MINUTES, 0.05),
            (WINDOW_WEEKLY_MINUTES, 0.05),
            (WINDOW_MONTHLY_MINUTES, 0.05),
        ]
        for window_mins, tolerance in candidates:
            if abs(mins - window_mins) / max(window_mins, 1) <= tolerance:
                return window_mins
        return mins  # Return as-is if no match

    @staticmethod
    def _window_label(window_mins: int | None) -> str:
        """Human-readable window label — mirrors codext's limit_label_for_window()."""
        if window_mins is None:
            return "usage"
        if window_mins == WINDOW_5H_MINUTES:
            return "5h"
        elif window_mins == WINDOW_DAILY_MINUTES:
            return "daily"
        elif window_mins == WINDOW_WEEKLY_MINUTES:
            return "weekly"
        elif window_mins == WINDOW_MONTHLY_MINUTES:
            return "monthly"
        return f"{window_mins}m"

    def _check_warnings(self, account_id: str, snap: AccountUsageSnapshot) -> None:
        """Emit warnings when usage crosses thresholds.

        Mirrors codext's RateLimitWarningState::take_warnings().
        """
        self._warned_thresholds.setdefault(account_id, {})
        warned = self._warned_thresholds[account_id]

        for window_key, window in [("primary", snap.primary), ("secondary", snap.secondary)]:
            if window is None:
                continue
            if window.used_percent >= 100.0:
                for cb in self._on_limit_reached_callbacks:
                    try:
                        cb(account_id, snap)
                    except Exception:
                        pass
                continue

            last_warned = warned.get(window_key, 0.0)
            for threshold in WARNING_THRESHOLDS:
                if window.used_percent >= threshold and last_warned < threshold:
                    warned[window_key] = threshold
                    warning_text = (
                        f"Heads up, you have less than {100.0 - threshold:.0f}% "
                        f"of your {window.window_label} {window_key} limit left."
                    )
                    for cb in self._on_warning_callbacks:
                        try:
                            cb(account_id, warning_text, threshold)
                        except Exception:
                            pass
                    logger.info({
                        "event": "usage_warning",
                        "account": account_id,
                        "window": window_key,
                        "used_pct": window.used_percent,
                        "threshold": threshold,
                        "message": warning_text,
                    })

    def get_status_summary(self) -> dict[str, Any]:
        """Rich status summary for display (like codext's status header).

        Returns data suitable for a dashboard or status endpoint.
        """
        with self._lock:
            accounts = []
            total_quota = 0
            limited_count = 0
            for aid, snap in self._snapshots.items():
                primary = snap.primary
                acct = {
                    "id": aid,
                    "email": snap.account_email,
                    "plan": snap.plan_type,
                    "has_quota": snap.has_quota,
                    "rate_limit_reached": snap.rate_limit_reached,
                    "primary_remaining_pct": round(primary.remaining_percent, 1) if primary else None,
                    "primary_window": primary.window_label if primary else None,
                    "primary_resets_at": primary.resets_at if primary else None,
                    "secondary_remaining_pct": round(snap.secondary.remaining_percent, 1) if snap.secondary else None,
                    "fetched_seconds_ago": round(time.time() - snap.fetched_at, 1),
                    "error": snap.fetch_error or None,
                }
                accounts.append(acct)
                if snap.has_quota:
                    total_quota += 1
                if snap.rate_limit_reached:
                    limited_count += 1

            return {
                "total_accounts": len(self._snapshots),
                "accounts_with_quota": total_quota,
                "rate_limited_accounts": limited_count,
                "poll_interval_s": POLL_INTERVAL_SECONDS,
                "accounts": accounts,
            }


# Singleton
usage_snapshot_poller = UsageSnapshotPoller()
