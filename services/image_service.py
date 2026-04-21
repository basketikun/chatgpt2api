from __future__ import annotations

import base64
import hashlib
import json
import random
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from curl_cffi.requests import Session
from curl_cffi.requests.exceptions import RequestException

from services.account_service import account_service
from services import proof_of_work
from services.utils import InputImage


BASE_URL = "https://chatgpt.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_MODEL = "gpt-4o"
MAX_POW_ATTEMPTS = 500000
CLIENT_BUILD_NUMBER = "5955942"
CLIENT_VERSION = "prod-be885abbfcfe7b1f511e88b3003d9ee44757fbad"
TIMEZONE_OFFSET_MIN = -480
TIMEZONE_NAME = "America/Los_Angeles"
FILE_USE_CASE = "multimodal"

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


@dataclass(frozen=True)
class UploadedImageAsset:
    file_id: str
    name: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    source: str


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


def _base_api_headers(access_token: str, device_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "content-type": "application/json",
        "oai-device-id": device_id,
        "oai-language": "zh-CN",
        "oai-client-build-number": CLIENT_BUILD_NUMBER,
        "oai-client-version": CLIENT_VERSION,
        "origin": BASE_URL,
        "referer": BASE_URL + "/",
    }


def _chat_requirements(session: Session, access_token: str, device_id: str) -> tuple[str, Optional[dict]]:
    config = _pow_config(USER_AGENT)
    response = _retry(
        lambda: session.post(
            BASE_URL + "/backend-api/sentinel/chat-requirements",
            headers=_base_api_headers(access_token, device_id),
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


def _upload_input_image(session: Session, access_token: str, device_id: str, image: InputImage) -> UploadedImageAsset:
    base_headers = _base_api_headers(access_token, device_id)
    file_request = _retry(
        lambda: session.post(
            BASE_URL + "/backend-api/files",
            headers=base_headers,
            json={
                "file_name": image.name,
                "file_size": image.size_bytes,
                "use_case": FILE_USE_CASE,
                "timezone_offset_min": TIMEZONE_OFFSET_MIN,
                "reset_rate_limits": False,
            },
            timeout=30,
        ),
        retries=2,
    )
    if not file_request.ok:
        raise ImageGenerationError(file_request.text[:400] or f"file init failed: {file_request.status_code}")

    file_payload = file_request.json() or {}
    file_id = str(file_payload.get("file_id") or "").strip()
    upload_url = str(file_payload.get("upload_url") or "").strip()
    if not file_id or not upload_url:
        raise ImageGenerationError("invalid upload session")

    upload_response = session.put(
        upload_url,
        headers={
            "content-type": image.mime_type,
            "x-ms-blob-type": "BlockBlob",
        },
        data=image.data,
        timeout=60,
    )
    if not upload_response.ok:
        raise ImageGenerationError(upload_response.text[:400] or f"file upload failed: {upload_response.status_code}")

    process_request = _retry(
        lambda: session.post(
            BASE_URL + "/backend-api/files/process_upload_stream",
            headers=base_headers,
            json={
                "file_id": file_id,
                "file_name": image.name,
                "file_size": image.size_bytes,
                "use_case": FILE_USE_CASE,
                "timezone_offset_min": TIMEZONE_OFFSET_MIN,
                "index_for_retrieval": False,
            },
            timeout=30,
        ),
        retries=2,
    )
    if not process_request.ok:
        raise ImageGenerationError(process_request.text[:400] or f"file process failed: {process_request.status_code}")

    return UploadedImageAsset(
        file_id=file_id,
        name=image.name,
        mime_type=image.mime_type,
        size_bytes=image.size_bytes,
        width=image.width,
        height=image.height,
        source="local",
    )


def _build_user_message(prompt: str, uploaded_images: list[UploadedImageAsset]) -> dict[str, object]:
    if not uploaded_images:
        return {
            "id": str(uuid.uuid4()),
            "author": {"role": "user"},
            "content": {"content_type": "text", "parts": [prompt]},
            "metadata": {
                "attachments": [],
            },
        }

    parts: list[object] = []
    attachments: list[dict[str, object]] = []
    for image in uploaded_images:
        parts.append(
            {
                "content_type": "image_asset_pointer",
                "asset_pointer": f"file-service://{image.file_id}",
                "size_bytes": image.size_bytes,
                "width": image.width,
                "height": image.height,
            }
        )
        attachments.append(
            {
                "id": image.file_id,
                "size": image.size_bytes,
                "name": image.name,
                "mime_type": image.mime_type,
                "width": image.width,
                "height": image.height,
                "source": image.source,
            }
        )
    parts.append(prompt)

    return {
        "id": str(uuid.uuid4()),
        "author": {"role": "user"},
        "content": {"content_type": "multimodal_text", "parts": parts},
        "metadata": {
            "attachments": attachments,
        },
    }


def _send_conversation(
    session: Session,
    access_token: str,
    device_id: str,
    chat_token: str,
    proof_token: Optional[str],
    parent_message_id: str,
    prompt: str,
    model: str,
    uploaded_images: list[UploadedImageAsset] | None = None,
):
    headers = {
        **_base_api_headers(access_token, device_id),
        "accept": "text/event-stream",
        "openai-sentinel-chat-requirements-token": chat_token,
    }
    if proof_token:
        headers["openai-sentinel-proof-token"] = proof_token
    user_message = _build_user_message(prompt, uploaded_images or [])
    response = _retry(
        lambda: session.post(
            BASE_URL + "/backend-api/conversation",
            headers=headers,
            json={
                "action": "next",
                "messages": [user_message],
                "parent_message_id": parent_message_id,
                "model": model,
                "history_and_training_disabled": False,
                "timezone_offset_min": TIMEZONE_OFFSET_MIN,
                "timezone": TIMEZONE_NAME,
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
            },
            stream=True,
            timeout=180,
        ),
        retries=3,
    )
    if not response.ok:
        raise ImageGenerationError(response.text[:400] or f"conversation failed: {response.status_code}")
    return response


def _parse_sse(response) -> dict:
    file_ids: list[str] = []
    conversation_id = ""
    text_parts: list[str] = []
    iterator = iter(response.iter_lines())
    while True:
        try:
            raw_line = next(iterator)
        except StopIteration:
            break
        except RequestException as exc:
            if conversation_id or file_ids or text_parts:
                print(
                    "[image-upstream] warn sse interrupted "
                    f"conversation_id={conversation_id or '-'} file_ids={len(file_ids)} error={exc}"
                )
                break
            raise ImageGenerationError(f"upstream stream read failed: {exc}") from exc
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
        content = message.get("content") or {}
        if content.get("content_type") == "text":
            parts = content.get("parts") or []
            if parts:
                text_parts.append(str(parts[0]))
    return {"conversation_id": conversation_id, "file_ids": file_ids, "text": "".join(text_parts)}


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


def _poll_image_ids(session: Session, access_token: str, device_id: str, conversation_id: str) -> list[str]:
    started = time.time()
    while time.time() - started < 180:
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
            time.sleep(3)
            continue
        try:
            payload = response.json()
        except Exception:
            time.sleep(3)
            continue
        file_ids = _extract_image_ids(payload.get("mapping") or {})
        if file_ids:
            return file_ids
        time.sleep(3)
    return []


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
    input_images: list[InputImage] | None = None,
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
        print(
            f"[image-upstream] start token={access_token[:12]}... "
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
        parent_message_id = str(uuid.uuid4())
        uploaded_images = [
            _upload_input_image(session, access_token, device_id, image)
            for image in (input_images or [])
        ]
        response = _send_conversation(
            session,
            access_token,
            device_id,
            chat_token,
            proof_token,
            parent_message_id,
            prompt,
            upstream_model,
            uploaded_images,
        )
        parsed = _parse_sse(response)
        actual_conversation_id = parsed.get("conversation_id") or ""
        file_ids = parsed.get("file_ids") or []
        response_text = str(parsed.get("text") or "").strip()
        if actual_conversation_id and not file_ids:
            file_ids = _poll_image_ids(session, access_token, device_id, actual_conversation_id)
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
        print(f"[image-upstream] success token={access_token[:12]}... images=1")
        return {
            "created": time.time_ns() // 1_000_000_000,
            "data": [
                {
                    "b64_json": result.b64_json,
                    "revised_prompt": result.revised_prompt,
                    "url": result.url,
                }
            ],
        }
    except ImageGenerationError as exc:
        print(f"[image-upstream] fail token={access_token[:12]}... error={exc}")
        raise
    except RequestException as exc:
        message = f"upstream request failed: {exc}"
        print(f"[image-upstream] fail token={access_token[:12]}... error={message}")
        raise ImageGenerationError(message) from exc
    except Exception as exc:
        print(f"[image-upstream] fail token={access_token[:12]}... error={exc}")
        raise
    finally:
        session.close()
