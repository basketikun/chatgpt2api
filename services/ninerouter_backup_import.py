"""
9router Backup Import — extract usable tokens from 9router backup files.

9router exportDb() format:
{
  "settings": {...},
  "providerConnections": [
    {
      "provider": "codex",      // ChatGPT via OpenAI OAuth
      "connectionName": "...",
      "data": { "accessToken": "eyJ...", "expiresAt": "...", ... }
    },
    {
      "provider": "claude",
      "data": { "accessToken": "...", ... }
    },
    ...
  ],
  "apiKeys": [...],
  "combos": [...]
}

This module extracts tokens that chatgpt2api can use:
- codex → ChatGPT access tokens (primary target)
- Other OAuth tokens → stored for future provider support
"""

from __future__ import annotations

import json
import gzip
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.account_service import account_service
from utils.log import logger


def detect_9router_backup(data: dict[str, Any]) -> bool:
    """Check if a JSON object looks like a 9router backup."""
    if not isinstance(data, dict):
        return False
    # 9router backup has providerConnections array
    if isinstance(data.get("providerConnections"), list):
        return True
    # Nested data format
    inner = data.get("data") or {}
    if isinstance(inner, dict) and isinstance(inner.get("providerConnections"), list):
        return True
    return False


def extract_chatgpt_tokens(data: dict[str, Any]) -> list[str]:
    """Extract ChatGPT access tokens from a 9router backup.

    Prioritizes codex provider (ChatGPT via OpenAI OAuth).
    These tokens can be used directly in chatgpt2api.

    Returns:
        List of access token strings (JWT format: eyJ...)
    """
    tokens: list[str] = []

    # Find providerConnections in the data
    connections = data.get("providerConnections") or []
    if not connections:
        inner = data.get("data") or {}
        connections = inner.get("providerConnections") or []

    if not isinstance(connections, list):
        return tokens

    for conn in connections:
        if not isinstance(conn, dict):
            continue

        provider = str(conn.get("provider") or "").strip().lower()

        # accessToken can be at top level OR nested in "data" field
        access_token = str(conn.get("accessToken") or "")
        if not access_token:
            conn_data = conn.get("data") or {}
            if isinstance(conn_data, dict):
                access_token = str(conn_data.get("accessToken") or "")

        # ChatGPT-compatible providers
        if provider in ("codex", "cursor", "openai"):
            if access_token and access_token.startswith("eyJ"):
                tokens.append(access_token.strip())
                logger.info({
                    "event": "9router_import_token",
                    "provider": provider,
                    "connection": str(conn.get("name") or conn.get("id") or "")[:30],
                })

    return tokens


def extract_all_oauth_tokens(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract ALL OAuth tokens from 9router backup (for all providers).

    Returns:
        List of {provider, name, accessToken, refreshToken, expiresAt} dicts
    """
    all_tokens: list[dict[str, Any]] = []

    connections = data.get("providerConnections") or []
    if not connections:
        inner = data.get("data") or {}
        connections = inner.get("providerConnections") or []

    if not isinstance(connections, list):
        return all_tokens

    for conn in connections:
        if not isinstance(conn, dict):
            continue

        provider = str(conn.get("provider") or "").strip().lower()

        # accessToken can be at top level OR nested in "data" field
        access_token = str(conn.get("accessToken") or "")
        if not access_token:
            conn_data = conn.get("data") or {}
            if isinstance(conn_data, dict):
                access_token = str(conn_data.get("accessToken") or "")

        if not access_token:
            continue

        all_tokens.append({
            "provider": provider,
            "name": str(conn.get("name") or conn.get("id") or provider),
            "access_token": access_token.strip(),
            "refresh_token": str(conn.get("refreshToken") or "").strip() or None,
            "expires_at": str(conn.get("expiresAt") or "").strip() or None,
        })

    return all_tokens


def extract_combos(data: dict[str, Any]) -> dict[str, list[str]]:
    """Extract combo model definitions from 9router backup."""
    combos = data.get("combos") or []
    if not combos and isinstance(data.get("data"), dict):
        combos = data["data"].get("combos") or []

    if not isinstance(combos, list):
        return {}

    result: dict[str, list[str]] = {}
    for combo in combos:
        if not isinstance(combo, dict):
            continue
        name = str(combo.get("name") or "").strip()
        models = combo.get("models") or []
        if name and isinstance(models, list):
            result[name] = [str(m) for m in models if m]

    return result


def import_9router_backup(filepath: str | Path) -> dict[str, Any]:
    """Import a 9router backup file into chatgpt2api.

    Steps:
    1. Read & parse the backup file (supports .json and .json.gz)
    2. Detect if it's a 9router backup
    3. Extract ChatGPT-compatible tokens (codex provider)
    4. Add them to the account pool
    5. Optionally merge combo models

    Returns:
        { imported_tokens: int, skipped: int, combos_merged: int, errors: [...] }
    """
    path = Path(filepath)
    if not path.exists():
        return {"imported_tokens": 0, "skipped": 0, "combos_merged": 0, "errors": [f"File not found: {filepath}"]}

    errors: list[str] = []

    # Read file (supports gzip)
    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rb") as f:
                data = json.loads(f.read().decode("utf-8"))
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"imported_tokens": 0, "skipped": 0, "combos_merged": 0, "errors": [f"Failed to read backup: {exc}"]}

    if not isinstance(data, dict):
        return {"imported_tokens": 0, "skipped": 0, "combos_merged": 0, "errors": ["Invalid backup format: not a JSON object"]}

    # Check if it's a 9router backup
    if not detect_9router_backup(data):
        # Might be chatgpt2api backup — try state_backup
        try:
            from services.state_backup import state_backup
            report = state_backup.import_all(data)
            return {
                "imported_tokens": report.items_restored.get("accounts", 0),
                "skipped": 0,
                "combos_merged": report.items_restored.get("combo_models", 0),
                "errors": report.errors,
                "import_type": "chatgpt2api",
            }
        except Exception as exc:
            return {"imported_tokens": 0, "skipped": 0, "combos_merged": 0, "errors": [f"Not a recognized backup format: {exc}"]}

    # Extract ChatGPT tokens from 9router backup
    tokens = extract_chatgpt_tokens(data)
    # Also extract all OAuth tokens — needed to map access_token -> refresh_token
    all_oauth = extract_all_oauth_tokens(data)
    refresh_lookup: dict[str, dict[str, Any]] = {}
    for t in all_oauth:
        if t.get("provider") in ("codex", "cursor", "openai"):
            at = (t.get("access_token") or "").strip()
            if at:
                refresh_lookup[at] = {
                    "refresh_token": t.get("refresh_token"),
                    "expires_at": t.get("expires_at"),
                }

    imported = 0
    skipped = 0

    if tokens:
        try:
            # Build credentials list (access + refresh + expiry) for refreshable accounts
            creds = [
                {
                    "access_token": tok,
                    "refresh_token": refresh_lookup.get(tok, {}).get("refresh_token"),
                    "expires_at": refresh_lookup.get(tok, {}).get("expires_at"),
                }
                for tok in tokens
            ]
            result = account_service.add_accounts_with_credentials(creds, "codex")
            for token in tokens:
                account_service.update_account(token, {
                    "image_quota_unknown": False,
                    "quota": 10,
                    "status": "active",
                })
            imported = result.get("added", 0) + result.get("updated", 0)
            skipped = result.get("skipped", 0)
            logger.info({
                "event": "9router_backup_imported",
                "tokens_found": len(tokens),
                "with_refresh": sum(1 for c in creds if c.get("refresh_token")),
                "imported": imported,
                "skipped": skipped,
            })
        except Exception as exc:
            errors.append(f"Failed to add Codex accounts: {exc}")

    # Extract & import Antigravity tokens
    antigravity_oauth = [t for t in all_oauth if t.get("provider") == "antigravity"]
    if antigravity_oauth:
        try:
            creds_ag = [
                {
                    "access_token": t["access_token"],
                    "refresh_token": t.get("refresh_token"),
                    "expires_at": t.get("expires_at"),
                }
                for t in antigravity_oauth
            ]
            result_ag = account_service.add_accounts_with_credentials(creds_ag, "antigravity")
            for t in antigravity_oauth:
                tok = t["access_token"]
                account_service.update_account(tok, {
                    "image_quota_unknown": True,
                    "quota": 100,
                    "status": "active",
                })
            imported_ag = result_ag.get("added", 0) + result_ag.get("updated", 0)
            skipped_ag = result_ag.get("skipped", 0)
            logger.info({
                "event": "9router_backup_antigravity_imported",
                "tokens_found": len(antigravity_oauth),
                "imported": imported_ag,
                "skipped": skipped_ag,
            })
        except Exception as exc:
            errors.append(f"Failed to add Antigravity accounts: {exc}")

    # Provider summary for response
    provider_counts: dict[str, int] = {}
    for t in all_oauth:
        p = t["provider"]
        provider_counts[p] = provider_counts.get(p, 0) + 1

    # Extract combos
    combos = extract_combos(data)
    combos_merged = 0
    if combos:
        try:
            from services.config import config
            existing_combos = config.data.get("combo_models") or {}
            if isinstance(existing_combos, dict):
                merged = {**combos, **existing_combos}  # Existing takes priority
                config.data["combo_models"] = merged
                config._save()
                combos_merged = len(combos)
        except Exception as exc:
            errors.append(f"Failed to merge combos: {exc}")

    return {
        "imported_tokens": imported,
        "skipped": skipped,
        "combos_merged": combos_merged,
        "total_tokens_found": len(tokens),
        "oauth_providers_found": provider_counts,
        "errors": errors,
        "import_type": "9router",
    }


def import_9router_backup_from_api(filepath: str) -> dict[str, Any]:
    """API-friendly wrapper with user-facing messages."""
    result = import_9router_backup(filepath)

    if result["errors"]:
        return {"ok": False, **result}

    return {
        "ok": True,
        "message": (
            f"Đã import {result['imported_tokens']} token ChatGPT từ backup 9router. "
            f"({result['skipped']} đã tồn tại, {result['combos_merged']} combo đã hợp nhất)"
        ),
        **result,
    }
