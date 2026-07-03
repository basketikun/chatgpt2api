import base64
import json
import mimetypes
import os
import random
import re
import time

import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from collections.abc import Callable
from typing import Any, Dict, Iterator, Optional
from urllib.parse import unquote, urlparse

from curl_cffi import requests
from PIL import Image

from services.account_service import account_service
from services.config import config
from services.proxy_service import proxy_settings
from utils.helper import UpstreamHTTPError, ensure_ok, iter_sse_payloads, new_uuid, split_image_model
from utils.log import logger
from utils.pow import build_legacy_requirements_token, build_proof_token, parse_pow_resources
from utils.turnstile import solve_turnstile_token


class InvalidAccessTokenError(RuntimeError):
    pass


class ImagePollTimeoutError(RuntimeError):
    pass


class ImageContentPolicyError(RuntimeError):
    """Raised when image generation is blocked by content policy moderation."""
    pass


@dataclass
class ChatRequirements:
    """保存一次对话请求所需的 sentinel token。"""
    token: str
    proof_token: str = ""
    turnstile_token: str = ""
    so_token: str = ""
    raw_finalize: Optional[Dict[str, Any]] = None


DEFAULT_CLIENT_VERSION = "prod-a194cd50d4416d3c0b47c740f206b12ce60f5887"
DEFAULT_CLIENT_BUILD_NUMBER = "6708908"
DEFAULT_POW_SCRIPT = "https://chatgpt.com/backend-api/sentinel/sdk.js"
CODEX_IMAGE_MODEL = "codex-gpt-image-2"
CODEX_RESPONSES_MODEL = "gpt-5.5"
SEARCH_MODEL = "gpt-5-5"
SEARCH_TIMEOUT_SECS = 300.0
SEARCH_POLL_INTERVAL_SECS = 3.0
SEARCH_DONE_STATUS = {"finished_successfully", "finished_partial_completion"}
SEARCH_CONVERSATION_ID_RE = re.compile(r'"conversation_id"\s*:\s*"([^"]+)"')
SEARCH_URL_RE = re.compile(r"https?://[^\s\"'<>）)\]}]+")
EDITABLE_FILE_MODEL = "gpt-5-5-thinking"
EDITABLE_FILE_THINKING_EFFORT = "extended"
EDITABLE_FILE_TIMEOUT_SECS = 1200.0
EDITABLE_FILE_POLL_INTERVAL_SECS = 5.0
EDITABLE_FILE_CLIENT_VERSION = "prod-bede35f9dcd856d080e012478f0c1031faa2588e"
EDITABLE_FILE_CLIENT_BUILD_NUMBER = "6631702"
EDITABLE_FILE_PSD_OUTPUT_DIR = "data/files/psd"
EDITABLE_FILE_PPT_OUTPUT_DIR = "data/files/ppt"
EDITABLE_FILE_PPT_PROMPT = """我需要你根据用户的需求，来制作一个可以编辑的PPT，你可以使用Agent来做，你不要再继续询问用户问题，内容风格、版式、配色、内容结构和页面信息你可以自行补充并直接执行。整体的流程如下：
1. 用生图的方式，帮我生成一个精美的产品介绍ppt，5-6个页面
2. 帮我把以上涉及到的所有图像和形状素材拆分成单独png，每个素材单独一张图片，不要有遗漏，让我可以直接在ppt里拼接素材还原，不要文字
3. 利用以上所有图片和形状素材，帮我还原你第一次生成的展示ppt，我需要是可编辑的ppt格式，主要部分需要你单独还原插入，文字需要可以编辑
最后只需要给我生成一个PPT文件，以及生成中遇到的各种素材压缩包zip文件就行。"""
EDITABLE_FILE_PSD_PROMPT = "帮我生成这个图像，把这张海报分成若干图像，包括背景图，每个元素不要改位置，这样子我可以直接在 平时里无需拖动，底色为白色，不要伪透明底。再帮我将以上拆分的图像拼合成一个psd文件，去除白色底，不要改变每个图层的相应位置，保留每个元素所在图层的相应位置，保留每个元素的图层，最后只需要给我输出psd文件，以及每个图层的zip文件"
EDITABLE_ASSET_POINTER_RE = re.compile(r"(?:file-service|sediment)://([A-Za-z0-9_-]+)")
EDITABLE_ZIP_MIME_TYPES = {"application/zip", "application/x-zip-compressed"}
EDITABLE_PSD_MIME_TYPES = {"image/vnd.adobe.photoshop", "application/vnd.adobe.photoshop"}
EDITABLE_PPT_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
}
EDITABLE_PSD_EXPORT_FILE_RE = re.compile(r"(?:sandbox:)?(/mnt/data/[^\s\"'\)\]]+\.(?:psd|zip))", re.IGNORECASE)
EDITABLE_PPT_EXPORT_FILE_RE = re.compile(r"(?:sandbox:)?(/mnt/data/[^\s\"'\)\]]+\.(?:pptx?|zip))", re.IGNORECASE)
FILE_SERVICE_ID_RE = re.compile(r"file-service://([A-Za-z0-9_-]+)")
FILE_ID_RE = re.compile(r"\b(file[-_](?!service\b)[A-Za-z0-9_-]+)\b")
# 真正的图片文件 ID 格式：file_00000000 + 24位十六进制字符（共32字符）
REAL_IMAGE_FILE_ID_RE = re.compile(r"\bfile_00000000[a-f0-9]{24}\b")
SEDIMENT_ID_RE = re.compile(r"sediment://([A-Za-z0-9_-]+)")
IMAGE_POLL_SETTLE_SECS = 2.0
CODEX_RESPONSES_INSTRUCTIONS = (
    "Use the image_generation tool to create exactly one image for the user's request. "
    "Return the generated image result."
)

# 内容政策违规错误关键词（上游拒绝生成图片的各种表述）
_CONTENT_POLICY_KEYWORDS = (
    # 明确的内容政策违规
    "内容政策", "防护限制", "违反", "moderation", "policy", "blocked",
    # 拒绝生成类
    "不能生成", "无法生成", "不能帮助", "无法帮助",
    # 敏感内容类
    "裸体", "裸露", "色情", "性内容", "未成年",
    # 通用拒绝
    "抱歉，我不能",
)


def _is_content_policy_error(error_msg: str) -> bool:
    """检查错误消息是否为内容政策违规。"""
    if not error_msg:
        return False
    msg_lower = error_msg.lower()
    return any(keyword in msg_lower for keyword in _CONTENT_POLICY_KEYWORDS)


@dataclass
class EditableFileArtifact:
    attachment_id: str = ""
    file_id: str = ""
    name: str = ""
    mime_type: str = ""
    create_time: float = 0.0
    author_role: str = ""
    sandbox_path: str = ""
    message_id: str = ""


@dataclass
class EditableFileExportResult:
    conversation_id: str
    primary_path: Path
    zip_path: Path


class OpenAIBackendAPI:
    """ChatGPT Web 后端封装。

    说明：
    - 传入 `access_token` 时，聊天和模型列表都会走已登录链路
      例如 `/backend-api/sentinel/chat-requirements`、`/backend-api/conversation`
    - 不传 `access_token` 时，会走未登录链路
      例如 `/backend-anon/sentinel/chat-requirements`、`/backend-anon/conversation`
    - `stream_conversation()` 是底层统一流式入口
    - 协议兼容转换放在 `services.protocol`
    """

    def __init__(self, access_token: str = "") -> None:
        """初始化后端客户端。

        参数：
        - `access_token`：可选。传入后表示使用已登录链路；不传则使用未登录链路。
        """
        self.base_url = "https://chatgpt.com"
        self.client_version = DEFAULT_CLIENT_VERSION
        self.client_build_number = DEFAULT_CLIENT_BUILD_NUMBER
        self.access_token = access_token
        self.account = account_service.get_account(self.access_token) if self.access_token else {}
        self.account = self.account if isinstance(self.account, dict) else {}
        self.fp = self._build_fp()
        self.user_agent = self.fp["user-agent"]
        self.device_id = self.fp["oai-device-id"]
        self.session_id = self.fp["oai-session-id"]
        self.pow_script_sources: list[str] = []
        self.pow_data_build = ""
        self.progress_callback: Callable[[str], None] | None = None
        self.session = requests.Session(**proxy_settings.build_session_kwargs(
            account=self.account,
            impersonate=self.fp["impersonate"],
            verify=True,
        ))
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Origin": self.base_url,
            "Referer": self.base_url + "/",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Priority": "u=1, i",
            "Sec-Ch-Ua": self.fp["sec-ch-ua"],
            "Sec-Ch-Ua-Arch": '"x86"',
            "Sec-Ch-Ua-Bitness": '"64"',
            "Sec-Ch-Ua-Full-Version": '"143.0.3650.96"',
            "Sec-Ch-Ua-Full-Version-List": '"Microsoft Edge";v="143.0.3650.96", "Chromium";v="143.0.7499.147", "Not A(Brand";v="24.0.0.0"',
            "Sec-Ch-Ua-Mobile": self.fp["sec-ch-ua-mobile"],
            "Sec-Ch-Ua-Model": '""',
            "Sec-Ch-Ua-Platform": self.fp["sec-ch-ua-platform"],
            "Sec-Ch-Ua-Platform-Version": '"19.0.0"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "OAI-Device-Id": self.device_id,
            "OAI-Session-Id": self.session_id,
            "OAI-Language": "zh-CN",
            "OAI-Client-Version": self.client_version,
            "OAI-Client-Build-Number": self.client_build_number,
        })
        if self.access_token:
            self.session.headers["Authorization"] = f"Bearer {self.access_token}"

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        session = getattr(self, "session", None)
        if session:
            try:
                session.close()
            except Exception:
                pass

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False

    def _build_fp(self) -> Dict[str, str]:
        account = self.account
        raw_fp = account.get("fp")
        fp = {str(k).lower(): str(v) for k, v in raw_fp.items()} if isinstance(raw_fp, dict) else {}
        for key in (
                "user-agent",
                "impersonate",
                "oai-device-id",
                "oai-session-id",
                "sec-ch-ua",
                "sec-ch-ua-mobile",
                "sec-ch-ua-platform",
        ):
            value = str(account.get(key) or "").strip()
            if value:
                fp[key] = value
        fp.setdefault(
            "user-agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0",
        )
        fp.setdefault("impersonate", "chrome110")
        fp.setdefault("oai-device-id", new_uuid())
        fp.setdefault("oai-session-id", new_uuid())
        fp.setdefault("sec-ch-ua", '"Microsoft Edge";v="143", "Chromium";v="143", "Not A(Brand";v="24"')
        fp.setdefault("sec-ch-ua-mobile", "?0")
        fp.setdefault("sec-ch-ua-platform", '"Windows"')
        return fp

    def _headers(self, path: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """构造请求头，并补上 web 端要求的 target path/route。"""
        headers = dict(self.session.headers)
        headers["X-OpenAI-Target-Path"] = path
        headers["X-OpenAI-Target-Route"] = path
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _extract_quota_and_restore_at(limits_progress: list[Any]) -> tuple[int, str | None, bool]:
        for item in limits_progress:
            if isinstance(item, dict) and item.get("feature_name") == "image_gen":
                return int(item.get("remaining") or 0), str(item.get("reset_after") or "") or None, False
        return 0, None, True

    def _raise_on_error(self, response: Any, path: str) -> None:
        if response.status_code == 401:
            raise InvalidAccessTokenError(f"token invalidated ({path})")
        raise RuntimeError(f"{path} failed: HTTP {response.status_code}")

    def _get_me(self) -> Dict[str, Any]:
        path = "/backend-api/me"
        response = self.session.get(self.base_url + path, headers=self._headers(path), timeout=20)
        if response.status_code != 200:
            self._raise_on_error(response, path)
        return response.json()

    def _get_conversation_init(self) -> Dict[str, Any]:
        path = "/backend-api/conversation/init"
        response = self.session.post(
            self.base_url + path,
            headers=self._headers(path, {"Content-Type": "application/json"}),
            json={
                "gizmo_id": None,
                "requested_default_model": None,
                "conversation_id": None,
                "timezone_offset_min": -480,
            },
            timeout=20,
        )
        if response.status_code != 200:
            self._raise_on_error(response, path)
        return response.json()

    def _get_default_account(self) -> Dict[str, Any]:
        path = "/backend-api/accounts/check/v4-2023-04-27"
        response = self.session.get(self.base_url + path + "?timezone_offset_min=-480", headers=self._headers(path),
                                    timeout=20)
        if response.status_code != 200:
            self._raise_on_error(response, path)
        payload = response.json()
        default_account = ((payload.get("accounts") or {}).get("default") or {}).get("account") or {}
        logger.debug({
            "event": "backend_user_info_account_payload",
            "plan_type": default_account.get("plan_type"),
            "account_user_role": default_account.get("account_user_role"),
            "account_id": default_account.get("account_id"),
            "is_deactivated": default_account.get("is_deactivated"),
            "has_active_subscription": (payload.get("accounts") or {}).get("default", {}).get("entitlement", {}).get("has_active_subscription"),
            "subscription_plan": (payload.get("accounts") or {}).get("default", {}).get("entitlement", {}).get("subscription_plan"),
        })
        return default_account

    def get_user_info(self) -> Dict[str, Any]:
        """获取当前 token 的账号信息。"""
        if not self.access_token:
            raise RuntimeError("access_token is required")
        executor = ThreadPoolExecutor(max_workers=3)
        try:
            me_future = executor.submit(self._get_me)
            init_future = executor.submit(self._get_conversation_init)
            account_future = executor.submit(self._get_default_account)
            me_payload, init_payload, default_account = me_future.result(), init_future.result(), account_future.result()
        except (KeyboardInterrupt, SystemExit):
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True, cancel_futures=True)

        plan_type = str(default_account.get("plan_type") or "free")

        limits_progress = init_payload.get("limits_progress")
        limits_progress = limits_progress if isinstance(limits_progress, list) else []
        quota, restore_at, image_quota_unknown = self._extract_quota_and_restore_at(limits_progress)
        result = {
            "email": me_payload.get("email"),
            "user_id": me_payload.get("id"),
            "type": plan_type,
            "quota": quota,
            "image_quota_unknown": image_quota_unknown,
            "limits_progress": limits_progress,
            "default_model_slug": init_payload.get("default_model_slug"),
            "restore_at": restore_at,
            "status": "正常" if image_quota_unknown and plan_type.lower() != "free" else ("限流" if quota == 0 else "正常"),
        }
        logger.debug({
            "event": "backend_user_info_result",
            "email": result.get("email"),
            "user_id": result.get("user_id"),
            "type": result.get("type"),
            "quota": result.get("quota"),
            "image_quota_unknown": result.get("image_quota_unknown"),
            "default_model_slug": result.get("default_model_slug"),
            "restore_at": result.get("restore_at"),
            "status": result.get("status"),
        })
        return result

    def _bootstrap_headers(self) -> Dict[str, str]:
        """构造首页预热请求头。"""
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Sec-Ch-Ua": self.session.headers["Sec-Ch-Ua"],
            "Sec-Ch-Ua-Mobile": self.session.headers["Sec-Ch-Ua-Mobile"],
            "Sec-Ch-Ua-Platform": self.session.headers["Sec-Ch-Ua-Platform"],
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

    def _build_requirements(self, data: Dict[str, Any], source_p: str = "") -> ChatRequirements:
        """把 sentinel 响应整理成后续对话需要的 token 集合。"""
        if (data.get("arkose") or {}).get("required"):
            raise RuntimeError("chat requirements requires arkose token, which is not implemented")

        proof_token = ""
        proof_info = data.get("proofofwork") or {}
        if proof_info.get("required"):
            proof_token = build_proof_token(
                proof_info.get("seed", ""),
                proof_info.get("difficulty", ""),
                self.user_agent,
                script_sources=self.pow_script_sources,
                data_build=self.pow_data_build,
            )

        turnstile_token = ""
        turnstile_info = data.get("turnstile") or {}
        if turnstile_info.get("required") and turnstile_info.get("dx"):
            turnstile_token = solve_turnstile_token(turnstile_info["dx"], source_p) or ""

        return ChatRequirements(
            token=data.get("token", ""),
            proof_token=proof_token,
            turnstile_token=turnstile_token,
            so_token=data.get("so_token", ""),
            raw_finalize=data,
        )

    def _conversation_headers(self, path: str, requirements: ChatRequirements) -> Dict[str, str]:
        """根据当前 requirements 构造对话 SSE 请求头。"""
        headers = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "OpenAI-Sentinel-Chat-Requirements-Token": requirements.token,
        }
        if requirements.proof_token:
            headers["OpenAI-Sentinel-Proof-Token"] = requirements.proof_token
        if requirements.turnstile_token:
            headers["OpenAI-Sentinel-Turnstile-Token"] = requirements.turnstile_token
        if requirements.so_token:
            headers["OpenAI-Sentinel-SO-Token"] = requirements.so_token
        return self._headers(path, headers)

    def _api_messages_to_conversation_messages(self, messages: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        """把标准 chat messages 转成 web conversation 所需的 messages。"""
        conversation_messages = []
        for item in messages:
            role = item.get("role", "user")
            content = item.get("content", "")
            if isinstance(content, str):
                conversation_messages.append({
                    "id": new_uuid(),
                    "author": {"role": role},
                    "content": {"content_type": "text", "parts": [content]},
                })
                continue
            if not isinstance(content, list):
                raise RuntimeError("only string or list message content is supported")
            text_parts: list[str] = []
            image_inputs: list[tuple[bytes, str]] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_type = str(part.get("type") or "")
                if part_type == "text":
                    text_parts.append(str(part.get("text") or ""))
                elif part_type == "image":
                    data = part.get("data")
                    mime = str(part.get("mime") or "image/png")
                    if isinstance(data, (bytes, bytearray)):
                        image_inputs.append((bytes(data), mime))
            if not image_inputs:
                conversation_messages.append({
                    "id": new_uuid(),
                    "author": {"role": role},
                    "content": {"content_type": "text", "parts": ["".join(text_parts)]},
                })
                continue
            if not self.access_token:
                raise RuntimeError("authenticated upstream account required for image input")
            uploaded: list[Dict[str, Any]] = []
            for idx, (data, mime) in enumerate(image_inputs, start=1):
                ext_part = mime.split("/", 1)[1].split("+")[0] if "/" in mime else "png"
                extension = "jpg" if ext_part == "jpeg" else (ext_part or "png")
                b64 = base64.b64encode(data).decode("ascii")
                uploaded.append(self._upload_image(f"data:{mime};base64,{b64}", f"image_{idx}.{extension}"))
            parts: list[Any] = []
            for ref in uploaded:
                parts.append({
                    "content_type": "image_asset_pointer",
                    "asset_pointer": f"file-service://{ref['file_id']}",
                    "width": ref["width"],
                    "height": ref["height"],
                    "size_bytes": ref["file_size"],
                })
            text = "".join(text_parts)
            if text:
                parts.append(text)
            conversation_messages.append({
                "id": new_uuid(),
                "author": {"role": role},
                "content": {"content_type": "multimodal_text", "parts": parts},
                "metadata": {
                    "attachments": [{
                        "id": ref["file_id"],
                        "mimeType": ref["mime_type"],
                        "name": ref["file_name"],
                        "size": ref["file_size"],
                        "width": ref["width"],
                        "height": ref["height"],
                    } for ref in uploaded],
                },
            })
        return conversation_messages

    @staticmethod
    def _normalize_thinking_effort(value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"", "none"}:
            return ""
        if normalized in {"low", "medium", "high"}:
            return normalized
        if normalized in {"xhigh", "extended"}:
            return "extended"
        return ""

    def _conversation_payload(
            self,
            messages: list[Dict[str, Any]],
            model: str,
            timezone: str,
            thinking_effort: str = "",
    ) -> Dict[str, Any]:
        """把标准 messages 构造成 web 对话请求体。"""
        payload = {
            "action": "next",
            "messages": self._api_messages_to_conversation_messages(messages),
            "model": model,
            "parent_message_id": new_uuid(),
            "conversation_mode": {"kind": "primary_assistant"},
            "conversation_origin": None,
            "force_paragen": False,
            "force_paragen_model_slug": "",
            "force_rate_limit": False,
            "force_use_sse": True,
            "history_and_training_disabled": True,
            "reset_rate_limits": False,
            "suggestions": [],
            "supported_encodings": [],
            "system_hints": [],
            "timezone": timezone,
            "timezone_offset_min": -480,
            "variant_purpose": "comparison_implicit",
            "websocket_request_id": new_uuid(),
            "client_contextual_info": {
                "is_dark_mode": False,
                "time_since_loaded": 120,
                "page_height": 900,
                "page_width": 1400,
                "pixel_ratio": 2,
                "screen_height": 1440,
                "screen_width": 2560,
            },
        }
        normalized_effort = self._normalize_thinking_effort(thinking_effort)
        if normalized_effort:
            payload["thinking_effort"] = normalized_effort
        return payload

    def _image_model_slug(self, model: str) -> str:
        """把标准图片模型名映射到底层 model slug。"""
        _, base_model = split_image_model(model)
        if not base_model:
            return "auto"
        if base_model == "gpt-image-2":
            return "gpt-5-3"
        if base_model == CODEX_IMAGE_MODEL:
            return base_model
        return "auto"

    def _image_headers(self, path: str, requirements: ChatRequirements, conduit_token: str = "", accept: str = "*/*") -> \
            Dict[str, str]:
        """构造图片链路请求头。"""
        headers = {
            "Content-Type": "application/json",
            "Accept": accept,
            "OpenAI-Sentinel-Chat-Requirements-Token": requirements.token,
        }
        if requirements.proof_token:
            headers["OpenAI-Sentinel-Proof-Token"] = requirements.proof_token
        if conduit_token:
            headers["X-Conduit-Token"] = conduit_token
        if accept == "text/event-stream":
            headers["X-Oai-Turn-Trace-Id"] = new_uuid()
        return self._headers(path, headers)

    def _codex_responses_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _ensure_codex_source_account(self) -> None:
        account = account_service.get_account(self.access_token)
        source_type = str((account or {}).get("source_type") or "web").strip().lower()
        if source_type != "codex":
            raise RuntimeError("codex responses endpoint requires a codex source account")

    @staticmethod
    def _codex_image_input(prompt: str, images: list[str]) -> list[Dict[str, Any]]:
        content: list[Dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        for image in images:
            payload = image if image.startswith("data:image/") else f"data:image/png;base64,{image}"
            content.append({"type": "input_image", "image_url": payload})
        return [{"role": "user", "content": content}]

    @staticmethod
    def _codex_body_preview(body: Any, limit: int = 4000) -> str:
        if isinstance(body, (dict, list)):
            try:
                text = json.dumps(body, ensure_ascii=False)
            except Exception:
                text = repr(body)
        else:
            text = str(body or "")
        return text if len(text) <= limit else text[:limit] + "...[truncated]"

    @staticmethod
    def _codex_event_image_result_lengths(value: Any) -> list[int]:
        if isinstance(value, dict):
            lengths: list[int] = []
            if value.get("type") == "image_generation_call" and isinstance(value.get("result"), str):
                lengths.append(len(value["result"]))
            for item in value.values():
                lengths.extend(OpenAIBackendAPI._codex_event_image_result_lengths(item))
            return lengths
        if isinstance(value, list):
            lengths: list[int] = []
            for item in value:
                lengths.extend(OpenAIBackendAPI._codex_event_image_result_lengths(item))
            return lengths
        return []

    @staticmethod
    def _codex_event_summary(event: Dict[str, Any]) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "type": str(event.get("type") or ""),
            "keys": list(event.keys())[:30],
        }
        for key in ("id", "status", "sequence_number", "response_id", "item_id", "output_index", "content_index"):
            value = event.get(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                summary[key] = value
        for key in ("response", "item", "output"):
            value = event.get(key)
            if isinstance(value, dict):
                summary[f"{key}_type"] = value.get("type")
                summary[f"{key}_status"] = value.get("status")
                summary[f"{key}_keys"] = list(value.keys())[:30]
            elif isinstance(value, list):
                summary[f"{key}_len"] = len(value)
                summary[f"{key}_types"] = [
                    item.get("type") for item in value[:10] if isinstance(item, dict)
                ]
        error = event.get("error")
        if isinstance(error, dict):
            summary["error"] = {
                key: error.get(key)
                for key in ("type", "code", "message")
                if error.get(key) is not None
            }
        delta = event.get("delta")
        if isinstance(delta, str):
            summary["delta_len"] = len(delta)
            summary["delta_preview"] = delta[:200]
        result_lengths = OpenAIBackendAPI._codex_event_image_result_lengths(event)
        if result_lengths:
            summary["image_result_lengths"] = result_lengths[:10]
        return summary

    def _log_codex_response_failure(
            self,
            path: str,
            status_code: int,
            headers: Any,
            payload: Dict[str, Any],
            body: Any,
    ) -> None:
        request_headers = self._codex_responses_headers()
        safe_request_headers = {
            key: value for key, value in request_headers.items() if key.lower() != "authorization"
        }
        response_headers = dict(headers.items()) if hasattr(headers, "items") else dict(headers or {})
        tool = ((payload.get("tools") or [{}])[0]) if isinstance(payload.get("tools"), list) else {}
        logger.warning({
            "event": "codex_responses_http_error",
            "path": path,
            "status_code": status_code,
            "request": {
                "model": payload.get("model"),
                "tool_model": tool.get("model"),
                "tool_action": tool.get("action"),
                "size": tool.get("size"),
                "quality": tool.get("quality"),
                "image_input_count": max(len((payload.get("input") or [{}])[0].get("content") or []) - 1, 0),
                "prompt_preview": self._codex_body_preview(
                    (((payload.get("input") or [{}])[0].get("content") or [{}])[0].get("text") or ""),
                    500,
                ),
                "headers": safe_request_headers,
            },
            "response": {
                "headers": response_headers,
                "body_preview": self._codex_body_preview(body),
            },
        })

    @staticmethod
    def _iter_codex_response_events(raw: Any) -> Iterator[Dict[str, Any]]:
        content_type = str(raw.headers.get("content-type") or "").lower()
        text = raw.read().decode("utf-8", "replace")
        status_code = getattr(raw, "status", None)
        parse_errors: list[str] = []
        events: list[Dict[str, Any]] = []
        if "application/json" in content_type:
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    events.append(data)
            except Exception as exc:
                parse_errors.append(str(exc))
        else:
            lines: list[str] = []
            for line in text.splitlines() + [""]:
                if not line:
                    if lines:
                        payload_text = "\n".join(lines).strip()
                        if payload_text and payload_text != "[DONE]":
                            try:
                                data = json.loads(payload_text)
                            except Exception as exc:
                                parse_errors.append(str(exc))
                                data = None
                            if isinstance(data, dict):
                                events.append(data)
                        lines = []
                elif line.startswith("data:"):
                    lines.append(line[5:].lstrip())

        event_types: Dict[str, int] = {}
        image_result_lengths: list[int] = []
        for event in events:
            event_type = str(event.get("type") or "<missing>")
            event_types[event_type] = event_types.get(event_type, 0) + 1
            image_result_lengths.extend(OpenAIBackendAPI._codex_event_image_result_lengths(event))
        logger.info({
            "event": "codex_responses_response_debug",
            "status_code": status_code,
            "content_type": content_type,
            "response_text_len": len(text),
            "event_count": len(events),
            "event_types": event_types,
            "image_result_lengths": image_result_lengths[:10],
            "parse_error_count": len(parse_errors),
            "parse_errors": parse_errors[:5],
            "event_summaries": [OpenAIBackendAPI._codex_event_summary(event) for event in events[:30]],
            "event_previews": [
                OpenAIBackendAPI._codex_body_preview(event, 1500)
                for event in events[:10]
            ] if not image_result_lengths else [],
            "body_preview": text[:1000] if not events else "",
        })
        for event in events:
            yield event

    def iter_codex_image_response_events(
            self,
            prompt: str,
            images: list[str] | None = None,
            size: str | None = None,
            quality: str = "auto",
    ) -> Iterator[Dict[str, Any]]:
        if not self.access_token:
            raise RuntimeError("access_token is required for codex image endpoints")
        self._ensure_codex_source_account()
        path = "/backend-api/codex/responses"
        payload = {
            "model": CODEX_RESPONSES_MODEL,
            "instructions": CODEX_RESPONSES_INSTRUCTIONS,
            "store": False,
            "input": self._codex_image_input(prompt, images or []),
            "tools": [{
                "type": "image_generation",
                "model": "gpt-image-2",
                "action": "edit" if images else "generate",
                "size": str(size or "1024x1024"),
                "quality": str(quality or "auto"),
                "output_format": "png",
            }],
            "tool_choice": {"type": "image_generation"},
            "stream": True,
        }
        request = urllib.request.Request(
            self.base_url + path,
            json.dumps(payload).encode(),
            self._codex_responses_headers(),
            method="POST",
        )
        account = account_service.get_account(self.access_token) or {}
        token_payload = account_service._decode_jwt_payload(self.access_token)
        auth_claim = token_payload.get("https://api.openai.com/auth")
        auth_claim = auth_claim if isinstance(auth_claim, dict) else {}
        tool = payload["tools"][0]
        logger.info({
            "event": "codex_responses_request_debug",
            "url": self.base_url + path,
            "transport": "urllib.request",
            "timeout_secs": 1200,
            "account_email": str(account.get("email") or "").strip(),
            "source_type": str(account.get("source_type") or "").strip(),
            "account_type": str(account.get("type") or "").strip(),
            "token_claims": {
                "jti": token_payload.get("jti"),
                "iat": token_payload.get("iat"),
                "exp": token_payload.get("exp"),
                "client_id": token_payload.get("client_id"),
                "chatgpt_account_id": auth_claim.get("chatgpt_account_id"),
                "chatgpt_plan_type": auth_claim.get("chatgpt_plan_type"),
                "localhost": auth_claim.get("localhost"),
            },
            "request": {
                "model": payload.get("model"),
                "tool_model": tool.get("model"),
                "tool_action": tool.get("action"),
                "size": tool.get("size"),
                "quality": tool.get("quality"),
                "output_format": tool.get("output_format"),
                "stream": payload.get("stream"),
                "image_input_count": max(len((payload.get("input") or [{}])[0].get("content") or []) - 1, 0),
                "prompt_preview": self._codex_body_preview(
                    (((payload.get("input") or [{}])[0].get("content") or [{}])[0].get("text") or ""),
                    500,
                ),
            },
            "headers": {
                key: value for key, value in self._codex_responses_headers().items()
                if key.lower() != "authorization"
            },
        })
        try:
            with urllib.request.urlopen(request, timeout=1200) as raw:
                yield from self._iter_codex_response_events(raw)
        except urllib.error.HTTPError as error:
            body_text = error.read().decode("utf-8", "replace")
            body: Any = body_text
            try:
                body = json.loads(body_text)
            except Exception:
                pass
            self._log_codex_response_failure(path, error.code, error.headers, payload, body)
            retry_after_header = error.headers.get("Retry-After") if error.headers else None
            retry_after = int(retry_after_header) if str(retry_after_header or "").isdigit() else None
            raise UpstreamHTTPError(path, error.code, body, retry_after=retry_after) from error

    def _prepare_image_conversation(self, prompt: str, requirements: ChatRequirements, model: str) -> str:
        """为图片生成准备 conduit token。"""
        path = "/backend-api/f/conversation/prepare"
        payload = {
            "action": "next",
            "fork_from_shared_post": False,
            "parent_message_id": new_uuid(),
            "model": self._image_model_slug(model),
            "client_prepare_state": "success",
            "timezone_offset_min": -480,
            "timezone": "Asia/Shanghai",
            "conversation_mode": {"kind": "primary_assistant"},
            "system_hints": ["picture_v2"],
            "partial_query": {
                "id": new_uuid(),
                "author": {"role": "user"},
                "content": {"content_type": "text", "parts": [prompt]},
            },
            "supports_buffering": True,
            "supported_encodings": ["v1"],
            "client_contextual_info": {"app_name": "chatgpt.com"},
        }
        response = self.session.post(
            self.base_url + path,
            headers=self._image_headers(path, requirements),
            json=payload,
            timeout=60,
        )
        ensure_ok(response, path)
        return response.json().get("conduit_token", "")

    def _decode_image_base64(self, image: str) -> bytes:
        """把 base64 图片字符串或本地路径解码成二进制。"""
        if (
                image
                and len(image) < 512
                and not image.startswith("data:")
                and "\n" not in image
                and "\r" not in image
        ):
            file_path = Path(os.path.expanduser(image))
            if file_path.exists() and file_path.is_file():
                return file_path.read_bytes()
        payload = image.split(",", 1)[1] if image.startswith("data:") and "," in image else image
        return base64.b64decode(payload)

    def _upload_image(self, image: str, file_name: str = "image.png") -> Dict[str, Any]:
        """上传一张 base64 图片，返回底层文件元数据。"""
        data = self._decode_image_base64(image)
        if (
                image
                and len(image) < 512
                and not image.startswith("data:")
                and "\n" not in image
                and "\r" not in image
        ):
            candidate_path = Path(os.path.expanduser(image))
            if candidate_path.exists() and candidate_path.is_file():
                file_name = candidate_path.name
        image = Image.open(BytesIO(data))
        width, height = image.size
        mime_type = Image.MIME.get(image.format, "image/png")
        path = "/backend-api/files"
        response = self.session.post(
            self.base_url + path,
            headers=self._headers(path, {"Content-Type": "application/json", "Accept": "application/json"}),
            json={"file_name": file_name, "file_size": len(data), "use_case": "multimodal", "width": width,
                  "height": height},
            timeout=60,
        )
        ensure_ok(response, path)
        upload_meta = response.json()
        response = self.session.put(
            upload_meta["upload_url"],
            headers={
                "Content-Type": mime_type,
                "x-ms-blob-type": "BlockBlob",
                "x-ms-version": "2020-04-08",
                "Origin": self.base_url,
                "Referer": self.base_url + "/",
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.8",
            },
            data=data,
            timeout=120,
        )
        ensure_ok(response, "image_upload")
        path = f"/backend-api/files/{upload_meta['file_id']}/uploaded"
        response = self.session.post(
            self.base_url + path,
            headers=self._headers(path, {"Content-Type": "application/json", "Accept": "application/json"}),
            data="{}",
            timeout=60,
        )
        ensure_ok(response, path)
        return {
            "file_id": upload_meta["file_id"],
            "file_name": file_name,
            "file_size": len(data),
            "mime_type": mime_type,
            "width": width,
            "height": height,
        }

    def _start_image_generation(self, prompt: str, requirements: ChatRequirements, conduit_token: str, model: str,
                                references: Optional[list[Dict[str, Any]]] = None) -> requests.Response:
        """启动图片生成或编辑的 SSE 请求。"""
        references = references or []
        parts = [{
            "content_type": "image_asset_pointer",
            "asset_pointer": f"file-service://{item['file_id']}",
            "width": item["width"],
            "height": item["height"],
            "size_bytes": item["file_size"],
        } for item in references]
        parts.append(prompt)
        content = {"content_type": "multimodal_text", "parts": parts} if references else {"content_type": "text",
                                                                                          "parts": [prompt]}
        metadata = {
            "developer_mode_connector_ids": [],
            "selected_github_repos": [],
            "selected_all_github_repos": False,
            "system_hints": ["picture_v2"],
            "serialization_metadata": {"custom_symbol_offsets": []},
        }
        if references:
            metadata["attachments"] = [{
                "id": item["file_id"],
                "mimeType": item["mime_type"],
                "name": item["file_name"],
                "size": item["file_size"],
                "width": item["width"],
                "height": item["height"],
            } for item in references]
        payload = {
            "action": "next",
            "messages": [{
                "id": new_uuid(),
                "author": {"role": "user"},
                "create_time": time.time(),
                "content": content,
                "metadata": metadata,
            }],
            "parent_message_id": new_uuid(),
            "model": self._image_model_slug(model),
            "client_prepare_state": "sent",
            "timezone_offset_min": -480,
            "timezone": "Asia/Shanghai",
            "conversation_mode": {"kind": "primary_assistant"},
            "enable_message_followups": True,
            "system_hints": ["picture_v2"],
            "supports_buffering": True,
            "supported_encodings": ["v1"],
            "client_contextual_info": {
                "is_dark_mode": False,
                "time_since_loaded": 1200,
                "page_height": 1072,
                "page_width": 1724,
                "pixel_ratio": 1.2,
                "screen_height": 1440,
                "screen_width": 2560,
                "app_name": "chatgpt.com",
            },
            "paragen_cot_summary_display_override": "allow",
            "force_parallel_switch": "auto",
        }
        path = "/backend-api/f/conversation"
        response = self.session.post(
            self.base_url + path,
            headers=self._image_headers(path, requirements, conduit_token, "text/event-stream"),
            json=payload,
            timeout=300,
            stream=True,
        )
        ensure_ok(response, path)
        return response

    def _get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """获取完整 conversation 详情。"""
        path = f"/backend-api/conversation/{conversation_id}"
        response = self.session.get(self.base_url + path, headers=self._headers(path, {"Accept": "application/json"}),
                                    timeout=60)
        ensure_ok(response, path)
        return response.json()

    def delete_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """删除本地对话记录。"""
        path = f"/backend-api/conversation/{conversation_id}"
        headers = self._headers(path, {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Referer": f"{self.base_url}/c/{conversation_id}",
            "X-OpenAI-Target-Route": "/backend-api/conversation/{conversation_id}",
        })
        response = self.session.patch(
            self.base_url + path,
            headers=headers,
            json={"is_visible": False},
            timeout=60,
        )
        ensure_ok(response, path)
        return response.json()

    def _list_recent_conversations(self, limit: int = 5, timeout_secs: float = 10.0) -> list[Dict[str, Any]]:
        """列出最近的对话列表，按更新时间倒序。

        当 SSE 流太短导致 conversation_id 丢失时，可以通过此方法
        查找最近创建的对话来恢复 conversation_id。
        """
        path = f"/backend-api/conversations?offset=0&limit={limit}&order=updated&conversation_filter=all"
        try:
            response = self.session.get(
                self.base_url + path,
                headers=self._headers(path, {"Accept": "application/json"}),
                timeout=timeout_secs,
            )
            ensure_ok(response, path)
            data = response.json()
            return data.get("items") or data.get("conversations") or []
        except Exception as exc:
            logger.debug({"event": "list_conversations_failed", "error": str(exc)})
            return []

    def find_conversation_by_prompt(self, prompt: str, started_at: float, timeout_secs: float = 10.0) -> str:
        """根据 prompt 和开始时间，从最近对话列表中查找匹配的 conversation_id。

        当 SSE 流太短导致 conversation_id 丢失时，使用此方法恢复。
        通过对比 prompt 关键词和时间戳来匹配最可能的对话。

        参数：
            prompt: 用户输入的 prompt 文本
            started_at: 请求开始的时间戳（epoch seconds）
            timeout_secs: 请求超时秒数

        返回：
            匹配的 conversation_id，如果未找到返回空字符串
        """
        items = self._list_recent_conversations(limit=10, timeout_secs=timeout_secs)
        if not items:
            return ""
        # 筛选在 started_at 之前或附近创建的对话（最多往前 5 分钟）
        # ChatGPT 的 updated_at 通常晚于实际请求时间
        prompt_lower = str(prompt or "").lower().strip()
        best_match = ""
        best_score = 0.0
        for item in items:
            # item 可能是完整的 conversation 对象或摘要
            conv_id = str(item.get("id") or item.get("conversation_id") or "")
            if not conv_id:
                continue
            # 检查时间范围：对话的 updated_at 应该在请求开始时间之后（或附近）
            updated_at = float(item.get("update_time") or item.get("updated_at") or 0)
            if updated_at and started_at and (updated_at < started_at - 30 or updated_at > started_at + 600):
                continue
            # 匹配 prompt 关键词
            title = str(item.get("title") or "").lower()
            # 计算匹配分数
            score = 0.0
            if prompt_lower and title:
                # 简单的关键词匹配
                prompt_words = set(prompt_lower.split())
                title_words = set(title.split())
                common = prompt_words & title_words
                if common:
                    score = len(common) / max(len(prompt_words), 1)
            # 图生图通常标题为 "Image" 开头
            if title.startswith("image"):
                score += 0.3
            if score > best_score:
                best_score = score
                best_match = conv_id
        if best_match and best_score > 0.1:
            logger.info({
                "event": "conversation_prompt_match_found",
                "conversation_id": best_match,
                "match_score": round(best_score, 2),
            })
            return best_match
        # 如果没有标题匹配，返回最新的对话（时间最近的）
        for item in items:
            conv_id = str(item.get("id") or item.get("conversation_id") or "")
            updated_at = float(item.get("update_time") or item.get("updated_at") or 0)
            if conv_id and updated_at and started_at and updated_at >= started_at - 30:
                logger.info({
                    "event": "conversation_latest_match",
                    "conversation_id": conv_id,
                    "updated_at": updated_at,
                })
                return conv_id
        return ""

    @staticmethod
    def _editable_prompt(fixed_prompt: str, user_prompt_text: str) -> str:
        extra = str(user_prompt_text or "").strip()
        return fixed_prompt if not extra else fixed_prompt + "\n\n以下是用户补充需求，请直接结合执行：\n" + extra

    def export_ppt_zip(
            self,
            base64_images: list[str] | None,
            prompt: str,
            output_dir: str | Path = EDITABLE_FILE_PPT_OUTPUT_DIR,
            timeout_secs: float = EDITABLE_FILE_TIMEOUT_SECS,
            poll_interval_secs: float = EDITABLE_FILE_POLL_INTERVAL_SECS,
    ) -> EditableFileExportResult:
        return self._export_editable_file_zip(
            base64_images or [],
            self._editable_prompt(EDITABLE_FILE_PPT_PROMPT, prompt),
            output_dir,
            primary_label="ppt",
            primary_suffixes=(".ppt", ".pptx"),
            primary_mime_types=EDITABLE_PPT_MIME_TYPES,
            primary_mime_keywords=("presentationml.presentation", "ms-powerpoint"),
            primary_default_extension=".pptx",
            export_file_re=EDITABLE_PPT_EXPORT_FILE_RE,
            timeout_secs=timeout_secs,
            poll_interval_secs=poll_interval_secs,
        )

    def export_psd_zip(
            self,
            base64_images: list[str],
            prompt: str,
            output_dir: str | Path = EDITABLE_FILE_PSD_OUTPUT_DIR,
            timeout_secs: float = EDITABLE_FILE_TIMEOUT_SECS,
            poll_interval_secs: float = EDITABLE_FILE_POLL_INTERVAL_SECS,
    ) -> EditableFileExportResult:
        if not base64_images:
            raise ValueError("base64_images is empty")
        return self._export_editable_file_zip(
            base64_images,
            self._editable_prompt(EDITABLE_FILE_PSD_PROMPT, prompt),
            output_dir,
            primary_label="psd",
            primary_suffixes=(".psd",),
            primary_mime_types=EDITABLE_PSD_MIME_TYPES,
            primary_mime_keywords=("photoshop",),
            primary_default_extension=".psd",
            export_file_re=EDITABLE_PSD_EXPORT_FILE_RE,
            timeout_secs=timeout_secs,
            poll_interval_secs=poll_interval_secs,
        )

    def _export_editable_file_zip(
            self,
            base64_images: list[str],
            prompt: str,
            output_dir: str | Path,
            *,
            primary_label: str,
            primary_suffixes: tuple[str, ...],
            primary_mime_types: set[str],
            primary_mime_keywords: tuple[str, ...],
            primary_default_extension: str,
            export_file_re: re.Pattern[str],
            timeout_secs: float,
            poll_interval_secs: float,
    ) -> EditableFileExportResult:
        if not self.access_token:
            raise RuntimeError("access_token is required for editable file export")
        self.client_version = EDITABLE_FILE_CLIENT_VERSION
        self.client_build_number = EDITABLE_FILE_CLIENT_BUILD_NUMBER
        self.session.headers["OAI-Client-Version"] = EDITABLE_FILE_CLIENT_VERSION
        self.session.headers["OAI-Client-Build-Number"] = EDITABLE_FILE_CLIENT_BUILD_NUMBER
        output_path = Path(output_dir).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        uploaded = [self._upload_editable_base64_image(item, index) for index, item in enumerate(base64_images, start=1)]
        conduit_token = self._prepare_editable_conversation(prompt, [item["mime_type"] for item in uploaded])
        conversation_id = self._run_editable_conversation(prompt, uploaded, conduit_token)
        artifacts = self._wait_editable_output_artifacts(
            conversation_id,
            primary_label,
            primary_suffixes,
            primary_mime_types,
            primary_mime_keywords,
            export_file_re,
            timeout_secs,
            poll_interval_secs,
        )
        downloaded = [self._download_editable_artifact(
            conversation_id,
            item,
            output_path,
            primary_mime_types,
            primary_mime_keywords,
            primary_default_extension,
        ) for item in artifacts]
        primary_path = next((item for item in downloaded if item.suffix.lower() in primary_suffixes), None)
        zip_path = next((item for item in downloaded if item.suffix.lower() == ".zip"), None)
        if not primary_path or not zip_path:
            raise RuntimeError(f"download finished but did not get both {primary_label} and zip files: {downloaded}")
        return EditableFileExportResult(conversation_id=conversation_id, primary_path=primary_path, zip_path=zip_path)

    def _upload_editable_base64_image(self, base64_image: str, index: int) -> Dict[str, Any]:
        data, file_name, mime_type, width, height = self._decode_editable_base64_image(base64_image, index)
        path = "/backend-api/files"
        response = self.session.post(
            self.base_url + path,
            headers=self._headers(path, {"Accept": "*/*", "Content-Type": "application/json"}),
            json={
                "file_name": file_name,
                "file_size": len(data),
                "use_case": "multimodal",
                "timezone_offset_min": -480,
                "reset_rate_limits": False,
                "store_in_library": True,
                "library_persistence_mode": "opportunistic",
            },
            timeout=60,
        )
        ensure_ok(response, path)
        payload = response.json()
        upload_url = str(payload.get("upload_url") or "")
        file_id = str(payload.get("file_id") or "")
        if not upload_url or not file_id:
            raise RuntimeError(f"invalid upload response: {payload}")
        response = self.session.put(
            upload_url,
            headers={
                "Content-Type": mime_type,
                "x-ms-blob-type": "BlockBlob",
                "x-ms-version": "2020-04-08",
                "Origin": self.base_url,
                "Referer": self.base_url + "/",
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.8",
            },
            data=data,
            timeout=120,
        )
        ensure_ok(response, "image_upload")
        path = f"/backend-api/files/{file_id}/uploaded"
        response = self.session.post(
            self.base_url + path,
            headers=self._headers(path, {"Accept": "*/*", "Content-Type": "application/json"}),
            data="{}",
            timeout=60,
        )
        ensure_ok(response, path)
        return {
            "file_id": file_id,
            "library_file_id": str(payload.get("library_file_id") or ""),
            "file_name": file_name,
            "file_size": len(data),
            "mime_type": mime_type,
            "width": width,
            "height": height,
        }

    def _decode_editable_base64_image(self, base64_image: str, index: int) -> tuple[bytes, str, str, int, int]:
        raw = str(base64_image or "").strip()
        if not raw:
            raise ValueError("base64 image is empty")
        mime_type = ""
        payload = raw
        match = re.match(r"^data:([^;]+);base64,(.*)$", raw, re.IGNORECASE | re.DOTALL)
        if match:
            mime_type = str(match.group(1) or "").strip().lower()
            payload = str(match.group(2) or "").strip()
        data = base64.b64decode(payload)
        image = Image.open(BytesIO(data))
        image.load()
        width, height = image.size
        mime_type = Image.MIME.get(image.format, mime_type or "image/png")
        extension = mimetypes.guess_extension(mime_type) or ".png"
        return data, f"image_{index}{extension}", mime_type, width, height

    def _prepare_editable_conversation(self, prompt: str, attachment_mime_types: list[str]) -> str:
        path = "/backend-api/f/conversation/prepare"
        payload: Dict[str, Any] = {
            "action": "next",
            "fork_from_shared_post": False,
            "parent_message_id": "client-created-root",
            "model": EDITABLE_FILE_MODEL,
            "client_prepare_state": "success",
            "timezone_offset_min": -480,
            "timezone": "Asia/Shanghai",
            "conversation_mode": {"kind": "primary_assistant"},
            "system_hints": [],
            "partial_query": {"id": new_uuid(), "author": {"role": "user"}, "content": {"content_type": "text", "parts": [prompt]}},
            "supports_buffering": True,
            "supported_encodings": ["v1"],
            "client_contextual_info": {"app_name": "chatgpt.com"},
            "thinking_effort": EDITABLE_FILE_THINKING_EFFORT,
        }
        if attachment_mime_types:
            payload["attachment_mime_types"] = attachment_mime_types
        response = self.session.post(
            self.base_url + path,
            headers=self._headers(path, {"Accept": "*/*", "Content-Type": "application/json", "X-Conduit-Token": "no-token"}),
            json=payload,
            timeout=60,
        )
        ensure_ok(response, path)
        conduit_token = str(response.json().get("conduit_token") or "")
        if not conduit_token:
            raise RuntimeError(f"missing conduit_token: {response.text}")
        return conduit_token

    def _run_editable_conversation(self, prompt: str, uploaded: list[Dict[str, Any]], conduit_token: str) -> str:
        self._bootstrap()
        requirements = self._get_chat_requirements()
        message: Dict[str, Any] = {"id": new_uuid(), "author": {"role": "user"}, "create_time": time.time()}
        if uploaded:
            parts = [{
                "content_type": "image_asset_pointer",
                "asset_pointer": f"sediment://{item['file_id']}",
                "size_bytes": item["file_size"],
                "width": item["width"],
                "height": item["height"],
            } for item in uploaded]
            parts.append(prompt)
            message["content"] = {"content_type": "multimodal_text", "parts": parts}
            message["metadata"] = {
                "attachments": [{
                    "id": item["file_id"],
                    "size": item["file_size"],
                    "name": item["file_name"],
                    "mime_type": item["mime_type"],
                    "width": item["width"],
                    "height": item["height"],
                    "source": "library",
                    "library_file_id": item["library_file_id"],
                    "is_big_paste": False,
                } for item in uploaded],
                "developer_mode_connector_ids": [],
                "selected_sources": [],
                "selected_github_repos": [],
                "selected_all_github_repos": False,
                "serialization_metadata": {"custom_symbol_offsets": []},
            }
        else:
            message["content"] = {"content_type": "text", "parts": [prompt]}
        path = "/backend-api/f/conversation"
        response = self.session.post(
            self.base_url + path,
            headers=self._image_headers(path, requirements, conduit_token, "text/event-stream"),
            json={
                "action": "next",
                "messages": [message],
                "parent_message_id": "client-created-root",
                "model": EDITABLE_FILE_MODEL,
                "client_prepare_state": "sent",
                "timezone_offset_min": -480,
                "timezone": "Asia/Shanghai",
                "conversation_mode": {"kind": "primary_assistant"},
                "enable_message_followups": True,
                "system_hints": [],
                "supports_buffering": True,
                "supported_encodings": ["v1"],
                "client_contextual_info": {
                    "is_dark_mode": False,
                    "time_since_loaded": 401,
                    "page_height": 1138,
                    "page_width": 803,
                    "pixel_ratio": 2,
                    "screen_height": 1440,
                    "screen_width": 2560,
                    "app_name": "chatgpt.com",
                },
                "paragen_cot_summary_display_override": "allow",
                "force_parallel_switch": "auto",
                "thinking_effort": EDITABLE_FILE_THINKING_EFFORT,
            },
            timeout=300,
            stream=True,
        )
        ensure_ok(response, path)
        conversation_id = ""
        try:
            for payload in iter_sse_payloads(response):
                if payload == "[DONE]":
                    break
                conversation_id = conversation_id or self._find_editable_value(payload, "conversation_id")
        finally:
            response.close()
        if not conversation_id:
            raise RuntimeError("conversation_id not found in stream")
        return conversation_id

    def _wait_editable_output_artifacts(
            self,
            conversation_id: str,
            primary_label: str,
            primary_suffixes: tuple[str, ...],
            primary_mime_types: set[str],
            primary_mime_keywords: tuple[str, ...],
            export_file_re: re.Pattern[str],
            timeout_secs: float,
            poll_interval_secs: float,
    ) -> list[EditableFileArtifact]:
        deadline = time.time() + timeout_secs
        while time.time() < deadline:
            try:
                conversation = self._get_editable_conversation_detail(conversation_id)
            except UpstreamHTTPError as exc:
                if exc.status_code in {404, 409, 423, 429, 500, 502, 503, 504}:
                    time.sleep(poll_interval_secs)
                    continue
                raise
            targeted = self._pick_editable_target_artifacts(
                self._extract_editable_artifacts(conversation, export_file_re),
                primary_suffixes,
                primary_mime_types,
                primary_mime_keywords,
            )
            if targeted:
                return targeted
            time.sleep(poll_interval_secs)
        raise RuntimeError(f"timed out waiting for {primary_label}/zip outputs")

    def _get_editable_conversation_detail(self, conversation_id: str) -> Dict[str, Any]:
        path = f"/backend-api/conversation/{conversation_id}"
        response = self.session.get(self.base_url + path, headers=self._editable_conversation_document_headers(path, conversation_id), timeout=60)
        ensure_ok(response, path)
        return response.json()

    def _editable_browser_headers(self, path: str, conversation_id: str) -> Dict[str, str]:
        headers = self._headers(path, {"Accept": "*/*"})
        headers["Referer"] = f"{self.base_url}/c/{conversation_id}"
        return headers

    def _editable_conversation_document_headers(self, path: str, conversation_id: str) -> Dict[str, str]:
        headers = self._editable_browser_headers(path, conversation_id)
        headers["X-OpenAI-Target-Route"] = "/backend-api/conversation/{conversation_id}"
        return headers

    def _extract_editable_artifacts(self, conversation: Dict[str, Any], export_file_re: re.Pattern[str]) -> list[EditableFileArtifact]:
        artifacts: dict[str, EditableFileArtifact] = {}
        for node in sorted((conversation.get("mapping") or {}).values(), key=lambda item: float(((item or {}).get("message") or {}).get("create_time") or 0.0)):
            message = (node or {}).get("message") or {}
            message_id = str(message.get("id") or "")
            author_role = str(((message.get("author") or {}).get("role") or "")).strip()
            if author_role not in {"assistant", "tool"}:
                continue
            create_time = float(message.get("create_time") or 0.0)
            message_text = self._editable_message_text(message)
            for artifact in self._extract_editable_message_artifacts(message, message_id, author_role, create_time, export_file_re):
                key = artifact.attachment_id or artifact.file_id or artifact.name or artifact.sandbox_path
                if key:
                    artifacts[key] = self._merge_editable_artifact(artifacts.get(key), artifact)
            for export_path in self._extract_editable_export_paths(message_text, export_file_re):
                inferred = EditableFileArtifact(name=Path(export_path).name, create_time=create_time, author_role=author_role, sandbox_path=export_path, message_id=message_id)
                artifacts[export_path] = self._merge_editable_artifact(artifacts.get(export_path), inferred)
        return sorted(artifacts.values(), key=lambda item: item.create_time)

    def _extract_editable_message_artifacts(
            self,
            message: Dict[str, Any],
            message_id: str,
            author_role: str,
            create_time: float,
            export_file_re: re.Pattern[str],
    ) -> list[EditableFileArtifact]:
        artifacts: list[EditableFileArtifact] = []
        for item in (message.get("metadata") or {}).get("attachments") or []:
            artifact = self._editable_artifact_from_dict(item, message_id, author_role, create_time, export_file_re)
            if artifact:
                artifacts.append(artifact)
        for obj in self._walk_search_dicts(message):
            artifact = self._editable_artifact_from_dict(obj, message_id, author_role, create_time, export_file_re)
            if artifact:
                artifacts.append(artifact)
        return artifacts

    def _editable_artifact_from_dict(
            self,
            payload: Dict[str, Any],
            message_id: str,
            author_role: str,
            create_time: float,
            export_file_re: re.Pattern[str],
    ) -> EditableFileArtifact | None:
        if not ({"id", "file_id", "asset_pointer", "name", "file_name", "filename", "mime_type", "mimeType"} & set(payload.keys())):
            return None
        attachment_id = self._match_editable_file_id(str(payload.get("id") or ""))
        file_id = self._match_editable_file_id(str(payload.get("file_id") or ""))
        name = self._sanitize_editable_filename(str(payload.get("name") or payload.get("file_name") or payload.get("filename") or payload.get("title") or "").strip())
        mime_type = self._clean_editable_mime_type(payload.get("mime_type") or payload.get("mimeType") or "")
        for asset_id in EDITABLE_ASSET_POINTER_RE.findall(str(payload.get("asset_pointer") or "")):
            attachment_id = attachment_id or asset_id
            file_id = file_id or asset_id
        if not attachment_id or not file_id:
            ids = self._extract_editable_file_ids(json.dumps(payload, ensure_ascii=False))
            attachment_id = attachment_id or (ids[0] if ids else "")
            file_id = file_id or (ids[0] if ids else "")
        if not attachment_id and not file_id:
            return None
        return EditableFileArtifact(
            attachment_id=attachment_id,
            file_id=file_id,
            name=name,
            mime_type=mime_type,
            create_time=create_time,
            author_role=author_role,
            sandbox_path=(self._extract_editable_export_paths(payload, export_file_re) or [""])[0],
            message_id=message_id,
        )

    def _pick_editable_target_artifacts(
            self,
            artifacts: list[EditableFileArtifact],
            primary_suffixes: tuple[str, ...],
            primary_mime_types: set[str],
            primary_mime_keywords: tuple[str, ...],
    ) -> list[EditableFileArtifact]:
        primary = next((item for item in reversed(artifacts) if self._looks_like_editable_primary(item, primary_suffixes, primary_mime_types, primary_mime_keywords)), None)
        zip_item = next((item for item in reversed(artifacts) if self._looks_like_editable_zip(item)), None)
        return [primary, zip_item] if primary and zip_item else []

    def _download_editable_artifact(
            self,
            conversation_id: str,
            artifact: EditableFileArtifact,
            output_dir: Path,
            primary_mime_types: set[str],
            primary_mime_keywords: tuple[str, ...],
            primary_default_extension: str,
    ) -> Path:
        download_url = self._resolve_editable_download_url(conversation_id, artifact)
        if not download_url:
            raise RuntimeError(f"download url not found for artifact: {artifact}")
        response = self.session.get(download_url, timeout=300)
        ensure_ok(response, "artifact_download")
        content_type = self._clean_editable_mime_type(response.headers.get("Content-Type") or artifact.mime_type)
        file_name = self._resolve_editable_output_name(artifact, response.url, response.headers.get("Content-Disposition"), content_type, primary_mime_types, primary_mime_keywords, primary_default_extension)
        target_path = self._unique_editable_path(output_dir / file_name)
        target_path.write_bytes(response.content)
        return target_path

    def _resolve_editable_download_url(self, conversation_id: str, artifact: EditableFileArtifact) -> str:
        ids: list[str] = []
        for item in (artifact.attachment_id, artifact.file_id):
            if item and item not in ids:
                ids.append(item)
        if artifact.sandbox_path and artifact.message_id:
            path = f"/backend-api/conversation/{conversation_id}/interpreter/download"
            response = self.session.get(
                self.base_url + path,
                headers=self._editable_download_headers(path, conversation_id, "/backend-api/conversation/{conversation_id}/interpreter/download"),
                params={"message_id": artifact.message_id, "sandbox_path": artifact.sandbox_path},
                timeout=60,
            )
            if 200 <= response.status_code < 300:
                url = self._download_url_from_response(response)
                if url:
                    return url
        for attachment_id in ids:
            path = f"/backend-api/conversation/{conversation_id}/attachment/{attachment_id}/download"
            response = self.session.get(
                self.base_url + path,
                headers=self._editable_download_headers(path, conversation_id, "/backend-api/conversation/{conversation_id}/attachment/{attachment_id}/download"),
                timeout=60,
            )
            if 200 <= response.status_code < 300:
                url = self._download_url_from_response(response)
                if url:
                    return url
        for file_id in ids:
            path = f"/backend-api/files/download/{file_id}"
            response = self.session.get(
                self.base_url + path,
                headers=self._editable_download_headers(path, conversation_id, "/backend-api/files/download/{file_id}"),
                params={"post_id": "", "inline": "false"},
                timeout=60,
            )
            if 200 <= response.status_code < 300:
                url = self._download_url_from_response(response)
                if url:
                    return url
        for file_id in ids:
            path = f"/backend-api/files/{file_id}/download"
            response = self.session.get(
                self.base_url + path,
                headers=self._editable_download_headers(path, conversation_id, "/backend-api/files/download/{file_id}"),
                timeout=60,
            )
            if 200 <= response.status_code < 300:
                url = self._download_url_from_response(response)
                if url:
                    return url
        return ""

    def _editable_download_headers(self, path: str, conversation_id: str, route: str) -> Dict[str, str]:
        headers = self._editable_browser_headers(path, conversation_id)
        headers["X-OpenAI-Target-Route"] = route
        return headers

    @staticmethod
    def _download_url_from_response(response: Any) -> str:
        try:
            payload = response.json()
        except Exception:
            payload = {}
        return str(payload.get("download_url") or payload.get("url") or "")

    def _resolve_editable_output_name(
            self,
            artifact: EditableFileArtifact,
            final_url: str,
            content_disposition: str | None,
            content_type: str,
            primary_mime_types: set[str],
            primary_mime_keywords: tuple[str, ...],
            primary_default_extension: str,
    ) -> str:
        file_name = self._sanitize_editable_filename(artifact.name)
        if not file_name and artifact.sandbox_path:
            file_name = self._sanitize_editable_filename(Path(artifact.sandbox_path).name)
        if not file_name:
            file_name = self._sanitize_editable_filename(self._editable_filename_from_content_disposition(content_disposition or ""))
        if not file_name:
            file_name = self._sanitize_editable_filename(Path(urlparse(final_url).path).name)
        extension = self._editable_extension_from_mime_type(content_type, primary_mime_types, primary_mime_keywords, primary_default_extension)
        return f"artifact{extension}" if not file_name else (file_name if Path(file_name).suffix else file_name + extension)

    def _find_editable_value(self, payload: Any, key: str) -> str:
        if isinstance(payload, str):
            match = SEARCH_CONVERSATION_ID_RE.search(payload) if key == "conversation_id" else None
            if match:
                return match.group(1)
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return ""
        if isinstance(payload, dict):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
            return next((found for item in payload.values() if (found := self._find_editable_value(item, key))), "")
        if isinstance(payload, list):
            return next((found for item in payload if (found := self._find_editable_value(item, key))), "")
        return ""

    def _extract_editable_file_ids(self, text: str) -> list[str]:
        values: list[str] = []
        for item in EDITABLE_ASSET_POINTER_RE.findall(text):
            if item not in values:
                values.append(item)
        for item in FILE_ID_RE.findall(text):
            if item not in values:
                values.append(item)
        return values

    @staticmethod
    def _match_editable_file_id(value: str) -> str:
        match = FILE_ID_RE.search(value)
        return match.group(1) if match else ""

    @staticmethod
    def _clean_editable_mime_type(value: Any) -> str:
        text = str(value or "").strip().lower()
        return text.split(";", 1)[0] if "/" in text else ""

    def _looks_like_editable_primary(
            self,
            artifact: EditableFileArtifact,
            primary_suffixes: tuple[str, ...],
            primary_mime_types: set[str],
            primary_mime_keywords: tuple[str, ...],
    ) -> bool:
        path, name, mime = artifact.sandbox_path.lower(), artifact.name.lower(), artifact.mime_type
        return name.endswith(primary_suffixes) or path.endswith(primary_suffixes) or mime in primary_mime_types or any(keyword in mime for keyword in primary_mime_keywords)

    @staticmethod
    def _looks_like_editable_zip(artifact: EditableFileArtifact) -> bool:
        path, name, mime = artifact.sandbox_path.lower(), artifact.name.lower(), artifact.mime_type
        return name.endswith(".zip") or path.endswith(".zip") or mime in EDITABLE_ZIP_MIME_TYPES or mime.endswith("/zip")

    @staticmethod
    def _editable_extension_from_mime_type(
            mime_type: str,
            primary_mime_types: set[str],
            primary_mime_keywords: tuple[str, ...],
            primary_default_extension: str,
    ) -> str:
        if mime_type in primary_mime_types or any(keyword in mime_type for keyword in primary_mime_keywords):
            return primary_default_extension
        if mime_type in EDITABLE_ZIP_MIME_TYPES or mime_type.endswith("/zip"):
            return ".zip"
        return mimetypes.guess_extension(mime_type) or ""

    @staticmethod
    def _editable_filename_from_content_disposition(content_disposition: str) -> str:
        extended_match = re.search(r"filename\*=UTF-8''([^;]+)", content_disposition, re.IGNORECASE)
        if extended_match:
            return unquote(extended_match.group(1)).strip()
        plain_match = re.search(r'filename="([^"]+)"', content_disposition, re.IGNORECASE)
        return plain_match.group(1).strip() if plain_match else ""

    @staticmethod
    def _sanitize_editable_filename(value: str) -> str:
        return Path(str(value or "").strip()).name.replace("\x00", "").strip()

    @staticmethod
    def _unique_editable_path(path: Path) -> Path:
        if not path.exists():
            return path
        for index in range(1, 1000):
            candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"failed to allocate output path for {path}")

    @staticmethod
    def _merge_editable_artifact(current: EditableFileArtifact | None, latest: EditableFileArtifact) -> EditableFileArtifact:
        if current is None:
            return latest
        return EditableFileArtifact(
            attachment_id=latest.attachment_id or current.attachment_id,
            file_id=latest.file_id or current.file_id,
            name=latest.name or current.name,
            mime_type=latest.mime_type or current.mime_type,
            create_time=max(current.create_time, latest.create_time),
            author_role=latest.author_role or current.author_role,
            sandbox_path=latest.sandbox_path or current.sandbox_path,
            message_id=latest.message_id or current.message_id,
        )

    @staticmethod
    def _editable_message_text(message: Any) -> str:
        if not isinstance(message, dict):
            return ""
        content = message.get("content") or {}
        parts: list[str] = []
        if isinstance(content, dict):
            if isinstance(content.get("text"), str):
                parts.append(content["text"])
            for part in content.get("parts") or []:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    parts.extend(str(part.get(key) or "") for key in ("text", "asset_pointer", "model_set_context") if part.get(key))
        if isinstance(message.get("content"), str):
            parts.append(str(message["content"]))
        return "\n".join(part for part in parts if part).strip()

    @staticmethod
    def _extract_editable_export_paths(payload: Any, export_file_re: re.Pattern[str]) -> list[str]:
        if isinstance(payload, str):
            text = payload
        else:
            try:
                text = json.dumps(payload, ensure_ascii=False)
            except Exception:
                text = str(payload)
        values: list[str] = []
        for item in export_file_re.findall(text):
            path = str(item or "").strip()
            if path and path not in values:
                values.append(path)
        return values

    def search(self, prompt: str, model: str = SEARCH_MODEL, timeout_secs: float = SEARCH_TIMEOUT_SECS,
               poll_interval_secs: float = SEARCH_POLL_INTERVAL_SECS) -> Dict[str, Any]:
        if not self.access_token:
            raise RuntimeError("access_token is required for search")
        conduit_token = self._prepare_search_conversation(prompt, model)
        self._bootstrap()
        conversation_id = self._run_search_conversation(prompt, conduit_token, model)
        return self._wait_search_result(conversation_id, timeout_secs, poll_interval_secs)

    def _prepare_search_conversation(self, prompt: str, model: str) -> str:
        path = "/backend-api/f/conversation/prepare"
        response = self.session.post(
            self.base_url + path,
            headers=self._headers(path, {"Accept": "*/*", "Content-Type": "application/json", "X-Conduit-Token": "no-token"}),
            json={
                "action": "next",
                "fork_from_shared_post": False,
                "parent_message_id": "client-created-root",
                "model": model,
                "client_prepare_state": "success",
                "timezone_offset_min": -480,
                "timezone": "Asia/Shanghai",
                "conversation_mode": {"kind": "primary_assistant"},
                "system_hints": ["search"],
                "partial_query": {"id": new_uuid(), "author": {"role": "user"}, "content": {"content_type": "text", "parts": [prompt]}},
                "supports_buffering": True,
                "supported_encodings": ["v1"],
                "client_contextual_info": {"app_name": "chatgpt.com"},
            },
            timeout=60,
        )
        ensure_ok(response, path)
        token = str(response.json().get("conduit_token") or "")
        if not token:
            raise RuntimeError("missing conduit_token")
        return token

    def _run_search_conversation(self, prompt: str, conduit_token: str, model: str) -> str:
        requirements = self._get_chat_requirements()
        path = "/backend-api/f/conversation"
        response = self.session.post(
            self.base_url + path,
            headers=self._image_headers(path, requirements, conduit_token, "text/event-stream"),
            json={
                "action": "next",
                "messages": [{
                    "id": new_uuid(),
                    "author": {"role": "user"},
                    "create_time": time.time(),
                    "content": {"content_type": "text", "parts": [prompt]},
                    "metadata": {
                        "developer_mode_connector_ids": [],
                        "selected_github_repos": [],
                        "selected_all_github_repos": False,
                        "system_hints": ["search"],
                        "serialization_metadata": {"custom_symbol_offsets": []},
                    },
                }],
                "parent_message_id": "client-created-root",
                "model": model,
                "client_prepare_state": "success",
                "timezone_offset_min": -480,
                "timezone": "Asia/Shanghai",
                "conversation_mode": {"kind": "primary_assistant"},
                "enable_message_followups": True,
                "system_hints": [],
                "supports_buffering": True,
                "supported_encodings": ["v1"],
                "force_use_search": True,
                "client_reported_search_source": "conversation_composer_web_icon",
                "client_contextual_info": {"is_dark_mode": False, "time_since_loaded": 36, "page_height": 925, "page_width": 886, "pixel_ratio": 2, "screen_height": 1440, "screen_width": 2560, "app_name": "chatgpt.com"},
                "paragen_cot_summary_display_override": "allow",
                "force_parallel_switch": "auto",
            },
            timeout=300,
            stream=True,
        )
        ensure_ok(response, path)
        conversation_id = ""
        try:
            for payload in iter_sse_payloads(response):
                conversation_id = conversation_id or self._find_search_value(payload, "conversation_id")
                if payload == "[DONE]":
                    break
        finally:
            response.close()
        if not conversation_id:
            raise RuntimeError("conversation_id not found in stream")
        return conversation_id

    def _wait_search_result(self, conversation_id: str, timeout_secs: float, poll_interval_secs: float) -> Dict[str, Any]:
        deadline = time.time() + timeout_secs
        last_result: Dict[str, Any] | None = None
        last_answer = ""
        stable_hits = 0
        while time.time() < deadline:
            try:
                last_result = self._extract_search_result(conversation_id, self._get_search_conversation(conversation_id))
            except UpstreamHTTPError as exc:
                if exc.status_code not in {404, 409, 423, 429, 500, 502, 503, 504}:
                    raise
            if last_result and last_result.get("answer"):
                if last_result.get("status") in SEARCH_DONE_STATUS:
                    return last_result
                answer = str(last_result.get("answer") or "")
                stable_hits = stable_hits + 1 if answer == last_answer else 0
                last_answer = answer
                if stable_hits >= 2:
                    return last_result
            time.sleep(poll_interval_secs)
        if last_result:
            return last_result
        raise RuntimeError(f"timed out waiting for search result: {conversation_id}")

    def _get_search_conversation(self, conversation_id: str) -> Dict[str, Any]:
        path = f"/backend-api/conversation/{conversation_id}"
        headers = self._headers(path, {"Accept": "*/*"})
        headers["Referer"] = f"{self.base_url}/c/{conversation_id}"
        headers["X-OpenAI-Target-Route"] = "/backend-api/conversation/{conversation_id}"
        response = self.session.get(self.base_url + path, headers=headers, timeout=60)
        ensure_ok(response, path)
        return response.json()

    def _extract_search_result(self, conversation_id: str, conversation: Dict[str, Any]) -> Dict[str, Any]:
        messages = []
        for node in (conversation.get("mapping") or {}).values():
            message = (node or {}).get("message") or {}
            if ((message.get("author") or {}).get("role") or "") == "assistant":
                messages.append(message)
        message = max(messages, key=lambda item: float(item.get("create_time") or 0.0)) if messages else {}
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        finish_details = metadata.get("finish_details") if isinstance(metadata.get("finish_details"), dict) else {}
        answer = self._search_message_text(message)
        sources = self._extract_search_sources(message)
        for url in SEARCH_URL_RE.findall(answer):
            url = self._clean_search_url(url)
            if url and all(item["url"] != url for item in sources):
                sources.append({"title": "", "url": url, "snippet": "", "source_type": ""})
        return {
            "conversation_id": conversation_id,
            "status": str(finish_details.get("type") or metadata.get("status") or self._find_search_value(message, "status") or "").strip(),
            "answer": answer,
            "sources": sources,
            "assistant_message_id": str(message.get("id") or ""),
            "create_time": float(message.get("create_time") or 0.0),
        }

    def _extract_search_sources(self, payload: Any) -> list[Dict[str, str]]:
        sources: list[Dict[str, str]] = []
        for obj in self._walk_search_dicts(payload):
            metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
            url = self._clean_search_url(obj.get("url") or obj.get("link") or obj.get("source_url") or metadata.get("url"))
            if url and all(item["url"] != url for item in sources):
                sources.append({
                    "title": str(obj.get("title") or obj.get("name") or obj.get("source") or "").strip(),
                    "url": url,
                    "snippet": str(obj.get("snippet") or obj.get("text") or obj.get("description") or "").strip(),
                    "source_type": str(obj.get("type") or obj.get("source_type") or "").strip(),
                })
        return sources

    def _search_message_text(self, message: Any) -> str:
        content = message.get("content") if isinstance(message, dict) else {}
        parts = []
        if isinstance(content, dict):
            if isinstance(content.get("text"), str):
                parts.append(content["text"])
            for part in content.get("parts") or []:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    parts.extend(str(part.get(key) or "") for key in ("text", "summary", "content") if part.get(key))
        elif isinstance(content, str):
            parts.append(content)
        return "\n".join(part.strip() for part in parts if str(part).strip()).strip()

    def _find_search_value(self, payload: Any, key: str) -> str:
        if isinstance(payload, str):
            match = SEARCH_CONVERSATION_ID_RE.search(payload) if key == "conversation_id" else None
            if match:
                return match.group(1)
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return ""
        if isinstance(payload, dict):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
            return next((found for item in payload.values() if (found := self._find_search_value(item, key))), "")
        if isinstance(payload, list):
            return next((found for item in payload if (found := self._find_search_value(item, key))), "")
        return ""

    def _walk_search_dicts(self, payload: Any) -> list[Dict[str, Any]]:
        if isinstance(payload, dict):
            return [payload, *(item for value in payload.values() for item in self._walk_search_dicts(value))]
        if isinstance(payload, list):
            return [item for value in payload for item in self._walk_search_dicts(value)]
        return []

    def _clean_search_url(self, value: Any) -> str:
        return str(value or "").strip().rstrip(".,;，。；")

    @staticmethod
    def _add_unique(values: list[str], candidates: list[str]) -> None:
        for candidate in candidates:
            if candidate and candidate not in values:
                values.append(candidate)

    @classmethod
    def _extract_image_reference_ids(cls, payload: Any) -> tuple[list[str], list[str]]:
        file_ids: list[str] = []
        sediment_ids: list[str] = []

        def walk(value: Any) -> None:
            if isinstance(value, str):
                # 只提取真正的图片文件 ID（file_00000000... 格式）和 file-service:// URI
                cls._add_unique(file_ids, FILE_SERVICE_ID_RE.findall(value))
                cls._add_unique(file_ids, REAL_IMAGE_FILE_ID_RE.findall(value))
                cls._add_unique(sediment_ids, SEDIMENT_ID_RE.findall(value))
                return
            if isinstance(value, dict):
                for item in value.values():
                    walk(item)
                return
            if isinstance(value, list):
                for item in value:
                    walk(item)

        walk(payload)
        return file_ids, sediment_ids

    @classmethod
    def _has_image_asset_pointer(cls, payload: Any) -> bool:
        if isinstance(payload, dict):
            if str(payload.get("content_type") or "") == "image_asset_pointer":
                return True
            asset_pointer = str(payload.get("asset_pointer") or "")
            if asset_pointer.startswith(("file-service://", "sediment://")):
                return True
            return any(cls._has_image_asset_pointer(item) for item in payload.values())
        if isinstance(payload, list):
            return any(cls._has_image_asset_pointer(item) for item in payload)
        return False

    def _extract_image_tool_records(self, data: Dict[str, Any]) -> list[Dict[str, Any]]:
        """从 conversation 明细里提取图片工具输出记录。"""
        mapping = data.get("mapping") or {}
        records = []
        for message_id, node in mapping.items():
            message = (node or {}).get("message") or {}
            author = message.get("author") or {}
            metadata = message.get("metadata") or {}
            content = message.get("content") or {}
            role = str(author.get("role") or "").strip().lower()
            if role not in {"tool", "assistant"}:
                continue
            is_image_gen = metadata.get("async_task_type") == "image_gen"
            has_asset_pointer = self._has_image_asset_pointer(content) or self._has_image_asset_pointer(metadata)
            if role == "assistant" and not (is_image_gen or has_asset_pointer):
                continue
            file_ids, sediment_ids = self._extract_image_reference_ids({"content": content, "metadata": metadata})
            if not is_image_gen and not has_asset_pointer and not file_ids and not sediment_ids:
                continue
            records.append(
                {"message_id": message_id, "create_time": message.get("create_time") or 0, "file_ids": file_ids,
                 "sediment_ids": sediment_ids})
        return sorted(records, key=lambda item: item["create_time"])

    @staticmethod
    def _find_content_policy_error_in_conversation(data: Dict[str, Any]) -> str:
        """从对话文档中查找内容政策违规错误消息。

        上游拒绝生成图片时，错误消息会出现在 assistant 消息的文本中。
        本方法遍历所有 assistant/tool 消息，检查是否包含内容政策违规关键词，
        如果匹配则返回该消息文本（截断至 500 字符），否则返回空字符串。
        """
        mapping = data.get("mapping") or {}
        for node in mapping.values():
            message = (node or {}).get("message") or {}
            author = message.get("author") or {}
            role = str(author.get("role") or "").strip().lower()
            if role not in {"assistant", "tool"}:
                continue
            content = message.get("content") or {}
            # 提取消息文本
            text_parts: list[str] = []
            if isinstance(content, dict):
                msg_parts = content.get("parts") or []
                if isinstance(msg_parts, list):
                    for part in msg_parts:
                        if isinstance(part, str) and part.strip():
                            text_parts.append(part.strip())
                text_field = str(content.get("text") or "")
                if text_field.strip():
                    text_parts.append(text_field.strip())
            elif isinstance(content, str) and content.strip():
                text_parts.append(content.strip())
            msg_text = "\n".join(text_parts)
            if msg_text and _is_content_policy_error(msg_text):
                return msg_text[:500]
        return ""

    def _poll_image_results(
            self,
            conversation_id: str,
            timeout_secs: float = 120.0,
            initial_file_ids: list[str] | None = None,
            initial_sediment_ids: list[str] | None = None,
    ) -> tuple[list[str], list[str]]:
        """Poll the conversation document until image file ids appear or budget runs out.

        - Sleeps image_poll_initial_wait_secs first (default 10s, +jitter). ChatGPT
          image generation takes ~30s; polling immediately wastes requests and trips
          a transient 429 the upstream returns within ~200ms of the SSE stream
          closing (the conversation document is not yet committed).
        - Subsequent polls are image_poll_interval_secs apart (default 10s).
        - On upstream 429 / 5xx or network errors, backs off exponentially
          (capped at 16s, +jitter) honoring Retry-After when present.
        - All sleeps stay within timeout_secs; on exhaustion raises ImagePollTimeoutError.
        """
        start = time.time()
        attempt = 0
        interval = float(config.image_poll_interval_secs)
        initial_wait = float(config.image_poll_initial_wait_secs)
        file_ids: list[str] = []
        sediment_ids: list[str] = []
        self._add_unique(file_ids, initial_file_ids or [])
        self._add_unique(sediment_ids, initial_sediment_ids or [])
        has_initial_ids = bool(file_ids or sediment_ids)
        last_hit_key: tuple[tuple[str, ...], tuple[str, ...]] | None = (
            (tuple(file_ids), tuple(sediment_ids)) if has_initial_ids else None
        )
        logger.info({
            "event": "image_poll_start",
            "conversation_id": conversation_id,
            "timeout_secs": timeout_secs,
            "initial_wait_secs": initial_wait,
            "interval_secs": interval,
            "initial_file_ids": file_ids,
            "initial_sediment_ids": sediment_ids,
        })

        def _remaining() -> float:
            return timeout_secs - (time.time() - start)

        if has_initial_ids and config.image_settle_enabled:
            settle_for = min(config.image_settle_secs, max(0.0, _remaining()))
            if settle_for > 0:
                time.sleep(settle_for)
        elif initial_wait > 0:
            jitter = random.uniform(0, min(2.0, initial_wait * 0.2))
            sleep_for = min(initial_wait + jitter, max(0.0, _remaining()))
            if sleep_for > 0:
                time.sleep(sleep_for)

        def _retry_sleep(reason: str, status_code: int | None, error: str | None, retry_after: int | None) -> bool:
            # retry_after=0 means "retry immediately" — must not be coerced via falsy check.
            base = retry_after if retry_after is not None else min(2 ** min(attempt, 4), 16)
            backoff = base + random.uniform(0, 0.5)
            remaining = _remaining()
            if remaining <= 0:
                return False
            sleep_for = min(backoff, remaining)
            log_payload: Dict[str, Any] = {
                "event": "image_poll_retry",
                "conversation_id": conversation_id,
                "attempt": attempt,
                "reason": reason,
                "sleep_secs": round(sleep_for, 2),
            }
            if status_code is not None:
                log_payload["status_code"] = status_code
            if error is not None:
                log_payload["error"] = error
            logger.warning(log_payload)
            time.sleep(sleep_for)
            return True

        last_task_error = ""
        while _remaining() > 0:
            attempt += 1
            # 在每次轮询时，检查 /backend-api/tasks/ 是否有错误（仅记录，不中断）
            # 内容政策违规检测通过对话文本进行（在 _find_content_policy_error_in_conversation 中）
            last_task_error = ""
            try:
                tasks = self._query_backend_tasks(conversation_id=conversation_id, timeout_secs=5.0)
                for task in tasks:
                    is_error, error_msg, metadata = self.check_task_error(task)
                    if is_error and error_msg:
                        last_task_error = error_msg
                        logger.info({
                            "event": "image_poll_task_error_not_blocking",
                            "conversation_id": conversation_id,
                            "attempt": attempt,
                            "error_msg": error_msg,
                            "metadata": metadata,
                        })
            except Exception as exc:
                # tasks 查询失败不影响正常轮询流程
                logger.debug({
                    "event": "image_poll_task_check_failed",
                    "conversation_id": conversation_id,
                    "attempt": attempt,
                    "error": str(exc),
                })

            try:
                conversation = self._get_conversation(conversation_id)
            except UpstreamHTTPError as exc:
                if exc.status_code in (429, 500, 502, 503, 504):
                    if _retry_sleep("upstream_status", exc.status_code, None, exc.retry_after):
                        continue
                    break
                raise
            except requests.exceptions.RequestException as exc:
                if _retry_sleep("network", None, str(exc), None):
                    continue
                break

            for record in self._extract_image_tool_records(conversation):
                for file_id in record["file_ids"]:
                    if file_id not in file_ids:
                        file_ids.append(file_id)
                for sediment_id in record["sediment_ids"]:
                    if sediment_id not in sediment_ids:
                        sediment_ids.append(sediment_id)

            # 检查对话文本中是否包含内容政策违规错误
            # 当上游拒绝生成图片时，错误消息会出现在对话文档的 assistant 消息中，
            # 而非 /backend-api/tasks/ 的 task error 结构中。
            # 如果在没有找到图片文件 ID 的同时检测到内容政策违规，立即中断轮询。
            if not file_ids and not sediment_ids:
                policy_msg = self._find_content_policy_error_in_conversation(conversation)
                if policy_msg:
                    logger.warning({
                        "event": "image_poll_conversation_text_policy_violation",
                        "conversation_id": conversation_id,
                        "attempt": attempt,
                        "error_msg": policy_msg[:200],
                    })
                    raise ImageContentPolicyError(policy_msg)

            logger.debug({"event": "image_poll_check", "conversation_id": conversation_id, "attempt": attempt,
                          "file_ids": file_ids, "sediment_ids": sediment_ids})
            if file_ids or sediment_ids:
                if not config.image_check_before_hit_enabled:
                    # 先check再hit 机制关闭：直接返回首次发现的 file_ids
                    logger.info({"event": "image_poll_hit_no_settle", "conversation_id": conversation_id,
                                 "file_ids": file_ids, "sediment_ids": sediment_ids})
                    return file_ids, sediment_ids
                hit_key = (tuple(file_ids), tuple(sediment_ids))
                if last_hit_key == hit_key:
                    logger.info({"event": "image_poll_hit", "conversation_id": conversation_id, "file_ids": file_ids,
                                 "sediment_ids": sediment_ids})
                    return file_ids, sediment_ids
                last_hit_key = hit_key
                if not config.image_settle_enabled:
                    # 二次确认机制关闭：直接返回首次发现的 file_ids
                    logger.info({"event": "image_poll_hit_settle_disabled", "conversation_id": conversation_id,
                                 "file_ids": file_ids, "sediment_ids": sediment_ids})
                    return file_ids, sediment_ids
                logger.info({"event": "image_poll_hit_pending_settle", "conversation_id": conversation_id,
                             "file_ids": file_ids, "sediment_ids": sediment_ids,
                             "settle_secs": config.image_settle_secs})
                wait = min(config.image_settle_secs, max(0.0, _remaining()))
                if wait > 0:
                    time.sleep(wait)
                    continue
                return file_ids, sediment_ids
            logger.debug({"event": "image_poll_wait", "conversation_id": conversation_id,
                          "elapsed_secs": round(time.time() - start, 1)})
            wait = min(interval, max(0.0, _remaining()))
            if wait > 0:
                time.sleep(wait)
        logger.info({
            "event": "image_poll_timeout",
            "conversation_id": conversation_id,
            "timeout_secs": timeout_secs,
            "attempts_made": attempt,
            # attempts_made == 0 means the initial_wait consumed the entire budget — no HTTP attempted.
            "initial_wait_exhausted_budget": attempt == 0,
            "last_task_error": last_task_error if last_task_error else None,
        })
        exc = ImagePollTimeoutError(
            f"ChatGPT 生图超时（已等待 {timeout_secs} 秒）。"
            f"当前超时阈值可在 config.json 中调大 image_poll_timeout_secs，"
            f"也可能是账号被限流或生图队列拥堵导致。"
        )
        if last_task_error:
            setattr(exc, "task_error", last_task_error)
        setattr(exc, "conversation_id", conversation_id or "")
        raise exc

    def _get_file_download_url(self, file_id: str) -> str:
        """获取文件下载地址。"""
        path = f"/backend-api/files/{file_id}/download"
        response = self.session.get(self.base_url + path, headers=self._headers(path, {"Accept": "application/json"}),
                                    timeout=60)
        ensure_ok(response, path)
        data = response.json()
        return data.get("download_url") or data.get("url") or ""

    def _get_attachment_download_url(self, conversation_id: str, attachment_id: str) -> str:
        """通过 conversation 附件接口获取下载地址。"""
        path = f"/backend-api/conversation/{conversation_id}/attachment/{attachment_id}/download"
        response = self.session.get(self.base_url + path, headers=self._headers(path, {"Accept": "application/json"}),
                                    timeout=60)
        ensure_ok(response, path)
        data = response.json()
        return data.get("download_url") or data.get("url") or ""

    def _query_backend_tasks(
        self,
        conversation_id: str = "",
        task_id: str = "",
        timeout_secs: float = 30.0,
    ) -> list[Dict[str, Any]]:
        """查询 /backend-api/tasks/ 接口获取异步任务状态和错误信息。

        参数：
        - `conversation_id`：可选。按 conversation_id 过滤任务。
        - `task_id`：可选。按 task_id 过滤任务。
        - `timeout_secs`：请求超时秒数。

        返回：
        - 任务列表，每个任务包含 image_gen_message 等字段。
        """
        path = "/backend-api/tasks"
        response = self.session.get(
            self.base_url + path,
            headers=self._headers(path, {"Accept": "application/json"}),
            timeout=timeout_secs,
        )
        ensure_ok(response, path)
        data = response.json()
        tasks = data.get("tasks", [])
        if not isinstance(tasks, list):
            return []

        # 按 conversation_id 或 task_id 过滤
        if conversation_id:
            tasks = [
                t for t in tasks
                if isinstance(t, dict) and (
                    t.get("conversation_id") == conversation_id
                    or t.get("original_conversation_id") == conversation_id
                )
            ]
        if task_id:
            tasks = [t for t in tasks if isinstance(t, dict) and t.get("task_id") == task_id]
        return tasks

    def check_task_error(self, task: Dict[str, Any]) -> tuple[bool, str, Dict[str, Any]]:
        """检查单个任务是否包含结构化错误。

        通过以下字段判断（不依赖文本匹配）：
        - image_gen_message.metadata.is_error == True
        - image_gen_message.author.role == "assistant" (而非 "tool")
        - image_gen_message.content.content_type == "text" (而非 "multimodal_text")

        返回：
        - (is_error, error_msg, metadata)
        """
        img_msg = task.get("image_gen_message") or {}
        if not img_msg:
            return False, "", {}

        metadata = img_msg.get("metadata") or {}
        content = img_msg.get("content") or {}
        author = img_msg.get("author") or {}

        is_error = metadata.get("is_error", False)
        is_text_only = content.get("content_type") == "text"
        is_assistant_role = author.get("role") == "assistant"

        # 提取错误文本
        error_msg = ""
        if is_error and is_text_only:
            parts = content.get("parts", [])
            error_msg = "".join(p for p in parts if isinstance(p, str))

        return is_error, error_msg, metadata

    def _resolve_image_urls(self, conversation_id: str, file_ids: list[str], sediment_ids: list[str]) -> list[str]:
        """把图片结果 id 解析成可下载 URL。"""
        urls = []
        skip_patterns = {"file_upload"}
        for file_id in file_ids:
            if file_id in skip_patterns:
                logger.debug({
                    "event": "image_file_id_skipped",
                    "source": "file",
                    "conversation_id": conversation_id,
                    "id": file_id,
                })
                continue
            try:
                url = self._get_file_download_url(file_id)
            except Exception as exc:
                logger.debug({
                    "event": "image_download_url_failed",
                    "source": "file",
                    "conversation_id": conversation_id,
                    "id": file_id,
                    "error": repr(exc),
                })
                continue
            if url:
                if url not in urls:
                    urls.append(url)
            else:
                logger.debug({
                    "event": "image_download_url_empty",
                    "source": "file",
                    "conversation_id": conversation_id,
                    "id": file_id,
                })
        if not conversation_id or not sediment_ids:
            logger.debug({
                "event": "image_urls_resolved",
                "conversation_id": conversation_id,
                "file_ids": file_ids,
                "sediment_ids": sediment_ids,
                "urls": urls,
            })
            return urls
        for sediment_id in sediment_ids:
            try:
                url = self._get_attachment_download_url(conversation_id, sediment_id)
            except Exception as exc:
                logger.debug({
                    "event": "image_download_url_failed",
                    "source": "sediment",
                    "conversation_id": conversation_id,
                    "id": sediment_id,
                    "error": repr(exc),
                })
                continue
            if url:
                if url not in urls:
                    urls.append(url)
            else:
                logger.debug({
                    "event": "image_download_url_empty",
                    "source": "sediment",
                    "conversation_id": conversation_id,
                    "id": sediment_id,
                })
        logger.debug({
            "event": "image_urls_resolved",
            "conversation_id": conversation_id,
            "file_ids": file_ids,
            "sediment_ids": sediment_ids,
            "urls": urls,
        })
        return urls

    def resolve_conversation_image_urls(
            self,
            conversation_id: str,
            file_ids: list[str],
            sediment_ids: list[str],
            poll: bool = True,
            poll_timeout_secs: float | None = None,
    ) -> list[str]:
        file_ids = [item for item in file_ids if item != "file_upload"]
        sediment_ids = list(sediment_ids)
        timeout = poll_timeout_secs if poll_timeout_secs is not None else config.image_poll_timeout_secs
        # 当 check-before-hit 和 settle 均已关闭，且 SSE 已给出 file_ids 时，
        # 跳过轮询直接解析 URL，省去 initial_wait + 轮询耗时。
        if poll and conversation_id and (file_ids or sediment_ids):
            if not config.image_check_before_hit_enabled and not config.image_settle_enabled:
                logger.info({
                    "event": "image_resolve_skip_poll_direct_resolve",
                    "conversation_id": conversation_id,
                    "file_ids": file_ids,
                    "sediment_ids": sediment_ids,
                })
                return self._resolve_image_urls(conversation_id, file_ids, sediment_ids)
        if poll and conversation_id:
            logger.info({
                "event": "image_resolve_poll_needed",
                "conversation_id": conversation_id,
                "initial_file_ids": file_ids,
                "initial_sediment_ids": sediment_ids,
                "poll_timeout_secs": timeout,
            })
            try:
                polled_file_ids, polled_sediment_ids = self._poll_image_results(
                    conversation_id,
                    timeout,
                    file_ids,
                    sediment_ids,
                )
            except ImagePollTimeoutError as exc:
                # 如果轮询超时且有 task error（如 moderation 拦截），抛出 ImageContentPolicyError
                # 而非 ImagePollTimeoutError，让调用方能区分真正的超时和上游拒绝
                task_error = getattr(exc, "task_error", "")
                if not file_ids and not sediment_ids:
                    if task_error:
                        raise ImageContentPolicyError(task_error) from exc
                    raise
                logger.warning({
                    "event": "image_resolve_poll_partial_timeout",
                    "conversation_id": conversation_id,
                    "file_ids": file_ids,
                    "sediment_ids": sediment_ids,
                })
            except Exception as exc:
                if not file_ids and not sediment_ids:
                    raise
                logger.warning({
                    "event": "image_resolve_poll_partial_error",
                    "conversation_id": conversation_id,
                    "file_ids": file_ids,
                    "sediment_ids": sediment_ids,
                    "error": repr(exc),
                })
            else:
                file_ids.extend(item for item in polled_file_ids if item and item not in file_ids)
                sediment_ids.extend(item for item in polled_sediment_ids if item and item not in sediment_ids)
        return self._resolve_image_urls(conversation_id, file_ids, sediment_ids)

    def download_image_bytes(self, urls: list[str]) -> list[bytes]:
        images = []
        for url in urls:
            response = self.session.get(url, timeout=120)
            ensure_ok(response, "image_download")
            if response.content not in images:
                images.append(response.content)
        return images

    def stream_conversation(
            self,
            messages: Optional[list[Dict[str, Any]]] = None,
            model: str = "auto",
            prompt: str = "",
            images: Optional[list[str]] = None,
            system_hints: Optional[list[str]] = None,
            thinking_effort: str = "",
    ) -> Iterator[str]:
        system_hints = system_hints or []
        if "picture_v2" in system_hints:
            yield from self._stream_picture_conversation(prompt, model, images or [])
            return

        normalized = messages or [{"role": "user", "content": prompt}]
        self._bootstrap()
        requirements = self._get_chat_requirements()
        path, timezone = self._chat_target()
        payload = self._conversation_payload(normalized, model, timezone, thinking_effort=thinking_effort)
        response = self.session.post(
            self.base_url + path,
            headers=self._conversation_headers(path, requirements),
            json=payload,
            timeout=300,
            stream=True,
        )
        ensure_ok(response, path)
        try:
            yield from iter_sse_payloads(response)
        finally:
            response.close()

    def _report_progress(self, step: str) -> None:
        """Report progress step to the callback if set."""
        if self.progress_callback:
            try:
                self.progress_callback(step)
            except Exception:
                pass

    def _stream_picture_conversation(
            self,
            prompt: str,
            model: str,
            images: list[str],
    ) -> Iterator[str]:
        if not self.access_token:
            raise RuntimeError("access_token is required for image endpoints")
        self._report_progress("uploading")
        references = [self._upload_image(image, f"image_{idx}.png") for idx, image in enumerate(images, start=1)]
        self._report_progress("bootstrapping")
        self._bootstrap()
        self._report_progress("getting_token")
        requirements = self._get_chat_requirements()
        self._report_progress("preparing_conversation")
        conduit_token = self._prepare_image_conversation(prompt, requirements, model)
        self._report_progress("starting_generation")
        response = self._start_image_generation(prompt, requirements, conduit_token, model, references)
        self._report_progress("generating")
        try:
            yield from iter_sse_payloads(response)
        finally:
            response.close()

    def _bootstrap(self) -> None:
        """预热首页，并提取 PoW 相关脚本引用。"""
        response = self.session.get(
            self.base_url + "/",
            headers=self._bootstrap_headers(),
            timeout=30,
        )
        ensure_ok(response, "bootstrap")
        self.pow_script_sources, self.pow_data_build = parse_pow_resources(response.text)
        if not self.pow_script_sources:
            self.pow_script_sources = [DEFAULT_POW_SCRIPT]

    def _get_chat_requirements(self) -> ChatRequirements:
        """获取当前模式对话所需的 sentinel token（prepare + finalize 两步流程）。"""
        base = "/backend-api/sentinel/chat-requirements" if self.access_token else "/backend-anon/sentinel/chat-requirements"
        p_token = build_legacy_requirements_token(self.user_agent, self.pow_script_sources, self.pow_data_build)

        prepare_path = base + "/prepare"
        response = self.session.post(
            self.base_url + prepare_path,
            headers=self._headers(prepare_path, {"Content-Type": "application/json"}),
            json={"p": p_token},
            timeout=30,
        )
        ensure_ok(response, "chat_requirements_prepare")
        prepare_data = response.json()

        if (prepare_data.get("arkose") or {}).get("required"):
            raise RuntimeError("chat requirements requires arkose token, which is not implemented")

        proof_token = ""
        proof_info = prepare_data.get("proofofwork") or {}
        if proof_info.get("required"):
            proof_token = build_proof_token(
                proof_info.get("seed", ""),
                proof_info.get("difficulty", ""),
                self.user_agent,
                script_sources=self.pow_script_sources,
                data_build=self.pow_data_build,
            )

        turnstile_token = ""
        turnstile_info = prepare_data.get("turnstile") or {}
        if turnstile_info.get("required") and turnstile_info.get("dx"):
            turnstile_token = solve_turnstile_token(turnstile_info["dx"], p_token) or ""

        finalize_path = base + "/finalize"
        response = self.session.post(
            self.base_url + finalize_path,
            headers=self._headers(finalize_path, {"Content-Type": "application/json"}),
            json={
                "prepare_token": prepare_data.get("prepare_token", ""),
                "proof_token": proof_token,
                "turnstile_token": turnstile_token,
            },
            timeout=30,
        )
        ensure_ok(response, "chat_requirements_finalize")
        data = response.json()

        token = data.get("token", "")
        if not token:
            message = "missing auth chat requirements token" if self.access_token else "missing chat requirements token"
            raise RuntimeError(f"{message}: {data}")

        return ChatRequirements(
            token=token,
            proof_token=proof_token,
            turnstile_token=turnstile_token,
            so_token=data.get("so_token", ""),
            raw_finalize=data,
        )

    def _chat_target(self) -> tuple[str, str]:
        if self.access_token:
            return "/backend-api/conversation", "Asia/Shanghai"
        return "/backend-anon/conversation", "America/Los_Angeles"

    def list_models(self) -> Dict[str, Any]:
        """返回当前模式下可用模型，格式对齐 OpenAI `/v1/models`。"""
        self._bootstrap()
        path = "/backend-api/models?history_and_training_disabled=false" if self.access_token else (
            "/backend-anon/models?iim=false&is_gizmo=false"
        )
        route = "/backend-api/models" if self.access_token else "/backend-anon/models"
        context = "auth_models" if self.access_token else "anon_models"
        response = self.session.get(
            self.base_url + path,
            headers=self._headers(route),
            timeout=30,
        )
        ensure_ok(response, context)
        data = []
        seen = set()
        for item in response.json().get("models", []):
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug", "")).strip()
            if not slug or slug in seen:
                continue
            seen.add(slug)
            data.append({
                "id": slug,
                "object": "model",
                "created": int(item.get("created") or 0),
                "owned_by": str(item.get("owned_by") or "chatgpt"),
                "permission": [],
                "root": slug,
                "parent": None,
            })
        data.sort(key=lambda item: item["id"])
        return {"object": "list", "data": data}
