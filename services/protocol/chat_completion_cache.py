from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator

from services.config import config

CACHEABLE_TEXT_KEYS = {
    "frequency_penalty",
    "max_completion_tokens",
    "max_tokens",
    "metadata",
    "model",
    "presence_penalty",
    "reasoning_effort",
    "response_format",
    "seed",
    "stop",
    "temperature",
    "thinking_effort",
    "tool_choice",
    "tools",
    "top_p",
    "user",
    "reasoning",
}


@dataclass
class CacheEntry:
    expires_at: float
    value: Any


@dataclass
class InflightCall:
    condition: threading.Condition = field(default_factory=lambda: threading.Condition(threading.RLock()))
    done: bool = False
    value: Any = None
    error: BaseException | None = None


def _json_safe(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes_sha256__": hashlib.sha256(value).hexdigest(), "length": len(value)}
    if isinstance(value, bytearray):
        data = bytes(value)
        return {"__bytes_sha256__": hashlib.sha256(data).hexdigest(), "length": len(data)}
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def canonical_body(body: dict[str, Any], messages: list[dict[str, Any]], *, stream: bool) -> dict[str, Any]:
    payload = {key: body.get(key) for key in CACHEABLE_TEXT_KEYS if key in body}
    payload["messages"] = messages
    payload["stream"] = bool(stream)
    return payload


def cache_key(body: dict[str, Any], messages: list[dict[str, Any]], *, stream: bool) -> str:
    encoded = json.dumps(
        _json_safe(canonical_body(body, messages, stream=stream)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _message_signature(message: dict[str, Any]) -> str:
    return json.dumps(_json_safe(message), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalize_text_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    settings = config.get_chat_completion_cache_settings()
    if not settings.get("normalize_messages"):
        return messages

    normalized: list[dict[str, Any]] = []
    previous_signature = ""
    for message in messages:
        if settings.get("drop_assistant_history") and str(message.get("role") or "") == "assistant":
            continue
        signature = _message_signature(message)
        if settings.get("drop_adjacent_duplicates") and signature == previous_signature:
            continue
        normalized.append(message)
        previous_signature = signature
    return normalized


class ChatCompletionCache:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, CacheEntry] = {}
        self._inflight: dict[str, InflightCall] = {}

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._inflight.clear()

    def _settings(self) -> dict[str, object]:
        return config.get_chat_completion_cache_settings()

    def _prune_locked(self, now: float, max_entries: int) -> None:
        expired = [key for key, item in self._entries.items() if item.expires_at <= now]
        for key in expired:
            self._entries.pop(key, None)
        while len(self._entries) > max_entries:
            oldest_key = min(self._entries, key=lambda key: self._entries[key].expires_at)
            self._entries.pop(oldest_key, None)

    @staticmethod
    def _copy(value: Any) -> Any:
        return copy.deepcopy(value)

    def get_or_compute_response(self, key: str, compute: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        settings = self._settings()
        if not settings.get("enabled") or int(settings.get("ttl_seconds") or 0) <= 0:
            return compute()

        now = time.time()
        max_entries = int(settings.get("max_entries") or 1)
        with self._lock:
            self._prune_locked(now, max_entries)
            entry = self._entries.get(key)
            if entry and entry.expires_at > now:
                return self._copy(entry.value)
            inflight = self._inflight.get(key) if settings.get("dedupe_inflight") else None
            if inflight is None:
                inflight = InflightCall()
                if settings.get("dedupe_inflight"):
                    self._inflight[key] = inflight
                owner = True
            else:
                owner = False

        if not owner:
            with inflight.condition:
                while not inflight.done:
                    inflight.condition.wait()
                if inflight.error:
                    raise inflight.error
                return self._copy(inflight.value)

        try:
            value = compute()
        except BaseException as exc:
            with self._lock:
                self._inflight.pop(key, None)
            with inflight.condition:
                inflight.error = exc
                inflight.done = True
                inflight.condition.notify_all()
            raise

        expires_at = time.time() + int(settings.get("ttl_seconds") or 0)
        with self._lock:
            self._entries[key] = CacheEntry(expires_at=expires_at, value=self._copy(value))
            self._prune_locked(time.time(), max_entries)
            self._inflight.pop(key, None)
        with inflight.condition:
            inflight.value = self._copy(value)
            inflight.done = True
            inflight.condition.notify_all()
        return value

    def get_or_compute_stream(self, key: str, compute: Callable[[], Iterable[dict[str, Any]]]) -> Iterator[dict[str, Any]]:
        settings = self._settings()
        if (
            not settings.get("enabled")
            or not settings.get("stream_cache")
            or int(settings.get("ttl_seconds") or 0) <= 0
        ):
            yield from compute()
            return

        now = time.time()
        max_entries = int(settings.get("max_entries") or 1)
        with self._lock:
            self._prune_locked(now, max_entries)
            entry = self._entries.get(key)
            if entry and entry.expires_at > now:
                yield from self._copy(entry.value)
                return
            inflight = self._inflight.get(key) if settings.get("dedupe_inflight") else None
            if inflight is None:
                inflight = InflightCall()
                if settings.get("dedupe_inflight"):
                    self._inflight[key] = inflight
                owner = True
            else:
                owner = False

        if not owner:
            with inflight.condition:
                while not inflight.done:
                    inflight.condition.wait()
                if inflight.error:
                    raise inflight.error
                yield from self._copy(inflight.value)
                return

        chunks: list[dict[str, Any]] = []
        try:
            for chunk in compute():
                chunks.append(self._copy(chunk))
                yield chunk
        except BaseException as exc:
            with self._lock:
                self._inflight.pop(key, None)
            with inflight.condition:
                inflight.error = exc
                inflight.done = True
                inflight.condition.notify_all()
            raise

        expires_at = time.time() + int(settings.get("ttl_seconds") or 0)
        with self._lock:
            self._entries[key] = CacheEntry(expires_at=expires_at, value=self._copy(chunks))
            self._prune_locked(time.time(), max_entries)
            self._inflight.pop(key, None)
        with inflight.condition:
            inflight.value = self._copy(chunks)
            inflight.done = True
            inflight.condition.notify_all()


chat_completion_cache = ChatCompletionCache()
