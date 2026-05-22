"""Telegram Bot — Full 2-way chat channel with AI + MCP tools.

Telegram là một kênh chat như web UI:
- Mỗi Telegram chat = 1 phiên hội thoại
- Gọi qua chatgpt2api /v1/chat/completions (có đầy đủ MCP tools)
- Model dành riêng cho Telegram, cấu hình trong Settings
- Lưu lịch sử hội thoại theo chat_id (giữ context)
"""

from __future__ import annotations

import logging
import json
import urllib.request
import time
from typing import Any

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"

# Conversation history per chat_id (max 20 messages each)
_conversations: dict[str, list[dict]] = {}
MAX_HISTORY = 20


def _get_settings() -> dict:
    from src.rag.settings import read
    s = read()
    return {
        "bot_token": str(s.get("telegram_bot_token", "")).strip(),
        "chat_ids": s.get("telegram_chat_ids", []) or [],
        "ai_model": str(s.get("telegram_ai_model", "")).strip() or str(s.get("ai_model", "cx/auto")),
        "api_key": str(s.get("api_key", "")).strip(),
        "base_url": str(s.get("api_base_url", "http://chatgpt2api:3030/v1")).rstrip("/"),
        "system_prompt": str(s.get("telegram_system_prompt", "")).strip() or (
            "Bạn là trợ lý AI thông minh qua Telegram. "
            "Trả lời ngắn gọn, chính xác bằng tiếng Việt. "
            "Sử dụng các công cụ MCP có sẵn khi cần tra cứu thông tin thực tế "
            "(thời tiết, tỷ giá, tin tức, phạt nguội, kiến thức...). "
            "Định dạng Markdown cho dễ đọc."
        ),
        "webhook_url": str(s.get("telegram_webhook_url", "")).strip(),
    }


def _api_call(method: str, data: dict | None = None) -> dict:
    settings = _get_settings()
    token = settings["bot_token"]
    if not token:
        return {"ok": False, "error": "No bot token"}
    url = f"{TELEGRAM_API}/bot{token}/{method}"
    try:
        if data:
            req = urllib.request.Request(url, data=json.dumps(data).encode(),
                headers={"Content-Type": "application/json"})
        else:
            req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except Exception as exc:
        logger.warning("Telegram API %s: %s", method, exc)
        return {"ok": False, "error": str(exc)}


def register_webhook() -> bool:
    """Register Telegram webhook URL. Called on startup."""
    settings = _get_settings()
    if not settings["bot_token"] or not settings["webhook_url"]:
        return False
    webhook_url = f"{settings['webhook_url'].rstrip('/')}/telegram/webhook"
    result = _api_call("setWebhook", {"url": webhook_url, "allowed_updates": ["message", "edited_message"]})
    if result.get("ok"):
        logger.info("Telegram webhook OK: %s", webhook_url)
        return True
    logger.warning("Telegram webhook failed: %s", result)
    return False


def send_message(chat_id: int | str, text: str, parse_mode: str = "Markdown") -> dict:
    """Send message, auto-split if > 4000 chars."""
    if len(text) <= 4000:
        return _api_call("sendMessage", {
            "chat_id": str(chat_id), "text": text,
            "parse_mode": parse_mode,
            "link_preview_options": {"is_disabled": True},
        })
    # Split long messages
    parts = []
    while len(text) > 3800:
        split_at = text.rfind("\n", 0, 3800)
        if split_at < 3000:
            split_at = text.rfind(". ", 0, 3800)
        if split_at < 3000:
            split_at = 3800
        parts.append(text[:split_at])
        text = text[split_at:].strip()
    parts.append(text)
    last = None
    for i, part in enumerate(parts):
        prefix = f"({i+1}/{len(parts)})\n" if len(parts) > 1 else ""
        last = _api_call("sendMessage", {
            "chat_id": str(chat_id), "text": prefix + part,
            "parse_mode": parse_mode,
            "link_preview_options": {"is_disabled": True},
        })
        time.sleep(0.3)
    return last or {}


async def handle_webhook(request) -> dict:
    """Handle incoming Telegram webhook POST."""
    try:
        body = await request.json()
    except Exception:
        return {"ok": False}

    message = body.get("message") or body.get("edited_message")
    if not message:
        return {"ok": True}

    chat = message.get("chat", {})
    chat_id = str(chat.get("id", ""))
    text = (message.get("text") or "").strip()

    # Handle /start, /help commands
    if text.startswith("/"):
        cmd_result = _handle_command(text, chat_id)
        if cmd_result:
            send_message(chat_id, cmd_result)
            return {"ok": True}

    if not text:
        return {"ok": True}

    # Security check
    settings = _get_settings()
    allowed_ids = [str(c) for c in settings["chat_ids"]]
    if allowed_ids and chat_id not in allowed_ids:
        send_message(chat_id, "⛔ Bạn không được phép sử dụng bot này.")
        return {"ok": False}

    # Typing indicator
    _api_call("sendChatAction", {"chat_id": chat_id, "action": "typing"})

    # Build conversation with history
    conv_key = f"tg_{chat_id}"
    if conv_key not in _conversations:
        _conversations[conv_key] = [
            {"role": "system", "content": settings["system_prompt"]}
        ]
    _conversations[conv_key].append({"role": "user", "content": text})

    # Trim old messages, keep system prompt
    if len(_conversations[conv_key]) > MAX_HISTORY:
        _conversations[conv_key] = (
            [_conversations[conv_key][0]] +
            _conversations[conv_key][-(MAX_HISTORY - 1):]
        )

    # Call chatgpt2api with full pipeline (MCP tools included)
    url = f"{settings['base_url']}/chat/completions"
    payload = {
        "model": settings["ai_model"],
        "messages": _conversations[conv_key],
        "stream": False,
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
            "Authorization": f"Bearer {settings['api_key']}",
            "Content-Type": "application/json",
        })
        resp = urllib.request.urlopen(req, timeout=90)
        data = json.loads(resp.read().decode())
        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        reply = reply.strip() or "Xin lỗi, tôi không có câu trả lời."
    except Exception as exc:
        logger.warning("AI pipeline error for %s: %s", chat_id, exc)
        reply = "⏳ Hệ thống đang bận, thử lại sau."

    # Save assistant response to history
    _conversations[conv_key].append({"role": "assistant", "content": reply})
    if len(_conversations[conv_key]) > MAX_HISTORY:
        _conversations[conv_key] = (
            [_conversations[conv_key][0]] +
            _conversations[conv_key][-(MAX_HISTORY - 1):]
        )

    # Clear history on /clear command
    send_message(chat_id, reply)
    return {"ok": True}


def _handle_command(text: str, chat_id: str) -> str | None:
    """Handle Telegram bot commands."""
    cmd = text.lower().split()[0]
    conv_key = f"tg_{chat_id}"

    if cmd == "/start":
        settings = _get_settings()
        return (
            "👋 **Chào mừng đến với chatgpt2api Telegram Bot!**\n\n"
            f"🤖 Model: `{settings['ai_model']}`\n"
            "💬 Chat tự nhiên, có hỗ trợ MCP tools\n\n"
            "Lệnh:\n"
            "/help - Trợ giúp\n"
            "/clear - Xóa lịch sử chat\n"
            "/model - Xem model đang dùng\n"
        )
    elif cmd == "/help":
        return (
            "**Trợ giúp Telegram Bot**\n\n"
            "📌 Bot này kết nối với chatgpt2api, hỗ trợ:\n"
            "- Chat AI thông minh\n"
            "- Tra cứu thời tiết, tỷ giá, tin tức\n"
            "- Tra cứu phạt nguội, luật\n"
            "- Truy vấn kho kiến thức RAG\n\n"
            "📋 Lệnh: /clear /model"
        )
    elif cmd == "/clear":
        _conversations.pop(conv_key, None)
        return "✅ Đã xóa lịch sử chat."
    elif cmd == "/model":
        settings = _get_settings()
        return f"🤖 Model hiện tại: `{settings['ai_model']}`"
    return None
