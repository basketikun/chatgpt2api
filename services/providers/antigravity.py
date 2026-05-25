"""
Antigravity Provider — Google Cloud Companion / Cloud Code API.
Offers Gemini 3+ models with thinking and native tool calling via Google Cloud Companion endpoints.
"""

from __future__ import annotations

import json
import random
import time
import uuid
from typing import Any, Iterator

from curl_cffi import requests

from services.account_service import account_service
from services.providers.gemini_free import _convert_request
from utils.log import logger

# Try daily/sandbox, fall back to production cloudcode-pa
ANTIGRAVITY_BASE_URLS = [
    "https://daily-cloudcode-pa.googleapis.com",
    "https://daily-cloudcode-pa.sandbox.googleapis.com",
    "https://cloudcode-pa.googleapis.com",
]


def generate_project_id() -> str:
    """Generate a random cloudaicompanion project ID (binary style decoy)."""
    adjectives = ["useful", "bright", "swift", "calm", "bold"]
    nouns = ["fuze", "wave", "spark", "flow", "core"]
    return f"{random.choice(adjectives)}-{random.choice(nouns)}-{uuid.uuid4().hex[:5]}"


def generate_session_id() -> str:
    """Generate a stable-looking session ID in binary style."""
    return f"{uuid.uuid4()}{int(time.time() * 1000)}"


def load_code_assist(access_token: str) -> str:
    """Fetch cloudaicompanion project ID from Google Cloud Code API."""
    try:
        resp = requests.post(
            "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "User-Agent": "google-api-nodejs-client/9.15.1",
                "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
                "Client-Metadata": json.dumps({"ideType": "IDE_UNSPECIFIED", "platform": "PLATFORM_UNSPECIFIED", "pluginType": "GEMINI"}),
            },
            json={"metadata": {"ideType": "IDE_UNSPECIFIED", "platform": "PLATFORM_UNSPECIFIED", "pluginType": "GEMINI"}},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            proj = data.get("cloudaicompanionProject")
            if isinstance(proj, dict) and proj.get("id"):
                return str(proj["id"]).strip()
            if isinstance(proj, str):
                return proj.strip()
    except Exception as exc:
        logger.warning({"event": "antigravity_load_code_assist_failed", "error": str(exc)})
    return ""


def _try_refresh_antigravity_token(stale_access_token: str) -> str | None:
    """Refresh Google OAuth token for Antigravity provider and persist it."""
    if not stale_access_token:
        return None
    with account_service._lock:
        item = account_service._accounts.get(stale_access_token)
        if not item:
            return None
        refresh_token = item.get("refresh_token") or ""
        device_id = item.get("device_id") or None
    if not refresh_token:
        return None

    from services.antigravity_token_refresh import refresh_antigravity_token
    result = refresh_antigravity_token(refresh_token, device_id=device_id)
    if not result:
        return None
    if result.get("error") == "unrecoverable":
        account_service.update_account(stale_access_token, {"status": "disabled"})
        logger.warning({"event": "antigravity_account_disabled_after_refresh_fail",
                        "code": result.get("code")})
        return None

    new_access = result.get("access_token") or ""
    new_refresh = result.get("refresh_token") or refresh_token
    expires_at = result.get("expires_at") or None
    if not new_access:
        return None

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
    logger.info({"event": "antigravity_token_refreshed"})
    return new_access


class AntigravityProvider:
    """Antigravity provider using rotated Google Cloud Code companion tokens."""

    def get_token_for_request(self, exclude_tokens: set[str] | None = None) -> dict[str, Any]:
        """Get next available Google OAuth account with type 'antigravity'."""
        excluded = set(exclude_tokens or set())
        with account_service._lock:
            all_items = list(account_service._accounts.values())
            candidates = [
                item
                for item in all_items
                if item.get("status") not in ("disabled", "error")
                and (token := item.get("access_token") or "")
                and token not in excluded
                and "antigravity" in str(item.get("type") or "").split(",")
            ]
            if not candidates:
                raise RuntimeError("No Antigravity accounts available. Please import a 9router backup containing Antigravity connections.")
            
            # Select account and rotate index
            account = candidates[account_service._index % len(candidates)]
            account_service._index += 1
            
            # Auto-refresh if token is expired or close to expiry (within 5 minutes)
            expires_at = account.get("expires_at")
            if expires_at and float(expires_at) < time.time() + 300:
                new_token = _try_refresh_antigravity_token(account.get("access_token"))
                if new_token:
                    fresh_account = account_service.get_account(new_token)
                    if fresh_account:
                        return fresh_account
            return account

    def chat_completions(
        self,
        account: dict[str, Any],
        messages: list[dict[str, Any]],
        model: str = "gemini-3.1-pro-high",
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        **kwargs,
    ) -> dict[str, Any] | Iterator[dict[str, Any]]:
        """Call Antigravity streamGenerateContent / generateContent."""
        access_token = account["access_token"]
        
        # Load or generate project ID — NEVER use email (causes 403 CONSUMER_INVALID)
        project_id = account.get("project_id") or ""
        if not str(project_id).strip():
            # Try fetching the real GCP project ID from loadCodeAssist API
            project_id = load_code_assist(access_token)
            if project_id:
                account_service.update_account(access_token, {"project_id": project_id})
            else:
                # Generate a decoy — will fail but allows graceful error vs email 403
                project_id = generate_project_id()

        # Convert OpenAI request structures to Gemini structures
        contents, system_instruction, gemini_tools = _convert_request(messages, tools)

        # Build request envelope
        generation_config: dict[str, Any] = {}
        if temperature is not None:
            generation_config["temperature"] = temperature
        if max_tokens:
            generation_config["maxOutputTokens"] = max_tokens

        transformed_request = {
            "generationConfig": generation_config,
            "contents": contents,
        }
        if system_instruction:
            transformed_request["systemInstruction"] = system_instruction
        if gemini_tools:
            transformed_request["tools"] = gemini_tools
            transformed_request["toolConfig"] = {"functionCallingConfig": {"mode": "VALIDATED"}}

        session_id = generate_session_id()

        body = {
            "project": project_id,
            "model": model,
            "userAgent": "antigravity",
            "requestType": "agent",
            "requestId": f"agent-{uuid.uuid4()}",
            "request": transformed_request,
        }

        # Try base URLs in order
        last_error = ""
        for url_index, base_url in enumerate(ANTIGRAVITY_BASE_URLS):
            action = "streamGenerateContent?alt=sse" if stream else "generateContent"
            url = f"{base_url}/v1internal:{action}"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "antigravity/1.107.0 Windows/x64",
                "x-request-source": "local",
                "X-Machine-Session-Id": session_id,
                "Accept": "text/event-stream" if stream else "application/json",
            }

            logger.info({
                "event": "antigravity_request",
                "url": url,
                "model": model,
                "project": project_id,
                "try": url_index + 1,
            })

            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=body,
                    timeout=300,
                    stream=stream,
                )

                if resp.status_code == 401:
                    # Token invalid/expired — trigger refresh and try again with the new token
                    new_token = _try_refresh_antigravity_token(access_token)
                    if new_token:
                        access_token = new_token
                        headers["Authorization"] = f"Bearer {access_token}"
                        resp = requests.post(
                            url,
                            headers=headers,
                            json=body,
                            timeout=300,
                            stream=stream,
                        )
                        if resp.status_code == 401:
                            account_service.update_account(access_token, {"status": "disabled"})
                            raise RuntimeError("Antigravity OAuth token expired (refresh did not resolve)")
                    else:
                        account_service.update_account(access_token, {"status": "disabled"})
                        raise RuntimeError("Antigravity OAuth token expired")

                if resp.status_code == 429:
                    # Quota exhausted — mark account as limited and raise immediately
                    # so combo fallback can try next provider
                    err_text = resp.text[:300]
                    logger.warning({
                        "event": "antigravity_quota_exhausted",
                        "status": 429,
                        "body": err_text,
                    })
                    account_service.update_account(access_token, {"status": "limited"})
                    raise RuntimeError(f"Antigravity quota exhausted (429): {err_text}")

                if resp.status_code >= 400:
                    err_text = resp.text[:500]
                    logger.warning({
                        "event": "antigravity_upstream_error",
                        "status": resp.status_code,
                        "body": err_text,
                    })
                    last_error = f"Antigravity error {resp.status_code}: {err_text}"
                    continue

                if stream:
                    return _parse_antigravity_stream(resp, model)
                else:
                    # Parse non-stream response
                    event = resp.json()
                    resp_obj = event.get("response") or event
                    candidates = resp_obj.get("candidates") or []
                    
                    text = ""
                    pending_tool_calls = []
                    
                    for c in candidates:
                        content = c.get("content") or {}
                        parts = content.get("parts") or []
                        for part in parts:
                            if part.get("text"):
                                text += part["text"]
                            if part.get("functionCall"):
                                pending_tool_calls.append({
                                    "id": f"call_{uuid.uuid4().hex[:12]}",
                                    "type": "function",
                                    "function": {
                                        "name": part["functionCall"].get("name", ""),
                                        "arguments": json.dumps(part["functionCall"].get("args", {}), ensure_ascii=False),
                                    },
                                })

                    message: dict[str, Any] = {"role": "assistant", "content": text}
                    if pending_tool_calls:
                        message["tool_calls"] = pending_tool_calls

                    return {
                        "id": f"chatcmpl-{uuid.uuid4().hex}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                        "usage": {
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                        },
                    }

            except requests.RequestsError as exc:
                last_error = f"Connection failed: {exc}"
                continue

        raise RuntimeError(f"All Antigravity URLs failed: {last_error}")


def _parse_antigravity_stream(response, model: str) -> Iterator[dict[str, Any]]:
    """Parse Antigravity SSE stream -> OpenAI chunks with reasoning & tool calls."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    sent_role = False
    pending_tool_calls: list[dict] = []
    function_index = 0

    try:
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="ignore") if isinstance(raw_line, bytes) else str(raw_line)
            line = line.strip()
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload.strip() == "[DONE]":
                break
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue

            resp_obj = event.get("response") or event
            candidates = resp_obj.get("candidates") or []

            for c in candidates:
                content = c.get("content") or {}
                parts = content.get("parts") or []
                finish_reason = c.get("finishReason")

                for part in parts:
                    has_thought_sig = part.get("thoughtSignature") or part.get("thought_signature")
                    is_thought = part.get("thought") is True

                    text = part.get("text", "")
                    if text:
                        if not sent_role:
                            sent_role = True
                            yield {"id": completion_id, "object": "chat.completion.chunk",
                                   "created": created, "model": model,
                                   "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}

                        delta_payload = {}
                        if has_thought_sig or is_thought:
                            delta_payload["reasoning_content"] = text
                        else:
                            delta_payload["content"] = text

                        yield {"id": completion_id, "object": "chat.completion.chunk",
                               "created": created, "model": model,
                               "choices": [{"index": 0, "delta": delta_payload, "finish_reason": None}]}

                    # Handle function call response
                    func_call = part.get("functionCall")
                    if func_call:
                        pending_tool_calls.append({
                            "index": function_index,
                            "id": f"call_{uuid.uuid4().hex[:12]}",
                            "type": "function",
                            "function": {
                                "name": func_call.get("name", ""),
                                "arguments": json.dumps(func_call.get("args", {}), ensure_ascii=False),
                            },
                        })
                        function_index += 1

                if finish_reason:
                    mapped_reason = finish_reason.lower()
                    if mapped_reason == "stop" and pending_tool_calls:
                        mapped_reason = "tool_calls"

                    if pending_tool_calls:
                        yield {"id": completion_id, "object": "chat.completion.chunk",
                               "created": created, "model": model,
                               "choices": [{"index": 0, "delta": {"tool_calls": pending_tool_calls}, "finish_reason": None}]}
                        pending_tool_calls = []

                    yield {"id": completion_id, "object": "chat.completion.chunk",
                           "created": created, "model": model,
                           "choices": [{"index": 0, "delta": {}, "finish_reason": mapped_reason}]}

        if pending_tool_calls:
            yield {"id": completion_id, "object": "chat.completion.chunk",
                   "created": created, "model": model,
                   "choices": [{"index": 0, "delta": {"tool_calls": pending_tool_calls}, "finish_reason": None}]}

    except Exception as exc:
        logger.error({"event": "antigravity_stream_error", "error": str(exc)})

    if not sent_role and not pending_tool_calls:
        yield {"id": completion_id, "object": "chat.completion.chunk",
               "created": created, "model": model,
               "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]}

    yield {"id": completion_id, "object": "chat.completion.chunk",
           "created": created, "model": model,
           "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}


# Singleton
antigravity_provider = AntigravityProvider()
