"""
Codex OAuth Provider — uses 9router Codex tokens to call chatgpt.com/backend-api/codex/responses.

This is the EXACT same endpoint 9router uses. No api.openai.com — the tokens
work with chatgpt.com's Codex Responses API. No 24KB limit, native tool calling.

Format: OpenAI Responses API (not chat/completions).
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Iterator

from curl_cffi import requests

from services.config import config
from services.account_service import account_service
from utils.log import logger

CODEX_URL = "https://chatgpt.com/backend-api/codex/responses"
CODEX_DEFAULT_MODEL = "gpt-5.5"  # First try; fallback chain: 5.5 → 5.4 → 5.3-codex
CODEX_AUTO_FALLBACK = ["gpt-5.5", "gpt-5.4", "gpt-5.3-codex"]
CODEX_HEADERS = {
    "originator": "codex-cli",
    "User-Agent": "codex-cli/1.0.18 (Windows; x64)",
    "Content-Type": "application/json",
    "Accept": "text/event-stream",
}


def _is_openai_api_only(token: str) -> bool:
    """Check if token only works with api.openai.com (not chatgpt.com).
    Detected by: no user_id set (never successfully refreshed from chatgpt.com).
    """
    return False  # Let the account's refresh status determine eligibility


def _chat_to_responses_input(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
                              tool_choice: Any = None, instructions: str | None = None) -> dict[str, Any]:
    """Convert OpenAI chat format → Codex Responses API format.

    Handles the full conversation flow including tool calls:
    - system → instructions
    - user → input_item (role="user")
    - assistant (text) → input_item (role="assistant")
    - assistant (tool_calls) → function_call items
    - tool (result) → function_call_output items
    """
    body: dict[str, Any] = {"stream": True}

    input_items: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, list):
            text_parts = []
            image_parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(str(part.get("text", "")))
                    elif part.get("type") == "image_url":
                        url = part.get("image_url", {}).get("url", "")
                        if url.startswith("data:"):
                            header, b64 = url.split(",", 1)
                            mime = header.split(";")[0].replace("data:", "")
                            image_parts.append({"type": "input_image", "image_url": url})
                        elif url:
                            image_parts.append({"type": "input_image", "image_url": url})
                    elif part.get("type") == "input_image":
                        image_parts.append(part)
            content = " ".join(text_parts) if text_parts else ""
            # Build Responses-format content with images
            if image_parts:
                items = []
                if content:
                    items.append({"type": "input_text", "text": content})
                for img in image_parts:
                    img_url = img.get("image_url", "")
                    if isinstance(img_url, str) and img_url.startswith("data:"):
                        # Inline base64 image
                        items.append({"type": "input_image", "image_url": img_url})
                    elif isinstance(img_url, str):
                        items.append({"type": "input_image", "image_url": img_url})
                input_items.append({"role": "user", "content": items})
                continue
        else:
            content = str(content or "")

        if role == "system":
            instructions = (instructions or "") + "\n" + content
            continue

        # Tool call result → function_call_output in Responses API
        if role == "tool":
            tool_call_id = str(msg.get("tool_call_id") or "")
            input_items.append({
                "type": "function_call_output",
                "call_id": tool_call_id,
                "output": content,
            })
            continue

        # Assistant message with tool_calls → function_call items
        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                # First, add any text content the assistant said before calling tools
                if content and content.strip():
                    input_items.append({"role": "assistant", "content": content})
                # Then add each function_call as an item
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        fn = tc.get("function") or {}
                        input_items.append({
                            "type": "function_call",
                            "call_id": str(tc.get("id") or ""),
                            "name": str(fn.get("name") or ""),
                            "arguments": str(fn.get("arguments") or ""),
                        })
                continue
            # Regular assistant text response
            input_items.append({"role": "assistant", "content": content})
            continue

        # User message
        if role == "user":
            input_items.append({"role": "user", "content": content})
        else:
            input_items.append({"role": "user", "content": content})

    body["input"] = input_items

    if instructions and instructions.strip():
        body["instructions"] = instructions.strip()

    if tools:
        body["tools"] = [{
            "type": "function",
            "name": t.get("function", {}).get("name", ""),
            "description": t.get("function", {}).get("description", ""),
            "parameters": t.get("function", {}).get("parameters", {}),
        } for t in tools if isinstance(t, dict)]

    if tool_choice:
        body["tool_choice"] = tool_choice

    return body


def _responses_to_chat_chunk(event: dict[str, Any], model: str, completion_id: str, created: int) -> dict[str, Any] | None:
    """Convert Codex Responses SSE event → OpenAI chat completion chunk."""
    event_type = event.get("type", "")

    if event_type == "response.output_text.delta":
        delta = event.get("delta", "")
        return {
            "id": completion_id, "object": "chat.completion.chunk",
            "created": created, "model": model,
            "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
        }

    if event_type == "response.output_item.done":
        item = event.get("item", {})
        if item.get("type") == "function_call":
            return {
                "id": completion_id, "object": "chat.completion.chunk",
                "created": created, "model": model,
                "choices": [{"index": 0, "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": item.get("call_id", ""),
                        "type": "function",
                        "function": {
                            "name": item.get("name", ""),
                            "arguments": item.get("arguments", ""),
                        },
                    }]
                }, "finish_reason": None}],
            }

    if event_type == "response.completed":
        return {
            "id": completion_id, "object": "chat.completion.chunk",
            "created": created, "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }

    if event_type == "error":
        return {
            "id": completion_id, "object": "chat.completion.chunk",
            "created": created, "model": model,
            "choices": [{"index": 0, "delta": {
                "content": f"Codex error: {event.get('message', 'unknown')}"
            }, "finish_reason": "stop"}],
        }

    return None


class CodexOAuthProvider:
    """Direct Codex OAuth — no 9router dependency."""

    def chat_completions(
        self,
        access_token: str,
        messages: list[dict[str, Any]],
        model: str = "auto",
        stream: bool = True,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        **kwargs,
    ) -> dict[str, Any] | Iterator[dict[str, Any]]:
        """Call Codex Responses API with OAuth token."""

        instructions = None
        base_body = _chat_to_responses_input(messages, tools, tool_choice, instructions)

        # Resolve model — auto always uses full fallback chain, ignoring enabled_models.
        # Filtering enabled_models is for HA /v1/models display only; rotation should
        # always try every model in CODEX_AUTO_FALLBACK so it can recover from per-model
        # outages even when the user has unticked some entries in the UI.
        is_auto = not model or model == "auto"
        if is_auto:
            models_to_try = list(CODEX_AUTO_FALLBACK)
        else:
            models_to_try = [model]

        last_error = ""
        for try_idx, try_model in enumerate(models_to_try):
            if try_idx > 0:
                logger.warning({"event": "codex_fallback", "from": models_to_try[try_idx-1],
                                "to": try_model})

            body = dict(base_body)  # fresh copy each attempt
            resolved_model = try_model

            # Parse 9router effort/review suffixes from model name
            _EFFORT_LEVELS = {"xhigh", "high", "medium", "low", "none"}
            _suffixes = resolved_model.split("-")
            _effort = None
            _review = False
            _seen: list[str] = []
            for _s in reversed(_suffixes):
                if _s == "review":
                    _review = True
                elif _s in _EFFORT_LEVELS and _effort is None:
                    _effort = _s
                else:
                    _seen.insert(0, _s)
            if _effort or _review:
                resolved_model = "-".join(_seen)
                if _effort:
                    body["reasoning"] = {"effort": _effort}
                if _review:
                    body["include"] = body.get("include", []) or []
                    if isinstance(body["include"], list):
                        body["include"].append("reasoning")

            body["model"] = resolved_model
            body["store"] = False
            body["stream"] = True
            if "instructions" not in body or not body.get("instructions"):
                body["instructions"] = "You are a helpful assistant."

            for key in ("temperature", "top_p", "frequency_penalty", "presence_penalty",
                         "n", "seed", "logprobs", "top_logprobs", "user",
                         "stream_options", "safety_identifier", "metadata",
                         "parallel_tool_calls"):
                body.pop(key, None)

            headers = dict(CODEX_HEADERS)
            headers["Authorization"] = f"Bearer {access_token}"

            logger.info({
                "event": "codex_request",
                "model": resolved_model,
                "try": try_idx + 1,
                "message_count": len(messages),
            })

            try:
                resp = requests.post(
                    CODEX_URL, headers=headers, json=body,
                    timeout=300, stream=True,
                    impersonate="chrome110",
                )

                if resp.status_code == 401:
                    # Try OAuth refresh once before giving up on this token
                    refreshed = _try_refresh_token(access_token)
                    if refreshed:
                        access_token = refreshed
                        headers["Authorization"] = f"Bearer {access_token}"
                        # Re-issue the same request with the new token
                        try:
                            resp.close()
                        except Exception:
                            pass
                        resp = requests.post(
                            CODEX_URL, headers=headers, json=body,
                            timeout=300, stream=True,
                            impersonate="chrome110",
                        )
                        if resp.status_code == 401:
                            # Refresh succeeded but the new token is still rejected → unrecoverable
                            account_service.update_account(access_token, {"status": "disabled"})
                            logger.warning({"event": "codex_account_disabled",
                                            "reason": "401_after_refresh"})
                            raise RuntimeError("Codex OAuth token expired (refresh did not help)")
                    else:
                        # Refresh impossible (no refresh_token) or transient — disable so the
                        # rotation pool stops handing this token out instead of looping.
                        account_service.update_account(access_token, {"status": "disabled"})
                        logger.warning({"event": "codex_account_disabled",
                                        "reason": "401_no_refresh"})
                        raise RuntimeError("Codex OAuth token expired")
                if resp.status_code >= 400:
                    error_text = ""
                    try:
                        raw = b""
                        for chunk in resp.iter_content(chunk_size=8192):
                            if chunk:
                                raw += chunk if isinstance(chunk, bytes) else chunk.encode()
                                if len(raw) > 10000:
                                    break
                        if raw:
                            error_text = raw.decode("utf-8", errors="ignore")[:1000]
                    except Exception:
                        try:
                            error_text = (resp.text or "")[:1000]
                        except Exception:
                            pass
                    resp_headers = dict(resp.headers) if hasattr(resp, 'headers') else {}
                    logger.error({
                        "event": "codex_upstream_error",
                        "status": resp.status_code,
                        "model": resolved_model,
                        "error": error_text,
                        "headers": {k: str(v)[:200] for k, v in resp_headers.items()},
                    })
                    # Auto-mark account state for quota/forbidden errors so the pool
                    # rotates away from this token without manual intervention.
                    err_lower = error_text.lower()
                    if resp.status_code == 403 or "forbidden" in err_lower:
                        account_service.update_account(access_token, {"status": "disabled"})
                        logger.warning({"event": "codex_account_disabled",
                                        "reason": "403_forbidden"})
                    elif resp.status_code == 429 or "quota" in err_lower or "rate" in err_lower:
                        account_service.update_account(access_token, {"status": "limited"})
                        logger.warning({"event": "codex_account_limited",
                                        "reason": "429_quota"})
                    msg = f"Codex error {resp.status_code}: {error_text[:200]}"
                    if try_idx < len(models_to_try) - 1:
                        last_error = msg
                        continue
                    raise RuntimeError(msg)

                # Success
                if stream:
                    return self._stream_response(resp, resolved_model)
                else:
                    text = ""
                    tool_calls = []
                    for chunk in self._stream_response(resp, resolved_model):
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        text += delta.get("content", "")
                        if delta.get("tool_calls"):
                            tool_calls.extend(delta["tool_calls"])
                        if delta.get("finish_reason") == "stop":
                            break

                    message = {"role": "assistant", "content": text}
                    if tool_calls:
                        message["tool_calls"] = tool_calls

                    from services.protocol.openai_v1_chat_complete import count_message_tokens, count_text_tokens

                    return {
                        "id": f"chatcmpl-{uuid.uuid4().hex}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": resolved_model,
                        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                        "usage": {
                            "prompt_tokens": count_message_tokens(messages, resolved_model),
                            "completion_tokens": count_text_tokens(text, resolved_model),
                            "total_tokens": count_message_tokens(messages, resolved_model) + count_text_tokens(text, resolved_model),
                        },
                    }

            except requests.RequestsError as exc:
                msg = f"Codex connection failed: {exc}"
                if try_idx < len(models_to_try) - 1:
                    last_error = msg
                    continue
                raise RuntimeError(msg) from exc

        raise RuntimeError(f"All Codex models failed: {last_error}")

    def _stream_response(self, response, model: str) -> Iterator[dict[str, Any]]:
        """Convert Codex SSE → OpenAI chat completion chunks (dicts)."""
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())
        sent_role = False

        try:
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="ignore") if isinstance(raw_line, bytes) else str(raw_line)
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                chunk = _responses_to_chat_chunk(event, model, completion_id, created)
                if chunk:
                    if not sent_role and chunk["choices"][0]["delta"].get("content"):
                        chunk["choices"][0]["delta"]["role"] = "assistant"
                        sent_role = True
                    yield chunk

        except Exception as exc:
            logger.error({"event": "codex_stream_error", "error": str(exc)})

        if not sent_role:
            yield {
                "id": completion_id, "object": "chat.completion.chunk",
                "created": created, "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
            }
        yield {
            "id": completion_id, "object": "chat.completion.chunk",
            "created": created, "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }

    def _non_stream_response(self, response, model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Handle non-streaming Codex response."""
        data = response.json()
        output_text = ""
        tool_calls = []

        for item in data.get("output", []):
            if item.get("type") == "message":
                for content_item in item.get("content", []):
                    if content_item.get("type") == "output_text":
                        output_text += content_item.get("text", "")
            elif item.get("type") == "function_call":
                tool_calls.append({
                    "id": item.get("call_id", ""),
                    "type": "function",
                    "function": {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", ""),
                    },
                })

        message = {"role": "assistant", "content": output_text}
        if tool_calls:
            message["tool_calls"] = tool_calls

        from services.protocol.openai_v1_chat_complete import count_message_tokens, count_text_tokens

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": count_message_tokens(messages, model),
                "completion_tokens": count_text_tokens(output_text, model),
                "total_tokens": count_message_tokens(messages, model) + count_text_tokens(output_text, model),
            },
        }

    def get_token_for_request(self, exclude_tokens: set[str] | None = None) -> str:
        """Get next available JWT token for Codex OAuth. Accepts any JWT token."""
        excluded = set(exclude_tokens or set())
        with account_service._lock:
            all_items = list(account_service._accounts.values())
            logger.info({
                "event": "codex_debug",
                "total_accounts": len(all_items),
                "statuses": [i.get("status") for i in all_items],
                "types": [i.get("type") for i in all_items],
                "has_jwt": sum(1 for i in all_items if str(i.get("access_token","")).startswith("eyJ")),
            })
            candidates = [
                token
                for item in all_items
                if item.get("status") not in ("disabled", "error")
                and (token := item.get("access_token") or "")
                and token.startswith("eyJ")
                and token not in excluded
                # Skip tokens that only work with api.openai.com (web session)
                and not _is_openai_api_only(token)
            ]
            if not candidates:
                raise RuntimeError("No Codex OAuth tokens available. Add via OAuth login or import 9router backup.")
            token = candidates[account_service._index % len(candidates)]
            account_service._index += 1
            return token


def _try_refresh_token(stale_access_token: str) -> str | None:
    """Refresh a Codex OAuth access_token using its stored refresh_token.

    Returns the new access_token on success, None if no refresh_token is stored
    or the refresh failed transiently. On unrecoverable refresh errors
    (refresh_token_reused / invalid_grant) the account is marked disabled
    so the pool stops handing it out.
    """
    if not stale_access_token:
        return None
    with account_service._lock:
        item = account_service._accounts.get(stale_access_token)
        if not item:
            return None
        refresh_token = item.get("refresh_token") or ""
    if not refresh_token:
        return None

    from services.codex_token_refresh import refresh_codex_token
    result = refresh_codex_token(refresh_token)
    if not result:
        return None
    if result.get("error") == "unrecoverable":
        account_service.update_account(stale_access_token, {"status": "disabled"})
        logger.warning({"event": "codex_account_disabled_after_refresh_fail",
                        "code": result.get("code")})
        return None

    new_access = result.get("access_token") or ""
    new_refresh = result.get("refresh_token") or refresh_token
    expires_at = result.get("expires_at") or None
    if not new_access:
        return None

    # Persist new credentials. The access_token is the dict key, so when it
    # rotates we delete the old entry and reinsert under the new key.
    with account_service._lock:
        old = account_service._accounts.pop(stale_access_token, None) or {}
        merged = {**old, "access_token": new_access, "refresh_token": new_refresh,
                  "status": "active"}
        if expires_at:
            merged["expires_at"] = expires_at
        normalized = account_service._normalize_account(merged)
        if normalized is not None:
            account_service._accounts[new_access] = normalized
        account_service._save_accounts()
    logger.info({"event": "codex_token_refreshed"})
    return new_access


# Singleton
codex_oauth = CodexOAuthProvider()
