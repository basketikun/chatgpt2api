"""
Model Cooldown — per-model rate-limit state tracking.

Ports the per-model cooldown + structured error pattern from CLIProxyAPI:
- ModelState per (account, model) — a token can be blocked for model A but fine for B
- Aggregate check — when ALL tokens for a model are cooling, return structured 429
- Provider retry-after parsing — extract reset hints from Codex/Gemini error bodies
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from services.account_service import account_service
from utils.log import logger


@dataclass
class ModelState:
    """Per-account, per-model cooldown state (like CLIProxyAPI's ModelState)."""
    model: str
    status: str = "active"       # active | cooldown | blocked | disabled
    next_retry_at: float = 0.0   # Unix timestamp
    backoff_level: int = 0
    reason: str = ""             # quota | unauthorized | payment_required | server_error
    last_error: str = ""

    @property
    def is_cooling(self) -> bool:
        return self.status == "cooldown" and time.time() < self.next_retry_at

    @property
    def remaining_seconds(self) -> float:
        if self.status != "cooldown":
            return 0
        return max(0, self.next_retry_at - time.time())


class ModelCooldownManager:
    """Tracks per-model cooldown across all accounts.

    Like CLIProxyAPI's authScheduler + modelScheduler combined.
    """

    BACKOFF_BASE = 1.0       # seconds
    BACKOFF_MAX = 1800.0     # 30 minutes
    BACKOFF_401_COOLDOWN = 1800.0   # 30 min
    BACKOFF_402_403_COOLDOWN = 1800.0
    BACKOFF_404_COOLDOWN = 43200.0  # 12 hours
    BACKOFF_5XX_COOLDOWN = 60.0     # 1 minute
    BACKOFF_UNKNOWN_COOLDOWN = 60.0

    def __init__(self):
        # {account_token: {model: ModelState}}
        self._states: dict[str, dict[str, ModelState]] = {}

    # ── Public API ──────────────────────────────────────────────

    def record_success(self, account_id: str, model: str):
        """Clear cooldown for a model on success (fast recovery)."""
        states = self._states.get(account_id, {})
        state = states.get(model)
        if state:
            state.status = "active"
            state.backoff_level = max(0, state.backoff_level - 2)
            state.next_retry_at = 0
            state.reason = ""

    def record_failure(
        self,
        account_id: str,
        model: str,
        status_code: int = 0,
        error_body: str = "",
        provider: str = "",
    ) -> ModelState:
        """Record a failure and return the updated ModelState.

        Args:
            account_id: Account identifier (token hash)
            model: Model that failed
            status_code: HTTP status code from upstream
            error_body: Error response body text
            provider: Provider key (codex, gemini, etc.)
        """
        acc_key = account_id or "unknown"
        mdl_key = (model or "default").strip()
        states = self._states.setdefault(acc_key, {})
        state = states.get(mdl_key)
        if state is None:
            state = ModelState(model=mdl_key)
            states[mdl_key] = state

        # Try provider-reported retry-after first
        provider_retry = _parse_provider_retry_after(status_code, error_body, provider)
        if provider_retry:
            cooldown = min(provider_retry, self.BACKOFF_MAX)
            state.status = "cooldown"
            state.next_retry_at = time.time() + cooldown
            state.reason = "quota"
            state.last_error = error_body[:200]
            return state

        # Classify by status code
        if status_code == 401:
            cooldown = self.BACKOFF_401_COOLDOWN
            reason = "unauthorized"
        elif status_code in (402, 403):
            cooldown = self.BACKOFF_402_403_COOLDOWN
            reason = "payment_required"
        elif status_code == 404:
            cooldown = self.BACKOFF_404_COOLDOWN
            reason = "not_found"
        elif status_code == 429:
            cooldown = self._exponential_backoff(state.backoff_level)
            state.backoff_level += 1
            reason = "quota"
        elif status_code >= 500:
            cooldown = self.BACKOFF_5XX_COOLDOWN
            reason = "server_error"
        elif _is_quota_exceeded(error_body):
            cooldown = self._exponential_backoff(state.backoff_level)
            state.backoff_level += 1
            reason = "quota"
        else:
            cooldown = self.BACKOFF_UNKNOWN_COOLDOWN
            reason = "unknown"

        state.status = "cooldown"
        state.next_retry_at = time.time() + cooldown
        state.reason = reason
        state.last_error = error_body[:200]

        return state

    def is_available(self, account_id: str, model: str) -> bool:
        """Check if an account+model is available (not cooling)."""
        states = self._states.get(account_id, {})
        state = states.get(model)
        if state is None:
            return True
        if not state.is_cooling:
            return True
        return False

    def get_available_accounts(self, model: str, provider: str = "") -> list[dict[str, Any]]:
        """Get all non-cooling accounts for a model.

        Returns accounts that are NOT in cooldown for this specific model.
        """
        all_accounts = account_service.list_accounts()
        available = []
        for acc in all_accounts:
            acc_id = acc.get("access_token", "")
            if not acc_id:
                continue
            status = acc.get("status", "")
            if status in ("disabled", "error"):
                continue
            if self.is_available(acc_id, model):
                available.append(acc)
        return available

    def get_cooldown_info(self, model: str) -> dict[str, Any] | None:
        """Get structured cooldown error info for a model.

        Returns None if at least one account is available.
        Returns error dict if ALL accounts are cooling.
        """
        all_accounts = account_service.list_accounts()
        model_accounts = []
        cooling_accounts: list[ModelState] = []

        for acc in all_accounts:
            acc_id = acc.get("access_token", "")
            if not acc_id:
                continue
            status = acc.get("status", "")
            if status in ("disabled", "error"):
                continue
            model_accounts.append(acc)
            state = self._states.get(acc_id, {}).get(model)
            if state and state.is_cooling:
                cooling_accounts.append(state)

        if not model_accounts:
            return {"code": "no_accounts", "message": f"No accounts available for {model}"}

        # Check if all are cooling
        available = sum(1 for acc in model_accounts
                       if self.is_available(acc.get("access_token", ""), model))

        if available > 0:
            return None  # At least one account is available

        # All cooling — compute collective reset time
        now = time.time()
        next_reset = min(
            (s.next_retry_at for s in cooling_accounts if s.next_retry_at > now),
            default=now + 60
        )
        reset_seconds = int(max(0, next_reset - now))
        reasons = list(set(s.reason for s in cooling_accounts))

        return {
            "code": "model_cooldown",
            "message": f"All credentials for model {model} are cooling down",
            "model": model,
            "reset_seconds": reset_seconds,
            "reasons": reasons,
            "cooling_accounts": len(cooling_accounts),
            "total_accounts": len(model_accounts),
        }

    def get_state(self, account_id: str, model: str) -> ModelState | None:
        """Get the current state for an account+model."""
        return self._states.get(account_id, {}).get(model)

    def get_stats(self) -> dict[str, Any]:
        """Get cooldown statistics."""
        total_states = 0
        cooling = 0
        for acc_states in self._states.values():
            total_states += len(acc_states)
            cooling += sum(1 for s in acc_states.values() if s.is_cooling)
        return {
            "total_tracked": total_states,
            "cooling": cooling,
            "accounts_tracked": len(self._states),
        }

    def cleanup_stale(self, max_age: float = 3600):
        """Remove cooldown states that are no longer relevant."""
        now = time.time()
        for acc_id in list(self._states):
            states = self._states[acc_id]
            for mdl_key in list(states):
                state = states[mdl_key]
                if state.status == "active" or (not state.is_cooling and state.next_retry_at > 0):
                    del states[mdl_key]
            if not states:
                del self._states[acc_id]

    # ── Internal ────────────────────────────────────────────────

    def _exponential_backoff(self, level: int) -> float:
        """Exponential backoff: 1s, 2s, 4s, ... up to 30min, with jitter."""
        cooldown = self.BACKOFF_BASE * (2 ** level)
        cooldown = min(cooldown, self.BACKOFF_MAX)
        # 10% jitter
        import random
        jitter = cooldown * 0.1 * (random.random() * 2 - 1)
        return cooldown + jitter


# ── Provider Retry-After Parsing ────────────────────────────────

def _parse_provider_retry_after(
    status_code: int, error_body: str, provider: str = ""
) -> float | None:
    """Parse provider-reported retry time from error body.

    Returns retry-after in seconds, or None if not found.

    Handles:
    - Codex: {"error":{"type":"usage_limit_reached","resets_in_seconds":123}}
    - Codex: {"error":{"type":"usage_limit_reached","resets_at":<unix>}}
    - Standard: Retry-After header values
    - Gemini: "quota exceeded" text
    """
    if not error_body:
        return None

    body_lower = error_body.lower()

    # Codex usage_limit_reached
    if status_code in (429, 400) and "usage_limit_reached" in body_lower:
        try:
            data = json.loads(error_body) if error_body.strip().startswith("{") else {}
            err = data.get("error", {})
            if isinstance(err, dict):
                if err.get("type") == "usage_limit_reached":
                    # resets_at takes priority over resets_in_seconds
                    resets_at = err.get("resets_at")
                    if resets_at:
                        remaining = resets_at - time.time()
                        if remaining > 0:
                            return remaining
                    resets_in = err.get("resets_in_seconds")
                    if resets_in and resets_in > 0:
                        return float(resets_in)
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    # Codex capacity_exceeded on 400 → treat as retryable
    if status_code == 400 and "capacity_exceeded" in body_lower:
        return 60  # 1 minute retry

    # Gemini quota exhausted text
    if status_code == 429 or (status_code == 403 and "quota" in body_lower):
        if provider in ("gemini", "gemini_free"):
            # Try to parse "retry in Xs" pattern
            match = re.search(r"retry.*?(\d+)\s*s", body_lower)
            if match:
                return float(match.group(1))
            # Default Gemini cooldown
            return 60

    # Generic retry-after parse from text
    match = re.search(r"retry.*?(?:in|after)\s*(\d+)\s*(s|sec|second)s?", body_lower)
    if match:
        return float(match.group(1))

    return None


def _is_quota_exceeded(error_text: str) -> bool:
    """Check if error text indicates quota/rate limit exceeded."""
    if not error_text:
        return False
    text = error_text.lower()
    indicators = [
        "quota exceeded", "rate limit", "too many requests",
        "capacity", "exceeded your quota", "429", "rate_limit",
        "resource has been exhausted", "usage_limit_reached",
    ]
    return any(ind in text for ind in indicators)


# Singleton
model_cooldown = ModelCooldownManager()
