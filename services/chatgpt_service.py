from __future__ import annotations

from typing import Iterable

from fastapi import HTTPException

from services.account_service import AccountService
from services.image_service import ImageGenerationError, edit_image_result, generate_image_result, is_token_invalid_error
from services.utils import (
    build_chat_image_completion,
    extract_chat_image,
    extract_chat_prompt,
    extract_image_from_message_content,
    extract_response_prompt,
    has_response_image_generation_tool,
    is_image_chat_request,
    parse_image_count,
)


def _extract_response_image(input_value: object) -> tuple[bytes, str] | None:
    if isinstance(input_value, dict):
        return extract_image_from_message_content(input_value.get("content"))
    if not isinstance(input_value, list):
        return None
    for item in reversed(input_value):
        if isinstance(item, dict):
            if str(item.get("type") or "").strip() == "input_image":
                import base64 as b64
                image_url = str(item.get("image_url") or "")
                if image_url.startswith("data:"):
                    header, _, data = image_url.partition(",")
                    mime = header.split(";")[0].removeprefix("data:")
                    return b64.b64decode(data), mime or "image/png"
            content = item.get("content")
            if content:
                result = extract_image_from_message_content(content)
                if result:
                    return result
    return None


class ChatGPTService:
    def __init__(self, account_service: AccountService):
        self.account_service = account_service

    def generate_with_pool(self, prompt: str, model: str, n: int, response_format: str = "b64_json", base_url: str = None, progress_callback=None):
        created = None
        image_items: list[dict[str, object]] = []

        for index in range(1, n + 1):
            while True:
                try:
                    request_token = self.account_service.get_available_access_token()
                except RuntimeError as exc:
                    print(f"[image-generate] stop index={index}/{n} error={exc}")
                    break

                print(f"[image-generate] start pooled token={request_token[:12]}... model={model} index={index}/{n}")
                try:
                    result = generate_image_result(request_token, prompt, model, response_format, base_url, progress_callback)
                    account = self.account_service.mark_image_result(request_token, success=True)
                    if created is None:
                        created = result.get("created")
                    data = result.get("data")
                    if isinstance(data, list):
                        image_items.extend(item for item in data if isinstance(item, dict))
                    print(
                        f"[image-generate] success pooled token={request_token[:12]}... "
                        f"quota={account.get('quota') if account else 'unknown'} status={account.get('status') if account else 'unknown'}"
                    )
                    break
                except ImageGenerationError as exc:
                    account = self.account_service.mark_image_result(request_token, success=False)
                    message = str(exc)
                    print(
                        f"[image-generate] fail pooled token={request_token[:12]}... "
                        f"error={message} quota={account.get('quota') if account else 'unknown'} status={account.get('status') if account else 'unknown'}"
                    )
                    if is_token_invalid_error(message):
                        self.account_service.remove_token(request_token)
                        print(f"[image-generate] remove invalid token={request_token[:12]}...")
                        continue
                    break

        if not image_items:
            raise ImageGenerationError("image generation failed")

        return {
            "created": created,
            "data": image_items,
        }

    def edit_with_pool(
        self,
        prompt: str,
        images: Iterable[tuple[bytes, str, str]],
        model: str,
        n: int,
        response_format: str = "b64_json",
        base_url: str = None,
        progress_callback=None,
    ):
        created = None
        image_items: list[dict[str, object]] = []
        normalized_images = list(images)
        if not normalized_images:
            raise ImageGenerationError("image is required")

        for index in range(1, n + 1):
            while True:
                try:
                    request_token = self.account_service.get_available_access_token()
                except RuntimeError as exc:
                    print(f"[image-edit] stop index={index}/{n} error={exc}")
                    break

                print(
                    f"[image-edit] start pooled token={request_token[:12]}... "
                    f"model={model} index={index}/{n} images={len(normalized_images)}"
                )
                try:
                    result = edit_image_result(request_token, prompt, normalized_images, model, response_format, base_url, progress_callback)
                    account = self.account_service.mark_image_result(request_token, success=True)
                    if created is None:
                        created = result.get("created")
                    data = result.get("data")
                    if isinstance(data, list):
                        image_items.extend(item for item in data if isinstance(item, dict))
                    print(
                        f"[image-edit] success pooled token={request_token[:12]}... "
                        f"quota={account.get('quota') if account else 'unknown'} status={account.get('status') if account else 'unknown'}"
                    )
                    break
                except ImageGenerationError as exc:
                    account = self.account_service.mark_image_result(request_token, success=False)
                    message = str(exc)
                    print(
                        f"[image-edit] fail pooled token={request_token[:12]}... "
                        f"error={message} quota={account.get('quota') if account else 'unknown'} status={account.get('status') if account else 'unknown'}"
                    )
                    if is_token_invalid_error(message):
                        self.account_service.remove_token(request_token)
                        print(f"[image-edit] remove invalid token={request_token[:12]}...")
                        continue
                    break

        if not image_items:
            raise ImageGenerationError("image edit failed")

        return {
            "created": created,
            "data": image_items,
        }

    def create_image_completion(self, body: dict[str, object], base_url: str = None) -> dict[str, object]:
        if not is_image_chat_request(body):
            raise HTTPException(
                status_code=400,
                detail={"error": "only image generation requests are supported on this endpoint"},
            )

        if bool(body.get("stream")):
            raise HTTPException(status_code=400, detail={"error": "stream is not supported for image generation synchronous endpoint"})

        model = str(body.get("model") or "gpt-image-1").strip() or "gpt-image-1"
        n = parse_image_count(body.get("n"))
        prompt = extract_chat_prompt(body)
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "prompt is required"})

        image_info = extract_chat_image(body)
        try:
            if image_info:
                image_data, mime_type = image_info
                image_result = self.edit_with_pool(prompt, [(image_data, "image.png", mime_type)], model, n, base_url=base_url)
            else:
                image_result = self.generate_with_pool(prompt, model, n, base_url=base_url)
        except ImageGenerationError as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        return build_chat_image_completion(model, prompt, image_result)

    async def stream_image_completion(self, body: dict[str, object], base_url: str = None):
        import asyncio
        import json
        import time
        import threading
        
        if not is_image_chat_request(body):
            yield 'data: {"error": "only image generation requests are supported on this endpoint"}\n\n'
            return

        model = str(body.get("model") or "gpt-image-1").strip() or "gpt-image-1"
        n = parse_image_count(body.get("n"))
        prompt = extract_chat_prompt(body)
        if not prompt:
            yield 'data: {"error": "prompt is required"}\n\n'
            return

        image_info = extract_chat_image(body)
        
        q = asyncio.Queue()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            yield 'data: {"error": "no running event loop"}\n\n'
            return
            
        def progress_callback(status: str):
            asyncio.run_coroutine_threadsafe(q.put({"type": "progress", "data": status}), loop)

        def run_sync():
            try:
                if image_info:
                    image_data, mime_type = image_info
                    res = self.edit_with_pool(prompt, [(image_data, "image.png", mime_type)], model, n, base_url=base_url, progress_callback=progress_callback)
                else:
                    res = self.generate_with_pool(prompt, model, n, base_url=base_url, progress_callback=progress_callback)
                asyncio.run_coroutine_threadsafe(q.put({"type": "done", "data": res}), loop)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(q.put({"type": "error", "error": str(e)}), loop)

        t = threading.Thread(target=run_sync)
        t.start()
        
        created = int(time.time())
        chunk_id = f"chatcmpl-{created}"
        
        initial_chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]
        }
        yield f"data: {json.dumps(initial_chunk, ensure_ascii=False)}\n\n"
        
        has_polled = False
        while True:
            msg = await q.get()
            if msg["type"] == "progress":
                if msg["data"] == "polling" and not has_polled:
                    has_polled = True
                    chunk = {
                        "id": chunk_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {"content": "图片生成排队中，请稍候...\n"}, "finish_reason": None}]
                    }
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                elif msg["data"] == "polling":
                    yield ": keepalive\n\n"
            elif msg["type"] == "done":
                res = msg["data"]
                final_content = build_chat_image_completion(model, prompt, res)
                choice = final_content.get("choices", [{}])[0]
                text = choice.get("message", {}).get("content", "")
                if has_polled:
                    text = "\n" + text
                chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": "stop"}]
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                break
            elif msg["type"] == "error":
                e = msg["error"]
                chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": f"\n[Error] {str(e)}"}, "finish_reason": "stop"}]
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                break

    def create_response(self, body: dict[str, object]) -> dict[str, object]:
        if bool(body.get("stream")):
            raise HTTPException(status_code=400, detail={"error": "stream is not supported"})

        if not has_response_image_generation_tool(body):
            raise HTTPException(
                status_code=400,
                detail={"error": "only image_generation tool requests are supported on this endpoint"},
            )

        prompt = extract_response_prompt(body.get("input"))
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "input text is required"})

        image_info = _extract_response_image(body.get("input"))
        model = str(body.get("model") or "gpt-5").strip() or "gpt-5"
        try:
            if image_info:
                image_data, mime_type = image_info
                image_result = self.edit_with_pool(prompt, [(image_data, "image.png", mime_type)], "gpt-image-1", 1)
            else:
                image_result = self.generate_with_pool(prompt, "gpt-image-1", 1)
        except ImageGenerationError as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        image_items = image_result.get("data") if isinstance(image_result.get("data"), list) else []
        output = []
        for item in image_items:
            if not isinstance(item, dict):
                continue
            b64_json = str(item.get("b64_json") or "").strip()
            if not b64_json:
                continue
            output.append(
                {
                    "id": f"ig_{len(output) + 1}",
                    "type": "image_generation_call",
                    "status": "completed",
                    "result": b64_json,
                    "revised_prompt": str(item.get("revised_prompt") or prompt).strip(),
                }
            )

        if not output:
            raise HTTPException(status_code=502, detail={"error": "image generation failed"})

        created = int(image_result.get("created") or 0)
        return {
            "id": f"resp_{created}",
            "object": "response",
            "created_at": created,
            "status": "completed",
            "error": None,
            "incomplete_details": None,
            "model": model,
            "output": output,
            "parallel_tool_calls": False,
        }
