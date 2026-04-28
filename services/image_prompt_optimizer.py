from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from services.config import config
from services.image_trace_logger import ImageTraceLogger

OPTIMIZER_TIMEOUT_SECONDS = 45
MAX_OPTIMIZED_CHARS = 900
SIMPLIFIED_CHINESE_KEYWORD = "\u7b80\u4f53\u4e2d\u6587"
SIMPLIFIED_CHINESE_REQUIREMENT = (
    "\u753b\u9762\u4e2d\u7684\u6240\u6709\u53ef\u89c1\u6587\u5b57\u3001"
    "\u6807\u9898\u3001\u6807\u7b7e\u3001\u6807\u724c\u3001UI\u3001"
    "\u56fe\u8868\u6ce8\u91ca\u7b49\u5fc5\u987b\u4f7f\u7528"
    "\u7b80\u4f53\u4e2d\u6587\u3002"
)
TRIM_CHARS = " ,.;:\uff0c\u3002\uff1b\uff1a"
JOIN_SEPARATOR = "\uff0c"

SENSITIVE_REPLACEMENTS = {
    "20\u5c81\u51fa\u5934": "\u6210\u5e74",
    "\u5973\u5076\u50cf": "\u5973\u6027\u6a21\u7279",
    "\u6027\u611f": "\u4f18\u96c5",
    "\u8bf1\u4eba": "\u6e29\u67d4",
    "\u8bf1\u60d1": "\u6e29\u67d4",
    "\u6311\u9017": "\u81ea\u7136",
    "\u6545\u610f": "\u81ea\u7136",
    "\u6ed1\u4e0b\u6765": "\u7a7f\u7740\u6574\u6d01",
    "\u5fae\u5999\u7684\u4e73\u6c9f": "\u81ea\u7136\u7684\u670d\u88c5\u5c42\u6b21",
    "\u6df1\u4e73\u6c9f": "\u81ea\u7136\u670d\u88c5\u5c42\u6b21",
    "\u4e73\u6c9f": "\u81ea\u7136\u670d\u88c5\u5c42\u6b21",
    "\u8d64\u811a": "\u59ff\u6001\u81ea\u7136",
    "\u5f13\u8d77\u80cc\u90e8": "\u59ff\u6001\u653e\u677e",
    "\u7a81\u51fa\u66f2\u7ebf": "\u59ff\u6001\u4f18\u96c5",
}


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.prompt_optimizer_api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "chatgpt2api-prompt-optimizer/1.0",
    }


def _upstream_url(path: str) -> str:
    return f"{config.prompt_optimizer_base_url.rstrip('/')}/{path.lstrip('/')}"


def _compact_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize_mode(mode: str) -> str:
    return "edit" if str(mode or "").strip().lower() == "edit" else "generate"


def _has_simplified_chinese_requirement(value: str) -> bool:
    return SIMPLIFIED_CHINESE_KEYWORD in value or "simplified chinese" in value.lower()


def _trim_optimized_prompt(prompt: str) -> str:
    normalized = _compact_spaces(prompt)
    if len(normalized) <= MAX_OPTIMIZED_CHARS:
        return normalized
    return normalized[:MAX_OPTIMIZED_CHARS].rstrip(TRIM_CHARS)


def _ensure_simplified_chinese_requirement(prompt: str) -> str:
    normalized = _compact_spaces(prompt)
    if not normalized:
        return SIMPLIFIED_CHINESE_REQUIREMENT

    if _has_simplified_chinese_requirement(normalized):
        trimmed = _trim_optimized_prompt(normalized)
        if _has_simplified_chinese_requirement(trimmed):
            return trimmed

    suffix = SIMPLIFIED_CHINESE_REQUIREMENT
    separator = " "
    budget = MAX_OPTIMIZED_CHARS - len(separator) - len(suffix)
    if budget <= 0:
        return suffix[:MAX_OPTIMIZED_CHARS]

    head = normalized[:budget].rstrip(TRIM_CHARS)
    if not head:
        return suffix
    return f"{head}{separator}{suffix}"


def _extract_message_content(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    return str(message.get("content") or "").strip()


def _call_optimizer_model(prompt: str, mode: str = "generate", *, trace: ImageTraceLogger | None = None) -> str:
    normalized_mode = _normalize_mode(mode)
    edit_instruction = (
        "For image edit requests, preserve the source image identity, layout, and important existing details; "
        "only apply the user's requested changes unless they explicitly ask for broader changes. "
        if normalized_mode == "edit"
        else ""
    )
    body = {
        "model": config.prompt_optimizer_model or "gpt-5.4",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a conservative image-prompt editor. Preserve the user's subject, scene, style, "
                    "composition, named places, and language as much as possible. Do not rewrite into a new concept. "
                    f"{edit_instruction}"
                    "Only make minimal edits that reduce generation failures: fix obviously truncated endings, "
                    "remove duplicated phrases, soften clearly sexualized, age-coded, celebrity/idol, or excessive "
                    "body-detail wording, and keep important visual details. "
                    "Always include this exact requirement in the returned prompt: "
                    f"{SIMPLIFIED_CHINESE_REQUIREMENT} "
                    "If the prompt is already safe, return it nearly unchanged. Keep the result under 900 characters. "
                    "Return only the prompt."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.2,
    }
    started = time.time()
    trace and trace.event("prompt_optimizer.model.start", model=body["model"], mode=normalized_mode)
    request = urllib.request.Request(
        _upstream_url("/chat/completions"),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=_headers(),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=OPTIMIZER_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    optimized = _compact_spaces(_extract_message_content(payload))
    trace and trace.event(
        "prompt_optimizer.model.success",
        duration_ms=int((time.time() - started) * 1000),
        optimized_length=len(optimized),
    )
    return optimized


def _fallback_optimize(prompt: str) -> str:
    normalized = _compact_spaces(prompt)
    for source, target in SENSITIVE_REPLACEMENTS.items():
        normalized = normalized.replace(source, target)

    normalized = re.sub(
        r"[\uff0c,]?(?:\u65e0\u7455\u75b5|\u65e0\u75d8|\u65e0\u6cb9\u6027\u76ae\u80a4|"
        r"\u65e0\u55b7\u6c14|\u65e0\u6570\u5b57\u8fc7\u5ea6\u9510\u5316|\u65e0\u5851\u6599\u76ae\u80a4)",
        "",
        normalized,
    )

    parts = re.split(r"[\u3002\uff01\uff1f!?;\uff1b\n\r]+|\s*\|\s*", normalized)
    kept: list[str] = []
    banned = ("\u4e73\u6c9f", "\u6311\u9017", "\u672a\u6210\u5e74", "teen")
    for part in parts:
        part = part.strip()
        if not part or any(word.lower() in part.lower() for word in banned):
            continue
        kept.append(part)
        if len(JOIN_SEPARATOR.join(kept)) >= MAX_OPTIMIZED_CHARS:
            break

    optimized = JOIN_SEPARATOR.join(kept).strip(f"{JOIN_SEPARATOR} ")
    if not optimized:
        optimized = normalized[:MAX_OPTIMIZED_CHARS]
    return _trim_optimized_prompt(optimized)


def optimize_image_prompt(
    prompt: str,
    mode: str = "generate",
    *,
    trace: ImageTraceLogger | None = None,
) -> dict[str, Any]:
    normalized_mode = _normalize_mode(mode)
    original = str(prompt or "").strip()
    if not original:
        optimized = SIMPLIFIED_CHINESE_REQUIREMENT
        return {
            "prompt": "",
            "optimized_prompt": optimized,
            "changed": True,
            "optimizer": "none",
            "reason": "empty_prompt",
            "mode": normalized_mode,
            "original_length": 0,
            "optimized_length": len(optimized),
        }

    try:
        optimized = _call_optimizer_model(original, normalized_mode, trace=trace)
        if optimized:
            optimized = _ensure_simplified_chinese_requirement(optimized)
            return {
                "prompt": original,
                "optimized_prompt": optimized,
                "changed": optimized != original,
                "optimizer": "model",
                "model": config.prompt_optimizer_model,
                "mode": normalized_mode,
                "original_length": len(original),
                "optimized_length": len(optimized),
            }
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        trace and trace.event(
            "prompt_optimizer.model.error",
            error_type="HTTPError",
            status=exc.code,
            error=error_body[:1000],
        )
    except Exception as exc:
        trace and trace.event("prompt_optimizer.model.error", error_type=type(exc).__name__, error=str(exc))

    optimized = _ensure_simplified_chinese_requirement(_fallback_optimize(original))
    return {
        "prompt": original,
        "optimized_prompt": optimized,
        "changed": optimized != original,
        "optimizer": "fallback",
        "reason": "model_optimizer_unavailable",
        "mode": normalized_mode,
        "original_length": len(original),
        "optimized_length": len(optimized),
    }
