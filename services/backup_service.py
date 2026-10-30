from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import random
import subprocess
import tarfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlencode

from curl_cffi import requests

from services.config import BASE_DIR, CONFIG_FILE, DATA_DIR, config, load_backup_state, save_backup_state
from services.image_storage_service import IMAGE_INDEX_FILE
from services.image_tags_service import TAGS_FILE
from utils.i18n import get_locale, t


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_now() -> str:
    return _utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: object) -> str:
    return str(value or "").strip()


def _sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_backup_object(key: object) -> bool:
    name = _clean(key).rsplit("/", 1)[-1]
    return name.startswith("backup-") and (name.endswith(".tar.gz") or name.endswith(".tar.gz.enc"))


def _hmac_sha256(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _openssl_encrypt(data: bytes, passphrase: str) -> bytes:
    env = dict(os.environ)
    env["CHATGPT2API_BACKUP_PASSPHRASE"] = passphrase
    try:
        result = subprocess.run(
            [
                "openssl",
                "enc",
                "-aes-256-cbc",
                "-pbkdf2",
                "-salt",
                "-md",
                "sha256",
                "-pass",
                "env:CHATGPT2API_BACKUP_PASSPHRASE",
            ],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            env=env,
        )
    except FileNotFoundError as exc:
        raise BackupError(t("backup.openssl_missing_encrypt")) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", errors="replace").strip() or t("backup.openssl_exec_failed_generic")
        raise BackupError(t("backup.encrypt_failed").format(detail=detail)) from exc
    return result.stdout


def _openssl_decrypt(data: bytes, passphrase: str) -> bytes:
    env = dict(os.environ)
    env["CHATGPT2API_BACKUP_PASSPHRASE"] = passphrase
    try:
        result = subprocess.run(
            [
                "openssl",
                "enc",
                "-d",
                "-aes-256-cbc",
                "-pbkdf2",
                "-md",
                "sha256",
                "-pass",
                "env:CHATGPT2API_BACKUP_PASSPHRASE",
            ],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            env=env,
        )
    except FileNotFoundError as exc:
        raise BackupError(t("backup.openssl_missing_decrypt")) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", errors="replace").strip() or t("backup.openssl_exec_failed_generic")
        raise BackupError(t("backup.decrypt_failed").format(detail=detail)) from exc
    return result.stdout


def _guess_content_type(name: str) -> str:
    if name.endswith(".json"):
        return "application/json"
    if name.endswith(".jsonl"):
        return "application/x-ndjson"
    if name.endswith(".tar.gz"):
        return "application/gzip"
    if name.endswith(".gz"):
        return "application/gzip"
    return "application/octet-stream"


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def _count_items(value: object) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return len(value)
    return 0


class BackupError(RuntimeError):
    pass


class CloudflareR2Client:
    def __init__(self, settings: dict[str, object]) -> None:
        self.account_id = _clean(settings.get("account_id"))
        self.access_key_id = _clean(settings.get("access_key_id"))
        self.secret_access_key = _clean(settings.get("secret_access_key"))
        self.bucket = _clean(settings.get("bucket"))
        self.prefix = _clean(settings.get("prefix")) or "backups"
        self.session = requests.Session(impersonate="chrome", verify=True)

    def validate(self) -> None:
        missing = []
        if not self.account_id:
            missing.append("Account ID")
        if not self.access_key_id:
            missing.append("Access Key ID")
        if not self.secret_access_key:
            missing.append("Secret Access Key")
        if not self.bucket:
            missing.append("Bucket")
        if missing:
            separator = "、" if get_locale() == "zh" else ", "
            raise BackupError(t("backup.config_incomplete").format(missing=separator.join(missing)))

    @property
    def endpoint(self) -> str:
        return f"https://{self.account_id}.r2.cloudflarestorage.com"

    def _aws_v4_headers(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        body: bytes = b"",
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, str]]:
        now = _utc_now()
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        encoded_query = urlencode(sorted((query or {}).items()))
        payload_hash = _sha256_hex(body)
        host = f"{self.account_id}.r2.cloudflarestorage.com"
        headers = {
            "host": host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if extra_headers:
            for key, value in extra_headers.items():
                headers[key.lower()] = value.strip()
        sorted_items = sorted((key.lower(), " ".join(str(value).strip().split())) for key, value in headers.items())
        canonical_headers = "".join(f"{key}:{value}\n" for key, value in sorted_items)
        signed_headers = ";".join(key for key, _ in sorted_items)
        canonical_request = "\n".join([
            method.upper(),
            path,
            encoded_query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ])
        credential_scope = f"{date_stamp}/auto/s3/aws4_request"
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            _sha256_hex(canonical_request.encode("utf-8")),
        ])
        k_date = _hmac_sha256(("AWS4" + self.secret_access_key).encode("utf-8"), date_stamp)
        k_region = hmac.new(k_date, b"auto", hashlib.sha256).digest()
        k_service = hmac.new(k_region, b"s3", hashlib.sha256).digest()
        k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self.access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        request_headers = {key: value for key, value in headers.items()}
        request_headers["authorization"] = authorization
        return encoded_query, request_headers

    def _request(
        self,
        method: str,
        key: str = "",
        *,
        query: dict[str, str] | None = None,
        body: bytes = b"",
        extra_headers: dict[str, str] | None = None,
        timeout: float = 60.0,
    ):
        object_path = f"/{self.bucket}"
        if key:
            object_path += f"/{quote(key.lstrip('/'), safe='/')}"
        encoded_query, headers = self._aws_v4_headers(method, object_path, query=query, body=body, extra_headers=extra_headers)
        url = f"{self.endpoint}{object_path}"
        if encoded_query:
            url += f"?{encoded_query}"
        response = self.session.request(method.upper(), url, headers=headers, data=body, timeout=timeout)
        return response

    def test_connection(self) -> dict[str, object]:
        self.validate()
        response = self._request("GET", query={"list-type": "2", "max-keys": "1"}, timeout=30.0)
        if response.status_code >= 400:
            raise BackupError(t("backup.connect_failed").format(status=response.status_code))
        return {"ok": True, "status": int(response.status_code)}

    def upload_bytes(self, key: str, payload: bytes, *, content_type: str, metadata: dict[str, str] | None = None) -> dict[str, object]:
        headers = {"content-type": content_type}
        if metadata:
            for item_key, item_value in metadata.items():
                headers[f"x-amz-meta-{item_key}"] = str(item_value)
        response = self._request("PUT", key, body=payload, extra_headers=headers)
        if response.status_code >= 400:
            raise BackupError(t("backup.upload_failed").format(status=response.status_code))
        return {"key": key, "etag": str(response.headers.get("etag") or "").strip('"')}

    def delete_object(self, key: str) -> None:
        response = self._request("DELETE", key, timeout=30.0)
        if response.status_code >= 400 and response.status_code != 404:
            raise BackupError(t("backup.delete_failed").format(status=response.status_code))

    def download_bytes(self, key: str) -> bytes:
        response = self._request("GET", key, timeout=60.0)
        if response.status_code >= 400:
            raise BackupError(t("backup.read_failed").format(status=response.status_code))
        return bytes(response.content or b"")

    def list_objects(self) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        continuation = ""
        while True:
            query = {"list-type": "2", "prefix": f"{self.prefix.rstrip('/')}/", "max-keys": "1000"}
            if continuation:
                query["continuation-token"] = continuation
            response = self._request("GET", query=query, timeout=30.0)
            if response.status_code >= 400:
                raise BackupError(t("backup.list_failed").format(status=response.status_code))
            text = response.text
            for block in text.split("<Contents>")[1:]:
                key = _clean(block.split("<Key>", 1)[1].split("</Key>", 1)[0]) if "<Key>" in block else ""
                if not key:
                    continue
                size_text = _clean(block.split("<Size>", 1)[1].split("</Size>", 1)[0]) if "<Size>" in block else "0"
                updated = _clean(block.split("<LastModified>", 1)[1].split("</LastModified>", 1)[0]) if "<LastModified>" in block else ""
                items.append({
                    "key": key,
                    "size": int(size_text or 0),
                    "updated_at": updated,
                })
            truncated = "<IsTruncated>true</IsTruncated>" in text
            if not truncated:
                break
            if "<NextContinuationToken>" not in text:
                break
            continuation = _clean(text.split("<NextContinuationToken>", 1)[1].split("</NextContinuationToken>", 1)[0])
            if not continuation:
                break
        items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return items

    def close(self) -> None:
        self.session.close()


class BackupService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="r2-backup-scheduler")
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            thread = self._thread
            self._thread = None
        if thread and thread.is_alive():
            thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_scheduled_backup_if_needed()
            except Exception:
                pass
            self._stop_event.wait(30)

    def run_scheduled_backup_if_needed(self) -> None:
        settings = config.get_backup_settings()
        if not settings.get("enabled"):
            return
        state = self.get_status()
        if state.get("running"):
            return
        interval_minutes = int(settings.get("interval_minutes") or 360)
        last_finished_raw = _clean(state.get("last_finished_at"))
        if last_finished_raw:
            try:
                last_finished = datetime.fromisoformat(last_finished_raw.replace("Z", "+00:00"))
                elapsed = (_utc_now() - last_finished.astimezone(UTC)).total_seconds()
                if elapsed < interval_minutes * 60:
                    return
            except Exception:
                pass
        self.run_backup(trigger="schedule")

    def get_status(self) -> dict[str, object]:
        return {
            **load_backup_state(),
            "running": self._running,
        }

    def is_configured(self) -> bool:
        settings = config.get_backup_settings()
        return all([
            _clean(settings.get("account_id")),
            _clean(settings.get("access_key_id")),
            _clean(settings.get("secret_access_key")),
            _clean(settings.get("bucket")),
        ])

    def get_settings(self) -> dict[str, object]:
        settings = dict(config.get_backup_settings())
        settings["secret_access_key"] = "********" if _clean(settings.get("secret_access_key")) else ""
        settings["passphrase"] = "********" if _clean(settings.get("passphrase")) else ""
        return settings

    def update_settings(self, payload: dict[str, object]) -> dict[str, object]:
        current = config.get_backup_settings()
        merged = dict(current)
        merged.update(dict(payload or {}))
        if "include" in payload and isinstance(payload.get("include"), dict):
            include = dict(current.get("include") or {})
            include.update(payload.get("include") or {})
            merged["include"] = include
        if payload.get("secret_access_key") == "********":
            merged["secret_access_key"] = current.get("secret_access_key")
        if payload.get("passphrase") == "********":
            merged["passphrase"] = current.get("passphrase")
        updated = config.update({"backup": merged})
        return dict(updated.get("backup") or {})

    def test_connection(self) -> dict[str, object]:
        client = CloudflareR2Client(config.get_backup_settings())
        try:
            return client.test_connection()
        finally:
            client.close()

    def list_backups(self) -> list[dict[str, object]]:
        if not self.is_configured():
            return []
        client = CloudflareR2Client(config.get_backup_settings())
        try:
            items = client.list_objects()
        finally:
            client.close()
        parsed: list[dict[str, object]] = []
        for item in items:
            key = _clean(item.get("key"))
            name = key.rsplit("/", 1)[-1]
            encrypted = name.endswith(".enc")
            parsed.append({
                "key": key,
                "name": name,
                "size": int(item.get("size") or 0),
                "updated_at": item.get("updated_at"),
                "encrypted": encrypted,
            })
        return parsed

    def delete_backup(self, key: str) -> None:
        candidate = _clean(key)
        if not candidate:
            raise BackupError(t("backup.key_required"))
        client = CloudflareR2Client(config.get_backup_settings())
        try:
            client.delete_object(candidate)
        finally:
            client.close()

    def download_backup(self, key: str) -> dict[str, object]:
        candidate = _clean(key)
        if not candidate:
            raise BackupError(t("backup.key_required"))
        client = CloudflareR2Client(config.get_backup_settings())
        try:
            payload = client.download_bytes(candidate)
        finally:
            client.close()
        name = candidate.rsplit("/", 1)[-1] or "backup.bin"
        if candidate.endswith(".enc"):
            passphrase = _clean(config.get_backup_settings().get("passphrase"))
            if not passphrase:
                raise BackupError(t("backup.passphrase_missing_download"))
            payload = _openssl_decrypt(payload, passphrase)
            if name.endswith(".enc"):
                name = name[:-4] or "backup.tar.gz"
        return {
            "key": candidate,
            "name": name,
            "content_type": _guess_content_type(name),
            "payload": payload,
            "size": len(payload),
        }

    def get_backup_detail(self, key: str) -> dict[str, object]:
        candidate = _clean(key)
        if not candidate:
            raise BackupError(t("backup.key_required"))
        client = CloudflareR2Client(config.get_backup_settings())
        try:
            payload = client.download_bytes(candidate)
        finally:
            client.close()
        detail = self._decode_backup_payload(candidate, payload)
        detail["key"] = candidate
        detail["name"] = candidate.rsplit("/", 1)[-1]
        detail["encrypted"] = candidate.endswith(".enc")
        return detail

    def run_backup(self, *, trigger: str = "manual") -> dict[str, object]:
        with self._lock:
            current = self.get_status()
            if self._running:
                raise BackupError(t("backup.already_running"))
            started_at = _iso_now()
            self._running = True
            save_backup_state({
                "last_started_at": started_at,
                "last_finished_at": current.get("last_finished_at"),
                "last_status": "idle",
                "last_error": None,
                "last_object_key": current.get("last_object_key"),
            })
        try:
            result = self._run_backup_once(trigger=trigger)
            save_backup_state({
                "last_started_at": started_at,
                "last_finished_at": _iso_now(),
                "last_status": "success",
                "last_error": None,
                "last_object_key": result["key"],
            })
            return result
        except Exception as exc:
            save_backup_state({
                "last_started_at": started_at,
                "last_finished_at": _iso_now(),
                "last_status": "error",
                "last_error": str(exc) or exc.__class__.__name__,
                "last_object_key": current.get("last_object_key"),
            })
            raise
        finally:
            self._running = False

    def _run_backup_once(self, *, trigger: str) -> dict[str, object]:
        settings = config.get_backup_settings()
        client = CloudflareR2Client(settings)
        client.validate()
        payload_raw = self._build_backup_archive(settings, trigger=trigger)
        encrypted = bool(settings.get("encrypt"))
        if encrypted:
            passphrase = _clean(settings.get("passphrase"))
            if not passphrase:
                raise BackupError(t("backup.passphrase_missing_encrypt"))
            payload = _openssl_encrypt(payload_raw, passphrase)
            suffix = ".tar.gz.enc"
        else:
            payload = payload_raw
            suffix = ".tar.gz"
        timestamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
        random_tag = f"{random.randint(0, 0xFFFF):04x}"
        object_key = f"{client.prefix.rstrip('/')}/backup-{timestamp}-{random_tag}{suffix}"
        metadata = {
            "created-at": _iso_now(),
            "encrypted": "true" if encrypted else "false",
            "trigger": trigger,
        }
        try:
            result = client.upload_bytes(object_key, payload, content_type="application/octet-stream", metadata=metadata)
            self._apply_rotation(client, int(settings.get("rotation_keep") or 0))
            return {
                "key": result["key"],
                "size": len(payload),
                "encrypted": encrypted,
            }
        finally:
            client.close()

    def _decode_backup_payload(self, key: str, payload: bytes) -> dict[str, object]:
        decoded = payload
        if key.endswith(".enc"):
            passphrase = _clean(config.get_backup_settings().get("passphrase"))
            if not passphrase:
                raise BackupError(t("backup.passphrase_missing_view"))
            decoded = _openssl_decrypt(decoded, passphrase)
        return self._decode_archive_detail(decoded)

    def _apply_rotation(self, client: CloudflareR2Client, keep: int) -> None:
        if keep <= 0:
            return
        items = [item for item in client.list_objects() if _is_backup_object(item.get("key"))]
        if len(items) <= keep:
            return
        for item in items[keep:]:
            key = _clean(item.get("key"))
            if key:
                client.delete_object(key)

    def _decode_archive_detail(self, payload: bytes) -> dict[str, object]:
        files: list[dict[str, object]] = []
        snapshots: list[dict[str, object]] = []
        metadata: dict[str, object] = {}
        try:
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
                members = [member for member in archive.getmembers() if member.isfile()]
                for member in members:
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        continue
                    raw = extracted.read()
                    name = member.name
                    if name == "backup-metadata.json":
                        try:
                            parsed = json.loads(raw.decode("utf-8"))
                            if isinstance(parsed, dict):
                                metadata = parsed
                        except Exception:
                            metadata = {}
                        continue
                    if name.startswith("snapshots/") and name.endswith(".json"):
                        count = 0
                        try:
                            parsed_snapshot = json.loads(raw.decode("utf-8"))
                            count = _count_items(parsed_snapshot)
                        except Exception:
                            count = 0
                        snapshots.append({
                            "name": name.removeprefix("snapshots/").removesuffix(".json"),
                            "count": count,
                        })
                        continue
                    files.append({
                        "name": name,
                        "exists": True,
                        "content_type": _guess_content_type(name),
                        "size": len(raw),
                        "sha256": _sha256_hex(raw),
                    })
        except tarfile.TarError as exc:
            raise BackupError(t("backup.archive_corrupted")) from exc
        files.sort(key=lambda item: str(item.get("name") or ""))
        snapshots.sort(key=lambda item: str(item.get("name") or ""))
        return {
            "created_at": metadata.get("created_at"),
            "trigger": metadata.get("trigger"),
            "app_version": metadata.get("app_version"),
            "storage_backend": metadata.get("storage_backend"),
            "files": files,
            "snapshots": snapshots,
        }

    def _build_backup_archive(self, settings: dict[str, object], *, trigger: str) -> bytes:
        include = settings.get("include") if isinstance(settings.get("include"), dict) else {}
        metadata = {
            "version": 2,
            "created_at": _iso_now(),
            "trigger": trigger,
            "app_version": config.app_version,
            "storage_backend": config.get_storage_backend().get_backend_info(),
        }
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            self._add_bytes_to_archive(archive, "backup-metadata.json", _json_bytes(metadata))
            if include.get("config"):
                self._add_file_to_archive(archive, CONFIG_FILE, "config.json")
            if include.get("cpa"):
                self._add_file_to_archive(archive, DATA_DIR / "cpa_config.json", "data/cpa_config.json")
            if include.get("sub2api"):
                self._add_file_to_archive(archive, DATA_DIR / "sub2api_config.json", "data/sub2api_config.json")
            if include.get("logs"):
                self._add_file_to_archive(archive, DATA_DIR / "logs.jsonl", "data/logs.jsonl")
            if include.get("image_tasks"):
                self._add_file_to_archive(archive, DATA_DIR / "image_tasks.json", "data/image_tasks.json")
                self._add_file_to_archive(archive, IMAGE_INDEX_FILE, "data/image_index.json")
            if include.get("accounts_snapshot"):
                self._add_bytes_to_archive(
                    archive,
                    "snapshots/accounts.json",
                    _json_bytes(config.get_storage_backend().load_accounts()),
                )
            if include.get("auth_keys_snapshot"):
                self._add_bytes_to_archive(
                    archive,
                    "snapshots/auth_keys.json",
                    _json_bytes(config.get_storage_backend().load_auth_keys()),
                )
            if include.get("images"):
                self._add_file_to_archive(archive, TAGS_FILE, "data/image_tags.json")
                self._add_directory_to_archive(archive, config.images_dir, "data/images")
        return buffer.getvalue()

    def _add_bytes_to_archive(self, archive: tarfile.TarFile, name: str, payload: bytes) -> None:
        info = tarfile.TarInfo(name=name)
        info.size = len(payload)
        info.mtime = int(_utc_now().timestamp())
        archive.addfile(info, io.BytesIO(payload))

    def _add_file_to_archive(self, archive: tarfile.TarFile, source: Path, arcname: str) -> None:
        if not source.exists() or not source.is_file():
            return
        archive.add(source, arcname=arcname)

    def _add_directory_to_archive(self, archive: tarfile.TarFile, source_dir: Path, arcname_root: str) -> None:
        if not source_dir.exists() or not source_dir.is_dir():
            return
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                relative = path.relative_to(source_dir).as_posix()
                archive.add(path, arcname=f"{arcname_root}/{relative}")


backup_service = BackupService()
