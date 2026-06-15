from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.storage.base import StorageBackend


class JSONStorageBackend(StorageBackend):
    """Local JSON file storage backend."""

    _BACKUP_DIR_NAME = ".json_backups"
    _BACKUP_KEEP = 30

    def __init__(self, file_path: Path, auth_keys_path: Path | None = None):
        self.file_path = file_path
        self.auth_keys_path = auth_keys_path or file_path.with_name("auth_keys.json")
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.auth_keys_path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _backup_dir(cls, file_path: Path) -> Path:
        return file_path.parent / cls._BACKUP_DIR_NAME

    @classmethod
    def _backup_glob(cls, file_path: Path) -> str:
        return f"{file_path.name}.*.bak"

    @classmethod
    def _prune_backups(cls, file_path: Path) -> None:
        backup_dir = cls._backup_dir(file_path)
        if not backup_dir.exists():
            return
        backups = sorted(
            backup_dir.glob(cls._backup_glob(file_path)),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for backup in backups[cls._BACKUP_KEEP:]:
            try:
                backup.unlink()
            except OSError:
                pass

    @classmethod
    def _write_backup(cls, file_path: Path) -> None:
        if not file_path.exists() or file_path.stat().st_size <= 0:
            return
        backup_dir = cls._backup_dir(file_path)
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        backup_path = backup_dir / f"{file_path.name}.{stamp}.{os.getpid()}.bak"
        shutil.copy2(file_path, backup_path)
        cls._prune_backups(file_path)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        try:
            fd = os.open(str(path), flags)
        except OSError:
            return
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @classmethod
    def _atomic_write_text(cls, file_path: Path, text: str) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        tmp_path = file_path.with_name(f".{file_path.name}.{os.getpid()}.{stamp}.tmp")
        try:
            with tmp_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, file_path)
            cls._fsync_directory(file_path.parent)
        finally:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass

    @classmethod
    def _read_json_value(cls, file_path: Path) -> Any:
        return json.loads(file_path.read_text(encoding="utf-8"))

    @classmethod
    def _load_latest_backup(cls, file_path: Path) -> Any | None:
        backup_dir = cls._backup_dir(file_path)
        if not backup_dir.exists():
            return None
        backups = sorted(
            backup_dir.glob(cls._backup_glob(file_path)),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for backup_path in backups:
            try:
                return cls._read_json_value(backup_path)
            except Exception:
                continue
        return None

    @classmethod
    def _load_json_value(cls, file_path: Path, default: Any) -> Any:
        if not file_path.exists():
            return default
        try:
            return cls._read_json_value(file_path)
        except Exception as exc:
            backup_value = cls._load_latest_backup(file_path)
            if backup_value is not None:
                cls._save_json_value(file_path, backup_value)
                print(f"[json-storage] recovered {file_path} from latest backup after load failure: {exc}")
                return backup_value
            raise RuntimeError(f"failed to load JSON storage file {file_path}: {exc}") from exc

    @classmethod
    def _save_json_value(cls, file_path: Path, value: Any) -> None:
        text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        cls._write_backup(file_path)
        cls._atomic_write_text(file_path, text)
        cls._write_backup(file_path)

    @classmethod
    def _load_json_list(cls, file_path: Path) -> list[dict[str, Any]]:
        if not file_path.exists():
            return []
        data = cls._load_json_value(file_path, [])
        if isinstance(data, list):
            return data
        backup_value = cls._load_latest_backup(file_path)
        if isinstance(backup_value, list):
            cls._save_json_value(file_path, backup_value)
            print(f"[json-storage] recovered {file_path} from latest list backup")
            return backup_value
        raise RuntimeError(f"failed to load JSON storage file {file_path}: expected a list")

    @classmethod
    def _save_json_list(cls, file_path: Path, items: list[dict[str, Any]]) -> None:
        cls._save_json_value(file_path, items)

    def load_accounts(self) -> list[dict[str, Any]]:
        return self._load_json_list(self.file_path)

    def save_accounts(self, accounts: list[dict[str, Any]]) -> None:
        self._save_json_list(self.file_path, accounts)

    def load_auth_keys(self) -> list[dict[str, Any]]:
        if not self.auth_keys_path.exists():
            return []
        data = self._load_json_value(self.auth_keys_path, [])
        if isinstance(data, dict):
            data = data.get("items")
        if isinstance(data, list):
            return data
        raise RuntimeError(f"failed to load JSON storage file {self.auth_keys_path}: expected a list or items object")

    def save_auth_keys(self, auth_keys: list[dict[str, Any]]) -> None:
        self._save_json_value(self.auth_keys_path, {"items": auth_keys})

    def health_check(self) -> dict[str, Any]:
        try:
            if self.file_path.exists():
                data = self._load_json_list(self.file_path)
                account_count = len(data)
            else:
                account_count = 0
            if self.auth_keys_path.exists():
                auth_key_count = len(self.load_auth_keys())
            else:
                auth_key_count = 0
            return {
                "status": "healthy",
                "backend": "json",
                "file_exists": self.file_path.exists(),
                "file_path": str(self.file_path),
                "account_count": account_count,
                "backup_dir": str(self._backup_dir(self.file_path)),
                "auth_keys_file_exists": self.auth_keys_path.exists(),
                "auth_keys_file_path": str(self.auth_keys_path),
                "auth_key_count": auth_key_count,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "backend": "json",
                "error": str(e),
            }

    def get_backend_info(self) -> dict[str, Any]:
        return {
            "type": "json",
            "description": "local JSON file storage",
            "file_path": str(self.file_path),
            "file_exists": self.file_path.exists(),
            "backup_dir": str(self._backup_dir(self.file_path)),
            "auth_keys_file_path": str(self.auth_keys_path),
            "auth_keys_file_exists": self.auth_keys_path.exists(),
        }
