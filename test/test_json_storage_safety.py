from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from services.storage.json_storage import JSONStorageBackend


def test_json_storage_saves_with_backup() -> None:
    with TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "accounts.json"
        storage = JSONStorageBackend(path)

        storage.save_accounts([{"access_token": "old"}])
        storage.save_accounts([{"access_token": "new"}])

        assert storage.load_accounts() == [{"access_token": "new"}]
        backups = sorted((Path(tmp_dir) / ".json_backups").glob("accounts.json.*.bak"))
        assert backups
        assert any(json.loads(item.read_text(encoding="utf-8")) == [{"access_token": "old"}] for item in backups)


def test_json_storage_recovers_from_latest_backup() -> None:
    with TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "accounts.json"
        storage = JSONStorageBackend(path)

        storage.save_accounts([{"access_token": "recover-me"}])
        path.write_text("{", encoding="utf-8")

        assert storage.load_accounts() == [{"access_token": "recover-me"}]
        assert json.loads(path.read_text(encoding="utf-8")) == [{"access_token": "recover-me"}]
