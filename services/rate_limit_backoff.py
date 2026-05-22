"""
Rate Limit Backoff — port from 9router open-sse/services/accountFallback.js.

Exponential backoff with configurable levels:
- base: 2000ms, max: 300000ms (5 phút), maxLevel: 15
- Error rules: text match trước, status code sau
- Per-model locking: model_lock_{model}
- Transient cooldown: 30s cho lỗi tạm thời

Used by both chat (via 9router providers) and image (via ChatGPT DALL-E) paths.
"""

from __future__ import annotations

import time
from typing import Any


# Backoff config — ported from 9router BACKOFF_CONFIG
BACKOFF_BASE_MS = 2000
BACKOFF_MAX_MS = 300_000  # 5 minutes
BACKOFF_MAX_LEVEL = 15
TRANSIENT_COOLDOWN_MS = 30_000  # 30 seconds
MAX_RATE_LIMIT_COOLDOWN_MS = 1_800_000  # 30 minutes (for provider-reported resets)

# Error rules — ported from 9router ERROR_RULES (open-sse/config/errorConfig.js)
# Priority order: text match first, then status code
ERROR_RULES: list[dict[str, Any]] = [
    # Text-based rules (checked case-insensitive)
    {"text": "no credentials", "cooldown_ms": 120_000, "level": 2},
    {"text": "request not allowed", "cooldown_ms": 120_000, "level": 2},
    {"text": "improperly formed request", "cooldown_ms": 60_000, "level": 1},
    {"text": "rate limit", "cooldown_ms": None, "level": None},  # Use exponential
    {"text": "too many requests", "cooldown_ms": None, "level": None},  # Use exponential
    {"text": "quota exceeded", "cooldown_ms": None, "level": None},  # Use exponential
    {"text": "capacity", "cooldown_ms": 30_000, "level": 1},
    {"text": "overloaded", "cooldown_ms": 30_000, "level": 1},
    {"text": "token_invalidated", "cooldown_ms": 0, "level": 0},
    {"text": "token_revoked", "cooldown_ms": 0, "level": 0},
    # Status-based rules
    {"status": 401, "cooldown_ms": 120_000, "level": 2},
    {"status": 402, "cooldown_ms": 120_000, "level": 2},
    {"status": 403, "cooldown_ms": 120_000, "level": 2},
    {"status": 404, "cooldown_ms": 120_000, "level": 2},
    {"status": 429, "cooldown_ms": None, "level": None},  # Use exponential backoff
    {"status": 503, "cooldown_ms": TRANSIENT_COOLDOWN_MS, "level": 1},
]


class RateLimitBackoff:
    """Per-account, per-model exponential backoff tracker.

    Ported from 9router accountFallback.js checkFallbackError() +
    getQuotaCooldown().
    """

    def __init__(self):
        # {account_key: {model_key: current_level}}
        self._levels: dict[str, dict[str, int]] = {}
        # {account_key: {model_key: locked_until_timestamp}}
        self._locks: dict[str, dict[str, float]] = {}

    def _account_key(self, account_id: str) -> str:
        return account_id or "unknown"

    def _model_key(self, model: str) -> str:
        return (model or "default").strip()

    def record_failure(
        self,
        account_id: str,
        model: str,
        error_text: str = "",
        status_code: int = 0,
        provider_reported_ms: int | None = None,
    ) -> float:
        """Record a failure and return the recommended cooldown in seconds.

        Args:
            account_id: Account identifier (email or token hash)
            model: Model name that failed
            error_text: Error message from upstream
            status_code: HTTP status code
            provider_reported_ms: Provider-reported reset time in ms (e.g., codex resets_at)

        Returns:
            Cooldown duration in seconds (0 = no cooldown, can retry immediately)
        """
        acc_key = self._account_key(account_id)
        mdl_key = self._model_key(model)

        # Initialize tracking if needed
        self._levels.setdefault(acc_key, {})
        current_level = self._levels[acc_key].get(mdl_key, 0)

        # If provider reported a precise reset time, use it
        if provider_reported_ms and provider_reported_ms > 0:
            cooldown_ms = min(provider_reported_ms, MAX_RATE_LIMIT_COOLDOWN_MS)
            self._set_lock(acc_key, mdl_key, cooldown_ms / 1000)
            return cooldown_ms / 1000

        # Match error rules — text first, then status
        error_lower = str(error_text or "").lower()

        for rule in ERROR_RULES:
            # Text match
            if "text" in rule and rule["text"] in error_lower:
                return self._apply_rule(acc_key, mdl_key, rule, current_level)

            # Status match
            if "status" in rule and rule["status"] == status_code:
                return self._apply_rule(acc_key, mdl_key, rule, current_level)

        # Default: transient cooldown
        cooldown_s = TRANSIENT_COOLDOWN_MS / 1000
        new_level = min(current_level + 1, BACKOFF_MAX_LEVEL)
        self._levels[acc_key][mdl_key] = new_level
        self._set_lock(acc_key, mdl_key, cooldown_s)
        return cooldown_s

    def _apply_rule(
        self,
        acc_key: str,
        mdl_key: str,
        rule: dict[str, Any],
        current_level: int,
    ) -> float:
        """Apply a matched error rule and return cooldown in seconds."""
        cooldown_ms = rule.get("cooldown_ms")
        rule_level = rule.get("level")

        if cooldown_ms is not None and rule_level is not None:
            # Fixed cooldown
            self._levels[acc_key][mdl_key] = rule_level
            cooldown_s = cooldown_ms / 1000
            self._set_lock(acc_key, mdl_key, cooldown_s)
            return cooldown_s
        else:
            # Exponential backoff
            new_level = min(current_level + 1, BACKOFF_MAX_LEVEL)
            self._levels[acc_key][mdl_key] = new_level
            cooldown_ms = min(BACKOFF_BASE_MS * (2 ** (new_level - 1)), BACKOFF_MAX_MS)
            # Add 10% jitter (port from 9router)
            import random
            jitter = cooldown_ms * 0.1 * (random.random() * 2 - 1)
            cooldown_ms = int(cooldown_ms + jitter)
            cooldown_s = cooldown_ms / 1000
            self._set_lock(acc_key, mdl_key, cooldown_s)
            return cooldown_s

    def record_success(self, account_id: str, model: str) -> None:
        """Reduce backoff level on successful request (fast recovery).

        Ported from 9router: decrement by 2 on success, min 0.
        """
        acc_key = self._account_key(account_id)
        mdl_key = self._model_key(model)

        if acc_key in self._levels and mdl_key in self._levels[acc_key]:
            self._levels[acc_key][mdl_key] = max(0, self._levels[acc_key][mdl_key] - 2)

        # Clear lock on success
        if acc_key in self._locks and mdl_key in self._locks[acc_key]:
            del self._locks[acc_key][mdl_key]

    def is_locked(self, account_id: str, model: str) -> bool:
        """Check if an account is locked for a specific model."""
        acc_key = self._account_key(account_id)
        mdl_key = self._model_key(model)

        if acc_key not in self._locks or mdl_key not in self._locks[acc_key]:
            return False

        locked_until = self._locks[acc_key][mdl_key]
        return time.time() < locked_until

    def get_lock_remaining(self, account_id: str, model: str) -> float:
        """Get remaining lock time in seconds (0 if not locked)."""
        acc_key = self._account_key(account_id)
        mdl_key = self._model_key(model)

        if acc_key not in self._locks or mdl_key not in self._locks[acc_key]:
            return 0.0

        remaining = self._locks[acc_key][mdl_key] - time.time()
        return max(0.0, remaining)

    def _set_lock(self, acc_key: str, mdl_key: str, cooldown_s: float) -> None:
        """Set a per-model lock on an account."""
        self._locks.setdefault(acc_key, {})
        self._locks[acc_key][mdl_key] = time.time() + cooldown_s

    def clear_account(self, account_id: str) -> None:
        """Clear all state for an account (e.g., on token removal)."""
        acc_key = self._account_key(account_id)
        self._levels.pop(acc_key, None)
        self._locks.pop(acc_key, None)

    def cleanup_stale(self, max_age_seconds: float = 1800) -> int:
        """Remove entries not accessed in max_age_seconds (30 min default).

        Returns:
            Number of account entries removed.
        """
        # Note: current implementation keeps levels/locks indefinitely.
        # This is a placeholder for future stale cleanup.
        return 0

    def get_stats(self) -> dict[str, Any]:
        """Get backoff statistics for monitoring."""
        total_locked = 0
        for acc_locks in self._locks.values():
            for locked_until in acc_locks.values():
                if time.time() < locked_until:
                    total_locked += 1

        total_levels = 0
        for acc_levels in self._levels.values():
            total_levels += sum(acc_levels.values())

        return {
            "total_accounts_tracked": len(self._levels),
            "total_locked_models": total_locked,
            "total_backoff_levels": total_levels,
            "max_level": BACKOFF_MAX_LEVEL,
        }


# Singleton
rate_limit_backoff = RateLimitBackoff()
