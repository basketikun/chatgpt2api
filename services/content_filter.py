from __future__ import annotations

import re

from curl_cffi import requests
from fastapi import HTTPException

from services.config import config
from services.proxy_service import proxy_settings
from utils.i18n import t
from utils.log import logger

DEFAULT_REVIEW_PROMPT = "判断用户请求是否允许。只回答 ALLOW 或 REJECT。"

# Strip base64 image data URIs before review: a text-only review model can't
# analyze image bytes, and a single inlined image easily blows past the token
# budget of the upstream review service.
_BASE64_DATA_URI = re.compile(r"data:[\w/.+;-]+;base64,[A-Za-z0-9+/=]+")

# Cap aligned to the upstream review service's max context. If text still
# exceeds the cap after base64 stripping, keep equal head/tail halves so both
# the system prompt and the most recent user message survive.
_MAX_REVIEW_TEXT_LEN = 100_000
_TRUNCATION_MARKER = "\n…[truncated]…\n"


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_text(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(_text(value.get(key)) for key in ("text", "input_text", "content", "input", "instructions", "system", "prompt"))
    return ""


def request_text(*values: object) -> str:
    return "\n".join(part for value in values if (part := _text(value).strip()))


def request_shape(*values: object) -> dict[str, int]:
    """Return a safe structural summary without logging prompts or image bytes."""
    stats = {
        "response_message_items": 0,
        "input_image_parts": 0,
        "image_url_parts": 0,
        "image_parts": 0,
        "data_url_images": 0,
        "remote_image_urls": 0,
        "literal_image_placeholders": 0,
    }

    def walk(value: object, key: str = "") -> None:
        if isinstance(value, str):
            text = value.strip()
            lower = text.lower()
            if "<image>" in lower:
                stats["literal_image_placeholders"] += 1
            if lower.startswith("data:image/"):
                stats["data_url_images"] += 1
            elif key in {"image_url", "url"} and lower.startswith(("http://", "https://")):
                stats["remote_image_urls"] += 1
            return
        if isinstance(value, list):
            for item in value:
                walk(item, key)
            return
        if not isinstance(value, dict):
            return
        item_type = str(value.get("type") or "").strip()
        if item_type == "message":
            stats["response_message_items"] += 1
        elif item_type == "input_image":
            stats["input_image_parts"] += 1
        elif item_type == "image_url":
            stats["image_url_parts"] += 1
        elif item_type == "image":
            stats["image_parts"] += 1
        for child_key, child in value.items():
            walk(child, str(child_key))

    for value in values:
        walk(value)
    return {key: value for key, value in stats.items() if value}


def _sanitize_for_review(text: str) -> tuple[str, dict[str, int]]:
    """Strip base64 data URIs and truncate to the review-service context limit.

    Returns (sanitized_text, stats) where stats carries base64_blocks_stripped
    and truncated_chars so callers can emit structured logs.
    """
    sanitized, base64_blocks_stripped = _BASE64_DATA_URI.subn("[image]", text)
    truncated_chars = 0
    if len(sanitized) > _MAX_REVIEW_TEXT_LEN:
        # Reserve marker space so the result stays within the cap.
        half = (_MAX_REVIEW_TEXT_LEN - len(_TRUNCATION_MARKER)) // 2
        truncated_chars = len(sanitized) - 2 * half
        sanitized = sanitized[:half] + _TRUNCATION_MARKER + sanitized[-half:]
    stats = {
        "base64_blocks_stripped": base64_blocks_stripped,
        "truncated_chars": truncated_chars,
    }
    return sanitized, stats


def _extract_review_decision(data: object) -> str | None:
    """Defensively pull the decision text out of the review service response.

    Returns None when the response shape doesn't match the OpenAI chat-completion
    contract (e.g. {"error": ...} with no choices). The caller treats None as
    "undecided" and applies the configured fail-open policy.
    """
    if not isinstance(data, dict):
        return None
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if content is None:
        return None
    return str(content).strip().lower()


def _is_allow_decision(decision: str) -> bool:
    return decision.startswith(("allow", "pass", "true", "yes", "通过", "允许", "安全"))


def _is_reject_decision(decision: str) -> bool:
    return decision.startswith(("reject", "deny", "block", "false", "no", "拒绝", "不允许", "违规", "禁止"))


def _resolve_fail_open(review: dict) -> bool:
    """Resolve fail_open from review config. Defaults to True."""
    value = review.get("fail_open")
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def check_request(text: str) -> None:
    text = str(text or "")
    if not text.strip():
        return
    # Local sensitive-word match runs on the raw text (cheap, no network).
    for word in config.sensitive_words:
        if word in text:
            raise HTTPException(status_code=400, detail={"error": t("filter.sensitive_word")})
    review = config.ai_review
    if not review.get("enabled"):
        return
    base_url = str(review.get("base_url") or "").strip().rstrip("/")
    api_key = str(review.get("api_key") or "").strip()
    model = str(review.get("model") or "").strip()
    if not base_url or not api_key or not model:
        raise HTTPException(status_code=400, detail={"error": "ai review config is incomplete"})

    fail_open = _resolve_fail_open(review)

    review_text, sanitize_stats = _sanitize_for_review(text)
    if sanitize_stats["base64_blocks_stripped"] or sanitize_stats["truncated_chars"]:
        logger.info({
            "event": "ai_review_text_sanitized",
            "original_text_len": len(text),
            "review_text_len": len(review_text),
            **sanitize_stats,
        })
    prompt = str(review.get("prompt") or DEFAULT_REVIEW_PROMPT).strip()
    content = f"{prompt}\n\n用户请求:\n{review_text}\n\n只回答 ALLOW 或 REJECT。"

    # fail_open=True (default): on upstream failure or ambiguous reply, let the
    # request through. The review is a soft safety net; one missed review is
    # preferable to a 5xx storm when the review service is flaky. Set
    # config.ai_review.fail_open=false for strict-compliance deployments.
    def _on_failure(event_payload: dict) -> None:
        logger.warning(event_payload)
        if not fail_open:
            raise HTTPException(
                status_code=503,
                detail={"error": t("review.unavailable")},
            )

    try:
        response = requests.post(
            f"{base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": content}], "temperature": 0},
            timeout=60,
            **proxy_settings.build_session_kwargs(),
        )
    except Exception as exc:
        _on_failure({
            "event": "ai_review_request_failed",
            "error": str(exc),
            "error_type": exc.__class__.__name__,
            "review_text_len": len(review_text),
            "original_text_len": len(text),
        })
        return

    try:
        data = response.json()
    except Exception as exc:
        _on_failure({
            "event": "ai_review_response_not_json",
            "status_code": response.status_code,
            "body_preview": str(response.text or "")[:200],
            "error": str(exc),
        })
        return

    decision = _extract_review_decision(data)
    if decision is None:
        _on_failure({
            "event": "ai_review_malformed_response",
            "status_code": response.status_code,
            "body_preview": str(data)[:300],
            "review_text_len": len(review_text),
            "original_text_len": len(text),
        })
        return

    if _is_allow_decision(decision):
        return
    if _is_reject_decision(decision):
        raise HTTPException(status_code=400, detail={"error": t("review.rejected")})
    # Ambiguous decisions (e.g. "MAYBE", empty content) fall back to fail-open policy.
    _on_failure({
        "event": "ai_review_ambiguous_decision",
        "decision": decision[:100],
        "review_text_len": len(review_text),
    })
    return
