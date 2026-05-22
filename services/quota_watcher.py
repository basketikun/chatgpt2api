"""
Quota Watcher — proactive token refresh scheduler.

Ports the min-heap priority queue pattern from CLIProxyAPI's auto_refresh_loop.go.
Runs as a background asyncio task, checking account quotas periodically and
refreshing tokens BEFORE they hit zero or expire.

Key differences from reactive-only approach:
- Predicts quota exhaustion and refreshes proactively
- Maintains a min-heap sorted by next check time
- Supports concurrent refresh workers
- Tracks restore_at for automatic re-enablement
"""

from __future__ import annotations

import asyncio
import heapq
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from services.account_service import account_service
from services.config import config
from utils.log import logger

# Refresh check interval (seconds) — how often to re-evaluate each account
DEFAULT_CHECK_INTERVAL = 300  # 5 minutes

# Lead time before quota exhaustion to trigger refresh (seconds)
QUOTA_EXHAUSTION_LEAD = 600  # 10 minutes

# Max concurrent refresh workers
MAX_REFRESH_WORKERS = 4

# Cooldown after a failed refresh attempt (seconds)
REFRESH_FAILURE_COOLDOWN = 300  # 5 minutes


@dataclass(order=True)
class QuotaCheckItem:
    """Min-heap entry ordered by next_check_at."""
    next_check_at: float
    account_id: str = field(compare=False)
    provider: str = field(compare=False)


class QuotaWatcher:
    """Background scheduler that proactively checks and refreshes account quotas.

    Uses a min-heap priority queue (like CLIProxyAPI's authAutoRefreshLoop).
    Accounts with approaching quota exhaustion or expiry are checked first.
    """

    def __init__(self):
        self._heap: list[QuotaCheckItem] = []
        self._index: dict[str, QuotaCheckItem] = {}  # account_id -> item
        self._running = False
        self._task: asyncio.Task | None = None
        self._wake_event = asyncio.Event()
        self._refresh_semaphore = asyncio.Semaphore(MAX_REFRESH_WORKERS)

    # ── Public API ──────────────────────────────────────────────

    async def start(self):
        """Start the background watcher loop."""
        if self._running:
            return
        self._running = True
        self._rebuild()
        logger.info({"event": "quota_watcher_started", "accounts": len(self._heap)})
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        """Stop the background watcher loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info({"event": "quota_watcher_stopped"})

    def schedule_now(self, account_id: str):
        """Force immediate recheck of a specific account."""
        self._wake_event.set()

    def _rebuild(self):
        """Rebuild the min-heap from all accounts."""
        try:
            accounts = account_service.list_accounts()
        except Exception as e:
            logger.error({"event": "quota_watcher_rebuild_error", "error": str(e)})
            return
        now = time.time()

        self._heap.clear()
        self._index.clear()

        count = 0
        for account in accounts:
            if not isinstance(account, dict):
                continue
            acc_id = account.get("access_token", "")
            if not acc_id:
                continue

            status = str(account.get("status", ""))
            quota = int(account.get("quota") or 0)

            # Skip disabled/abnormal accounts
            if status in ("disabled", "error"):
                continue

            # Determine next check time
            next_check = self._next_check_time(account, now)

            item = QuotaCheckItem(next_check_at=next_check, account_id=acc_id, provider="chatgpt")
            heapq.heappush(self._heap, item)
            self._index[acc_id] = item
            count += 1

        logger.info({"event": "quota_watcher_rebuilt", "accounts": count, "total_in_pool": len(accounts)})

    def _next_check_time(self, account: dict[str, Any], now: float) -> float:
        """Calculate when this account should next be checked.

        Priority rules (like CLIProxyAPI's nextRefreshCheckAt):
        1. Low quota (< 5) → check in 1 minute
        2. Rate-limited → check at restore_at time
        3. Normal → check in DEFAULT_CHECK_INTERVAL
        4. Never used → check now
        """
        status = account.get("status", "")
        quota = int(account.get("quota") or 0)
        restore_at = account.get("restore_at")
        last_used = account.get("last_used_at")

        # Rate-limited: check right after restore_at
        if status == "limited" and restore_at:
            try:
                restore_ts = _parse_iso_timestamp(restore_at)
                if restore_ts and restore_ts > now:
                    return restore_ts + 30  # 30s after restore
            except (ValueError, TypeError):
                pass
            return now + DEFAULT_CHECK_INTERVAL

        # Low quota: check more frequently
        if 0 < quota < 5:
            return now + 60  # 1 minute

        # Quota exhausted, waiting for restore
        if quota == 0:
            return now + 120  # 2 minutes

        # Never used: check soon
        if not last_used:
            return now + 30

        # Normal: regular interval
        return now + DEFAULT_CHECK_INTERVAL

    # ── Main Loop ──────────────────────────────────────────────

    async def _loop(self):
        """Main event loop — process due items, sleep until next."""
        last_rebuild = time.time()
        rebuild_interval = 1800  # Full rebuild every 30 minutes

        while self._running:
            try:
                now = time.time()

                # Periodic full rebuild to catch new/removed accounts
                if now - last_rebuild >= rebuild_interval:
                    self._rebuild()
                    last_rebuild = now

                # Process all due items
                while self._heap and self._heap[0].next_check_at <= now:
                    item = heapq.heappop(self._heap)
                    self._index.pop(item.account_id, None)
                    await self._process_account(item.account_id)

                # Calculate sleep duration
                if self._heap:
                    wait = max(0, self._heap[0].next_check_at - time.time())
                else:
                    wait = DEFAULT_CHECK_INTERVAL

                # Sleep or wake on signal
                try:
                    await asyncio.wait_for(
                        self._wake_event.wait(),
                        timeout=min(wait, 60)
                    )
                    self._wake_event.clear()
                except asyncio.TimeoutError:
                    pass

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception({"event": "quota_watcher_loop_error"})
                await asyncio.sleep(60)

    async def _process_account(self, account_id: str):
        """Check and potentially refresh a single account."""
        async with self._refresh_semaphore:
            try:
                accounts = account_service.list_accounts()
                account = None
                for a in accounts:
                    if a.get("access_token") == account_id:
                        account = a
                        break

                if not account:
                    return  # Account was removed

                # Check if we should refresh
                if self._should_refresh(account):
                    logger.info({
                        "event": "quota_watcher_refresh",
                        "account_id": account_id[:20] + "...",
                        "quota": account.get("quota"),
                        "status": account.get("status"),
                    })
                    await asyncio.to_thread(
                        account_service.refresh_accounts, [account_id]
                    )

                # Re-schedule with updated next check time
                now = time.time()
                next_check = self._next_check_time(account, now)
                item = QuotaCheckItem(next_check_at=next_check, account_id=account_id)
                heapq.heappush(self._heap, item)
                self._index[account_id] = item

            except Exception:
                logger.exception({
                    "event": "quota_watcher_process_error",
                    "account_id": account_id[:20] + "...",
                })
                # Re-queue with cooldown after failure
                next_check = time.time() + REFRESH_FAILURE_COOLDOWN
                item = QuotaCheckItem(next_check_at=next_check, account_id=account_id)
                heapq.heappush(self._heap, item)
                self._index[account_id] = item

    def _should_refresh(self, account: dict[str, Any]) -> bool:
        """Determine if an account needs refreshing based on its state.

        Like CLIProxyAPI's shouldRefresh:
        - Quota low or expired
        - Status is rate-limited (check if restore_at passed)
        - Never been refreshed
        """
        status = account.get("status", "")
        quota = int(account.get("quota") or 0)
        restore_at = account.get("restore_at")

        # Rate-limited: check if restore time has passed
        if status == "limited":
            if restore_at:
                try:
                    restore_ts = _parse_iso_timestamp(restore_at)
                    if restore_ts and time.time() >= restore_ts:
                        return True  # Should be restored now
                except (ValueError, TypeError):
                    pass
            return False  # Still in cooldown

        # Low quota: refresh to check latest status
        if quota < 5:
            return True

        # Abnormal: should refresh to check if recovered
        if status == "error":
            return True

        return False

    # ── Health API ─────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get watcher statistics for health endpoint."""
        return {
            "heap_size": len(self._heap),
            "running": self._running,
            "workers": MAX_REFRESH_WORKERS,
            "check_interval": DEFAULT_CHECK_INTERVAL,
        }


def _parse_iso_timestamp(value: str) -> float | None:
    """Parse ISO timestamp string to Unix timestamp."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, TypeError):
        pass
    return None


# Singleton
quota_watcher = QuotaWatcher()
