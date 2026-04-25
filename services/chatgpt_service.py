from __future__ import annotations

import base64
import hashlib
import re
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Iterator

from fastapi import HTTPException

from services.account_service import AccountService
from services.config import config
from services.minimax_backend_api import MINIMAX_MODELS, MinimaxBackendAPI, is_minimax_model
from services.openai_backend_api import CODEX_IMAGE_MODEL, OpenAIBackendAPI
from utils.helper import (
    IMAGE_MODELS,
    extract_chat_image,
    extract_chat_prompt,
    extract_image_from_message_content,
    extract_response_prompt,
    has_response_image_generation_tool,
    parse_image_count,
    build_chat_image_completion,
)
from utils.helper import is_image_chat_request
from utils.log import logger


class ImageGenerationError(Exception):
    pass


def is_token_invalid_error(message: str) -> bool:
    text = str(message or "").lower()
    return (
            "token_invalidated" in text
            or "token_revoked" in text
            or "authentication token has been invalidated" in text
            or "invalidated oauth token" in text
    )


def _save_image_bytes(image_data: bytes, base_url: str | None = None) -> str:
    file_hash = hashlib.md5(image_data).hexdigest()
    timestamp = int(time.time())
    filename = f"{timestamp}_{file_hash}.png"
    relative_dir = Path(time.strftime("%Y"), time.strftime("%m"), time.strftime("%d"))
    file_path = config.images_dir / relative_dir / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(image_data)
    return f"{(base_url or config.base_url)}/images/{relative_dir.as_posix()}/{filename}"


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

    @staticmethod
    def _new_backend(access_token: str = "") -> OpenAIBackendAPI:
        return OpenAIBackendAPI(access_token=access_token)

    def _get_text_access_token(self) -> str:
        tokens = self.account_service.list_tokens()
        return tokens[0] if tokens else ""

    @staticmethod
    def _encode_images(images: Iterable[tuple[bytes, str, str]]) -> list[str]:
        encoded_images: list[str] = []
        for image_data, _, _ in images:
            if image_data:
                encoded_images.append(base64.b64encode(image_data).decode("ascii"))
        return encoded_images

    def list_models(self) -> dict[str, object]:
        result = self._new_backend().list_models()
        data = result.get("data")
        if not isinstance(data, list):
            return result
        seen = {str(item.get("id") or "").strip() for item in data if isinstance(item, dict)}
        for model in sorted(IMAGE_MODELS):
            if model in seen:
                continue
            data.append({
                "id": model,
                "object": "model",
                "created": 0,
                "owned_by": "chatgpt2api",
                "permission": [],
                "root": model,
                "parent": None,
            })
        for model_id in MINIMAX_MODELS:
            if model_id in seen:
                continue
            seen.add(model_id)
            data.append({
                "id": model_id,
                "object": "model",
                "created": 0,
                "owned_by": "minimax",
                "permission": [],
                "root": model_id,
                "parent": None,
            })
        return result

    @staticmethod
    def _chat_messages_from_body(body: dict[str, object]) -> list[dict[str, object]]:
        messages = body.get("messages")
        if isinstance(messages, list) and messages:
            return [message for message in messages if isinstance(message, dict)]
        prompt = str(body.get("prompt") or "").strip()
        if prompt:
            return [{"role": "user", "content": prompt}]
        raise HTTPException(status_code=400, detail={"error": "messages or prompt is required"})

    @staticmethod
    def _response_messages_from_input(input_value: object, instructions: object = None) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []
        system_text = str(instructions or "").strip()
        if system_text:
            messages.append({"role": "system", "content": system_text})

        if isinstance(input_value, str):
            user_text = input_value.strip()
            if user_text:
                messages.append({"role": "user", "content": user_text})
            return messages

        if isinstance(input_value, dict):
            messages.append({
                "role": str(input_value.get("role") or "user"),
                "content": extract_response_prompt([input_value]) or input_value.get("content") or "",
            })
            return messages

        if isinstance(input_value, list):
            if all(isinstance(item, dict) and item.get("type") for item in input_value):
                text = extract_response_prompt(input_value)
                if text:
                    messages.append({"role": "user", "content": text})
                return messages
            for item in input_value:
                if not isinstance(item, dict):
                    continue
                messages.append({
                    "role": str(item.get("role") or "user"),
                    "content": extract_response_prompt([item]) or item.get("content") or "",
                })
            return messages

        return messages

    @staticmethod
    def _response_text_output_item(text: str, item_id: str | None = None, status: str = "completed") -> dict[str, object]:
        return {
            "id": item_id or f"msg_{uuid.uuid4().hex}",
            "type": "message",
            "status": status,
            "role": "assistant",
            "content": [{
                "type": "output_text",
                "text": text,
                "annotations": [],
            }],
        }

    def _create_text_response(self, body: dict[str, object]) -> dict[str, object]:
        model = str(body.get("model") or "auto").strip() or "auto"
        messages = self._response_messages_from_input(body.get("input"), body.get("instructions"))
        if len(messages) == 1 and messages[0].get("role") == "system":
            raise HTTPException(status_code=400, detail={"error": "input text is required"})
        try:
            result = self._new_backend(self._get_text_access_token()).chat_completions(messages=messages, model=model, stream=False)
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        created = int(result.get("created") or time.time())
        output_text = str((((result.get("choices") or [{}])[0].get("message") or {}).get("content")) or "")
        response_id = f"resp_{uuid.uuid4().hex}"
        output_item = self._response_text_output_item(output_text)
        return {
            "id": response_id,
            "object": "response",
            "created_at": created,
            "status": "completed",
            "error": None,
            "incomplete_details": None,
            "model": model,
            "output": [output_item],
            "parallel_tool_calls": False,
            "usage": result.get("usage"),
        }

    def _stream_text_response(self, body: dict[str, object]) -> Iterator[dict[str, object]]:
        model = str(body.get("model") or "auto").strip() or "auto"
        messages = self._response_messages_from_input(body.get("input"), body.get("instructions"))
        if len(messages) == 1 and messages[0].get("role") == "system":
            raise HTTPException(status_code=400, detail={"error": "input text is required"})

        response_id = f"resp_{uuid.uuid4().hex}"
        item_id = f"msg_{uuid.uuid4().hex}"
        created = int(time.time())
        full_text = ""

        yield {
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": created,
                "status": "in_progress",
                "error": None,
                "incomplete_details": None,
                "model": model,
                "output": [],
                "parallel_tool_calls": False,
            },
        }
        yield {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": self._response_text_output_item("", item_id=item_id, status="in_progress"),
        }

        try:
            stream = self._new_backend(self._get_text_access_token()).chat_completions(messages=messages, model=model, stream=True)
            for chunk in stream:
                choices = chunk.get("choices")
                first_choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
                delta = first_choice.get("delta") if isinstance(first_choice.get("delta"), dict) else {}
                delta_text = str(delta.get("content") or "")
                if delta_text:
                    full_text += delta_text
                    yield {
                        "type": "response.output_text.delta",
                        "item_id": item_id,
                        "output_index": 0,
                        "content_index": 0,
                        "delta": delta_text,
                    }
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        yield {
            "type": "response.output_text.done",
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "text": full_text,
        }
        output_item = self._response_text_output_item(full_text, item_id=item_id, status="completed")
        yield {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": output_item,
        }
        yield {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": created,
                "status": "completed",
                "error": None,
                "incomplete_details": None,
                "model": model,
                "output": [output_item],
                "parallel_tool_calls": False,
            },
        }

    @staticmethod
    def _is_text_response_request(body: dict[str, object]) -> bool:
        tools = body.get("tools")
        if isinstance(tools, list):
            for tool in tools:
                if isinstance(tool, dict) and str(tool.get("type") or "").strip() == "image_generation":
                    return False
        tool_choice = body.get("tool_choice")
        if isinstance(tool_choice, dict) and str(tool_choice.get("type") or "").strip() == "image_generation":
            return False
        return True

    @staticmethod
    def _is_codex_image_response_request(body: dict[str, object]) -> bool:
        return has_response_image_generation_tool(body) and str(body.get("model") or "").strip() == CODEX_IMAGE_MODEL

    @staticmethod
    def _build_image_response_output(
            prompt: str,
            image_result: dict[str, object],
    ) -> list[dict[str, object]]:
        image_items = image_result.get("data") if isinstance(image_result.get("data"), list) else []
        output: list[dict[str, object]] = []
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
        return output

    def _create_token_image_response(self, body: dict[str, object]) -> dict[str, object]:
        prompt = extract_response_prompt(body.get("input"))
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "input text is required"})

        model = str(body.get("model") or "gpt-image-2").strip() or "gpt-image-2"
        image_info = _extract_response_image(body.get("input"))
        try:
            if image_info:
                image_data, mime_type = image_info
                image_result = self.edit_with_pool(prompt, [(image_data, "image.png", mime_type)], model, 1)
            else:
                image_result = self.generate_with_pool(prompt, model, 1, size="1:1")
        except ImageGenerationError as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        output = self._build_image_response_output(prompt, image_result)
        if not output:
            raise HTTPException(status_code=502, detail={"error": "image generation failed"})

        created = int(image_result.get("created") or time.time())
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

    def _stream_token_image_response(self, body: dict[str, object]) -> Iterator[dict[str, object]]:
        prompt = extract_response_prompt(body.get("input"))
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "input text is required"})

        model = str(body.get("model") or "gpt-image-2").strip() or "gpt-image-2"
        image_info = _extract_response_image(body.get("input"))
        response_id = f"resp_{uuid.uuid4().hex}"
        item_id = f"ig_{uuid.uuid4().hex}"
        created = int(time.time())
        final_output: list[dict[str, object]] = []

        yield {
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": created,
                "status": "in_progress",
                "error": None,
                "incomplete_details": None,
                "model": model,
                "output": [],
                "parallel_tool_calls": False,
            },
        }

        try:
            if image_info:
                image_data, mime_type = image_info
                stream = self.stream_image_edit(prompt, [(image_data, "image.png", mime_type)], model, 1)
            else:
                stream = self.stream_image_generation(prompt, model, 1, size="1:1")

            for chunk in stream:
                data = chunk.get("data")
                if not isinstance(data, list) or not data:
                    continue
                output = self._build_image_response_output(
                    prompt,
                    {
                        "created": chunk.get("created"),
                        "data": data,
                    },
                )
                if output:
                    final_output = output
        except ImageGenerationError as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        if not final_output:
            raise HTTPException(status_code=502, detail={"error": "image generation failed"})

        final_item = dict(final_output[0])
        final_item["id"] = item_id
        yield {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": final_item,
        }
        yield {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": created,
                "status": "completed",
                "error": None,
                "incomplete_details": None,
                "model": model,
                "output": [final_item],
                "parallel_tool_calls": False,
            },
        }

    @staticmethod
    def _format_image_result(
            result: dict[str, object],
            prompt: str,
            response_format: str,
            base_url: str | None = None,
    ) -> dict[str, object]:
        created = result.get("created")
        data = result.get("data")
        formatted_items: list[dict[str, object]] = []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                revised_prompt = str(item.get("revised_prompt") or prompt).strip() or prompt
                b64_json = str(item.get("b64_json") or "").strip()
                if response_format == "b64_json":
                    if b64_json:
                        formatted_items.append({"b64_json": b64_json, "revised_prompt": revised_prompt})
                    continue
                if not b64_json:
                    continue
                image_data = base64.b64decode(b64_json)
                formatted_items.append(
                    {"url": _save_image_bytes(image_data, base_url), "revised_prompt": revised_prompt})
        return {"created": created, "data": formatted_items}

    @staticmethod
    def _extract_image_data_urls(markdown_content: str) -> list[str]:
        return re.findall(r"!\[[^\]]*\]\((data:image/[^;]+;base64,[^)]+)\)", markdown_content or "")

    def _stream_result_from_markdown(
            self,
            markdown_content: str,
            prompt: str,
            response_format: str,
            base_url: str | None = None,
            created: int | None = None,
    ) -> dict[str, object] | None:
        data_urls = self._extract_image_data_urls(markdown_content)
        if not data_urls:
            return None
        raw_items: list[dict[str, object]] = []
        for data_url in data_urls:
            header, _, data = data_url.partition(",")
            mime_type = header.split(";")[0].removeprefix("data:") or "image/png"
            raw_items.append({
                "b64_json": data,
                "revised_prompt": prompt,
                "mime_type": mime_type,
            })
        return self._format_image_result(
            {"created": created or int(time.time()), "data": raw_items},
            prompt,
            response_format,
            base_url,
        )

    @staticmethod
    def _progress_chunk(
            model: str,
            index: int,
            total: int,
            created: int | None = None,
            progress_text: str = "",
            upstream_event_type: str = "",
    ) -> dict[str, object]:
        return {
            "object": "image.generation.chunk",
            "created": created or int(time.time()),
            "model": model,
            "index": index,
            "total": total,
            "progress_text": progress_text,
            "upstream_event_type": upstream_event_type,
            "data": [],
        }

    def _stream_single_image_result(
            self,
            prompt: str,
            model: str,
            index: int,
            total: int,
            request_token: str,
            size: str | None = None,
            response_format: str = "b64_json",
            base_url: str | None = None,
            images: list[str] | None = None,
    ) -> Iterator[dict[str, object]]:
        stream = self._new_backend(request_token).stream_image_chat_completions(
            prompt=prompt,
            model=model,
            size=size,
            images=images or None,
        )
        for chunk in stream:
            created = int(chunk.get("created") or time.time()) if isinstance(chunk, dict) else int(time.time())
            choices = chunk.get("choices") if isinstance(chunk, dict) else None
            first_choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
            delta = first_choice.get("delta") if isinstance(first_choice.get("delta"), dict) else {}
            content = str(delta.get("content") or "")
            finish_reason = str(first_choice.get("finish_reason") or "")

            if "upstream_event" in chunk:
                upstream_event = chunk.get("upstream_event")
                upstream_event_type = ""
                if isinstance(upstream_event, dict):
                    upstream_event_type = str(upstream_event.get("type") or "")
                yield self._progress_chunk(model, index, total, created, content, upstream_event_type)
                continue

            formatted_result = self._stream_result_from_markdown(content, prompt, response_format, base_url, created)
            if formatted_result:
                yield {
                    "object": "image.generation.result",
                    "created": formatted_result.get("created"),
                    "model": model,
                    "index": index,
                    "total": total,
                    "data": formatted_result.get("data") if isinstance(formatted_result.get("data"), list) else [],
                }
                continue

            if finish_reason:
                yield {
                    "object": "image.generation.done",
                    "created": created,
                    "model": model,
                    "index": index,
                    "total": total,
                    "data": [],
                    "finish_reason": finish_reason,
                }

    def _iter_generated_images_with_pool(
            self,
            prompt: str,
            model: str,
            n: int,
            size: str | None = None,
            response_format: str = "b64_json",
            base_url: str | None = None,
    ) -> Iterator[dict[str, object]]:
        emitted = False
        last_error = ""
        for index in range(1, n + 1):
            while True:
                try:
                    request_token = self.account_service.get_available_access_token()
                except RuntimeError as exc:
                    last_error = str(exc)
                    logger.warning({
                        "event": "image_generate_stop",
                        "index": index,
                        "total": n,
                        "error": last_error,
                    })
                    if emitted:
                        return
                    raise ImageGenerationError(last_error or "image generation failed") from exc

                logger.info({
                    "event": "image_generate_start",
                    "request_token": request_token,
                    "model": model,
                    "index": index,
                    "total": n,
                })
                try:
                    result = self._format_image_result(self._new_backend(request_token).images_generations(
                        prompt=prompt,
                        model=model,
                        size=size,
                        response_format="b64_json",
                    ), prompt, response_format, base_url)
                    account = self.account_service.mark_image_result(request_token, success=True)
                    data = result.get("data")
                    image_items = [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
                    logger.info({
                        "event": "image_generate_success",
                        "request_token": request_token,
                        "quota": account.get("quota") if account else "unknown",
                        "status": account.get("status") if account else "unknown",
                    })
                    if image_items:
                        emitted = True
                        yield {
                            "created": result.get("created"),
                            "data": image_items,
                        }
                    break
                except Exception as exc:
                    account = self.account_service.mark_image_result(request_token, success=False)
                    message = str(exc)
                    last_error = message
                    logger.warning({
                        "event": "image_generate_fail",
                        "request_token": request_token,
                        "error": message,
                        "quota": account.get("quota") if account else "unknown",
                        "status": account.get("status") if account else "unknown",
                    })
                    if is_token_invalid_error(message):
                        self.account_service.remove_token(request_token)
                        logger.warning({
                            "event": "image_generate_remove_invalid_token",
                            "request_token": request_token,
                        })
                        continue
                    break

        if not emitted:
            raise ImageGenerationError(last_error or "image generation failed")

    def generate_with_pool(self, prompt: str, model: str, n: int, size: str | None = None, response_format: str = "b64_json",
                           base_url: str = None):
        created = None
        image_items: list[dict[str, object]] = []
        for result in self._iter_generated_images_with_pool(prompt, model, n, size, response_format, base_url):
            if created is None:
                created = result.get("created")
            data = result.get("data")
            if isinstance(data, list):
                image_items.extend(item for item in data if isinstance(item, dict))
        return {
            "created": created,
            "data": image_items,
        }

    def stream_image_generation(
            self,
            prompt: str,
            model: str,
            n: int,
            size: str | None = None,
            response_format: str = "b64_json",
            base_url: str | None = None,
    ) -> Iterator[dict[str, object]]:
        last_error = ""
        emitted = False
        for index in range(1, n + 1):
            while True:
                try:
                    request_token = self.account_service.get_available_access_token()
                except RuntimeError as exc:
                    last_error = str(exc)
                    logger.warning({
                        "event": "image_generate_stream_stop",
                        "index": index,
                        "total": n,
                        "error": last_error,
                    })
                    if emitted:
                        return
                    raise ImageGenerationError(last_error or "image generation failed") from exc

                logger.info({
                    "event": "image_generate_stream_start",
                    "request_token": request_token,
                    "model": model,
                    "index": index,
                    "total": n,
                })
                emitted_for_request = False
                has_result = False
                try:
                    for chunk in self._stream_single_image_result(
                            prompt,
                            model,
                            index,
                            n,
                            request_token,
                            size,
                            response_format,
                            base_url,
                    ):
                        emitted = True
                        emitted_for_request = True
                        data = chunk.get("data")
                        if isinstance(data, list) and data:
                            has_result = True
                        yield chunk
                    if not has_result:
                        last_error = "image generation failed"
                        raise ImageGenerationError(last_error)
                    account = self.account_service.mark_image_result(request_token, success=True)
                    logger.info({
                        "event": "image_generate_stream_success",
                        "request_token": request_token,
                        "quota": account.get("quota") if account else "unknown",
                        "status": account.get("status") if account else "unknown",
                        "has_result": has_result,
                    })
                    break
                except Exception as exc:
                    account = self.account_service.mark_image_result(request_token, success=False)
                    message = str(exc)
                    last_error = message
                    logger.warning({
                        "event": "image_generate_stream_fail",
                        "request_token": request_token,
                        "error": message,
                        "quota": account.get("quota") if account else "unknown",
                        "status": account.get("status") if account else "unknown",
                    })
                    if not emitted_for_request and is_token_invalid_error(message):
                        self.account_service.remove_token(request_token)
                        logger.warning({
                            "event": "image_generate_stream_remove_invalid_token",
                            "request_token": request_token,
                        })
                        continue
                    raise ImageGenerationError(last_error or "image generation failed") from exc

    def edit_with_pool(
            self,
            prompt: str,
            images: Iterable[tuple[bytes, str, str]],
            model: str,
            n: int,
            size: str | None = None,
            response_format: str = "b64_json",
            base_url: str = None,
    ):
        created = None
        image_items: list[dict[str, object]] = []
        last_error = ""
        normalized_images = list(images)
        if not normalized_images:
            raise ImageGenerationError("image is required")

        for index in range(1, n + 1):
            while True:
                try:
                    request_token = self.account_service.get_available_access_token()
                except RuntimeError as exc:
                    last_error = str(exc)
                    logger.warning({
                        "event": "image_edit_stop",
                        "index": index,
                        "total": n,
                        "error": last_error,
                    })
                    break

                logger.info({
                    "event": "image_edit_start",
                    "request_token": request_token,
                    "model": model,
                    "index": index,
                    "total": n,
                    "image_count": len(normalized_images),
                })
                try:
                    result = self._format_image_result(self._new_backend(request_token).images_edits(
                        image=self._encode_images(normalized_images),
                        prompt=prompt,
                        model=model,
                        size=size,
                        response_format="b64_json",
                    ), prompt, response_format, base_url)
                    account = self.account_service.mark_image_result(request_token, success=True)
                    if created is None:
                        created = result.get("created")
                    data = result.get("data")
                    if isinstance(data, list):
                        image_items.extend(item for item in data if isinstance(item, dict))
                    logger.info({
                        "event": "image_edit_success",
                        "request_token": request_token,
                        "quota": account.get("quota") if account else "unknown",
                        "status": account.get("status") if account else "unknown",
                    })
                    break
                except Exception as exc:
                    account = self.account_service.mark_image_result(request_token, success=False)
                    message = str(exc)
                    last_error = message
                    logger.warning({
                        "event": "image_edit_fail",
                        "request_token": request_token,
                        "error": message,
                        "quota": account.get("quota") if account else "unknown",
                        "status": account.get("status") if account else "unknown",
                    })
                    if is_token_invalid_error(message):
                        self.account_service.remove_token(request_token)
                        logger.warning({
                            "event": "image_edit_remove_invalid_token",
                            "request_token": request_token,
                        })
                        continue
                    break

        if not image_items:
            raise ImageGenerationError(last_error or "image edit failed")

        return {
            "created": created,
            "data": image_items,
        }

    def stream_image_edit(
            self,
            prompt: str,
            images: Iterable[tuple[bytes, str, str]],
            model: str,
            n: int,
            size: str | None = None,
            response_format: str = "b64_json",
            base_url: str | None = None,
    ) -> Iterator[dict[str, object]]:
        last_error = ""
        emitted = False
        normalized_images = list(images)
        if not normalized_images:
            raise ImageGenerationError("image is required")
        encoded_images = self._encode_images(normalized_images)

        for index in range(1, n + 1):
            while True:
                try:
                    request_token = self.account_service.get_available_access_token()
                except RuntimeError as exc:
                    last_error = str(exc)
                    logger.warning({
                        "event": "image_edit_stream_stop",
                        "index": index,
                        "total": n,
                        "error": last_error,
                    })
                    if emitted:
                        return
                    raise ImageGenerationError(last_error or "image edit failed") from exc

                logger.info({
                    "event": "image_edit_stream_start",
                    "request_token": request_token,
                    "model": model,
                    "index": index,
                    "total": n,
                    "image_count": len(normalized_images),
                })
                emitted_for_request = False
                has_result = False
                try:
                    for chunk in self._stream_single_image_result(
                            prompt=prompt,
                            model=model,
                            index=index,
                            total=n,
                            request_token=request_token,
                            size=size,
                            response_format=response_format,
                            base_url=base_url,
                            images=encoded_images,
                    ):
                        emitted = True
                        emitted_for_request = True
                        data = chunk.get("data")
                        if isinstance(data, list) and data:
                            has_result = True
                        yield chunk
                    if not has_result:
                        last_error = "image edit failed"
                        raise ImageGenerationError(last_error)
                    account = self.account_service.mark_image_result(request_token, success=True)
                    logger.info({
                        "event": "image_edit_stream_success",
                        "request_token": request_token,
                        "quota": account.get("quota") if account else "unknown",
                        "status": account.get("status") if account else "unknown",
                        "has_result": has_result,
                    })
                    break
                except Exception as exc:
                    account = self.account_service.mark_image_result(request_token, success=False)
                    message = str(exc)
                    last_error = message
                    logger.warning({
                        "event": "image_edit_stream_fail",
                        "request_token": request_token,
                        "error": message,
                        "quota": account.get("quota") if account else "unknown",
                        "status": account.get("status") if account else "unknown",
                    })
                    if not emitted_for_request and is_token_invalid_error(message):
                        self.account_service.remove_token(request_token)
                        logger.warning({
                            "event": "image_edit_stream_remove_invalid_token",
                            "request_token": request_token,
                        })
                        continue
                    raise ImageGenerationError(last_error or "image edit failed") from exc

    @staticmethod
    def _stream_completion_response(result: dict[str, object]) -> Iterator[dict[str, object]]:
        completion_id = str(result.get("id") or f"chatcmpl-{uuid.uuid4().hex}")
        created = int(result.get("created") or time.time())
        model = str(result.get("model") or "auto")
        choices = result.get("choices")
        first_choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        message = first_choice.get("message") if isinstance(first_choice.get("message"), dict) else {}
        content = str(message.get("content") or "")
        finish_reason = str(first_choice.get("finish_reason") or "stop")

        yield {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": content},
                "finish_reason": None,
            }],
        }
        yield {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": finish_reason,
            }],
        }

    def _create_image_chat_completion(self, body: dict[str, object]) -> dict[str, object]:
        model = str(body.get("model") or "gpt-image-2").strip() or "gpt-image-2"
        n = parse_image_count(body.get("n"))
        prompt = extract_chat_prompt(body)
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "prompt is required"})

        image_infos = extract_chat_image(body)
        try:
            if image_infos:
                images = [(data, f"image_{idx}.png", mime) for idx, (data, mime) in enumerate(image_infos, start=1)]
                image_result = self.edit_with_pool(prompt, images, model, n)
            else:
                image_result = self.generate_with_pool(prompt, model, n)
        except ImageGenerationError as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        return build_chat_image_completion(model, image_result)

    def _stream_image_chat_completion(self, body: dict[str, object]) -> Iterator[dict[str, object]]:
        model = str(body.get("model") or "gpt-image-2").strip() or "gpt-image-2"
        n = parse_image_count(body.get("n"))
        if n != 1:
            result = self._create_image_chat_completion(body)
            yield from self._stream_completion_response(result)
            return

        prompt = extract_chat_prompt(body)
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "prompt is required"})

        image_infos = extract_chat_image(body)
        encoded_images = []
        if image_infos:
            images = [(data, f"image_{idx}.png", mime) for idx, (data, mime) in enumerate(image_infos, start=1)]
            encoded_images = self._encode_images(images)

        last_error = ""
        while True:
            try:
                request_token = self.account_service.get_available_access_token()
            except RuntimeError as exc:
                raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

            logger.info({
                "event": "image_stream_start",
                "request_token": request_token,
                "model": model,
            })
            emitted = False
            try:
                stream = self._new_backend(request_token).stream_image_chat_completions(
                    prompt=prompt,
                    model=model,
                    images=encoded_images or None,
                )
                for chunk in stream:
                    emitted = True
                    yield chunk
                account = self.account_service.mark_image_result(request_token, success=True)
                logger.info({
                    "event": "image_stream_success",
                    "request_token": request_token,
                    "quota": account.get("quota") if account else "unknown",
                    "status": account.get("status") if account else "unknown",
                })
                return
            except Exception as exc:
                account = self.account_service.mark_image_result(request_token, success=False)
                message = str(exc)
                last_error = message
                logger.warning({
                    "event": "image_stream_fail",
                    "request_token": request_token,
                    "error": message,
                    "quota": account.get("quota") if account else "unknown",
                    "status": account.get("status") if account else "unknown",
                })
                if not emitted and is_token_invalid_error(message):
                    self.account_service.remove_token(request_token)
                    logger.warning({
                        "event": "image_stream_remove_invalid_token",
                        "request_token": request_token,
                    })
                    continue
                raise HTTPException(status_code=502, detail={"error": last_error or "image generation failed"}) from exc

    def _create_text_chat_completion(self, body: dict[str, object]) -> dict[str, object]:
        model = str(body.get("model") or "auto").strip() or "auto"
        messages = self._chat_messages_from_body(body)
        if is_minimax_model(model):
            try:
                return MinimaxBackendAPI().chat_completions(messages=messages, model=model, stream=False)
            except Exception as exc:
                raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc
        try:
            return self._new_backend(self._get_text_access_token()).chat_completions(messages=messages, model=model, stream=False)
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

    def create_chat_completion(self, body: dict[str, object]) -> dict[str, object]:
        if is_image_chat_request(body):
            return self._create_image_chat_completion(body)
        return self._create_text_chat_completion(body)

    def stream_chat_completion(self, body: dict[str, object]) -> Iterator[dict[str, object]]:
        if is_image_chat_request(body):
            yield from self._stream_image_chat_completion(body)
            return

        model = str(body.get("model") or "auto").strip() or "auto"
        messages = self._chat_messages_from_body(body)
        if is_minimax_model(model):
            try:
                yield from MinimaxBackendAPI().chat_completions(messages=messages, model=model, stream=True)
            except Exception as exc:
                raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc
            return
        try:
            yield from self._new_backend(self._get_text_access_token()).chat_completions(messages=messages, model=model, stream=True)
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

    def create_image_completion(self, body: dict[str, object]) -> dict[str, object]:
        if not is_image_chat_request(body):
            raise HTTPException(
                status_code=400,
                detail={"error": "only image generation requests are supported on this endpoint"},
            )
        return self._create_image_chat_completion(body)

    def _get_response_access_token(self, body: dict[str, object]) -> str:
        return self.account_service.get_available_access_token()

    def stream_response(self, body: dict[str, object]) -> Iterator[dict[str, object]]:
        if self._is_text_response_request(body):
            yield from self._stream_text_response(body)
            return
        if not self._is_codex_image_response_request(body):
            yield from self._stream_token_image_response(body)
            return
        try:
            access_token = self._get_response_access_token(body)
            yield from self._new_backend(access_token).responses(
                input=body.get("input") or "",
                model=str(body.get("model") or "gpt-5.4").strip() or "gpt-5.4",
                tools=body.get("tools") if isinstance(body.get("tools"), list) else None,
                instructions=str(body.get("instructions") or "you are a helpful assistant"),
                tool_choice=body.get("tool_choice") or "auto",
                stream=True,
                store=bool(body.get("store")),
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

    def create_response(self, body: dict[str, object]) -> dict[str, object]:
        if self._is_text_response_request(body):
            return self._create_text_response(body)
        if not self._is_codex_image_response_request(body):
            return self._create_token_image_response(body)
        try:
            access_token = self._get_response_access_token(body)
            return self._new_backend(access_token).responses(
                input=body.get("input") or "",
                model=str(body.get("model") or "gpt-5.4").strip() or "gpt-5.4",
                tools=body.get("tools") if isinstance(body.get("tools"), list) else None,
                instructions=str(body.get("instructions") or "you are a helpful assistant"),
                tool_choice=body.get("tool_choice") or "auto",
                stream=False,
                store=bool(body.get("store")),
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc
