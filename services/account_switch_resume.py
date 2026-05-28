"""
Account Switch Resume — parked recovery prompt pattern from codext.

When a request hits UsageLimitExceeded, we park a "recovery prompt" instead
of just failing. Once an account switch restores quota, the parked prompt
is auto-dispatched so the task continues without manual intervention.

Ported from codext codex-rs/tui/src/chatwidget/rate_limits.rs:
  - on_usage_limit_error() → parks a resume prompt
  - on_auth_reload_completed() → dispatches parked prompt after identity change
  - clear_pending_usage_limit_resume_turn() → user manual message clears it
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from utils.log import logger

# Default resume prompt — mirrors codext's built-in DEFAULT_USAGE_LIMIT_RESUME_PROMPT
DEFAULT_RESUME_PROMPT = (
    "Please continue from where the conversation left off after "
    "the usage limit reset or account switch."
)


@dataclass
class ParkedTask:
    """A task parked due to usage limit, waiting for account switch."""
    prompt: str
    model: str
    messages: list[dict] | None = None
    parked_at: float = field(default_factory=time.time)
    account_id: str = ""
    retry_count: int = 0
    max_retries: int = 5


class AccountSwitchResumeManager:
    """Manages parked recovery prompts that auto-dispatch after account switch.

    Ported from codext's pattern:
    - When usage limit hits, park a resume prompt
    - When account identity changes, dispatch the parked prompt
    - If user manually sends a message, clear the parked prompt (stale)
    - Configurable resume prompt (including disable via empty string)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._parked: dict[str, ParkedTask] = {}  # account_id -> ParkedTask
        # Track which accounts have pending dispatches waiting for identity change
        self._waiting_for_switch: dict[str, bool] = {}
        # Resume prompt override (None = use default, "" = disabled)
        self._custom_resume_prompt: str | None = None
        # Track last account identity for change detection
        self._last_account_email: str = ""
        # Callbacks registered by consumers
        self._on_resume_callbacks: list[callable] = []

    @property
    def resume_prompt(self) -> str | None:
        """Get the active resume prompt. None = disabled."""
        if self._custom_resume_prompt is not None:
            if self._custom_resume_prompt == "":
                return None
            return self._custom_resume_prompt
        return DEFAULT_RESUME_PROMPT

    def set_resume_prompt(self, prompt: str | None) -> None:
        """Configure the recovery prompt. Empty string disables, None = default.

        Mirrors codext's [tui].usage_limit_resume_prompt config.
        """
        with self._lock:
            self._custom_resume_prompt = prompt

    def park_task(
        self,
        account_id: str,
        prompt: str = "",
        model: str = "",
        messages: list[dict] | None = None,
    ) -> bool:
        """Park a task for later resumption after account switch.

        Returns True if the task was parked, False if resume is disabled.
        """
        resume_text = self.resume_prompt
        if resume_text is None:
            logger.info({"event": "resume_disabled", "account": account_id})
            return False

        with self._lock:
            final_prompt = prompt or resume_text
            self._parked[account_id] = ParkedTask(
                prompt=final_prompt,
                model=model,
                messages=messages,
                account_id=account_id,
            )
            self._waiting_for_switch[account_id] = True
            logger.info({
                "event": "task_parked_for_resume",
                "account": account_id,
                "prompt_preview": final_prompt[:100],
            })
            return True

    def on_account_switched(self, old_account_id: str, new_account_id: str) -> ParkedTask | None:
        """Called when account identity changes. Returns the parked task if any.

        Mirrors codext's pattern: only dispatch after actual identity change,
        not just any auth reload.
        """
        with self._lock:
            # Check if we have a parked task waiting for this switch
            if not self._waiting_for_switch.pop(old_account_id, False):
                return None

            task = self._parked.pop(old_account_id, None)
            if task is None:
                return None

            task.retry_count += 1
            logger.info({
                "event": "resume_dispatched",
                "old_account": old_account_id,
                "new_account": new_account_id,
                "retry": task.retry_count,
            })
            return task

    def clear_parked(self, account_id: str = "", reason: str = "manual_message") -> bool:
        """Clear parked task(s). Called when user manually sends a message.

        Mirrors codext's clear_pending_usage_limit_resume_turn().
        """
        with self._lock:
            if account_id:
                removed = self._parked.pop(account_id, None) is not None
                self._waiting_for_switch.pop(account_id, None)
            else:
                removed = bool(self._parked)
                self._parked.clear()
                self._waiting_for_switch.clear()
            if removed:
                logger.info({"event": "resume_cleared", "account": account_id, "reason": reason})
            return removed

    def has_parked(self, account_id: str = "") -> bool:
        """Check if there's a parked task."""
        with self._lock:
            if account_id:
                return account_id in self._parked
            return bool(self._parked)

    def get_parked(self, account_id: str) -> ParkedTask | None:
        """Get parked task without removing it."""
        with self._lock:
            return self._parked.get(account_id)

    def list_parked(self) -> list[dict[str, Any]]:
        """List all parked tasks (for status/monitoring)."""
        with self._lock:
            return [
                {
                    "account_id": tid,
                    "prompt_preview": t.prompt[:120],
                    "model": t.model,
                    "parked_seconds_ago": time.time() - t.parked_at,
                    "retry_count": t.retry_count,
                }
                for tid, t in self._parked.items()
            ]

    def register_resume_callback(self, callback: callable) -> None:
        """Register a callback(parked_task) invoked on dispatch."""
        self._on_resume_callbacks.append(callback)

    def invoke_resume_callbacks(self, task: ParkedTask) -> None:
        """Notify registered callbacks about the dispatched task."""
        for cb in self._on_resume_callbacks:
            try:
                cb(task)
            except Exception:
                logger.exception({"event": "resume_callback_error"})


# Singleton
account_switch_resume = AccountSwitchResumeManager()
