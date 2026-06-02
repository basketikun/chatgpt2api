from __future__ import annotations

import io
import shutil
import threading
import time
import zipfile
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps

from services.config import config
from services.image_storage_service import image_storage_service
from services.image_tags_service import load_tags, remove_tags
from utils.log import logger

THUMBNAIL_SIZE = (320, 320)


def _cleanup_empty_dirs(root: Path) -> None:
    for path in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass


def _safe_relative_path(path: str) -> str:
    value = str(path or "").strip().replace("\\", "/").lstrip("/")
    if not value:
        raise HTTPException(status_code=404, detail="image not found")
    parts = Path(value).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise HTTPException(status_code=404, detail="image not found")
    return Path(*parts).as_posix()


def _safe_image_path(relative_path: str) -> Path:
    rel = _safe_relative_path(relative_path)
    root = config.images_dir.resolve()
    path = (root / rel).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="image not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="image not found")
    return path


def get_image_response(relative_path: str) -> FileResponse | Response:
    if image_storage_service.has_local(relative_path):
        return FileResponse(_safe_image_path(relative_path))
    return Response(content=image_storage_service.get_bytes(relative_path), media_type="image/png")


def _thumbnail_path(relative_path: str) -> Path:
    rel = _safe_relative_path(relative_path)
    return config.image_thumbnails_dir / f"{rel}.png"


def thumbnail_url(base_url: str, relative_path: str) -> str:
    return f"{base_url.rstrip('/')}/image-thumbnails/{_safe_relative_path(relative_path)}"


def _image_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        return None


def ensure_thumbnail(relative_path: str) -> Path:
    target = _thumbnail_path(relative_path)
    source_mtime = 0.0
    source: Path | None = None
    if image_storage_service.has_local(relative_path):
        source = _safe_image_path(relative_path)
        source_mtime = source.stat().st_mtime
    if target.exists() and (not source_mtime or target.stat().st_mtime >= source_mtime):
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        image_source = source if source is not None else io.BytesIO(image_storage_service.get_bytes(relative_path))
        with Image.open(image_source) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            image.save(target, format="PNG", optimize=True)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="failed to create thumbnail") from exc
    return target


def get_thumbnail_response(relative_path: str) -> FileResponse:
    return FileResponse(ensure_thumbnail(relative_path))


def get_image_download_response(relative_path: str) -> FileResponse:
    if image_storage_service.has_local(relative_path):
        path = _safe_image_path(relative_path)
        return FileResponse(path, filename=path.name)
    rel = _safe_relative_path(relative_path)
    return Response(
        content=image_storage_service.get_bytes(rel),
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{Path(rel).name}"'},
    )


def cleanup_image_thumbnails() -> int:
    thumbnails_root = config.image_thumbnails_dir
    removed = 0
    for path in thumbnails_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(thumbnails_root).as_posix()
        if not rel.endswith(".png") or not image_storage_service.exists(rel[:-4]):
            path.unlink()
            removed += 1
    _cleanup_empty_dirs(thumbnails_root)
    return removed

def list_images(base_url: str, start_date: str = "", end_date: str = "") -> dict[str, object]:
    config.cleanup_old_images()
    cleanup_image_thumbnails()
    all_tags = load_tags()
    items = [
        {
            **item,
            "url": str(item.get("url") or f"{base_url.rstrip('/')}/images/{item['path']}"),
            "thumbnail_url": thumbnail_url(base_url, str(item["path"])),
            "tags": all_tags.get(str(item["path"]), []),
        }
        for item in image_storage_service.list_items(base_url, start_date, end_date)
    ]
    groups: dict[str, list[dict[str, object]]] = {}
    for item in items:
        groups.setdefault(str(item["date"]), []).append(item)
    return {"items": items, "groups": [{"date": key, "items": value} for key, value in groups.items()]}


def delete_images(paths: list[str] | None = None, start_date: str = "", end_date: str = "", all_matching: bool = False) -> dict[str, int]:
    root = config.images_dir.resolve()
    targets = [
        str(item["path"])
        for item in image_storage_service.list_items("", start_date=start_date, end_date=end_date)
    ] if all_matching else (paths or [])
    removed = 0
    for item in targets:
        path = (root / item).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            continue
        if image_storage_service.delete(item):
            removed += 1
        for thumbnail in (_thumbnail_path(item), config.image_thumbnails_dir / _safe_relative_path(item)):
            if thumbnail.is_file():
                thumbnail.unlink()
        remove_tags(item)
    _cleanup_empty_dirs(root)
    _cleanup_empty_dirs(config.image_thumbnails_dir)
    return {"removed": removed}


def download_images_zip(paths: list[str]) -> io.BytesIO:
    root = config.images_dir.resolve()
    buf = io.BytesIO()
    added = 0
    used_names: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in paths:
            rel = _safe_relative_path(item)
            path = (root / rel).resolve()
            payload: bytes | None = None
            try:
                path.relative_to(root)
            except ValueError:
                continue
            if path.is_file():
                payload = path.read_bytes()
            else:
                try:
                    payload = image_storage_service.get_bytes(rel)
                except Exception:
                    continue
            name = path.name
            if name in used_names:
                stem = path.stem
                suffix = path.suffix
                counter = 2
                while f"{stem}_{counter}{suffix}" in used_names:
                    counter += 1
                name = f"{stem}_{counter}{suffix}"
            used_names.add(name)
            zf.writestr(name, payload)
            added += 1
    if added == 0:
        raise HTTPException(status_code=404, detail="no images found")
    buf.seek(0)
    return buf
def storage_stats() -> dict:
    import shutil
    usage = shutil.disk_usage(config.images_dir)
    total_mb = usage.total // (1024 * 1024)
    used_mb = usage.used // (1024 * 1024)
    free_mb = usage.free // (1024 * 1024)

    image_count = 0
    image_size = 0
    for p in config.images_dir.rglob("*"):
        if p.is_file():
            image_count += 1
            image_size += p.stat().st_size

    return {
        "disk_total_mb": total_mb,
        "disk_used_mb": used_mb,
        "disk_free_mb": free_mb,
        "image_count": image_count,
        "image_size_mb": image_size // (1024 * 1024),
        "image_size_bytes": image_size,
    }


def compress_images(quality: int = 60) -> dict:
    """重新压缩所有图片，返回节省的空间"""
    saved = 0
    count = 0
    for p in sorted(config.images_dir.rglob("*.png")):
        if not p.is_file():
            continue
        try:
            orig = p.stat().st_size
            with Image.open(p) as img:
                img = ImageOps.exif_transpose(img)
                img.save(str(p) + ".tmp", format="PNG", optimize=True)
            new_size = Path(str(p) + ".tmp").stat().st_size
            if new_size < orig:
                Path(str(p) + ".tmp").replace(p)
                saved += orig - new_size
                count += 1
            else:
                Path(str(p) + ".tmp").unlink()
        except (OSError, ValueError):
            pass
    return {"compressed": count, "saved_bytes": saved, "saved_mb": saved // (1024 * 1024)}


def delete_to_target(target_free_mb: int, dry_run: bool = False) -> dict:
    """删除最旧的图片直到剩余空间达到 target_free_mb"""
    import shutil
    usage = shutil.disk_usage(config.images_dir)
    current_free = usage.free // (1024 * 1024)
    if current_free >= target_free_mb and not dry_run:
        return {"removed": 0, "current_free_mb": current_free, "target_free_mb": target_free_mb, "done": True}

    files = sorted(
        (p for p in config.images_dir.rglob("*.png") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
    )
    removed = 0
    freed = 0
    for p in files:
        if current_free + freed // (1024 * 1024) >= target_free_mb:
            break
        size = p.stat().st_size
        if not dry_run:
            rel = p.relative_to(config.images_dir).as_posix()
            for tp in (_thumbnail_path(rel), config.image_thumbnails_dir / _safe_relative_path(rel)):
                if tp.is_file():
                    tp.unlink()
            remove_tags(rel)
            p.unlink()
        freed += size
        removed += 1

    if not dry_run:
        _cleanup_empty_dirs(config.images_dir)
        _cleanup_empty_dirs(config.image_thumbnails_dir)

    return {
        "removed": removed,
        "freed_mb": freed // (1024 * 1024),
        "target_free_mb": target_free_mb,
        "current_free_mb": current_free + (freed // (1024 * 1024)),
        "done": (current_free + freed // (1024 * 1024)) >= target_free_mb,
        "dry_run": dry_run,
    }


def download_images_zip(paths: list[str]) -> io.BytesIO:
    root = config.images_dir.resolve()
    buf = io.BytesIO()
    added = 0
    used_names: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in paths:
            rel = _safe_relative_path(item)
            path = (root / rel).resolve()
            try:
                path.relative_to(root)
            except ValueError:
                continue
            if not path.is_file():
                continue
            name = path.name
            if name in used_names:
                stem = path.stem
                suffix = path.suffix
                counter = 2
                while f"{stem}_{counter}{suffix}" in used_names:
                    counter += 1
                name = f"{stem}_{counter}{suffix}"
            used_names.add(name)
            zf.write(path, name)
            added += 1
    if added == 0:
        raise HTTPException(status_code=404, detail="no images found")
    buf.seek(0)
    return buf


def _auto_cleanup_worker(stop_event: threading.Event) -> None:
    """后台线程：每30分钟检查存储，空间低于阈值自动清理最旧图片"""
    import shutil
    min_free_mb = getattr(config, "image_min_free_mb", None)
    if min_free_mb is None:
        min_free_mb = 500

    while not stop_event.wait(1800):  # 每30分钟
        try:
            config.cleanup_old_images()
            cleanup_image_thumbnails()
            usage = shutil.disk_usage(config.images_dir)
            free_mb = usage.free // (1024 * 1024)
            if free_mb < min_free_mb:
                logger.info({"event": "image_auto_cleanup", "free_mb": free_mb, "min_free_mb": min_free_mb})
                result = delete_to_target(min_free_mb)
                logger.info({"event": "image_auto_cleanup_done", **result})
        except (OSError, ValueError):
            pass


def start_image_cleanup_scheduler(stop_event: threading.Event) -> threading.Thread:
    t = threading.Thread(target=_auto_cleanup_worker, args=(stop_event,), daemon=True, name="image-cleanup")
    t.start()
    return t
