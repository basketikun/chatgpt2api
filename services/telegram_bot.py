"""Telegram Bot — 2-way AI chat channel through chatgpt2api.

Each Telegram chat = a chat session with full AI + MCP tool support.
"""

from __future__ import annotations

import logging
import json
import time
import urllib.request
from typing import Any

from services.config import config

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
_conversations: dict[str, list[dict]] = {}
MAX_HISTORY = 20


def _bot_token() -> str:
    return str(config.get().get("telegram_bot_token", "")).strip()


def _tg_model() -> str:
    return str(config.get().get("telegram_ai_model", "")).strip() or "cx/auto"


def _chat_ids() -> list:
    ids = config.get().get("telegram_chat_ids", [])
    return ids if isinstance(ids, list) else []


def _api_call(method: str, data: dict | None = None) -> dict:
    token = _bot_token()
    if not token:
        return {"ok": False}
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
        return {"ok": False}


def register_webhook() -> bool:
    token = _bot_token()
    webhook_url = str(config.get().get("telegram_webhook_url", "")).strip()
    if not token or not webhook_url:
        return False
    url = f"{webhook_url.rstrip('/')}/telegram/webhook"
    r = _api_call("setWebhook", {"url": url, "allowed_updates": ["message"]})
    if r.get("ok"):
        logger.info("Telegram webhook OK: %s", url)
        return True
    logger.warning("Telegram webhook failed: %s", r)
    return False


def send_message(chat_id: int | str, text: str) -> dict:
    if len(text) > 4000:
        text = text[:3900] + "..."
    return _api_call("sendMessage", {
        "chat_id": str(chat_id), "text": text, "parse_mode": "Markdown",
        "link_preview_options": {"is_disabled": True},
    })


async def handle_webhook(request) -> dict:
    try:
        body = await request.json()
    except Exception:
        return {"ok": False}
    msg = body.get("message") or body.get("edited_message")
    if not msg:
        return {"ok": True}
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = (msg.get("text") or "").strip()

    # Commands
    if text.startswith("/"):
        reply = _cmd(text, chat_id)
        if reply:
            send_message(chat_id, reply)
            return {"ok": True}

    if not text or not chat_id:
        return {"ok": True}

    # Whitelist
    allowed = [str(c) for c in _chat_ids()]
    if allowed and chat_id not in allowed:
        send_message(chat_id, "⛔ Không được phép.")
        return {"ok": False}

    _api_call("sendChatAction", {"chat_id": chat_id, "action": "typing"})

    # Conversation context
    key = f"tg_{chat_id}"
    if key not in _conversations:
        _conversations[key] = [{
            "role": "system",
            "content": "Bạn là trợ lý AI qua Telegram. Trả lời ngắn gọn, chính xác bằng tiếng Việt."
        }]
    _conversations[key].append({"role": "user", "content": text})
    if len(_conversations[key]) > MAX_HISTORY:
        _conversations[key] = [_conversations[key][0]] + _conversations[key][-(MAX_HISTORY - 1):]

    # Call AI
    base_url = str(config.get().get("api_base_url", "")).strip().rstrip("/") or "http://127.0.0.1/v1"
    api_key = str(config.get().get("api_key", "")).strip()
    payload = {"model": _tg_model(), "messages": _conversations[key], "stream": False}
    try:
        req = urllib.request.Request(f"{base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=90)
        reply = json.loads(resp.read().decode()).get("choices", [{}])[0].get("message", {}).get("content", "")
        reply = reply.strip() or "..."
    except Exception as exc:
        logger.warning("AI error for %s: %s", chat_id, exc)
        reply = "⏳ Hệ thống bận, thử lại."

    _conversations[key].append({"role": "assistant", "content": reply})
    if len(_conversations[key]) > MAX_HISTORY:
        _conversations[key] = [_conversations[key][0]] + _conversations[key][-(MAX_HISTORY - 1):]

    send_message(chat_id, reply)
    return {"ok": True}


def _cmd(text: str, chat_id: str) -> str | None:
    cmd = text.lower().split()[0]
    key = f"tg_{chat_id}"
    if cmd == "/start":
        return f"👋 **chatgpt2api Bot**\nModel: `{_tg_model()}`\n/help /clear /model"
    elif cmd == "/help":
        return "📌 Hỗ trợ: chat AI, MCP tools, tra cứu.\nLệnh: /clear /model"
    elif cmd == "/clear":
        _conversations.pop(key, None)
        return "✅ Đã xóa lịch sử."
    elif cmd == "/model":
        return f"🤖 `{_tg_model()}`"
    return None


def get_status() -> dict:
    return {
        "configured": bool(_bot_token()),
        "webhook_url": str(config.get().get("telegram_webhook_url", "")).strip(),
        "model": _tg_model(),
        "chat_ids_count": len(_chat_ids()),
    }
