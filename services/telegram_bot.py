"""Telegram Bot — 2-way AI chat channel through chatgpt2api.

Each Telegram chat = a chat session with full AI + MCP tool support.
"""

from __future__ import annotations

import logging
import json
import re
import time
import urllib.request
from typing import Any

from services.config import config


_MD_BOLD_DOUBLE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_MD_BOLD_UNDER_DOUBLE = re.compile(r"__(.+?)__", re.DOTALL)
_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_MD_STRIKE = re.compile(r"~~(.+?)~~", re.DOTALL)
_MD_TABLE_PIPE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
_MD_TABLE_SEP = re.compile(r"^\s*\|?[\s:-]+\|[\s:|\-]+\s*$", re.MULTILINE)


def _to_telegram_markdown(text: str) -> str:
    """Convert LLM markdown to Telegram MarkdownV1 syntax.

    Telegram MarkdownV1 uses *single-asterisk* for bold (not **double**),
    has no headings, and breaks on stray unbalanced markers. Convert the
    common cases so messages render with bold/italic/code instead of
    failing or showing literal asterisks.
    """
    if not text:
        return text
    out = _MD_BOLD_DOUBLE.sub(r"*\1*", text)
    out = _MD_BOLD_UNDER_DOUBLE.sub(r"*\1*", out)
    out = _MD_HEADING.sub("", out)
    out = _MD_STRIKE.sub(r"\1", out)
    return out

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
    converted = _to_telegram_markdown(text)
    r = _api_call("sendMessage", {
        "chat_id": str(chat_id), "text": converted, "parse_mode": "Markdown",
        "link_preview_options": {"is_disabled": True},
    })
    if r.get("ok"):
        return r
    # Telegram rejected the markdown (often unbalanced markers from the LLM).
    # Retry as plain text so the user at least sees the answer.
    return _api_call("sendMessage", {
        "chat_id": str(chat_id), "text": text,
        "link_preview_options": {"is_disabled": True},
    })

def send_photo(chat_id: int | str, photo_bytes: bytes, caption: str = "") -> dict:
    """Gửi ảnh qua Telegram."""
    import io, uuid
    token = _bot_token()
    if not token:
        return {"ok": False}
    try:
        boundary = f"bot{token[:8]}{uuid.uuid4().hex[:8]}"
        body = io.BytesIO()
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode())
        body.write(f"--{boundary}\r\n".encode())
        if caption:
            body.write(f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode())
            body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="photo"; filename="image.png"\r\n'.encode())
        body.write(f'Content-Type: image/png\r\n\r\n'.encode())
        body.write(photo_bytes)
        body.write(f"\r\n--{boundary}--\r\n".encode())
        body.seek(0)

        url = f"{TELEGRAM_API}/bot{token}/sendPhoto"
        req = urllib.request.Request(url, data=body.getvalue(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode())
    except Exception as e:
        logger.warning("sendPhoto failed: %s", e)
        return {"ok": False}

def send_document(chat_id: int | str, doc_bytes: bytes, filename: str, caption: str = "") -> dict:
    """Gửi file/document qua Telegram."""
    import io, uuid
    token = _bot_token()
    if not token:
        return {"ok": False}
    try:
        boundary = f"bot{token[:8]}{uuid.uuid4().hex[:8]}"
        body = io.BytesIO()
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode())
        body.write(f"--{boundary}\r\n".encode())
        if caption:
            body.write(f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode())
            body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'.encode())
        body.write(f'Content-Type: application/octet-stream\r\n\r\n'.encode())
        body.write(doc_bytes)
        body.write(f"\r\n--{boundary}--\r\n".encode())
        body.seek(0)

        url = f"{TELEGRAM_API}/bot{token}/sendDocument"
        req = urllib.request.Request(url, data=body.getvalue(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode())
    except Exception as e:
        logger.warning("sendDocument failed: %s", e)
        return {"ok": False}


async def handle_webhook(request) -> dict:
    """Handle incoming Telegram webhook POST. Returns immediately, processes AI in background."""
    try:
        body = await request.json()
    except Exception:
        return {"ok": False}
    msg = body.get("message") or body.get("edited_message")
    if not msg:
        return {"ok": True}
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = (msg.get("text") or "").strip()
    photo = msg.get("photo")
    document = msg.get("document")

    # Process in background thread so webhook returns immediately
    import threading
    t = threading.Thread(target=_process_message, args=(text, chat_id, photo, document), daemon=True)
    t.start()
    return {"ok": True}


def _download_file(file_id: str) -> bytes | None:
    """Download a file from Telegram by file_id."""
    token = _bot_token()
    if not token:
        return None
    try:
        # Get file path
        r = _api_call("getFile", {"file_id": file_id})
        if not r.get("ok") or not r.get("result", {}).get("file_path"):
            return None
        file_path = r["result"]["file_path"]
        url = f"{TELEGRAM_API}/file/bot{token}/{file_path}"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.read()
    except Exception as e:
        logger.warning("File download failed: %s", e)
        return None


def _process_message(text: str, chat_id: str, photo: list | None = None, document: dict | None = None) -> None:
    """Process a Telegram message in background thread."""
    # Handle photo
    if photo:
        _api_call("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        largest = max(photo, key=lambda p: p.get("file_size", 0))
        file_data = _download_file(largest["file_id"])
        if file_data:
            # Try OCR on image
            text = ""
            try:
                import pytesseract
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(file_data))
                text = pytesseract.image_to_string(img, lang="vie+eng").strip()
            except Exception:
                pass
            if text:
                send_message(chat_id, f"📷 OCR:\n{text[:2000]}")
            else:
                send_message(chat_id, f"📷 Đã nhận ảnh ({len(file_data)//1024}KB).")
        else:
            send_message(chat_id, "📷 Không thể tải ảnh.")
        return

    # Handle document (PDF, etc.)
    if document:
        doc_name = document.get("file_name", "document")
        doc_size = document.get("file_size", 0)
        mime = document.get("mime_type", "")

        if not doc_name.lower().endswith(".pdf"):
            send_message(chat_id, f"📎 Chỉ hỗ trợ file PDF. File: {doc_name}")
            return

        _api_call("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        send_message(chat_id, f"📄 Đang xử lý PDF: {doc_name} ({doc_size//1024}KB)...")

        file_data = _download_file(document["file_id"])
        if not file_data:
            send_message(chat_id, "❌ Không thể tải file.")
            return

        # Save to temp file and process
        import tempfile, os
        import subprocess
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp.write(file_data)
        tmp.close()

        try:
            # Try extracting text with Python
            text = ""
            try:
                from markitdown import MarkItDown
                md = MarkItDown()
                result = md.convert(tmp.name)
                text = result.text_content.strip()
            except Exception:
                pass

            # If markitdown fails or returns empty, try pdftotext
            if not text:
                try:
                    result = subprocess.run(["pdftotext", tmp.name, "-"], capture_output=True, text=True, timeout=30)
                    text = result.stdout.strip()
                except Exception:
                    pass

            if not text:
                send_message(chat_id, "❌ Không thể đọc nội dung PDF (có thể là ảnh chụp).")
                return

            # Summarize with AI
            ai_text = text[:8000]
            base_url = str(config.get().get("api_base_url", "")).strip().rstrip("/") or "http://127.0.0.1/v1"
            payload = {
                "model": _tg_model(),
                "messages": [
                    {"role": "system", "content": "Tóm tắt nội dung PDF ngắn gọn bằng tiếng Việt. Nêu các điểm chính."},
                    {"role": "user", "content": f"Tóm tắt PDF này:\n\n{ai_text}"},
                ],
                "stream": False,
            }
            req = urllib.request.Request(f"{base_url}/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Authorization": f"Bearer {config.auth_key}", "Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=120)
            summary = json.loads(resp.read().decode()).get("choices", [{}])[0].get("message", {}).get("content", "")
            send_message(chat_id, summary.strip() or "Không tóm tắt được.")
        except Exception as e:
            logger.warning("PDF processing error: %s", e)
            send_message(chat_id, f"❌ Lỗi xử lý PDF: {e}")
        finally:
            os.unlink(tmp.name)
        return
        reply = _cmd(text, chat_id)
        if reply:
            send_message(chat_id, reply)
            return

    if not text or not chat_id:
        return

    # Whitelist
    allowed = [str(c) for c in _chat_ids()]
    if allowed and chat_id not in allowed:
        send_message(chat_id, "⛔ Không được phép.")
        return

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
    auth_header = config.auth_key
    payload = {"model": _tg_model(), "messages": _conversations[key], "stream": False}
    try:
        req = urllib.request.Request(f"{base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {auth_header}", "Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=300)
        reply = json.loads(resp.read().decode()).get("choices", [{}])[0].get("message", {}).get("content", "")
        reply = reply.strip() or "..."
    except Exception as exc:
        logger.warning("AI error for %s: %s", chat_id, exc)
        reply = "⏳ Hệ thống bận, thử lại."

    _conversations[key].append({"role": "assistant", "content": reply})
    if len(_conversations[key]) > MAX_HISTORY:
        _conversations[key] = [_conversations[key][0]] + _conversations[key][-(MAX_HISTORY - 1):]

    send_message(chat_id, reply)


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
