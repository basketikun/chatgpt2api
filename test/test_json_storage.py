from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.storage.json_storage import JSONStorageBackend


class JSONStorageBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.backend = JSONStorageBackend(
            self.root / "accounts" / "accounts.json",
            self.root / "keys" / "auth_keys.json",
        )

    def snapshots(self):
        return (
            (self.backend.file_path, self.backend.save_accounts, self.backend.load_accounts),
            (self.backend.auth_keys_path, self.backend.save_auth_keys, self.backend.load_auth_keys),
        )

    def test_round_trip_preserves_json_formats_and_unicode(self):
        items = [{"id": "key-a", "access_token": "token-a", "name": "测试 😀"}]
        for path, save, load in self.snapshots():
            with self.subTest(path=path.name):
                save(items)
                self.assertEqual(load(), items)
                expected = items if path == self.backend.file_path else {"items": items}
                self.assertEqual(
                    path.read_text(encoding="utf-8"),
                    json.dumps(expected, ensure_ascii=False, indent=2) + "\n",
                )
                save([])
                self.assertEqual(load(), [])
                self.assertEqual(list(path.parent.iterdir()), [path])

    def test_encoding_failure_preserves_previous_snapshot(self):
        original = [{"id": "key-a", "access_token": "token-a", "name": "original"}]
        for path, save, load in self.snapshots():
            with self.subTest(path=path.name):
                save(original)
                before = path.read_bytes()
                with self.assertRaises(UnicodeEncodeError):
                    save([{**original[0], "name": "\ud800"}])
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(load(), original)
                self.assertEqual(list(path.parent.iterdir()), [path])

    def test_fsync_failure_preserves_previous_snapshot_and_cleans_temp_file(self):
        original = [{"id": "key-a", "access_token": "token-a"}]
        for path, save, load in self.snapshots():
            with self.subTest(path=path.name):
                save(original)
                before = path.read_bytes()
                with mock.patch("os.fsync", side_effect=OSError("disk full")):
                    with self.assertRaisesRegex(OSError, "disk full"):
                        save([])
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(load(), original)
                self.assertEqual(list(path.parent.iterdir()), [path])

    def test_replace_failure_preserves_previous_snapshot_and_cleans_temp_file(self):
        original = [{"id": "key-a", "access_token": "token-a"}]
        for path, save, load in self.snapshots():
            with self.subTest(path=path.name):
                save(original)
                before = path.read_bytes()
                with mock.patch("os.replace", side_effect=PermissionError("file locked")):
                    with self.assertRaisesRegex(PermissionError, "file locked"):
                        save([])
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(load(), original)
                self.assertEqual(list(path.parent.iterdir()), [path])

    def test_load_auth_keys_accepts_legacy_list(self):
        items = [{"id": "key-a"}]
        self.backend.auth_keys_path.write_text(json.dumps(items), encoding="utf-8")
        self.assertEqual(self.backend.load_auth_keys(), items)


if __name__ == "__main__":
    unittest.main()
