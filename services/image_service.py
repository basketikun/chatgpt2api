from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import random
import struct
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from curl_cffi.requests import Session

from services.account_service import account_service
from services.config import config
from services import proof_of_work
from services.utils import anonymize_token


BASE_URL = "https://chatgpt.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_MODEL = "gpt-4o"
MAX_POW_ATTEMPTS = 500000

_CORES = [16, 24, 32]
_SCREENS = [3000, 4000, 6000]
_NAV_KEYS = [
    "webdriver−false",
    "vendor−Google Inc.",
    "cookieEnabled−true",
    "pdfViewerEnabled−true",
    "hardwareConcurrency−32",
    "language−zh-CN",
    "mimeTypes−[object MimeTypeArray]",
    "userAgentData−[object NavigatorUAData]",
]
_WIN_KEYS = [
    "innerWidth",
    "innerHeight",
    "devicePixelRatio",
    "screen",
    "chrome",
    "location",
    "history",
    "navigator",
]


class ImageGenerationError(Exception):
    pass


@dataclass
class GeneratedImage:
    b64_json: str
    revised_prompt: str
    url: str = ""


@dataclass
class UploadedAsset:
    file_id: str
    file_name: str
    mime_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None


def _build_fp(access_token: str) -> dict:
    account = account_service.get_account(access_token) or {}
    fp = {}
    raw_fp = account.get("fp")
    if isinstance(raw_fp, dict):
        fp.update({str(k).lower(): v for k, v in raw_fp.items()})
    for key in (
        "user-agent",
        "impersonate",
        "oai-device-id",
        "sec-ch-ua",
        "sec-ch-ua-mobile",
        "sec-ch-ua-platform",
    ):
        if key in account:
            fp[key] = account[key]
    if "user-agent" not in fp:
        fp["user-agent"] = USER_AGENT
    if "impersonate" not in fp:
        fp["impersonate"] = "edge101"
    if "oai-device-id" not in fp:
        fp["oai-device-id"] = str(uuid.uuid4())
    return fp


def _new_session(access_token: str) -> tuple[Session, dict]:
    fp = _build_fp(access_token)
    session = Session(
        impersonate=fp.get("impersonate") or "edge101",
        verify=True,
        proxy=config.proxy_url,
    )
    session.headers.update(
        {
            "user-agent": fp.get("user-agent") or USER_AGENT,
            "accept-language": "en-US,en;q=0.9",
            "origin": BASE_URL,
            "referer": BASE_URL + "/",
            "accept": "*/*",
            "sec-ch-ua": fp.get("sec-ch-ua") or '"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": fp.get("sec-ch-ua-mobile") or "?0",
            "sec-ch-ua-platform": fp.get("sec-ch-ua-platform") or '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "oai-device-id": fp.get("oai-device-id"),
        }
    )
    return session, fp


def _retry(fn, retries: int = 4, delay: float = 2.0, retry_on_status: tuple[int, ...] = ()) -> object:
    last_error = None
    last_response = None
    for attempt in range(retries):
        try:
            response = fn()
        except Exception as exc:
            last_error = exc
            time.sleep(delay)
            continue
        if retry_on_status and getattr(response, "status_code", 0) in retry_on_status:
            last_response = response
            time.sleep(delay * (attempt + 1))
            continue
        return response
    if last_response is not None:
        return last_response
    if last_error is not None:
        raise last_error
    raise ImageGenerationError("request failed")


def _pow_config(user_agent: str) -> list:
    return proof_of_work.get_config(user_agent)


def _generate_requirements_answer(seed: str, difficulty: str, config: list) -> tuple[str, bool]:
    diff_len = len(difficulty)
    seed_bytes = seed.encode()
    prefix1 = (json.dumps(config[:3], separators=(",", ":"), ensure_ascii=False)[:-1] + ",").encode()
    prefix2 = ("," + json.dumps(config[4:9], separators=(",", ":"), ensure_ascii=False)[1:-1] + ",").encode()
    prefix3 = ("," + json.dumps(config[10:], separators=(",", ":"), ensure_ascii=False)[1:]).encode()
    target = bytes.fromhex(difficulty)
    for attempt in range(MAX_POW_ATTEMPTS):
        left = str(attempt).encode()
        right = str(attempt >> 1).encode()
        encoded = base64.b64encode(prefix1 + left + prefix2 + right + prefix3)
        digest = hashlib.sha3_512(seed_bytes + encoded).digest()
        if digest[:diff_len] <= target:
            return encoded.decode(), True
    fallback = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D" + base64.b64encode(f'"{seed}"'.encode()).decode()
    return fallback, False


def _get_requirements_token(config: list) -> str:
    seed = format(random.random())
    answer, _ = _generate_requirements_answer(seed, "0fffff", config)
    return "gAAAAAC" + answer


def _generate_proof_token(seed: str, difficulty: str, user_agent: str, proof_config: Optional[list] = None) -> str:
    answer, _ = proof_of_work.get_answer_token(seed, difficulty, proof_config or _pow_config(user_agent))
    return answer


def _bootstrap(session: Session, fp: dict) -> str:
    response = _retry(lambda: session.get(BASE_URL + "/", timeout=30))
    try:
        proof_of_work.get_data_build_from_html(response.text)
    except Exception:
        pass
    device_id = response.cookies.get("oai-did")
    if device_id:
        return device_id
    for cookie in session.cookies.jar if hasattr(session.cookies, "jar") else []:
        name = getattr(cookie, "name", getattr(cookie, "key", ""))
        if name == "oai-did":
            return cookie.value
    return str(fp.get("oai-device-id") or uuid.uuid4())


def _chat_requirements(session: Session, access_token: str, device_id: str) -> tuple[str, Optional[dict]]:
    config = _pow_config(USER_AGENT)
    response = _retry(
        lambda: session.post(
            BASE_URL + "/backend-api/sentinel/chat-requirements",
            headers={
                "Authorization": f"Bearer {access_token}",
                "oai-device-id": device_id,
                "content-type": "application/json",
            },
            json={"p": _get_requirements_token(config)},
            timeout=30,
        ),
        retries=4,
    )
    if not response.ok:
        raise ImageGenerationError(response.text[:400] or f"chat-requirements failed: {response.status_code}")
    payload = response.json()
    return payload["token"], payload.get("proofofwork") or {}


def is_token_invalid_error(message: str) -> bool:
    text = str(message or "").lower()
    return (
        "token_invalidated" in text
        or "token_revoked" in text
        or "authentication token has been invalidated" in text
        or "invalidated oauth token" in text
    )


def _send_conversation(
    session: Session,
    access_token: str,
    device_id: str,
    chat_token: str,
    proof_token: Optional[str],
    conversation_id: Optional[str],
    parent_message_id: str,
    message_content: dict[str, object],
    attachments: list[dict[str, object]],
    model: str,
):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "accept": "text/event-stream",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "content-type": "application/json",
        "oai-device-id": device_id,
        "oai-language": "zh-CN",
        "oai-client-build-number": "5955942",
        "oai-client-version": "prod-be885abbfcfe7b1f511e88b3003d9ee44757fbad",
        "origin": BASE_URL,
        "referer": BASE_URL + "/",
        "openai-sentinel-chat-requirements-token": chat_token,
    }
    if proof_token:
        headers["openai-sentinel-proof-token"] = proof_token
    payload = {
        "action": "next",
        "messages": [
            {
                "id": str(uuid.uuid4()),
                "author": {"role": "user"},
                "content": message_content,
                "metadata": {"attachments": attachments},
            }
        ],
        "parent_message_id": parent_message_id,
        "model": model,
        "history_and_training_disabled": False,
        "timezone_offset_min": -480,
        "timezone": "America/Los_Angeles",
        "conversation_mode": {"kind": "primary_assistant"},
        "conversation_origin": None,
        "force_paragen": False,
        "force_paragen_model_slug": "",
        "force_rate_limit": False,
        "force_use_sse": True,
        "paragen_cot_summary_display_override": "allow",
        "paragen_stream_type_override": None,
        "reset_rate_limits": False,
        "suggestions": [],
        "supported_encodings": [],
        "system_hints": ["picture_v2"],
        "variant_purpose": "comparison_implicit",
        "websocket_request_id": str(uuid.uuid4()),
        "client_contextual_info": {
            "is_dark_mode": False,
            "time_since_loaded": random.randint(50, 500),
            "page_height": random.randint(500, 1000),
            "page_width": random.randint(1000, 2000),
            "pixel_ratio": 1.2,
            "screen_height": random.randint(800, 1200),
            "screen_width": random.randint(1200, 2200),
        },
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id
    response = _retry(
        lambda: session.post(
            BASE_URL + "/backend-api/conversation",
            headers=headers,
            json=payload,
            stream=True,
            timeout=180,
        ),
        retries=3,
    )
    if not response.ok:
        raise ImageGenerationError(response.text[:400] or f"conversation failed: {response.status_code}")
    return response


def _get_image_dimensions(file_content: bytes, mime_type: str) -> tuple[int | None, int | None]:
    if mime_type == "image/png" and len(file_content) >= 24 and file_content.startswith(b"\x89PNG\r\n\x1a\n"):
        return struct.unpack(">II", file_content[16:24])

    if mime_type == "image/gif" and len(file_content) >= 10 and file_content[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", file_content[6:10])

    if mime_type == "image/jpeg":
        offset = 2
        data_len = len(file_content)
        while offset + 9 < data_len:
            if file_content[offset] != 0xFF:
                offset += 1
                continue
            marker = file_content[offset + 1]
            offset += 2
            if marker in {0xD8, 0xD9}:
                continue
            if offset + 2 > data_len:
                break
            segment_length = struct.unpack(">H", file_content[offset : offset + 2])[0]
            if segment_length < 2 or offset + segment_length > data_len:
                break
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            } and segment_length >= 7:
                height, width = struct.unpack(">HH", file_content[offset + 3 : offset + 7])
                return width, height
            offset += segment_length
        return None, None

    if mime_type == "image/webp" and len(file_content) >= 30 and file_content[:4] == b"RIFF" and file_content[8:12] == b"WEBP":
        chunk = file_content[12:16]
        if chunk == b"VP8X" and len(file_content) >= 30:
            width = 1 + int.from_bytes(file_content[24:27], "little")
            height = 1 + int.from_bytes(file_content[27:30], "little")
            return width, height
        if chunk == b"VP8L" and len(file_content) >= 25:
            bits = int.from_bytes(file_content[21:25], "little")
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            return width, height
        if chunk == b"VP8 " and len(file_content) >= 30:
            width, height = struct.unpack("<HH", file_content[26:30])
            return width & 0x3FFF, height & 0x3FFF

    return None, None


def _guess_file_extension(mime_type: str) -> str:
    return mimetypes.guess_extension(mime_type) or ".bin"


def _upload_input_image(
    session: Session,
    access_token: str,
    device_id: str,
    file_content: bytes,
    mime_type: str,
    filename: str | None,
) -> UploadedAsset:
    if not file_content:
        raise ImageGenerationError("input image is empty")

    width, height = _get_image_dimensions(file_content, mime_type)
    if width is None or height is None:
        raise ImageGenerationError(f"unsupported image format: {mime_type}")

    file_name = str(filename or "").strip()
    if not file_name:
        file_name = hashlib.sha256(file_content).hexdigest() + _guess_file_extension(mime_type)

    response = _retry(
        lambda: session.post(
            BASE_URL + "/backend-api/files",
            headers={
                "Authorization": f"Bearer {access_token}",
                "oai-device-id": device_id,
                "content-type": "application/json",
            },
            json={
                "file_name": file_name,
                "file_size": len(file_content),
                "use_case": "multimodal",
            },
            timeout=30,
        ),
        retries=3,
    )
    if response.status_code != 200:
        raise ImageGenerationError(response.text[:400] or f"file init failed: {response.status_code}")

    payload = response.json()
    upload_url = str(payload.get("upload_url") or "").strip()
    file_id = str(payload.get("file_id") or "").strip()
    if not upload_url or not file_id:
        raise ImageGenerationError("file upload initialization returned incomplete data")

    put_response = session.put(
        upload_url,
        headers={
            "Content-Type": mime_type,
            "x-ms-blob-type": "BlockBlob",
        },
        data=file_content,
        timeout=60,
    )
    if put_response.status_code not in {200, 201}:
        raise ImageGenerationError(put_response.text[:400] or f"file upload failed: {put_response.status_code}")

    check_response = _retry(
        lambda: session.post(
            f"{BASE_URL}/backend-api/files/{file_id}/uploaded",
            headers={
                "Authorization": f"Bearer {access_token}",
                "oai-device-id": device_id,
                "content-type": "application/json",
            },
            json={},
            timeout=30,
        ),
        retries=3,
    )
    if check_response.status_code != 200:
        raise ImageGenerationError(check_response.text[:400] or f"file finalize failed: {check_response.status_code}")
    if str((check_response.json() or {}).get("status") or "").strip().lower() != "success":
        raise ImageGenerationError("file upload completion check not successful")

    return UploadedAsset(
        file_id=file_id,
        file_name=file_name,
        mime_type=mime_type,
        size_bytes=len(file_content),
        width=width,
        height=height,
    )


def _build_image_edit_message(prompt: str, uploaded_asset: UploadedAsset) -> tuple[dict[str, object], list[dict[str, object]]]:
    parts: list[object] = [prompt]
    image_part: dict[str, object] = {
        "asset_pointer": f"file-service://{uploaded_asset.file_id}",
        "size_bytes": uploaded_asset.size_bytes,
    }
    attachment: dict[str, object] = {
        "name": uploaded_asset.file_name,
        "id": uploaded_asset.file_id,
        "mimeType": uploaded_asset.mime_type,
        "size": uploaded_asset.size_bytes,
    }
    if uploaded_asset.width is not None and uploaded_asset.height is not None:
        image_part["width"] = uploaded_asset.width
        image_part["height"] = uploaded_asset.height
        attachment["width"] = uploaded_asset.width
        attachment["height"] = uploaded_asset.height
    parts.append(image_part)
    return {"content_type": "multimodal_text", "parts": parts}, [attachment]


def _parse_sse(response) -> dict:
    file_ids: list[str] = []
    conversation_id = ""
    last_message_id = ""
    text_parts: list[str] = []
    for raw_line in response.iter_lines():
        if not raw_line:
            continue
        if isinstance(raw_line, bytes):
            raw_line = raw_line.decode("utf-8", errors="replace")
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload in ("", "[DONE]"):
            break
        for prefix, stored_prefix in (("file-service://", ""), ("sediment://", "sed:")):
            start = 0
            while True:
                index = payload.find(prefix, start)
                if index < 0:
                    break
                start = index + len(prefix)
                tail = payload[start:]
                file_id = []
                for char in tail:
                    if char.isalnum() or char in "_-":
                        file_id.append(char)
                    else:
                        break
                if file_id:
                    value = stored_prefix + "".join(file_id)
                    if value not in file_ids:
                        file_ids.append(value)
        try:
            obj = json.loads(payload)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        conversation_id = str(obj.get("conversation_id") or conversation_id)
        if obj.get("type") in {"resume_conversation_token", "message_marker", "message_stream_complete"}:
            conversation_id = str(obj.get("conversation_id") or conversation_id)
        data = obj.get("v")
        if isinstance(data, dict):
            conversation_id = str(data.get("conversation_id") or conversation_id)
        message = obj.get("message") or {}
        if message.get("id"):
            last_message_id = str(message.get("id") or last_message_id)
        content = message.get("content") or {}
        if content.get("content_type") == "text":
            parts = content.get("parts") or []
            if parts:
                text_parts.append(str(parts[0]))
    return {
        "conversation_id": conversation_id,
        "file_ids": file_ids,
        "text": "".join(text_parts),
        "last_message_id": last_message_id,
    }


def _extract_image_ids(mapping: dict) -> list[str]:
    file_ids: list[str] = []
    for node in mapping.values():
        message = (node or {}).get("message") or {}
        author = message.get("author") or {}
        metadata = message.get("metadata") or {}
        content = message.get("content") or {}
        if author.get("role") != "tool":
            continue
        if metadata.get("async_task_type") != "image_gen":
            continue
        if content.get("content_type") != "multimodal_text":
            continue
        for part in content.get("parts") or []:
            if isinstance(part, dict):
                pointer = str(part.get("asset_pointer") or "")
                if pointer.startswith("file-service://"):
                    file_id = pointer.removeprefix("file-service://")
                    if file_id not in file_ids:
                        file_ids.append(file_id)
                elif pointer.startswith("sediment://"):
                    file_id = "sed:" + pointer.removeprefix("sediment://")
                    if file_id not in file_ids:
                        file_ids.append(file_id)
    return file_ids


def _fetch_conversation_payload(session: Session, access_token: str, device_id: str, conversation_id: str) -> dict | None:
    response = _retry(
        lambda: session.get(
            f"{BASE_URL}/backend-api/conversation/{conversation_id}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "oai-device-id": device_id,
                "accept": "*/*",
            },
            timeout=30,
        ),
        retries=2,
        retry_on_status=(429, 502, 503, 504),
    )
    if response.status_code != 200:
        return None
    try:
        payload = response.json()
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _resolve_conversation_state(
    session: Session,
    access_token: str,
    device_id: str,
    conversation_id: str,
    require_file_ids: bool,
) -> dict[str, object]:
    started = time.time()
    last_current_node = ""
    last_file_ids: list[str] = []
    while time.time() - started < 180:
        payload = _fetch_conversation_payload(session, access_token, device_id, conversation_id)
        if not payload:
            time.sleep(3)
            continue
        current_node = str(payload.get("current_node") or "")
        if current_node:
            last_current_node = current_node
        file_ids = _extract_image_ids(payload.get("mapping") or {})
        if file_ids:
            last_file_ids = file_ids
        if last_current_node and (not require_file_ids or last_file_ids):
            return {"current_node": last_current_node, "file_ids": last_file_ids}
        time.sleep(3)
    return {"current_node": last_current_node, "file_ids": last_file_ids}


def _poll_image_ids(session: Session, access_token: str, device_id: str, conversation_id: str) -> list[str]:
    state = _resolve_conversation_state(
        session,
        access_token,
        device_id,
        conversation_id,
        require_file_ids=True,
    )
    file_ids = state.get("file_ids")
    return file_ids if isinstance(file_ids, list) else []


def _fetch_download_url(session: Session, access_token: str, device_id: str, conversation_id: str, file_id: str) -> str:
    is_sediment = file_id.startswith("sed:")
    raw_id = file_id[4:] if is_sediment else file_id
    if is_sediment:
        endpoint = f"{BASE_URL}/backend-api/conversation/{conversation_id}/attachment/{raw_id}/download"
    else:
        endpoint = f"{BASE_URL}/backend-api/files/{raw_id}/download"
    response = session.get(
        endpoint,
        headers={
            "Authorization": f"Bearer {access_token}",
            "oai-device-id": device_id,
        },
        timeout=30,
    )
    if not response.ok:
        return ""
    return str((response.json() or {}).get("download_url") or "")


def _download_as_base64(session: Session, download_url: str) -> str:
    response = session.get(download_url, timeout=60)
    if not response.ok or not response.content:
        raise ImageGenerationError("download image failed")
    return base64.b64encode(response.content).decode("ascii")


def _resolve_upstream_model(access_token: str, requested_model: str) -> str:
    requested_model = str(requested_model or "").strip() or "gpt-image-1"
    account = account_service.get_account(access_token) or {}
    is_free_account = str(account.get("type") or "Free").strip() == "Free"

    if requested_model == "gpt-image-1":
        return "auto"
    if requested_model == "gpt-image-2":
        return "auto" if is_free_account else "gpt-5-3"
    return str(requested_model or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def generate_image_result(
    access_token: str,
    prompt: str,
    model: str = DEFAULT_MODEL,
    conversation_id: str | None = None,
    parent_message_id: str | None = None,
) -> dict:
    prompt = str(prompt or "").strip()
    access_token = str(access_token or "").strip()
    if not prompt:
        raise ImageGenerationError("prompt is required")
    if not access_token:
        raise ImageGenerationError("token is required")

    session, fp = _new_session(access_token)
    try:
        upstream_model = _resolve_upstream_model(access_token, model)
        token_ref = anonymize_token(access_token)
        print(
            f"[image-upstream] start token={token_ref} "
            f"requested_model={model} upstream_model={upstream_model}"
        )
        device_id = _bootstrap(session, fp)
        chat_token, pow_info = _chat_requirements(session, access_token, device_id)
        proof_token = None
        if pow_info.get("required"):
            proof_token = _generate_proof_token(
                seed=str(pow_info["seed"]),
                difficulty=str(pow_info["difficulty"]),
                user_agent=USER_AGENT,
                proof_config=_pow_config(USER_AGENT),
            )
        request_parent_message_id = str(parent_message_id or "").strip() or str(uuid.uuid4())
        request_conversation_id = str(conversation_id or "").strip() or None
        response = _send_conversation(
            session,
            access_token,
            device_id,
            chat_token,
            proof_token,
            request_conversation_id,
            request_parent_message_id,
            {"content_type": "text", "parts": [prompt]},
            [],
            upstream_model,
        )
        parsed = _parse_sse(response)
        actual_conversation_id = parsed.get("conversation_id") or ""
        file_ids = parsed.get("file_ids") or []
        response_text = str(parsed.get("text") or "").strip()
        last_message_id = str(parsed.get("last_message_id") or "").strip()
        next_parent_message_id = last_message_id
        if actual_conversation_id:
            state = _resolve_conversation_state(
                session,
                access_token,
                device_id,
                actual_conversation_id,
                require_file_ids=not bool(file_ids),
            )
            current_node = str(state.get("current_node") or "").strip()
            if current_node:
                next_parent_message_id = current_node
            if not file_ids:
                file_ids = state.get("file_ids") or []
        if not file_ids:
            if response_text:
                raise ImageGenerationError(response_text)
            raise ImageGenerationError("no image returned from upstream")
        first_file_id = str(file_ids[0])
        download_url = _fetch_download_url(session, access_token, device_id, actual_conversation_id, first_file_id)
        if not download_url:
            raise ImageGenerationError("failed to get download url")
        result = GeneratedImage(
            b64_json=_download_as_base64(session, download_url),
            revised_prompt=prompt,
            url=download_url,
        )
        print(f"[image-upstream] success token={token_ref} images=1")
        return {
            "created": time.time_ns() // 1_000_000_000,
            "data": [{"b64_json": result.b64_json, "revised_prompt": result.revised_prompt}],
            "upstream_conversation_id": actual_conversation_id or None,
            "upstream_parent_message_id": next_parent_message_id or None,
        }
    except Exception as exc:
        print(f"[image-upstream] fail token={token_ref} error={exc}")
        raise
    finally:
        session.close()


def edit_image_result(
    access_token: str,
    prompt: str,
    image_bytes: bytes,
    image_mime_type: str,
    image_filename: str | None,
    model: str = DEFAULT_MODEL,
    conversation_id: str | None = None,
    parent_message_id: str | None = None,
) -> dict:
    prompt = str(prompt or "").strip()
    access_token = str(access_token or "").strip()
    image_mime_type = str(image_mime_type or "").split(";", 1)[0].strip().lower()
    if not prompt:
        raise ImageGenerationError("prompt is required")
    if not access_token:
        raise ImageGenerationError("token is required")
    if not image_mime_type.startswith("image/"):
        raise ImageGenerationError("input image must be an image/* file")

    session, fp = _new_session(access_token)
    try:
        upstream_model = _resolve_upstream_model(access_token, model)
        token_ref = anonymize_token(access_token)
        print(
            f"[image-edit] start token={token_ref} "
            f"requested_model={model} upstream_model={upstream_model}"
        )
        device_id = _bootstrap(session, fp)
        uploaded_asset = _upload_input_image(session, access_token, device_id, image_bytes, image_mime_type, image_filename)
        chat_token, pow_info = _chat_requirements(session, access_token, device_id)
        proof_token = None
        if pow_info.get("required"):
            proof_token = _generate_proof_token(
                seed=str(pow_info["seed"]),
                difficulty=str(pow_info["difficulty"]),
                user_agent=USER_AGENT,
                proof_config=_pow_config(USER_AGENT),
            )
        message_content, attachments = _build_image_edit_message(prompt, uploaded_asset)
        request_parent_message_id = str(parent_message_id or "").strip() or str(uuid.uuid4())
        request_conversation_id = str(conversation_id or "").strip() or None
        response = _send_conversation(
            session,
            access_token,
            device_id,
            chat_token,
            proof_token,
            request_conversation_id,
            request_parent_message_id,
            message_content,
            attachments,
            upstream_model,
        )
        parsed = _parse_sse(response)
        actual_conversation_id = parsed.get("conversation_id") or ""
        file_ids = parsed.get("file_ids") or []
        response_text = str(parsed.get("text") or "").strip()
        last_message_id = str(parsed.get("last_message_id") or "").strip()
        next_parent_message_id = last_message_id
        if actual_conversation_id:
            state = _resolve_conversation_state(
                session,
                access_token,
                device_id,
                actual_conversation_id,
                require_file_ids=not bool(file_ids),
            )
            current_node = str(state.get("current_node") or "").strip()
            if current_node:
                next_parent_message_id = current_node
            if not file_ids:
                file_ids = state.get("file_ids") or []
        if not file_ids:
            if response_text:
                raise ImageGenerationError(response_text)
            raise ImageGenerationError("no edited image returned from upstream")
        download_url = _fetch_download_url(session, access_token, device_id, actual_conversation_id, str(file_ids[0]))
        if not download_url:
            raise ImageGenerationError("failed to get download url")
        result = GeneratedImage(
            b64_json=_download_as_base64(session, download_url),
            revised_prompt=prompt,
            url=download_url,
        )
        print(f"[image-edit] success token={token_ref} images=1")
        return {
            "created": time.time_ns() // 1_000_000_000,
            "data": [{"b64_json": result.b64_json, "revised_prompt": result.revised_prompt}],
            "upstream_conversation_id": actual_conversation_id or None,
            "upstream_parent_message_id": next_parent_message_id or None,
        }
    except Exception as exc:
        print(f"[image-edit] fail token={token_ref} error={exc}")
        raise
    finally:
        session.close()
