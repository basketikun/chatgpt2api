import base64
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

from curl_cffi import requests
from fastapi import HTTPException
from utils.log import logger

IMAGE_MODELS = {
    "gpt-image-2",
    "codex-gpt-image-2",
    "gemini-image/imagen-3.0-generate-001",
    "gemini-image/gemini-2.5-flash-image",
    "gemini-image/gemini-3.1-flash-image-preview",
    # Google Labs Flow (driven via captcha-solver)
    "flow/auto",            # → Nano Banana Pro
    "flow/banana-pro",      # → Nano Banana Pro
    "flow/banana-2",        # → Nano Banana 2
    "flow/imagen-4",        # → Imagen 4
}
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# Model capability classification
_IMAGE_GEN_PREFIXES = {
    "nv-image/", "sdwebui/", "comfyui/", "huggingface/",
    "bfl/", "stability/", "fal-ai/", "cloudflare/",
    "recraft/", "runwayml/",
}
_IMAGE_GEN_KEYWORDS = {
    "flux", "stable-diffusion", "sdxl", "dall-e", "gpt-image",
    "image-generation", "image_generation", "imagen",
}
# Providers where ALL models support image generation
_IMAGE_GEN_PROVIDER_PREFIXES = {
    "nv-image/",     # NVIDIA image gen (FLUX, SD)
    "sdwebui/",      # Stable Diffusion WebUI
    "comfyui/",      # ComfyUI
    "huggingface/",  # HuggingFace inference
    "bfl/",          # Black Forest Labs
    "stability/",    # Stability AI
    "fal-ai/",       # Fal.ai
    "cloudflare/",   # Cloudflare AI
    "recraft/",      # Recraft
    "runwayml/",     # RunwayML
}
# Providers where ALL models support vision (multimodal)
_VISION_PROVIDER_PREFIXES: set[str] = {
    "cx/",            # Codex supports image input natively
    "gemini_free/",   # Gemini API supports image input
    "ag/",            # Antigravity supports multimodal vision
}
# Custom providers that support image generation
_IMAGE_GEN_CUSTOM_PROVIDERS = {
    "geminiapi",     # Gemini API server — supports image gen via /v1/responses
}
# Custom providers where ALL models support vision
_VISION_CUSTOM_PROVIDERS: set[str] = {
    "geminiapi",      # Gemini-FastAPI supports image input
}
# Individual model keywords for vision (used for nv/ and other providers)
_VISION_KEYWORDS = {
    "gemma-2", "gemma-3", "gemma-4", "gemma-7b",
    "fuyu", "kosmos", "nvclip", "vila", "trellis",
    "phi-3-vision", "phi-4-multimodal", "phi-3.5-moe",
    "llama-3.2-11b", "llama-3.2-90b", "llama-4-maverick",
    "nemotron-nano-12b-v2-vl", "nemotron-3-nano-omni",
    "bevformer", "sparsedrive", "streampetr", "visual-changenet",
    "cosmos-predict1", "nv-dinov2", "nv-grounding-dino",
    "retail-object-detection", "codegemma",
    "yi-large", "sarvam",
}
# Providers where ALL models support video analysis
_VIDEO_PROVIDER_PREFIXES: set[str] = {
    "cx/",            # Codex supports video via multimodal
    "gemini_free/",   # Gemini API supports video input
    "ag/",            # Antigravity supports video input
}
# Custom providers where ALL models support video
_VIDEO_CUSTOM_PROVIDERS: set[str] = {
    "geminiapi",      # Gemini-FastAPI supports video
}


def classify_model_capability(model_id: str) -> list[str]:
    """Classify a model by capabilities: ['chat'], ['chat','vision'], ['image'], etc.

    Image Gen: models that generate images (FLUX, SD, DALL-E)
    Vision: models that can analyze/understand images (multimodal)
    Chat: text models (all models are at least chat-capable)
    """
    mid = str(model_id or "").strip().lower()
    caps: list[str] = []

    # Check image gen first
    is_image = False
    for prefix in _IMAGE_GEN_PREFIXES:
        if mid.startswith(prefix):
            caps.append("image")
            is_image = True
            break
    if not is_image:
        for prefix in _IMAGE_GEN_PROVIDER_PREFIXES:
            if mid.startswith(prefix):
                caps.append("image")
                is_image = True
                break
    if not is_image:
        for kw in _IMAGE_GEN_KEYWORDS:
            if kw in mid:
                caps.append("image")
                break
    if not is_image:
        for cp_prefix in _IMAGE_GEN_CUSTOM_PROVIDERS:
            if mid.startswith(cp_prefix):  # matches geminiapi, geminiapi1, geminiapi2, etc.
                caps.append("image")
                break

    # Check vision capability
    for prefix in _VISION_PROVIDER_PREFIXES:
        if mid.startswith(prefix):
            caps.append("vision")
            break
    else:
        for cp_prefix in _VISION_CUSTOM_PROVIDERS:
            if mid.startswith(cp_prefix):  # matches geminiapi, geminiapi1, etc.
                caps.append("vision")
                break
        else:
            for kw in _VISION_KEYWORDS:
                if kw in mid:
                    caps.append("vision")
                    break

    # All models support chat (unless they're pure image gen with no text)
    if not is_image:
        caps.append("chat")

    # Check video analysis capability
    for prefix in _VIDEO_PROVIDER_PREFIXES:
        if mid.startswith(prefix):
            if "video" not in caps:
                caps.append("video")
            break
    else:
        for cp_prefix in _VIDEO_CUSTOM_PROVIDERS:
            if mid.startswith(cp_prefix):  # matches geminiapi, geminiapi1, etc.
                if "video" not in caps:
                    caps.append("video")
                break

    return caps if caps else ["chat"]


def get_model_capability_label(cap: str) -> str:
    """Human-readable label for model capability."""
    return {"chat": "Chat", "vision": "Phân tích ảnh", "image": "Tạo ảnh", "video": "Phân tích video"}.get(cap, cap)


def new_uuid() -> str:
    return str(uuid.uuid4())


def is_image_chat_request(body: dict[str, object]) -> bool:
    model = str(body.get("model") or "").strip()
    modalities = body.get("modalities")
    if model in IMAGE_MODELS:
        return True
    return isinstance(modalities, list) and "image" in {str(item or "").strip().lower() for item in modalities}


def ensure_ok(response: requests.Response, context: str) -> None:
    if 200 <= response.status_code < 300:
        return
    body: Any = response.text
    try:
        body = response.json()
    except Exception:
        pass
    raise RuntimeError(f"{context} failed: status={response.status_code}, body={body}")


def sse_json_stream(items) -> Iterator[str]:
    yield ": stream-open\n\n"
    try:
        for item in items:
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
    except Exception as exc:
        logger.warning({
            "event": "sse_stream_error",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        })
        error = exc.to_openai_error() if hasattr(exc, "to_openai_error") else {
            "error": {"message": str(exc), "type": exc.__class__.__name__}
        }
        yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def anthropic_sse_stream(items) -> Iterator[str]:
    try:
        for item in items:
            event = str(item.get("type") or "message_delta") if isinstance(item, dict) else "message_delta"
            yield f"event: {event}\n"
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
    except Exception as exc:
        logger.warning({
            "event": "anthropic_sse_stream_error",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        })
        error = {"type": "error", "error": {"type": exc.__class__.__name__, "message": str(exc)}}
        yield "event: error\n"
        yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"


def iter_sse_payloads(response: requests.Response) -> Iterator[str]:
    for raw_line in response.iter_lines():
        if not raw_line:
            continue
        line = raw_line.decode("utf-8", errors="ignore") if isinstance(raw_line, bytes) else str(raw_line)
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload:
            yield payload


def save_images_from_text(text: str, prefix: str) -> list[Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    matches = re.findall(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", text or "")
    saved_paths: list[Path] = []
    timestamp = int(time.time() * 1000)
    for index, data_url in enumerate(matches, start=1):
        header, encoded = data_url.split(",", 1)
        image_type = header.split(";")[0].removeprefix("data:image/").strip() or "png"
        extension = "jpg" if image_type == "jpeg" else image_type
        output_path = OUTPUT_DIR / f"{prefix}_{timestamp}_{index}.{extension}"
        output_path.write_bytes(base64.b64decode(encoded))
        saved_paths.append(output_path)
    return saved_paths


def anonymize_token(token: object) -> str:
    value = str(token or "").strip()
    if not value:
        return "token:empty"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"token:{digest}"


def extract_response_prompt(input_value: object) -> str:
    if isinstance(input_value, str):
        return input_value.strip()
    if isinstance(input_value, dict):
        role = str(input_value.get("role") or "").strip().lower()
        if role and role != "user":
            return ""
        return extract_prompt_from_message_content(input_value.get("content"))
    if not isinstance(input_value, list):
        return ""
    prompt_parts: list[str] = []
    for item in input_value:
        if isinstance(item, dict) and str(item.get("type") or "").strip() == "input_text":
            text = str(item.get("text") or "").strip()
            if text:
                prompt_parts.append(text)
            continue
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role and role != "user":
            continue
        prompt = extract_prompt_from_message_content(item.get("content"))
        if prompt:
            prompt_parts.append(prompt)
    return "\n".join(prompt_parts).strip()


def has_response_image_generation_tool(body: dict[str, object]) -> bool:
    tools = body.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, dict) and str(tool.get("type") or "").strip() == "image_generation":
                return True
    tool_choice = body.get("tool_choice")
    return isinstance(tool_choice, dict) and str(tool_choice.get("type") or "").strip() == "image_generation"


def extract_prompt_from_message_content(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type == "text":
            text = str(item.get("text") or "").strip()
            if text:
                parts.append(text)
        elif item_type == "input_text":
            text = str(item.get("text") or item.get("input_text") or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def extract_image_from_message_content(content: object) -> list[tuple[bytes, str]]:
    if not isinstance(content, list):
        return []
    images = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type == "image_url":
            url_obj = item.get("image_url") or item
            url = str(url_obj.get("url") or "") if isinstance(url_obj, dict) else str(url_obj)
            if url.startswith("data:"):
                header, _, data = url.partition(",")
                mime = header.split(";")[0].removeprefix("data:")
                images.append((base64.b64decode(data), mime or "image/png"))
        elif item_type == "input_image":
            image_url = str(item.get("image_url") or "")
            if image_url.startswith("data:"):
                header, _, data = image_url.partition(",")
                mime = header.split(";")[0].removeprefix("data:")
                images.append((base64.b64decode(data), mime or "image/png"))
    return images


def extract_chat_image(body: dict[str, object]) -> list[tuple[bytes, str]]:
    messages = body.get("messages")
    if not isinstance(messages, list):
        return []
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        if str(message.get("role") or "").strip().lower() != "user":
            continue
        images = extract_image_from_message_content(message.get("content"))
        if images:
            return images
    return []


def extract_chat_prompt(body: dict[str, object]) -> str:
    direct_prompt = str(body.get("prompt") or "").strip()
    if direct_prompt:
        return direct_prompt
    messages = body.get("messages")
    if not isinstance(messages, list):
        return ""
    prompt_parts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        if str(message.get("role") or "").strip().lower() != "user":
            continue
        prompt = extract_prompt_from_message_content(message.get("content"))
        if prompt:
            prompt_parts.append(prompt)
    return "\n".join(prompt_parts).strip()


def parse_image_count(raw_value: object) -> int:
    try:
        value = int(raw_value or 1)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"error": "n must be an integer"}) from exc
    if value < 1 or value > 4:
        raise HTTPException(status_code=400, detail={"error": "n must be between 1 and 4"})
    return value


def build_chat_image_markdown_content(image_result: dict[str, object]) -> str:
    image_items = image_result.get("data") if isinstance(image_result.get("data"), list) else []
    markdown_images: list[str] = []
    for index, item in enumerate(image_items, start=1):
        if not isinstance(item, dict):
            continue
        b64_json = str(item.get("b64_json") or "").strip()
        if b64_json:
            markdown_images.append(f"![image_{index}](data:image/png;base64,{b64_json})")
    return "\n\n".join(markdown_images) if markdown_images else "Image generation completed."
