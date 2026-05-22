"""
Lightweight usage tracker — logs per-request token/cost to JSONL file.
Aggregated by /api/v1/usage/stats and /api/v1/usage/recent.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from services.config import DATA_DIR

USAGE_LOG_PATH = DATA_DIR / "usage_log.jsonl"


def log_usage(
    model: str = "",
    endpoint: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    duration_ms: int = 0,
    status: str = "success",
    error: str = "",
    started_at: str = "",
) -> None:
    """Log a single API request's usage data."""
    entry = {
        "ts": time.time(),
        "model": model,
        "endpoint": endpoint,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "duration_ms": duration_ms,
        "status": status,
        "error": error,
        "started_at": started_at or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # non-critical


def get_usage_stats(period: str = "30d") -> dict:
    """Aggregate usage stats from log file."""
    if not USAGE_LOG_PATH.exists():
        return {
            "totalRequests": 0, "totalPromptTokens": 0, "totalCompletionTokens": 0,
            "totalTokens": 0, "totalCost": 0, "successRate": 0,
            "activeAccounts": 0, "totalAccounts": 0,
        }

    now = time.time()
    if period == "today":
        cutoff = now - 86400
    elif period == "24h":
        cutoff = now - 86400
    elif period == "7d":
        cutoff = now - 7 * 86400
    elif period == "30d":
        cutoff = now - 30 * 86400
    elif period == "60d":
        cutoff = now - 60 * 86400
    else:
        cutoff = now - 30 * 86400

    total_requests = 0
    total_success = 0
    total_prompt = 0
    total_completion = 0
    recent_models: dict[str, int] = {}

    try:
        lines = USAGE_LOG_PATH.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("ts", 0) < cutoff:
                continue
            total_requests += 1
            if entry.get("status") == "success":
                total_success += 1
            total_prompt += entry.get("prompt_tokens", 0)
            total_completion += entry.get("completion_tokens", 0)
            model = entry.get("model", "unknown")
            recent_models[model] = (recent_models.get(model, 0) + 1)
    except Exception:
        pass

    total_tokens = total_prompt + total_completion
    # Estimate cost (same rates as before)
    total_cost = (total_prompt / 1000) * 0.002 + (total_completion / 1000) * 0.006

    # Also include account-based stats
    from services.account_service import account_service
    accounts = account_service.list_accounts()

    return {
        "totalRequests": total_requests,
        "totalPromptTokens": total_prompt,
        "totalCompletionTokens": total_completion,
        "totalTokens": total_tokens,
        "totalCost": round(total_cost, 2),
        "successRate": round((total_success / total_requests * 100), 1) if total_requests > 0 else 0,
        "activeAccounts": sum(1 for a in accounts if a.get("status") == "active"),
        "totalAccounts": len(accounts),
        "topModels": dict(sorted(recent_models.items(), key=lambda x: -x[1])[:5]),
    }


def get_recent_requests(limit: int = 25) -> list[dict]:
    """Get recent request entries for the Recent Requests table."""
    if not USAGE_LOG_PATH.exists():
        return []

    result: list[dict] = []
    try:
        lines = USAGE_LOG_PATH.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            result.append({
                "model": entry.get("model", "unknown"),
                "promptTokens": entry.get("prompt_tokens", 0),
                "completionTokens": entry.get("completion_tokens", 0),
                "duration_ms": entry.get("duration_ms", 0),
                "status": entry.get("status", "success"),
                "started_at": entry.get("started_at", ""),
                "error": entry.get("error", ""),
            })
            if len(result) >= limit:
                break
    except Exception:
        pass
    return result


def get_active_providers(hours: int = 24) -> list[str]:
    """Return list of model prefixes that have been used in the last N hours.
    Used to filter topology to show only actively used providers."""
    if not USAGE_LOG_PATH.exists():
        return []

    cutoff = time.time() - hours * 3600
    used_models: set[str] = set()
    try:
        lines = USAGE_LOG_PATH.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("ts", 0) < cutoff:
                continue
            model = entry.get("model", "")
            if not model:
                continue
            # Extract provider prefix (e.g., "chatgpt/auto" → "chatgpt")
            prefix = model.split("/")[0] if "/" in model else model
            used_models.add(prefix)
    except Exception:
        pass
    return sorted(used_models)
