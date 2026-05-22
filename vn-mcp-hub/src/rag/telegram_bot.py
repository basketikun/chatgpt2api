"""Telegram Bot — 2-way communication with AI pipeline.

Flow:
  User → Telegram → webhook → this server → chatgpt2api (AI + MCPs) → Telegram → User

Webhook endpoint: POST /telegram/webhook
Requires Cloudflare Tunnel or public domain to receive Telegram callbacks.
"""

from __future__ import annotations

import logging
import json
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def _get_settings() -> dict:
    from src.rag.settings import read
    s = read()
    return {
        "bot_token": str(s.get("telegram_bot_token", "")).strip(),
        "chat_ids": s.get("telegram_chat_ids", []) or [],
    }


def _api_call(method: str, data: dict | None = None) -> dict:
    """Make a Telegram Bot API call."""
    settings = _get_settings()
    token = settings["bot_token"]
    if not token:
        return {"ok": False, "error": "No bot token configured"}
    url = f"{TELEGRAM_API}/bot{token}/{method}"
    try:
        if data:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode(),
                headers={"Content-Type": "application/json"},
            )
        else:
            req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except Exception as exc:
        logger.warning("Telegram API %s failed: %s", method, exc)
        return {"ok": False, "error": str(exc)}


def register_webhook(base_url: str = "") -> bool:
    """Register Telegram webhook URL. Call on startup."""
    settings = _get_settings()
    if not settings["bot_token"]:
        return False

    # Try to determine public URL
    if not base_url:
        from src.rag.settings import read
        base_url = str(read().get("telegram_webhook_url", "")).strip()

    if not base_url:
        logger.info("Telegram: no webhook URL configured, skipping webhook registration")
        return False

    webhook_url = f"{base_url.rstrip('/')}/telegram/webhook"
    result = _api_call("setWebhook", {"url": webhook_url})
    if result.get("ok"):
        logger.info("Telegram webhook registered: %s", webhook_url)
        return True
    logger.warning("Telegram webhook registration failed: %s", result)
    return False


def send_message(chat_id: int | str, text: str) -> dict:
    """Send a message to a Telegram chat."""
    max_len = 4000
    if len(text) > max_len:
        text = text[:max_len - 3] + "..."
    return _api_call("sendMessage", {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "Markdown",
    })


async def handle_webhook(request) -> dict:
    """Handle incoming Telegram webhook POST."""
    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}

    message = body.get("message") or body.get("edited_message")
    if not message:
        return {"ok": True, "info": "no message field"}

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if not text or not chat_id:
        return {"ok": True, "info": "empty message"}

    # Security: check chat_id whitelist
    settings = _get_settings()
    allowed_ids = settings["chat_ids"]
    if allowed_ids and str(chat_id) not in [str(c) for c in allowed_ids]:
        logger.warning("Telegram: unauthorized chat_id %s", chat_id)
        send_message(chat_id, "Unauthorized")
        return {"ok": False, "error": "unauthorized"}

    # Send typing indicator
    _api_call("sendChatAction", {"chat_id": chat_id, "action": "typing"})

    # Forward to AI pipeline
    response_text = await _process_with_ai(text, chat_id)

    # Send response
    send_message(chat_id, response_text)
    return {"ok": True}


async def _process_with_ai(user_message: str, chat_id: int) -> str:
    """Process user message through chatgpt2api AI pipeline."""
    from src.rag.settings import read as read_settings
    settings = read_settings()
    api_key = settings.get("api_key", "")
    base_url = settings.get("api_base_url", "http://chatgpt2api:3030/v1").rstrip("/")
    ai_model = settings.get("ai_model", "cx/auto")

    url = f"{base_url}/chat/completions"
    payload = {
        "model": ai_model,
        "messages": [
            {"role": "system", "content": (
                "Bạn là trợ lý AI hỗ trợ người dùng Việt Nam qua Telegram. "
                "Trả lời ngắn gọn, hữu ích bằng tiếng Việt. "
                "Nếu cần tra cứu thông tin, hãy sử dụng các công cụ MCP có sẵn."
            )},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read().decode())
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip() or "Xin lỗi, tôi không có câu trả lời."
    except Exception as exc:
        logger.warning("AI pipeline failed for Telegram chat %s: %s", chat_id, exc)
        return "Xin lỗi, hệ thống đang bận. Vui lòng thử lại sau."
