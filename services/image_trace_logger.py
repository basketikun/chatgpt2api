from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from services.config import config

_lock = threading.Lock()
BEIJING_TZ = timezone(timedelta(hours=8))


EVENT_LABELS = {
    "request.start": "请求开始",
    "request.success": "请求成功",
    "request.error": "请求失败",
    "request.validation_error": "参数校验失败",
    "request.uploads.read": "上传文件读取完成",
    "openai.generate.start": "OpenAI 生图开始",
    "openai.edit.start": "OpenAI 编辑开始",
    "chatgpt_pool.generate.start": "账号池生图开始",
    "chatgpt_pool.generate.success": "账号池生图成功",
    "chatgpt_pool.edit.start": "账号池编辑开始",
    "chatgpt_pool.edit.success": "账号池编辑成功",
    "upstream.attempt.start": "上游请求尝试开始",
    "upstream.request": "上游请求已发送",
    "upstream.response": "上游响应成功",
    "upstream.attempt.success": "上游请求尝试成功",
    "upstream.attempt.error": "上游请求尝试失败",
    "upstream.retry.sleep": "等待重试上游请求",
    "image.save.start": "保存图片开始",
    "image.save.file": "图片文件已保存",
    "image.save.skip": "跳过保存图片",
    "image.save.error": "保存图片失败",
    "image.save.complete": "保存图片完成",
    "prompt_optimizer.model.start": "提示词优化模型开始",
    "prompt_optimizer.model.success": "提示词优化模型成功",
    "prompt_optimizer.model.error": "提示词优化模型失败",
}

OPS_FIELD_LABELS = {
    "kind": "类型",
    "route": "接口",
    "mode": "模式",
    "upstream": "上游",
    "model": "模型",
    "n": "数量",
    "response_format": "响应格式",
    "prompt_length": "提示词长度",
    "duration_ms": "耗时",
    "item_count": "结果数",
    "input_images": "输入图片",
    "saved_images": "已保存图片",
    "file_name": "文件名",
    "file_path": "文件路径",
    "file_size": "文件大小",
    "images_dir": "图片目录",
    "index": "序号",
    "path": "上游路径",
    "method": "方法",
    "attempt": "尝试次数",
    "max_attempts": "最大尝试次数",
    "next_attempt": "下次尝试",
    "wait_seconds": "等待秒数",
    "status": "状态码",
    "files": "文件数",
    "field": "字段",
    "reason": "原因",
    "error_type": "错误类型",
    "error": "错误",
    "last_error": "上次错误",
    "optimizer": "优化器",
    "original_length": "原始长度",
    "optimized_length": "优化后长度",
}

OPS_FIELD_ORDER = [
    "kind",
    "route",
    "mode",
    "upstream",
    "model",
    "n",
    "response_format",
    "prompt_length",
    "duration_ms",
    "item_count",
    "input_images",
    "saved_images",
    "file_name",
    "file_path",
    "file_size",
    "images_dir",
    "index",
    "path",
    "method",
    "attempt",
    "max_attempts",
    "next_attempt",
    "wait_seconds",
    "status",
    "files",
    "field",
    "reason",
    "error_type",
    "error",
    "last_error",
    "optimizer",
    "original_length",
    "optimized_length",
]

OPS_DETAIL_SKIP_FIELDS = {"ts", "elapsed_ms", "trace_id", "event", "prompt"}


def _now_beijing() -> datetime:
    return datetime.now(BEIJING_TZ)


def _now_iso() -> str:
    return _now_beijing().isoformat(timespec="seconds")


def _safe_json(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _safe_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _truncate_prompt(prompt: str, limit: int = 4000) -> str:
    prompt = str(prompt or "")
    if len(prompt) <= limit:
        return prompt
    return prompt[:limit] + f"... [truncated {len(prompt) - limit} chars]"


def _ops_prompt_preview(prompt: str, limit: int = 120) -> str:
    prompt = " ".join(str(prompt or "").split())
    if len(prompt) <= limit:
        return prompt
    return prompt[:limit] + f"...（已省略 {len(prompt) - limit} 字）"


def _format_ops_value(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if value is None:
        return "空"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _format_ops_detail(payload: dict[str, Any]) -> str:
    ordered_keys = [key for key in OPS_FIELD_ORDER if key in payload]
    extra_keys = sorted(
        key for key in payload if key not in OPS_DETAIL_SKIP_FIELDS and key not in ordered_keys
    )
    parts = []
    for key in [*ordered_keys, *extra_keys]:
        value = payload.get(key)
        label = OPS_FIELD_LABELS.get(key, key)
        if key == "duration_ms":
            parts.append(f"{label}={value}ms")
        elif key == "wait_seconds":
            parts.append(f"{label}={value}s")
        else:
            parts.append(f"{label}={_format_ops_value(value)}")
    prompt = payload.get("prompt")
    if isinstance(prompt, str) and prompt.strip():
        parts.append(f"提示词预览={_ops_prompt_preview(prompt)}")
    return "；".join(parts)


def _format_ops_line(payload: dict[str, Any]) -> str:
    label = EVENT_LABELS.get(str(payload.get("event") or ""), str(payload.get("event") or "事件"))
    detail = _format_ops_detail(payload)
    base = (
        f"[{payload['ts']}] [{payload['trace_id']}] "
        f"+{payload['elapsed_ms']}ms {label}"
    )
    if not detail:
        return base + "\n"
    return f"{base}：{detail}\n"


class ImageTraceLogger:
    def __init__(self, trace_id: str, ai_file_path: Path, ops_file_path: Path):
        self.trace_id = trace_id
        self.ai_file_path = ai_file_path
        self.ops_file_path = ops_file_path
        self.started = time.time()

    def event(self, name: str, **fields: Any) -> None:
        payload = {
            "ts": _now_iso(),
            "elapsed_ms": int((time.time() - self.started) * 1000),
            "trace_id": self.trace_id,
            "event": name,
            **{key: _safe_json(value) for key, value in fields.items()},
        }
        ai_line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        ops_line = _format_ops_line(payload)
        self.ai_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.ops_file_path.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            with self.ai_file_path.open("a", encoding="utf-8") as handle:
                handle.write(ai_line)
            with self.ops_file_path.open("a", encoding="utf-8") as handle:
                handle.write(ops_line)


def start_image_trace(kind: str, prompt: str, **fields: Any) -> ImageTraceLogger:
    config.logs_dir.mkdir(parents=True, exist_ok=True)
    trace_id = uuid.uuid4().hex[:12]
    stem = f"image-{_now_beijing().strftime('%Y%m%d-%H%M%S')}-{trace_id}"
    logger = ImageTraceLogger(
        trace_id=trace_id,
        ai_file_path=config.logs_dir / "ai" / f"{stem}.jsonl",
        ops_file_path=config.logs_dir / "ops" / f"{stem}.log",
    )
    logger.event(
        "request.start",
        kind=kind,
        prompt=_truncate_prompt(prompt),
        prompt_length=len(str(prompt or "")),
        **fields,
    )
    return logger
