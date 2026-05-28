"""
Project Docs Watcher — AGENTS.md / CLAUDE.md / project-doc auto-reload.

Ported from codext's AGENTS.md reload semantics (CHANGED.md):
  - On each new user turn, checks whether project docs changed
  - If changed, reloads instructions before creating the turn
  - Emits explicit warning when a reload is applied

Also monitors CLAUDE.md (user's private global instructions) and
any custom instruction files configured by the user.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Any

from utils.log import logger

# Files to watch for changes (relative to project root + global locations)
DEFAULT_WATCH_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    "AI_PLAYBOOK.md",
    "README.md",
]

# User's global CLAUDE.md location
GLOBAL_CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"

# Reload debounce (avoids rapid reloads during saves)
DEBOUNCE_SECONDS = 1.0

# How often to check for changes (seconds)
CHECK_INTERVAL_SECONDS = 5


class ProjectDocsWatcher:
    """Watches project instruction files for changes and triggers reloads.

    Ports codext's pattern:
    - Check before each turn if AGENTS.md hierarchy changed
    - Reload and apply before creating the turn
    - Emit transcript warning on reload

    In the API context, this provides:
    - A `check_and_reload()` method callers invoke before processing chat requests
    - Content hash tracking for change detection
    - Reload notification for logging/monitoring
    """

    def __init__(self, project_root: str | Path = ""):
        self._lock = threading.Lock()
        self._project_root = Path(project_root) if project_root else Path.cwd()
        # {file_path: content_hash}
        self._hashes: dict[str, str] = {}
        # {file_path: content_text}
        self._content_cache: dict[str, str] = {}
        # Track which files exist
        self._file_list: list[str] = []
        # Reload history for auditing
        self._reload_history: list[dict] = []
        self._max_history = 50
        # Callbacks
        self._on_reload_callbacks: list[callable] = []
        # Last check timestamp for debounce
        self._last_check_at: float = 0.0
        # Custom watch paths (additional to defaults)
        self._custom_watch_files: list[str] = []

    # ── Public API ──────────────────────────────────────────────

    def add_watch_file(self, filepath: str) -> None:
        """Add a custom file to watch."""
        with self._lock:
            if filepath not in self._custom_watch_files:
                self._custom_watch_files.append(filepath)

    def set_project_root(self, root: str | Path) -> None:
        """Change the project root directory."""
        with self._lock:
            self._project_root = Path(root)
            self._hashes.clear()
            self._content_cache.clear()

    def check_and_reload(self) -> dict[str, Any]:
        """Check if any watched files changed. Returns the reload result.

        Call this before processing a chat request to apply updated
        instructions (mirrors codext's per-turn check).

        Returns:
            {
                "changed": bool,
                "files": [str],          # files that changed
                "combined_content": str,  # all instruction content combined
                "warning": str | None,    # warning to emit to user
            }
        """
        now = time.time()
        if now - self._last_check_at < DEBOUNCE_SECONDS:
            return {"changed": False, "files": [], "combined_content": "", "warning": None}

        self._last_check_at = now

        with self._lock:
            all_files = list(set(DEFAULT_WATCH_FILES + self._custom_watch_files))
            # Add global CLAUDE.md
            changed_files: list[str] = []
            current_hashes: dict[str, str] = {}

            for filename in all_files:
                filepath = self._resolve_path(filename)
                if not filepath:
                    continue
                try:
                    content = filepath.read_text(encoding="utf-8", errors="replace")
                except (OSError, PermissionError):
                    continue
                new_hash = hashlib.sha256(content.encode()).hexdigest()
                current_hashes[filename] = new_hash

                old_hash = self._hashes.get(filename)
                if old_hash and old_hash != new_hash:
                    changed_files.append(filename)
                    self._content_cache[filename] = content
                    logger.info({
                        "event": "project_doc_changed",
                        "file": filename,
                        "path": str(filepath),
                    })
                elif not old_hash:
                    # First time seeing this file
                    self._content_cache[filename] = content
                self._hashes[filename] = new_hash

            # Check global CLAUDE.md
            if GLOBAL_CLAUDE_MD.exists():
                try:
                    content = GLOBAL_CLAUDE_MD.read_text(encoding="utf-8", errors="replace")
                    gkey = str(GLOBAL_CLAUDE_MD)
                    new_hash = hashlib.sha256(content.encode()).hexdigest()
                    old_hash = self._hashes.get(gkey)
                    if old_hash and old_hash != new_hash:
                        changed_files.append("~/.claude/CLAUDE.md")
                    self._hashes[gkey] = new_hash
                    self._content_cache[gkey] = content
                except (OSError, PermissionError):
                    pass

            if not changed_files:
                return {"changed": False, "files": [], "combined_content": "", "warning": None}

            # Build warning — mirrors codext's transcript warning pattern
            reload_names = [Path(f).name for f in changed_files]
            warning = (
                f"AGENTS.md / project instructions changed: {', '.join(reload_names)}. "
                "Reloaded and applied starting this turn."
            )

            # Build combined content for system prompt injection
            combined = self._build_combined_content()

            # Record in history
            self._reload_history.append({
                "timestamp": time.time(),
                "files": list(changed_files),
                "warning": warning,
            })
            if len(self._reload_history) > self._max_history:
                self._reload_history = self._reload_history[-self._max_history:]

            # Notify callbacks
            for cb in self._on_reload_callbacks:
                try:
                    cb(changed_files, combined)
                except Exception:
                    pass

            logger.info({"event": "docs_reloaded", "files": changed_files})

            return {
                "changed": True,
                "files": changed_files,
                "combined_content": combined,
                "warning": warning,
            }

    def get_combined_instructions(self) -> str:
        """Get the current combined instruction content.

        Used by system prompt builders to inject project context.
        """
        with self._lock:
            return self._build_combined_content()

    def get_reload_history(self, limit: int = 20) -> list[dict]:
        """Get recent reload history."""
        with self._lock:
            return list(self._reload_history[-limit:])

    def get_watched_files(self) -> list[dict]:
        """List all watched files and their status."""
        with self._lock:
            files = []
            all_files = list(set(DEFAULT_WATCH_FILES + self._custom_watch_files))
            for filename in all_files:
                filepath = self._resolve_path(filename)
                files.append({
                    "name": filename,
                    "path": str(filepath) if filepath else None,
                    "exists": filepath.exists() if filepath else False,
                    "last_hash": self._hashes.get(filename, "")[:12],
                })
            if GLOBAL_CLAUDE_MD.exists():
                gkey = str(GLOBAL_CLAUDE_MD)
                files.append({
                    "name": "~/.claude/CLAUDE.md",
                    "path": str(GLOBAL_CLAUDE_MD),
                    "exists": True,
                    "last_hash": self._hashes.get(gkey, "")[:12],
                })
            return files

    def on_reload(self, callback: callable) -> None:
        """Register callback(changed_files, combined_content) on reload."""
        self._on_reload_callbacks.append(callback)

    def force_reload(self) -> dict[str, Any]:
        """Force a reload of all files (clears hash cache first)."""
        with self._lock:
            self._hashes.clear()
        return self.check_and_reload()

    # ── Internal ──────────────────────────────────────────────

    def _resolve_path(self, filename: str) -> Path | None:
        """Resolve a filename to an absolute path."""
        # Check project root first
        candidate = self._project_root / filename
        if candidate.exists():
            return candidate
        # Check global locations
        if filename in ("AGENTS.md", "CLAUDE.md"):
            global_candidate = Path.home() / ".claude" / filename
            if global_candidate.exists():
                return global_candidate
            # Also check RTK.md (referenced in CLAUDE.md)
            if filename == "CLAUDE.md":
                rtk_candidate = Path.home() / ".claude" / "RTK.md"
                if rtk_candidate.exists():
                    return rtk_candidate
        return None

    def _build_combined_content(self) -> str:
        """Build combined instruction content from all cached files."""
        parts: list[str] = []
        for filepath, content in self._content_cache.items():
            if content.strip():
                # Use short name for display
                name = Path(filepath).name if "/" in filepath or "\\" in filepath else filepath
                parts.append(f"<!-- {name} -->\n{content.strip()}\n<!-- /{name} -->")
        return "\n\n".join(parts)


# Singleton
project_docs_watcher = ProjectDocsWatcher()
