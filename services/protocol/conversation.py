from __future__ import annotations

import base64
import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

import tiktoken

from services.account_service import account_service
from services.config import config
from services.openai_backend_api import OpenAIBackendAPI
from utils.helper import IMAGE_MODELS, extract_image_from_message_content
from utils.log import logger

TOOL_CALL_RE = re.compile(r'<tool_call\s+name=["\'](.+?)["\']>(.*?)</tool_call>', re.DOTALL)
TOOL_CALL_DIRECT_RE = re.compile(r'<([A-Z][A-Za-z0-9_]*?)>(.*?)</\1>', re.DOTALL)
TOOL_CALL_SELF_CLOSING_RE = re.compile(r'<tool_call\s+name=["\'](.+?)["\']\s*/>', re.DOTALL)
TOOL_CALL_DIRECT_SELF_CLOSING_RE = re.compile(r'<([A-Z][A-Za-z0-9_]*?)\s*/>', re.DOTALL)
JSON_TOOL_CALL_RE = re.compile(r'\{\s*"path"\s*:\s*"([^"]+)"\s*,\s*"args"\s*:\s*(\{.*?\})\s*\}', re.DOTALL)
CONTROL_TOKEN_RE = re.compile(r'<\|im_(?:start|end)\|>')
# Strip ChatGPT internal citation markers, e.g. citeturn0search7, 【4†citeturn0search8】
CITATION_RE = re.compile(r'【?[0-9†]*\s*citeturn[^\s】]*\s*】?', re.IGNORECASE)


# Exact XML_WRAP_HINT from Gemini-FastAPI
_XML_WRAP_HINT = (
    "\nYou MUST wrap every tool call response inside a single fenced block exactly like:\n"
    '```xml\n<tool_call name="tool_name">{"arg": "value"}</tool_call>\n```\n'
    "Do not surround the fence with any other text or whitespace; otherwise the call will be ignored.\n"
)


def _build_tool_prompt(tools: list[dict[str, Any]], tool_choice: Any = None) -> str:
    """Generate a system prompt chunk describing available tools. Mirrors Gemini-FastAPI _build_tool_prompt."""
    if not tools:
        return ""
    lines: list[str] = [
        "You can invoke the following developer tools. Call a tool only when it is required and follow the JSON schema exactly when providing arguments."
    ]
    for tool in tools:
        f = tool.get("function", {})
        name = f.get("name")
        desc = f.get("description") or "No description provided."
        lines.append(f"Tool `{name}`: {desc}")
        params = f.get("parameters") or {}
        properties = params.get("properties") or {}
        if properties:
            schema_text = json.dumps(params, ensure_ascii=False, indent=2)
            lines.append("Arguments JSON schema:")
            lines.append(schema_text)
        else:
            lines.append("Arguments JSON schema: {}")
            lines.append(f"  >> `{name}` requires NO arguments. You MUST call it with exactly: {{}}")

    if tool_choice == "none":
        lines.append(
            "For this request you must not call any tool. Provide the best possible natural language answer."
        )
    elif tool_choice == "required":
        lines.append(
            "You must call at least one tool before responding to the user. Do not provide a final user-facing answer until a tool call has been issued."
        )
    elif isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
        target = (tool_choice.get("function") or {}).get("name", "")
        if target:
            lines.append(
                f"You are required to call the tool named `{target}`. Do not call any other tool."
            )

    lines.append(
        "When you decide to call a tool you MUST respond with nothing except a single fenced block exactly like the template below."
    )
    lines.append(
        "The fenced block MUST use ```xml as the opening fence and ``` as the closing fence. Do not add text before or after it."
    )
    lines.append("```xml")
    lines.append('<tool_call name="tool_name">{"argument": "value"}</tool_call>')
    lines.append("```")
    lines.append(
        "Use double quotes for JSON keys and values. If you omit the fenced block or include any extra text, the system will assume you are NOT calling a tool and your request will fail."
    )
    lines.append(
        "If multiple tool calls are required, include multiple <tool_call> entries inside the same fenced block. Without a tool call, reply normally and do NOT emit any ```xml fence."
    )
    return "\n".join(lines)


def _strip_system_hints(text: str) -> str:
    """Remove system-level hint text and ChatGPT internal markers from responses."""
    if not text:
        return text
    text = CONTROL_TOKEN_RE.sub("", text)
    text = CITATION_RE.sub("", text)
    return text.strip()


class ImageGenerationError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 502,
        error_type: str = "server_error",
        code: str | None = "upstream_error",
        param: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type
        self.code = code
        self.param = param

    def to_openai_error(self) -> dict[str, Any]:
        return {
            "error": {
                "message": str(self),
                "type": self.error_type,
                "param": self.param,
                "code": self.code,
            }
        }


def is_token_invalid_error(message: str) -> bool:
    text = str(message or "").lower()
    return (
        "token_invalidated" in text
        or "token_revoked" in text
        or "authentication token has been invalidated" in text
        or "invalidated oauth token" in text
    )


def image_stream_error_message(message: str) -> str:
    text = str(message or "")
    lower = text.lower()
    if "curl: (35)" in lower or "tls connect error" in lower or "openssl_internal" in lower:
        return "upstream image connection failed, please retry later"
    return text or "image generation failed"


def encode_images(images: Iterable[tuple[bytes, str, str]]) -> list[str]:
    return [base64.b64encode(data).decode("ascii") for data, _, _ in images if data]


def save_image_bytes(image_data: bytes, base_url: str | None = None) -> str:
    config.cleanup_old_images()
    file_hash = hashlib.md5(image_data).hexdigest()
    filename = f"{int(time.time())}_{file_hash}.png"
    relative_dir = Path(time.strftime("%Y"), time.strftime("%m"), time.strftime("%d"))
    file_path = config.images_dir / relative_dir / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(image_data)
    return f"{(base_url or config.base_url)}/images/{relative_dir.as_posix()}/{filename}"


def message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and str(item.get("type") or "") in {"text", "input_text", "output_text"}:
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return ""


# Maximum payload size in bytes before triggering truncation.
# ChatGPT backend hard limit is ~100 KB; we sit at the cap.
_MAX_PAYLOAD_BYTES = 100_000

# RTK-inspired compression thresholds
_RTK_TOOL_RESULT_MAX = 600   # Keep first+last chars of tool results
_RTK_ASSISTANT_DEDUP = True   # Collapse repeated assistant content
_RTK_SYSTEM_ENTITY_TRIM = 0.7  # Keep 70% of system entity list when truncating

# File upload for large text content (bypasses payload limit via /backend-api/files).
# When a user message exceeds this byte threshold, the full content is preserved
# in _file_upload_store and replaced with a short marker. The marker is later
# resolved by OpenAIBackendAPI._api_messages_to_conversation_messages() which
# uploads the content as a .txt file and references it via asset_pointer.
_FILE_UPLOAD_THRESHOLD = 80_000
_FILE_UPLOAD_MARKER = "[FILE_UPLOAD:"
_file_upload_store: dict[str, str] = {}


def _rtk_compress_tool_result(content: str) -> str:
    """RTK-style: compress large tool call results (keep head + tail)."""
    if len(content) <= _RTK_TOOL_RESULT_MAX:
        return content
    head = content[:_RTK_TOOL_RESULT_MAX // 2]
    tail = content[-(_RTK_TOOL_RESULT_MAX // 2):]
    return f"{head}\n\n[... {len(content) - _RTK_TOOL_RESULT_MAX} chars compressed ...]\n\n{tail}"


def _has_image_content(msg: dict[str, Any]) -> bool:
    """Check if a message contains images (should never be dropped)."""
    content = msg.get("content")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") in ("image", "image_url", "input_image"):
                return True
    return False


def _rtk_compress_messages(messages: list[dict[str, Any]], max_bytes: int = _MAX_PAYLOAD_BYTES, file_upload_threshold: int = 0) -> list[dict[str, Any]]:
    """RTK-inspired smart message compression.

    Strategies (ordered by priority):
    0. Deduplicate consecutive identical tool results (HA sends duplicates)
    1. Compress tool result content (keep head+tail, not just truncate)
    2. Deduplicate repeated assistant messages
    3. Drop oldest non-system messages
    4. Truncate system message (keep structure)
    5. Compress large user messages (head+tail, or file-upload marker if threshold set)
    """
    import copy
    import hashlib

    # Step 0: Deduplicate consecutive tool messages by tool_call_id (HA sends twice)
    seen_tool_ids = set()
    deduped = []
    for msg in messages:
        tid = msg.get("tool_call_id") or ""
        if tid and msg.get("role") in ("tool", "tool_result"):
            if tid in seen_tool_ids:
                continue
            seen_tool_ids.add(tid)
        deduped.append(msg)
    messages = deduped

    payload = json.dumps(messages, ensure_ascii=False, default=str)
    if len(payload.encode("utf-8")) <= max_bytes:
        return messages

    # Deep copy to avoid mutating original
    msgs = copy.deepcopy(messages)

    # Step 1: Compress large tool results (RTK-style: keep head+tail)
    # For user messages > file_upload_threshold, use file-upload marker
    # (preserves full content for later upload via /backend-api/files).
    for msg in msgs:
        if msg.get("role") == "tool" and isinstance(msg.get("content"), str):
            msg["content"] = _rtk_compress_tool_result(msg["content"])
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            content = msg["content"]
            if file_upload_threshold > 0 and len(content.encode("utf-8")) > file_upload_threshold:
                key = hashlib.md5(content.encode()).hexdigest()[:16]
                _file_upload_store[key] = content
                preview = content[:500]
                msg["content"] = f"{_FILE_UPLOAD_MARKER}{key}]\n{preview}\n...[full content uploaded as file]..."
            elif len(content) > 3000:
                head = content[:1000]
                tail = content[-1000:]
                msg["content"] = f"{head}\n\n[... {len(content) - 2000} chars compressed ...]\n\n{tail}"

    payload = json.dumps(msgs, ensure_ascii=False, default=str)
    if len(payload.encode("utf-8")) <= max_bytes:
        return msgs

    # Step 2: Deduplicate repeated assistant messages
    if _RTK_ASSISTANT_DEDUP:
        seen: dict[str, int] = {}
        for i, msg in enumerate(msgs):
            if msg.get("role") == "assistant" and isinstance(msg.get("content"), str):
                key = msg["content"][:80]
                if key in seen:
                    msgs[seen[key]]["content"] += f" [repeated {i - seen[key]}x]"
                    msg["content"] = "[see above]"
                else:
                    seen[key] = i
        # Remove placeholder messages
        msgs = [m for m in msgs if not (m.get("role") == "assistant" and m.get("content") == "[see above]")]

    payload = json.dumps(msgs, ensure_ascii=False, default=str)
    if len(payload.encode("utf-8")) <= max_bytes:
        return msgs

    # Step 3: Drop oldest non-system messages (preserve messages with images)
    system_msgs = [m for m in msgs if m.get("role") == "system"]
    other_msgs = [m for m in msgs if m.get("role") != "system"]
    # Separate image-containing messages — never drop them
    img_msgs = [m for m in other_msgs if _has_image_content(m)]
    other_msgs = [m for m in other_msgs if not _has_image_content(m)]
    while other_msgs:
        test_payload = json.dumps(system_msgs + img_msgs + other_msgs, ensure_ascii=False, default=str)
        if len(test_payload.encode("utf-8")) <= max_bytes:
            break
        other_msgs.pop(0)
    other_msgs = img_msgs + other_msgs  # Image messages first

    # Step 4: Truncate system message (keep first 70% + last 30%)
    test_payload = json.dumps(system_msgs + other_msgs, ensure_ascii=False, default=str)
    if len(test_payload.encode("utf-8")) > max_bytes and system_msgs:
        last_sys = system_msgs[-1]
        if isinstance(last_sys.get("content"), str):
            content = last_sys["content"]
            excess = len(test_payload.encode("utf-8")) - max_bytes
            keep = max(500, int(len(content) * _RTK_SYSTEM_ENTITY_TRIM))
            allowed = max(300, len(content) - excess - 200)
            if len(content) > min(keep, allowed):
                cutoff = min(keep, allowed)
                last_sys["content"] = content[:cutoff] + "\n\n[... System entities truncated ...]"

    # Step 5: Compress last user message (head+tail)
    test_payload = json.dumps(system_msgs + other_msgs, ensure_ascii=False, default=str)
    if len(test_payload.encode("utf-8")) > max_bytes and other_msgs:
        last_user = other_msgs[-1]
        if last_user.get("role") == "user" and isinstance(last_user.get("content"), str):
            content = last_user["content"]
            excess = len(test_payload.encode("utf-8")) - max_bytes
            allowed = max(300, len(content) - excess - 100)
            if len(content) > allowed:
                half = max(150, allowed // 2)
                last_user["content"] = content[:half] + "\n\n[... truncated ...]\n\n" + content[-half:]

    return system_msgs + other_msgs


def _payload_size_bytes(messages: list[dict[str, Any]]) -> int:
    """Approximate the wire-size of the messages without inflating binary
    image data — `json.dumps(..., default=str)` stringifies bytes as
    `b'\\xff\\xd8...'` which is 3-4x larger than the actual upload size.
    Treat image parts as their raw byte length so the truncation gate
    doesn't drop messages just because they carry an image attachment.
    """
    total = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image":
                    data = part.get("data")
                    if isinstance(data, (bytes, bytearray)):
                        total += len(data)
                    else:
                        total += len(json.dumps(part, ensure_ascii=False, default=str).encode("utf-8"))
                else:
                    total += len(json.dumps(part, ensure_ascii=False, default=str).encode("utf-8"))
        else:
            total += len(json.dumps(content, ensure_ascii=False, default=str).encode("utf-8"))
        # Per-message overhead for role/keys
        total += 40
    return total


def _truncate_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop oldest non-system messages when the serialized payload exceeds the size limit.

    INVARIANT — DO NOT BREAK: every message that carries image content
    (`_has_image_content` returns True) MUST be present in the return
    value. The chatgpt/free/auto vision path through ChatGPT Web depends
    on this; if an image message is dropped here, the model receives only
    the system prompt and replies with a generic greeting (the "Chào bạn!"
    bug). The image-preserving split below — and the
    `chatgpt_web_vision_image_dropped` warning in
    `OpenAIBackendAPI.stream_conversation` — guard against the bytes-size
    inflation that made the original `json.dumps(..., default=str)` size
    estimate overshoot by 3-4x and trigger this loop on payloads that
    were actually well under the cap.

    If you reorganize this function, run
    `plans/test_vision_truncation_regression.py` and keep the existing
    behaviour — text-only history can still be trimmed, images cannot.
    """
    if _payload_size_bytes(messages) <= _MAX_PAYLOAD_BYTES:
        return messages

    system_msgs = [m for m in messages if m.get("role") == "system"]
    other_msgs = [m for m in messages if m.get("role") != "system"]
    img_msgs = [m for m in other_msgs if _has_image_content(m)]
    text_msgs = [m for m in other_msgs if not _has_image_content(m)]

    while text_msgs:
        if _payload_size_bytes(system_msgs + img_msgs + text_msgs) <= _MAX_PAYLOAD_BYTES:
            break
        text_msgs.pop(0)

    remaining = system_msgs + img_msgs + text_msgs
    if _payload_size_bytes(remaining) > _MAX_PAYLOAD_BYTES and system_msgs:
        last_sys = system_msgs[-1]
        if isinstance(last_sys.get("content"), str):
            content = last_sys["content"]
            excess = _payload_size_bytes(remaining) - _MAX_PAYLOAD_BYTES
            allowed_len = max(500, len(content) - excess - 200)
            if len(content) > allowed_len:
                last_sys["content"] = content[:allowed_len] + "\n\n[System prompt truncated due to size limits]"

    if text_msgs and _payload_size_bytes(remaining) > _MAX_PAYLOAD_BYTES:
        last_user = text_msgs[-1]
        if last_user.get("role") == "user" and isinstance(last_user.get("content"), str):
            content = last_user["content"]
            excess = _payload_size_bytes(remaining) - _MAX_PAYLOAD_BYTES
            allowed_len = max(500, len(content) - excess - 200)
            if len(content) > allowed_len:
                last_user["content"] = content[:allowed_len] + "\n\n[Content truncated due to size limits]"

    final = system_msgs + img_msgs + text_msgs
    # Invariant: no image message may be dropped. Surface a loud warning if
    # the future-proofing somehow regresses; never silently fall through.
    inbound_img_count = sum(1 for m in messages if _has_image_content(m))
    outbound_img_count = sum(1 for m in final if _has_image_content(m))
    if inbound_img_count != outbound_img_count:
        import logging
        logging.getLogger(__name__).error({
            "event": "truncate_messages_dropped_image",
            "inbound_img_count": inbound_img_count,
            "outbound_img_count": outbound_img_count,
            "inbound_total": len(messages),
            "outbound_total": len(final),
        })
    return final


def normalize_messages(messages: object, system: Any = None, tools: list[dict[str, Any]] | None = None, tool_choice: Any = None) -> list[dict[str, Any]]:
    normalized = []

    # Inject global system prompt and tools documentation
    system_instructions = config.global_system_prompt or ""

    # Inject Karpathy guidelines if mode enabled
    if config.karpathy_mode:
        from services.karpathy_guidelines import load_guidelines
        karpathy_prompt = load_guidelines()
        if karpathy_prompt:
            system_instructions = karpathy_prompt + "\n\n" + system_instructions

    if tools:
        system_instructions += _build_tool_prompt(tools, tool_choice=tool_choice)

    if system_instructions:
        normalized.append({"role": "system", "content": system_instructions})

    system_text = message_text(system)
    if system_text:
        normalized.append({"role": "system", "content": system_text})

    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role", "user")
            content = message.get("content", "")
            text = message_text(content)

            # Map 'developer' role to 'system' (Gemini-FastAPI compat)
            if role == "developer":
                role = "system"

            # Map 'tool_result' role (HA format) to 'tool' first
            if role == "tool_result":
                role = "tool"

            # Map 'tool' role to 'user' for Web ChatGPT visibility
            # Preserve tool_call_id in the text so the model understands context
            if role == "tool":
                role = "user"
                tool_call_id = message.get("tool_call_id") or ""
                tool_name = message.get("name") or ""
                header = "[Tool Result]"
                if tool_name:
                    header += f" {tool_name}"
                if tool_call_id:
                    header += f" (id: {tool_call_id})"
                # Detect tool failure to prevent infinite retry loops
                failure_suffix = ""
                try:
                    result_data = json.loads(text) if text else {}
                    if isinstance(result_data, dict) and result_data.get("success") is False:
                        err = result_data.get("error") or "unknown error"
                        failure_suffix = (
                            f"\n\n[STOP: Tool call FAILED: \"{err}\". "
                            "Do NOT retry this tool. Do NOT call any tool again. "
                            "Respond to the user in plain language explaining the issue.]"
                        )
                except (json.JSONDecodeError, TypeError):
                    pass
                text = f"{header}: {text}{failure_suffix}"

            images: list[tuple[bytes, str]] = []
            if role == "user":
                images.extend(extract_image_from_message_content(content))
                if isinstance(content, list):
                    for part in content:
                        if not isinstance(part, dict) or part.get("type") != "image":
                            continue
                        data = part.get("data")
                        if isinstance(data, (bytes, bytearray)):
                            images.append((bytes(data), str(part.get("mime") or "image/png")))
            if images:
                parts: list[Any] = []
                if text:
                    parts.append({"type": "text", "text": text})
                for data, mime in images:
                    parts.append({"type": "image", "data": data, "mime": mime})
                normalized.append({"role": role, "content": parts})
            elif isinstance(content, list):
                # Preserve original list content (may have image_url with HTTP URLs)
                preserved = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") in ("image_url", "input_image"):
                        preserved.append(part)
                    elif isinstance(part, dict) and part.get("type") == "text":
                        preserved.append(part)
                if preserved:
                    normalized.append({"role": role, "content": preserved})
                else:
                    msg = {"role": role, "content": text}
                    if "tool_calls" in message:
                        msg["tool_calls"] = message["tool_calls"]
                    if "tool_call_id" in message:
                        msg["tool_call_id"] = message["tool_call_id"]
                    if "name" in message:
                        msg["name"] = message["name"]
                    normalized.append(msg)
            else:
                msg = {"role": role, "content": text}
                if "tool_calls" in message:
                    msg["tool_calls"] = message["tool_calls"]
                if "tool_call_id" in message:
                    msg["tool_call_id"] = message["tool_call_id"]
                if "name" in message:
                    msg["name"] = message["name"]
                normalized.append(msg)

    # Inject XML tool-call hint into last user message (mirrors Gemini-FastAPI _append_xml_hint_to_last_user_message)
    if tools:
        hint_stripped = _XML_WRAP_HINT.strip()
        for i in range(len(normalized) - 1, -1, -1):
            if normalized[i].get("role") == "user":
                existing = normalized[i].get("content") or ""
                if isinstance(existing, str) and hint_stripped not in existing:
                    normalized[i] = dict(normalized[i])
                    normalized[i]["content"] = existing + _XML_WRAP_HINT
                break

    # Truncate oversized payload to prevent HTTP 413 errors
    normalized = _truncate_messages(normalized)
    return normalized


def prompt_with_global_system(prompt: str) -> str:
    return f"{config.global_system_prompt}\n\n{prompt}" if config.global_system_prompt else prompt


def assistant_history_text(messages: list[dict[str, Any]]) -> str:
    return "".join(str(item.get("content") or "") for item in messages if item.get("role") == "assistant")


def assistant_history_messages(messages: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("content") or "") for item in messages if item.get("role") == "assistant" and item.get("content")]


# Map of common OpenAI pixel sizes to aspect ratio strings
_PIXEL_SIZE_TO_RATIO: dict[str, str] = {
    "1024x1024": "1:1",
    "1792x1024": "16:9",
    "1024x1792": "9:16",
}


def build_image_prompt(prompt: str, size: str | None) -> str:
    if not size:
        size = "16:9"
    # Normalize pixel format (e.g. "1792x1024") to aspect ratio
    normalized = _PIXEL_SIZE_TO_RATIO.get(size, size)
    if normalized not in {"1:1", "16:9", "9:16", "4:3", "3:4"}:
        return f"{prompt.strip()}\n\n输出图片，宽高比为 {normalized}。"
    hint = {
        "1:1": "输出为 1:1 正方形构图，主体居中，适合正方形画幅。",
        "16:9": "输出为 16:9 横屏构图，适合宽画幅展示。",
        "9:16": "输出为 9:16 竖屏构图，适合竖版画幅展示。",
        "4:3": "输出为 4:3 比例，兼顾宽度与高度，适合展示画面细节。",
        "3:4": "输出为 3:4 比例，纵向构图，适合人物肖像或竖向场景。",
    }[normalized]
    return f"{prompt.strip()}\n\n{hint}"


def encoding_for_model(model: str):
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        try:
            return tiktoken.get_encoding("o200k_base")
        except KeyError:
            return tiktoken.get_encoding("cl100k_base")


def count_message_tokens(messages: list[dict[str, Any]], model: str) -> int:
    encoding = encoding_for_model(model)
    total = 0
    for message in messages:
        total += 3
        for key, value in message.items():
            if not isinstance(value, str):
                continue
            total += len(encoding.encode(value))
            if key == "name":
                total += 1
    return total + 3


def count_text_tokens(text: str, model: str) -> int:
    return len(encoding_for_model(model).encode(text))


def format_image_result(
    items: list[dict[str, Any]],
    prompt: str,
    response_format: str,
    base_url: str | None = None,
    created: int | None = None,
    message: str = "",
) -> dict[str, Any]:
    data: list[dict[str, Any]] = []
    for item in items:
        b64_json = str(item.get("b64_json") or "").strip()
        if not b64_json:
            continue
        revised_prompt = str(item.get("revised_prompt") or prompt).strip() or prompt
        if response_format == "b64_json":
            clean_b64 = b64_json.split(",", 1)[1] if b64_json.startswith("data:") else b64_json
            data.append({
                "b64_json": b64_json,
                "url": save_image_bytes(base64.b64decode(clean_b64), base_url),
                "revised_prompt": revised_prompt,
            })
        else:
            clean_b64 = b64_json.split(",", 1)[1] if b64_json.startswith("data:") else b64_json
            data.append({
                "url": save_image_bytes(base64.b64decode(clean_b64), base_url),
                "revised_prompt": revised_prompt,
            })
    result: dict[str, Any] = {"created": created or int(time.time()), "data": data}
    if message and not data:
        result["message"] = message
    return result


@dataclass
class ConversationRequest:
    model: str = "auto"
    prompt: str = ""
    messages: list[dict[str, Any]] | None = None
    images: list[str] | None = None
    n: int = 1
    size: str | None = None
    response_format: str = "b64_json"
    base_url: str | None = None
    message_as_error: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None


@dataclass
class ConversationState:
    text: str = ""
    conversation_id: str = ""
    file_ids: list[str] = field(default_factory=list)
    sediment_ids: list[str] = field(default_factory=list)
    blocked: bool = False
    tool_invoked: bool | None = None
    turn_use_case: str = ""


@dataclass
class ImageOutput:
    kind: str
    model: str
    index: int
    total: int
    created: int = field(default_factory=lambda: int(time.time()))
    text: str = ""
    upstream_event_type: str = ""
    data: list[dict[str, Any]] = field(default_factory=list)

    def to_chunk(self) -> dict[str, Any]:
        chunk: dict[str, Any] = {
            "object": "image.generation.chunk",
            "created": self.created,
            "model": self.model,
            "index": self.index,
            "total": self.total,
            "progress_text": self.text,
            "upstream_event_type": self.upstream_event_type,
            "data": [],
        }
        if self.kind == "message":
            chunk.update({
                "object": "image.generation.message",
                "message": self.text,
            })
            chunk.pop("progress_text", None)
            chunk.pop("upstream_event_type", None)
        elif self.kind == "result":
            chunk.update({
                "object": "image.generation.result",
                "data": self.data,
            })
            chunk.pop("progress_text", None)
            chunk.pop("upstream_event_type", None)
        return chunk


def assistant_message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    parts = content.get("parts") or []
    if not isinstance(parts, list):
        return ""
    return "".join(part for part in parts if isinstance(part, str))


def strip_history(text: str, history_text: str = "") -> str:
    text = str(text or "")
    history_text = str(history_text or "")
    while history_text and text.startswith(history_text):
        text = text[len(history_text):]
    return text


def assistant_text(event: dict[str, Any], current_text: str = "", history_text: str = "") -> str:
    for candidate in (event, event.get("v")):
        if not isinstance(candidate, dict):
            continue
        message = candidate.get("message")
        if not isinstance(message, dict):
            continue
        role = str((message.get("author") or {}).get("role") or "").strip().lower()
        if role != "assistant":
            continue
        text = assistant_message_text(message)
        if text:
            return strip_history(text, history_text)
    return apply_text_patch(event, current_text, history_text)


def event_assistant_text(event: dict[str, Any], history_text: str = "") -> str:
    for candidate in (event, event.get("v")):
        if not isinstance(candidate, dict):
            continue
        message = candidate.get("message")
        if isinstance(message, dict) and (message.get("author") or {}).get("role") == "assistant":
            return strip_history(assistant_message_text(message), history_text)
    return ""


def apply_text_patch(event: dict[str, Any], current_text: str = "", history_text: str = "") -> str:
    if event.get("p") == "/message/content/parts/0":
        return apply_patch_op(event, current_text, history_text)

    operations = event.get("v")
    if isinstance(operations, str) and current_text and not event.get("p") and not event.get("o"):
        return current_text + operations

    if event.get("o") == "patch" and isinstance(operations, list):
        text = current_text
        for item in operations:
            if isinstance(item, dict):
                text = apply_text_patch(item, text, history_text)
        return text

    if not isinstance(operations, list):
        return current_text

    text = current_text
    for item in operations:
        if isinstance(item, dict):
            text = apply_text_patch(item, text, history_text)
    return text


def apply_patch_op(operation: dict[str, Any], current_text: str, history_text: str = "") -> str:
    op = operation.get("o")
    value = str(operation.get("v") or "")
    if op == "append":
        return current_text + value
    if op == "replace":
        return strip_history(value, history_text)
    return current_text


def add_unique(values: list[str], candidates: list[str]) -> None:
    for candidate in candidates:
        if candidate and candidate not in values:
            values.append(candidate)


def extract_conversation_ids(payload: str) -> tuple[str, list[str], list[str]]:
    conversation_match = re.search(r'"conversation_id"\s*:\s*"([^"]+)"', payload)
    conversation_id = conversation_match.group(1) if conversation_match else ""
    file_ids = re.findall(r"(file[-_][A-Za-z0-9]+)", payload)
    sediment_ids = re.findall(r"sediment://([A-Za-z0-9_-]+)", payload)
    return conversation_id, file_ids, sediment_ids


def is_image_tool_event(event: dict[str, Any]) -> bool:
    value = event.get("v")
    message = event.get("message") or (value.get("message") if isinstance(value, dict) else None)
    if not isinstance(message, dict):
        return False
    metadata = message.get("metadata") or {}
    author = message.get("author") or {}
    return author.get("role") == "tool" and metadata.get("async_task_type") == "image_gen"


def update_conversation_state(state: ConversationState, payload: str, event: dict[str, Any] | None = None) -> None:
    conversation_id, file_ids, sediment_ids = extract_conversation_ids(payload)
    if conversation_id and not state.conversation_id:
        state.conversation_id = conversation_id
    if isinstance(event, dict) and is_image_tool_event(event):
        add_unique(state.file_ids, file_ids)
        add_unique(state.sediment_ids, sediment_ids)
    if not isinstance(event, dict):
        return
    state.conversation_id = str(event.get("conversation_id") or state.conversation_id)
    value = event.get("v")
    if isinstance(value, dict):
        state.conversation_id = str(value.get("conversation_id") or state.conversation_id)
    if event.get("type") == "moderation":
        moderation = event.get("moderation_response")
        if isinstance(moderation, dict) and moderation.get("blocked") is True:
            state.blocked = True
    if event.get("type") == "server_ste_metadata":
        metadata = event.get("metadata")
        if isinstance(metadata, dict):
            if isinstance(metadata.get("tool_invoked"), bool):
                state.tool_invoked = metadata["tool_invoked"]
            state.turn_use_case = str(metadata.get("turn_use_case") or state.turn_use_case)


def conversation_base_event(event_type: str, state: ConversationState, **extra: Any) -> dict[str, Any]:
    return {
        "type": event_type,
        "text": state.text,
        "conversation_id": state.conversation_id,
        "file_ids": list(state.file_ids),
        "sediment_ids": list(state.sediment_ids),
        "blocked": state.blocked,
        "tool_invoked": state.tool_invoked,
        "turn_use_case": state.turn_use_case,
        **extra,
    }


def iter_conversation_payloads(payloads: Iterator[str], history_text: str = "",
                               history_messages: list[str] | None = None) -> Iterator[dict[str, Any]]:
    state = ConversationState()
    history_messages = history_messages or []
    history_index = 0
    for payload in payloads:
        # print(f"[upstream_sse] {payload}", flush=True)
        if not payload:
            continue
        if payload == "[DONE]":
            yield conversation_base_event("conversation.done", state, done=True)
            break
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            update_conversation_state(state, payload)
            yield conversation_base_event("conversation.raw", state, payload=payload)
            continue
        if not isinstance(event, dict):
            yield conversation_base_event("conversation.event", state, raw=event)
            continue
        update_conversation_state(state, payload, event)
        if history_index < len(history_messages) and event_assistant_text(event, history_text) == history_messages[history_index]:
            history_index += 1
            state.text = ""
            continue
        next_text = assistant_text(event, state.text, history_text)
        if next_text != state.text:
            delta = next_text[len(state.text):] if next_text.startswith(state.text) else next_text
            state.text = next_text
            yield conversation_base_event("conversation.delta", state, raw=event, delta=delta)
            continue
        yield conversation_base_event("conversation.event", state, raw=event)


def conversation_events(
    backend: OpenAIBackendAPI,
    messages: list[dict[str, Any]] | None = None,
    model: str = "auto",
    prompt: str = "",
    images: list[str] | None = None,
    size: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: Any = None,
) -> Iterator[dict[str, Any]]:
    normalized = normalize_messages(messages or ([{"role": "user", "content": prompt}] if prompt else []), tools=tools, tool_choice=tool_choice)
    image_model = str(model or "").strip() in IMAGE_MODELS

    if not image_model:
        last_user_text = ""
        for msg in reversed(normalized):
            if str(msg.get("role") or "") == "user":
                last_user_text = str(msg.get("content") or "").strip().lower()
                break
        if any(keyword in last_user_text for keyword in ("trạng thái nhà", "tình trạng nhà", "nhà đang", "state house", "home status")):
            normalized.insert(0, {
                "role": "system",
                "content": "For smart-home status questions, call available live context/tool first (such as GetLiveContext) before answering. Do not answer from assumptions.",
            })

    history_text = "" if image_model else assistant_history_text(normalized)
    history_messages = [] if image_model else assistant_history_messages(normalized)
    final_prompt = prompt_with_global_system(build_image_prompt(prompt, size)) if image_model else prompt
    payloads = backend.stream_conversation(
        messages=normalized,
        model=model,
        prompt=final_prompt,
        images=images if image_model else None,
        system_hints=["picture_v2"] if image_model else None,
        tools=tools,
        tool_choice=tool_choice,
    )
    yield from iter_conversation_payloads(payloads, history_text, history_messages)


def text_backend() -> OpenAIBackendAPI:
    return OpenAIBackendAPI(access_token=account_service.get_text_access_token())


def stream_conversation_events(backend: OpenAIBackendAPI, request: ConversationRequest) -> Iterator[dict[str, Any]]:
    attempted_tokens: set[str] = set()
    token = getattr(backend, "access_token", "")
    emitted = False
    while True:
        if token and token in attempted_tokens:
            raise RuntimeError("no available text account")
        if token:
            attempted_tokens.add(token)
        try:
            active_backend = OpenAIBackendAPI(access_token=token)
            for event in conversation_events(
                active_backend,
                messages=request.messages,
                model=request.model,
                prompt=request.prompt,
                tools=request.tools,
                tool_choice=request.tool_choice,
            ):
                if event:
                    emitted = True
                    yield event
            account_service.mark_text_used(token)
            return
        except Exception as exc:
            error_message = str(exc)
            if token and not emitted and is_token_invalid_error(error_message):
                account_service.remove_invalid_token(token, "text_stream")
                token = account_service.get_text_access_token(attempted_tokens)
                if token:
                    continue
            raise


def stream_text_deltas(backend: OpenAIBackendAPI, request: ConversationRequest) -> Iterator[str]:
    for event in stream_conversation_events(backend, request):
        if event.get("type") != "conversation.delta":
            continue
        delta = str(event.get("delta") or "")
        if delta:
            yield delta


def collect_text(backend: OpenAIBackendAPI, request: ConversationRequest) -> str:
    return "".join(stream_text_deltas(backend, request))


def stream_image_outputs(
        backend: OpenAIBackendAPI,
        request: ConversationRequest,
        index: int = 1,
        total: int = 1,
) -> Iterator[ImageOutput]:
    last: dict[str, Any] = {}
    all_file_ids: list[str] = []
    all_sediment_ids: list[str] = []
    for event in conversation_events(
            backend,
            prompt=request.prompt,
            model=request.model,
            images=request.images or [],
            size=request.size,
    ):
        last = event
        # Accumulate image IDs from all events (ChatGPT may return multiple)
        for fid in (event.get("file_ids") or []):
            if fid not in all_file_ids:
                all_file_ids.append(str(fid))
        for sid in (event.get("sediment_ids") or []):
            if sid not in all_sediment_ids:
                all_sediment_ids.append(str(sid))
        if event.get("type") == "conversation.delta":
            yield ImageOutput(
                kind="progress",
                model=request.model,
                index=index,
                total=total,
                text=str(event.get("delta") or ""),
                upstream_event_type="conversation.delta",
            )
            continue
        if event.get("type") == "conversation.event":
            raw = event.get("raw")
            raw_type = str(raw.get("type") or "") if isinstance(raw, dict) else ""
            yield ImageOutput(
                kind="progress",
                model=request.model,
                index=index,
                total=total,
                upstream_event_type=raw_type,
            )

    conversation_id = str(last.get("conversation_id") or "")
    file_ids = all_file_ids or [str(item) for item in last.get("file_ids") or []]
    sediment_ids = all_sediment_ids or [str(item) for item in last.get("sediment_ids") or []]
    message = str(last.get("text") or "").strip()
    is_text_response = last.get("tool_invoked") is False or last.get("turn_use_case") == "text"
    logger.info({
        "event": "image_stream_resolve_start",
        "conversation_id": conversation_id,
        "file_ids": file_ids,
        "sediment_ids": sediment_ids,
        "tool_invoked": last.get("tool_invoked"),
        "turn_use_case": last.get("turn_use_case"),
    })
    if message and not file_ids and not sediment_ids and (last.get("blocked") or is_text_response):
        yield ImageOutput(kind="message", model=request.model, index=index, total=total, text=message)
        return

    image_urls = backend.resolve_conversation_image_urls(conversation_id, file_ids, sediment_ids)
    if image_urls:
        image_items = [
            {"b64_json": base64.b64encode(image_data).decode("ascii")}
            for image_data in backend.download_image_bytes(image_urls)
        ]
        data = format_image_result(
            image_items,
            request.prompt,
            request.response_format,
            request.base_url,
            int(time.time()),
        )["data"]
        if data:
            yield ImageOutput(kind="result", model=request.model, index=index, total=total, data=data)
        return

    if message:
        yield ImageOutput(kind="message", model=request.model, index=index, total=total, text=message)


def stream_image_outputs_with_pool(request: ConversationRequest) -> Iterator[ImageOutput]:
    model = str(request.model or "").strip()
    # Support combo models: resolve to first image-capable model in the combo
    if model not in IMAGE_MODELS:
        from services.backend_router import backend_router
        if backend_router.is_combo(model):
            routes = backend_router.route_combo(model)
            for route in routes:
                if route.model in IMAGE_MODELS:
                    request.model = route.model
                    model = route.model
                    break
            else:
                raise ImageGenerationError("unsupported image model,supported models: " + ", ".join(IMAGE_MODELS))
        else:
            raise ImageGenerationError("unsupported image model,supported models: " + ", ".join(IMAGE_MODELS))

    emitted = False
    last_error = ""
    for index in range(1, request.n + 1):
        while True:
            try:
                token = account_service.get_available_access_token()
            except RuntimeError as exc:
                if emitted:
                    return
                raise ImageGenerationError(str(exc) or "image generation failed") from exc

            emitted_for_token = False
            returned_message = False
            returned_result = False
            try:
                backend = OpenAIBackendAPI(access_token=token)
                for output in stream_image_outputs(backend, request, index, request.n):
                    if output.kind == "message" and request.message_as_error:
                        raise ImageGenerationError(
                            output.text or "Image generation was rejected by upstream policy.",
                            status_code=400,
                            error_type="invalid_request_error",
                            code="content_policy_violation",
                        )
                    emitted = True
                    emitted_for_token = True
                    returned_message = output.kind == "message"
                    returned_result = returned_result or output.kind == "result"
                    yield output
                if returned_message or not returned_result:
                    account_service.mark_image_result(token, False)
                    return
                account_service.mark_image_result(token, True)
                break
            except ImageGenerationError:
                account_service.mark_image_result(token, False)
                raise
            except Exception as exc:
                account_service.mark_image_result(token, False)
                last_error = str(exc)
                logger.warning({"event": "image_stream_fail", "request_token": token, "error": last_error})
                if not emitted_for_token and is_token_invalid_error(last_error):
                    account_service.remove_invalid_token(token, "image_stream")
                    continue
                raise ImageGenerationError(image_stream_error_message(last_error)) from exc

    if not emitted:
        raise ImageGenerationError(image_stream_error_message(last_error))


def stream_image_chunks(outputs: Iterable[ImageOutput]) -> Iterator[dict[str, Any]]:
    for output in outputs:
        yield output.to_chunk()


def collect_image_outputs(outputs: Iterable[ImageOutput]) -> dict[str, Any]:
    created = None
    data: list[dict[str, Any]] = []
    message = ""
    progress_parts: list[str] = []
    for output in outputs:
        created = created or output.created
        if output.kind == "progress" and output.text:
            progress_parts.append(output.text)
        elif output.kind == "message":
            message = output.text
        elif output.kind == "result":
            data.extend(output.data)

    result: dict[str, Any] = {"created": created or int(time.time()), "data": data}
    if not data:
        text = message or "".join(progress_parts).strip()
        if text:
            result["message"] = text
    return result
