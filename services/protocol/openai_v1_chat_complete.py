from __future__ import annotations

import json
import time
import uuid
from typing import Any, Iterable, Iterator

from fastapi import HTTPException

from services.protocol.conversation import (
    ConversationRequest,
    ImageOutput,
    TOOL_CALL_RE,
    TOOL_CALL_SELF_CLOSING_RE,
    collect_image_outputs,
    collect_text,
    count_message_tokens,
    count_text_tokens,
    encode_images,
    normalize_messages,
    stream_image_outputs_with_pool,
    stream_text_deltas,
    text_backend,
)
from services.account_service import account_service
from services.backend_router import backend_router
from services.config import config
from services.model_cooldown import model_cooldown
from services.search_service import search_service
from utils.helper import build_chat_image_markdown_content, extract_chat_image, extract_chat_prompt, is_image_chat_request, parse_image_count
from utils.log import logger


def _extract_status(error_text: str) -> int:
    """Extract HTTP status code from error message text."""
    import re
    text = str(error_text)
    match = re.search(r'\b(4\d\d|5\d\d|error\s+(\d+))', text, re.IGNORECASE)
    if match:
        code = match.group(2) or match.group(1)
        try:
            return int(code)
        except ValueError:
            pass
    # Check for keyword patterns
    lower = text.lower()
    if "401" in lower or "unauthorized" in lower: return 401
    if "402" in lower: return 402
    if "403" in lower or "forbidden" in lower: return 403
    if "404" in lower: return 404
    if "429" in lower or "rate" in lower or "quota" in lower: return 429
    if "503" in lower or "502" in lower or "500" in lower: return 500
    return 0


def completion_chunk(model: str, delta: dict[str, Any], finish_reason: str | None = None, completion_id: str = "", created: int | None = None) -> dict[str, Any]:
    return {
        "id": completion_id or f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": created or int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def completion_response(
    model: str,
    content: str,
    created: int | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    prompt_tokens = count_message_tokens(messages, model) if messages else 0
    completion_tokens = count_text_tokens(content, model) if messages else 0
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": created or int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def stream_text_chat_completion(backend, messages: list[dict[str, Any]], model: str, tools: list[dict[str, Any]] | None = None, tool_choice: Any = None) -> Iterator[dict[str, Any]]:
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    sent_role = False
    request = ConversationRequest(model=model, messages=messages, tools=tools, tool_choice=tool_choice)
    for delta_text in stream_text_deltas(backend, request):
        if not sent_role:
            sent_role = True
            yield completion_chunk(model, {"role": "assistant", "content": delta_text}, None, completion_id, created)
        else:
            yield completion_chunk(model, {"content": delta_text}, None, completion_id, created)
    if not sent_role:
        yield completion_chunk(model, {"role": "assistant", "content": ""}, None, completion_id, created)
    yield completion_chunk(model, {}, "stop", completion_id, created)


def collect_chat_content(chunks: Iterable[dict[str, Any]]) -> str:
    parts: list[str] = []
    for chunk in chunks:
        choices = chunk.get("choices")
        first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        delta = first.get("delta") if isinstance(first.get("delta"), dict) else {}
        content = str(delta.get("content") or "")
        if content:
            parts.append(content)
    return "".join(parts)


def chat_messages_from_body(body: dict[str, Any]) -> list[dict[str, Any]]:
    messages = body.get("messages")
    if isinstance(messages, list) and messages:
        return [message for message in messages if isinstance(message, dict)]
    prompt = str(body.get("prompt") or "").strip()
    if prompt:
        return [{"role": "user", "content": prompt}]
    raise HTTPException(status_code=400, detail={"error": "messages or prompt is required"})


def chat_image_args(body: dict[str, Any]) -> tuple[str, str, int, list[tuple[bytes, str, str]]]:
    model = str(body.get("model") or "gpt-image-2").strip() or "gpt-image-2"
    prompt = extract_chat_prompt(body)
    if not prompt:
        raise HTTPException(status_code=400, detail={"error": "prompt is required"})
    images = [
        (data, f"image_{idx}.png", mime)
        for idx, (data, mime) in enumerate(extract_chat_image(body), start=1)
    ]
    return model, prompt, parse_image_count(body.get("n")), images


def text_chat_parts(body: dict[str, Any]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]] | None, Any]:
    model = str(body.get("model") or "auto").strip() or "auto"
    messages = chat_messages_from_body(body)
    tools = body.get("tools")
    if isinstance(tools, list) and tools:
        tools = [t for t in tools if isinstance(t, dict)]
    else:
        tools = None
    tool_choice = body.get("tool_choice")
    return model, messages, tools, tool_choice


def image_result_content(result: dict[str, Any]) -> str:
    data = result.get("data")
    if isinstance(data, list) and data:
        return build_chat_image_markdown_content(result)
    return str(result.get("message") or "Image generation completed.")


def image_chat_response(body: dict[str, Any]) -> dict[str, Any]:
    model, prompt, n, images = chat_image_args(body)
    result = collect_image_outputs(stream_image_outputs_with_pool(ConversationRequest(
        prompt=prompt,
        model=model,
        n=n,
        response_format="b64_json",
        images=encode_images(images) or None,
    )))
    return completion_response(model, image_result_content(result), int(result.get("created") or 0) or None)


def image_chat_events(body: dict[str, Any]) -> Iterator[dict[str, Any]]:
    model, prompt, n, images = chat_image_args(body)
    image_outputs = stream_image_outputs_with_pool(ConversationRequest(
        prompt=prompt,
        model=model,
        n=n,
        response_format="b64_json",
        images=encode_images(images) or None,
    ))
    yield from stream_image_chat_completion(image_outputs, model)


def stream_image_chat_completion(image_outputs: Iterable[ImageOutput], model: str) -> Iterator[dict[str, Any]]:
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    sent_role = False
    sent_text = ""
    for output in image_outputs:
        content = ""
        if output.kind == "progress":
            content = output.text
            sent_text += content
        elif output.kind == "result":
            content = build_chat_image_markdown_content({"data": output.data})
        elif output.kind == "message":
            content = output.text[len(sent_text):] if output.text.startswith(sent_text) else output.text
        if not content:
            continue
        if not sent_role:
            sent_role = True
            yield completion_chunk(model, {"role": "assistant", "content": content}, None, completion_id, created)
        else:
            yield completion_chunk(model, {"content": content}, None, completion_id, created)
    if not sent_role:
        yield completion_chunk(model, {"role": "assistant", "content": ""}, None, completion_id, created)
    yield completion_chunk(model, {}, "stop", completion_id, created)


def handle(body: dict[str, Any]) -> dict[str, Any] | Iterator[dict[str, Any]]:
    # Image chat requests always use existing DALL-E flow
    if is_image_chat_request(body):
        if body.get("stream"):
            return image_chat_events(body)
        return image_chat_response(body)

    model, messages, tools, tool_choice = text_chat_parts(body)

    # Detect vision request once — both combo and single-model paths use this
    # to skip MCP/HA tool injection (saves ~2.5s discovery + removes 60+ tools
    # that vision models have to scan before answering).
    is_vision_request = _messages_have_images(messages)

    # Detect HA intent on the PRISTINE user message before any search/HA
    # injection runs. Search results often contain phrases like "mở cửa"
    # (trading session jargon) or "đèn" (news headline) that would trip
    # the HA regex if we checked post-injection.
    try:
        from services.ha_client import is_ha_query as _is_ha
        ha_query_pristine = _is_ha(messages)
    except Exception:
        ha_query_pristine = False

    # Check if this is a combo model — try each model until success
    if backend_router.is_combo(model):
        routes = backend_router.route_combo(model)
        last_error = ""

        # Skip web search for pure HA queries — they're answered from the
        # registry, no need to spend 8s on grounding.
        search_injected = False
        if search_service.is_enabled and not ha_query_pristine and not is_vision_request:
            before_size = _messages_size(messages)
            messages_copy = search_service.process_messages(messages)
            search_injected = _messages_size(messages_copy) > before_size
            # Auto-curate search results to RAG after response (best-effort bg)
            _curate_search_results(messages_copy)
        else:
            messages_copy = messages

        # Mirror the non-combo path: inject HA registry as a system message for
        # HA-related queries so the LLM can answer in ONE round-trip instead of
        # doing GetLiveContext / ha_get_state → wait → final answer (saves ~7s).
        ha_context_injected = False
        if ha_query_pristine:
            try:
                from services.ha_client import inject_ha_context
                before_len = len(messages_copy)
                messages_copy = inject_ha_context(messages_copy)
                ha_context_injected = len(messages_copy) > before_len
            except Exception:
                pass

        tools_with_mcp = _inject_mcp_tools(
            tools, skip_ha_search=ha_context_injected,
            is_vision=is_vision_request, search_injected=search_injected,
        )

        for route in routes:
            try:
                cooldown = model_cooldown.get_cooldown_info(route.model)
                if cooldown:
                    logger.warning({"event": "model_cooldown_skip", "model": route.model, **cooldown})
                    last_error = cooldown["message"]
                    continue

                logger.info({"event": "combo_try", "combo": model, "provider": route.provider, "model": route.model})
                
                result = _dispatch(route, messages_copy, tools_with_mcp, tool_choice, body)
                # Execute MCP tools server-side for combo too
                if not isinstance(result, dict):
                    result = _wrap_mcp_stream(result, messages_copy, route, body)
                elif isinstance(result, dict):
                    result = _execute_mcp_tools_in_response(messages_copy, result, route, body)
                model_cooldown.record_success("combo:" + model, route.model)
                return result
            except Exception as exc:
                last_error = str(exc)
                logger.warning({"event": "combo_fail", "combo": model, "provider": route.provider, "error": last_error[:200]})
                model_cooldown.record_failure(
                    account_id="combo:" + model, model=route.model,
                    status_code=_extract_status(last_error), error_body=last_error, provider=route.provider,
                )
                continue
        return completion_response(model=model, content=f"All providers failed. Last error: {last_error[:200]}", messages=messages)

    # Single model — route directly
    route = backend_router.route(model, messages)

    # Apply search injection for all backends — but skip when the user query
    # is a pure HA command/status (answered from registry) or a vision task.
    search_injected = False
    if search_service.is_enabled and not ha_query_pristine and not is_vision_request:
        before_size = _messages_size(messages)
        messages = search_service.process_messages(messages)
        search_injected = _messages_size(messages) > before_size

    # Inject HA smart home context only when the PRISTINE user message looked
    # like an HA query. This avoids false positives from search-result text.
    ha_context_injected = False
    if ha_query_pristine:
        try:
            from services.ha_client import inject_ha_context
            before_len = len(messages)
            messages = inject_ha_context(messages)
            ha_context_injected = len(messages) > before_len
        except Exception:
            pass

    # Inject MCP tools from enabled presets
    tools = _inject_mcp_tools(
        tools, skip_ha_search=ha_context_injected,
        is_vision=is_vision_request, search_injected=search_injected,
    )

    result = _dispatch(route, messages, tools, tool_choice, body)

    # Execute MCP tools server-side — HA doesn't know these tools
    if not isinstance(result, dict):
        # Streaming (Iterator) — wrap to intercept tool calls
        result = _wrap_mcp_stream(result, messages, route, body)
    elif isinstance(result, dict):
        result = _execute_mcp_tools_in_response(messages, result, route, body)
    return result


def _curate_search_results(messages: list[dict[str, Any]]) -> None:
    """Extract last user query + search results → curate to RAG in background."""
    try:
        query = ""
        search_text = ""
        for m in reversed(messages):
            if m.get("role") == "user" and not query:
                c = m.get("content", "")
                query = c if isinstance(c, str) else str(c)[:200]
            if m.get("role") == "system" and "Search results" in str(m.get("content", "")):
                search_text = str(m.get("content", ""))[:2000]
        if query and search_text:
            search_service.curate_response(query, search_text)
    except Exception:
        pass


def _auto_search_enrich(query: str) -> str:
    """Run search alongside MCP tool execution for richer context."""
    if not search_service.is_enabled:
        return ""
    try:
        results = search_service.search_all(query)
        if not results:
            return ""
        lines = ["\n---\n## Kết quả tìm kiếm bổ sung\n"]
        for r in results[:5]:
            title = r.get("title", "")
            snippet = (r.get("snippet") or "")[:300]
            url = r.get("url", "")
            if title:
                lines.append(f"- **{title}**")
            if snippet:
                lines.append(f"  {snippet}")
            if url:
                lines.append(f"  {url}")
        return "\n".join(lines)
    except Exception:
        return ""


def _extract_user_query(messages: list[dict[str, Any]]) -> str:
    """Get the last user message text for search enrichment."""
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content", "")
            if isinstance(c, str):
                return c[:200]
            if isinstance(c, list):
                return str(c[0].get("text", ""))[:200] if c else ""
    return ""


def _wrap_mcp_stream(
    stream_iter, messages: list[dict[str, Any]], route, body: dict[str, Any]
):
    """Wrap a streaming response to execute MCP/HA tools and return final answer.

    Collects the full stream, checks for server-side tool calls, executes them in
    an agentic loop (multi-step: e.g. ha_search_entities → ha_get_state → answer),
    then streams the final LLM response.
    """
    # Collect full response from stream
    chunks = []
    full_content = ""
    final_tool_calls: list | None = None
    model = ""

    try:
        for chunk in stream_iter:
            chunks.append(chunk)
            if isinstance(chunk, dict):
                model = chunk.get("model", model)
                delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                full_content += delta.get("content") or ""
                tc = delta.get("tool_calls")
                if tc:
                    final_tool_calls = tc
    except Exception:
        for c in chunks:
            yield c
        return

    # No tool calls → stream as-is
    if not final_tool_calls:
        for c in chunks:
            yield c
        return

    # Filter to server-side tools only
    from services.mcp_client import get_enabled_mcp_tools
    from services.ha_client import get_ha_tools
    known_server_tools = {
        t.get("function", {}).get("name", "")
        for t in get_enabled_mcp_tools() + get_ha_tools()
    }

    mcp_calls = [tc for tc in final_tool_calls
                 if tc.get("function", {}).get("name", "") in known_server_tools]

    if not mcp_calls:
        for c in chunks:
            yield c
        return

    # Build a synthetic non-stream result to feed into the agentic loop
    synthetic_result = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": full_content,
                "tool_calls": mcp_calls,
            },
            "finish_reason": "tool_calls",
        }],
    }

    # Run agentic loop (handles multi-step chains)
    try:
        final_result = _execute_mcp_tools_in_response(messages, synthetic_result, route, body)
    except Exception as exc:
        logger.warning({"event": "mcp_stream_loop_failed", "error": str(exc)})
        for c in chunks:
            yield c
        return

    # Stream the final result back to client
    if hasattr(final_result, "__iter__") and not isinstance(final_result, (dict, str)):
        yield from final_result
    elif isinstance(final_result, dict):
        # Convert non-streaming result into stream chunks
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())
        choice = (final_result.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        yield completion_chunk(model, {"role": "assistant", "content": content}, None, completion_id, created)
        yield completion_chunk(model, {}, "stop", completion_id, created)
    else:
        for c in chunks:
            yield c


def _execute_mcp_tools_in_response(
    messages: list[dict[str, Any]], result: dict, route, body: dict[str, Any],
    max_iterations: int = 4,
) -> dict[str, Any]:
    """Execute MCP/HA tool calls in an agentic loop until final answer or max_iterations.

    Supports multi-step tool chains like:
      ha_search_entities → ha_get_state → final LLM answer
    """
    from services.mcp_client import get_enabled_mcp_tools
    from services.ha_client import get_ha_tools

    current_result = result
    current_messages = list(messages)

    for iteration in range(max_iterations):
        choice = (current_result.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            return current_result  # No more tool calls → final answer

        # Identify server-side vs native (HA pipeline) tools
        known_server_tools = {
            t.get("function", {}).get("name", "")
            for t in get_enabled_mcp_tools() + get_ha_tools()
        }

        mcp_calls = []
        native_calls = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            if name in known_server_tools:
                mcp_calls.append(tc)
            else:
                native_calls.append(tc)

        if not mcp_calls:
            return current_result  # Only native HA tools → pass through

        # Append assistant message with all server-side tool calls
        current_messages.append({
            "role": "assistant",
            "content": msg.get("content") or "",
            "tool_calls": mcp_calls,
        })

        # Execute ALL server-side tool calls IN PARALLEL for speed
        is_action_only = len(mcp_calls) > 0 and all(tc.get("function", {}).get("name") == "ha_call_service" for tc in mcp_calls) and not native_calls

        if len(mcp_calls) > 1:
            # Parallel execution for multiple tool calls
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(mcp_calls)) as pool:
                future_map = {}
                for tc in mcp_calls:
                    args_str = tc.get("function", {}).get("arguments", "{}")
                    try:
                        args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    except Exception:
                        args = {}
                    tool_name = tc.get("function", {}).get("name", "")
                    logger.info({"event": "mcp_tool_exec_parallel", "tool": tool_name})
                    future_map[pool.submit(_execute_mcp_tool, tool_name, args)] = tc

                # Collect results and append to messages
                for future in concurrent.futures.as_completed(future_map, timeout=30):
                    tc = future_map[future]
                    tool_name = tc.get("function", {}).get("name", "")
                    tool_id = tc.get("id", f"mcp_{iteration}")
                    try:
                        mcp_result = future.result()
                    except Exception as exc:
                        mcp_result = f"Tool error: {exc}"
                    if mcp_result is None:
                        mcp_result = f"Tool '{tool_name}' returned no result."
                    current_messages.append({
                        "role": "tool", "tool_call_id": tool_id,
                        "name": tool_name, "content": mcp_result[:3000],
                    })
        else:
            # Single tool call — sequential is fine
            for tc in mcp_calls:
                args_str = tc.get("function", {}).get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except Exception:
                    args = {}
                tool_name = tc.get("function", {}).get("name", "")
                tool_id = tc.get("id", f"mcp_{iteration}")
                logger.info({"event": "mcp_tool_exec", "tool": tool_name, "iteration": iteration})
                mcp_result = _execute_mcp_tool(tool_name, args)
                if mcp_result is None:
                    mcp_result = f"Tool '{tool_name}' returned no result."
                current_messages.append({
                    "role": "tool", "tool_call_id": tool_id,
                    "name": tool_name, "content": mcp_result[:3000],
                })

        if is_action_only:
            logger.info({"event": "ha_fast_short_circuit"})
            final_text = msg.get("content") or "Đã thực hiện xong lệnh điều khiển thiết bị."
            return {
                "id": f"chatcmpl-{uuid.uuid4().hex}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": current_result.get("model", ""),
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": final_text,
                    },
                    "finish_reason": "stop",
                }],
            }

        # Re-dispatch with updated messages
        tools = _inject_mcp_tools(body.get("tools"))
        try:
            current_result = _dispatch(route, current_messages, tools, body.get("tool_choice"), body)
            if not isinstance(current_result, dict):
                # Got a stream back — yield it directly
                return current_result
        except Exception as exc:
            logger.warning({"event": "mcp_followup_failed", "error": str(exc), "iteration": iteration})
            return current_result

    return current_result


def _dispatch(route, messages, tools, tool_choice, body):
    """Dispatch to the correct provider handler."""
    # RTK compression thresholds — 24KB → 80KB → 100KB. We sit at the
    # chatgpt.com hard-limit cap; over-cap payloads still get compressed
    # by _rtk_compress_messages so requests never 413.
    if route.provider == "chatgpt":
        rtk_on = config.rtk_enabled
        rtk_threshold = 100_000
    else:
        rtk_on = config.rtk_other_enabled
        rtk_threshold = 100_000
    if rtk_on:
        from services.protocol.conversation import _rtk_compress_messages
        messages = _rtk_compress_messages(messages, rtk_threshold)

    if route.provider == "opencode":
        return _handle_opencode_chat(route.model, messages, body.get("stream"), body)
    elif route.provider == "ninerouter":
        return _handle_ninerouter_chat(route.model, messages, tools, tool_choice, body.get("stream"), body)
    elif route.provider in ("openai_oauth", "codex"):
        return _handle_openai_oauth_chat(route.model, messages, tools, tool_choice, body.get("stream"), body)
    elif route.provider == "gemini_free":
        return _handle_gemini_chat(route.model, messages, body.get("stream"), body)
    elif route.provider == "antigravity":
        return _handle_antigravity_chat(route.model, messages, tools, tool_choice, body.get("stream"), body)
    elif route.provider == "nvidia_nim":
        return _handle_nvidia_chat(route.model, messages, tools, tool_choice, body.get("stream"), body)
    elif route.provider == "gemini_web":
        from services.providers.web_proxy import handle_gemini_web_chat
        return handle_gemini_web_chat(route.model, messages, body.get("stream"), body)
    elif route.provider == "chatgpt_web":
        from services.providers.web_proxy import handle_chatgpt_web_chat
        return handle_chatgpt_web_chat(route.model, messages, body.get("stream"), body)
    elif route.provider.startswith("custom:"):
        return _handle_custom_openai_chat(route.provider, route.model, messages, tools, tool_choice, body.get("stream"), body)
    elif route.provider == "chatgpt":
        # Vision: chatgpt.com backend uploads image_url/input_image blocks via
        # /backend-api/files (estuary) and references them as asset_pointer.
        # Requires an authenticated chatgpt account (free or codex JWT). If
        # the pool is empty/anon, fall back to gemini_free which accepts
        # inline base64 directly.
        if _messages_have_images(messages):
            try:
                from services.account_service import account_service
                has_chatgpt = any(
                    a.get("status") == "active"
                    and str(a.get("type") or "").split(",")
                    and any(t in ("free", "codex") for t in str(a.get("type") or "").split(","))
                    for a in account_service.list_accounts()
                )
            except Exception:
                has_chatgpt = False
            if not has_chatgpt:
                logger.info({"event": "vision_fallback_to_gemini",
                             "reason": "no_active_chatgpt_account"})
                return _handle_gemini_chat("auto", messages, body.get("stream"), body)
        return _handle_chatgpt_chat(route.model, messages, tools, tool_choice, body.get("stream"), body)
    else:
        logger.warning({"event": "unknown_provider", "provider": route.provider, "fallback": "chatgpt"})
        return _handle_chatgpt_chat(route.model, messages, tools, tool_choice, body.get("stream"), body)


def _restore_tool_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Undo normalize_messages tool→user conversion for OpenAI API compatibility.

    normalize_messages preserves tool_call_id field even when converting to user role.
    We check for that field to restore proper tool messages.
    """
    import re
    result: list[dict[str, Any]] = []
    stop_pattern = re.compile(r'\n\n\[STOP:.*$', re.DOTALL)

    for msg in messages:
        tool_call_id = str(msg.get("tool_call_id") or "")
        if msg.get("role") == "user" and tool_call_id:
            # This was originally a tool message — restore it
            content = str(msg.get("content") or "")
            # Strip [STOP:...] failure suffix if present
            content = stop_pattern.sub("", content).strip()
            result.append({"role": "tool", "tool_call_id": tool_call_id, "content": content})
        else:
            result.append(msg)
    return result


def _convert_images_for_openai(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert internal image format → OpenAI vision API format.
    Downloads HTTP URLs and converts to base64 (OpenAI can't fetch external URLs).
    """
    import base64
    from curl_cffi import requests as cffi_requests
    result: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            new_parts = []
            for part in content:
                if isinstance(part, dict):
                    ptype = part.get("type", "")
                    if ptype == "image":
                        data = part.get("data")
                        mime = part.get("mime", "image/png")
                        if isinstance(data, bytes):
                            b64 = base64.b64encode(data).decode("ascii")
                            new_parts.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"},
                            })
                        elif isinstance(data, str) and data.startswith("data:"):
                            new_parts.append({
                                "type": "image_url",
                                "image_url": {"url": data},
                            })
                        continue
                    elif ptype == "image_url":
                        url = part.get("image_url", {}).get("url", "")
                        if isinstance(url, str) and url.startswith("data:"):
                            new_parts.append(part)  # Already base64
                        elif isinstance(url, str) and url.startswith("http"):
                            # Download and convert to base64 (OpenAI can't fetch external URLs)
                            try:
                                # Use standard requests for image downloads (no impersonation needed)
                                import urllib.request
                                req = urllib.request.Request(url, headers={
                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                                })
                                with urllib.request.urlopen(req, timeout=15) as resp:
                                    img_data = resp.read()
                                    mime = resp.headers.get("Content-Type", "image/jpeg")
                                    b64 = base64.b64encode(img_data).decode("ascii")
                                    new_parts.append({
                                        "type": "image_url",
                                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                                    })
                            except Exception as e:
                                logger.warning({"event": "image_download_failed", "url": url[:120], "error": str(e)[:100]})
                        continue
                new_parts.append(part)
            result.append({**msg, "content": new_parts})
        else:
            result.append(msg)
    return result


def _ensure_openai_provider():
    """Auto-create openai custom provider if missing (for web session routing)."""
    from services.providers.custom_openai import get_custom_providers
    providers = get_custom_providers()
    if "openai" not in providers:
        cfg = config.data
        cfg.setdefault("custom_providers", {})["openai"] = {
            "name": "OpenAI",
            "prefix": "openai",
            "base_url": "https://api.openai.com",
            "api_key": "sk-auto-created",
            "enabled": True,
        }
        config._save()
        logger.info({"event": "openai_provider_auto_created"})


def _handle_chatgpt_chat(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    tool_choice: Any,
    stream: bool,
    body: dict[str, Any],
) -> dict[str, Any] | Iterator[dict[str, Any]]:
    """ChatGPT flow — auto-detects token type and routes to correct API.

    Optional model prefix to force a specific account type:
      chatgpt/free/<model>   → pick from ChatGPT free accounts only
      chatgpt/codex/<model>  → pick from Codex (OAuth) accounts only
      chatgpt/<model>        → auto (whichever active account comes first)
    """
    from services.account_service import detect_token_audience, _TOKEN_AUDIENCE_OPENAI_API, _TOKEN_AUDIENCE_CHATGPT

    # Parse optional type-override prefix from model string.
    preferred_type: str | None = None
    if model.startswith("chatgpt/free/"):
        preferred_type = "free"
        model = "chatgpt/" + model[len("chatgpt/free/"):]
    elif model.startswith("chatgpt/codex/"):
        preferred_type = "codex"
        model = "chatgpt/" + model[len("chatgpt/codex/"):]

    token = account_service.get_text_access_token(account_type=preferred_type)

    is_openai_api = False
    is_codex = False
    if token:
        if token.startswith("sk-"):
            is_openai_api = True
        else:
            acc = account_service.get_account(token)
            if acc:
                acc_type = str(acc.get("type") or "").split(",")
                if "codex" in acc_type:
                    is_codex = True
                elif ("standard" in acc_type or "openai" in acc_type) or (
                    detect_token_audience(token) == _TOKEN_AUDIENCE_OPENAI_API
                    and "free" not in acc_type
                    and "antigravity" not in acc_type
                ):
                    is_openai_api = True

    if is_codex:
        logger.info({"event": "chatgpt_codex_routed", "token_type": "codex"})
        import services.providers.openai_oauth as openai_oauth
        # Strip "chatgpt/" prefix — Codex doesn't know our routing-prefix
        # convention. "chatgpt/auto" → "auto" (Codex resolves auto from
        # its own model_settings.openai_oauth list).
        codex_model = model
        if codex_model.startswith("chatgpt/"):
            codex_model = codex_model[len("chatgpt/"):]
        # Map OpenAI public model names → 'auto'. Codex API rejects
        # 'gpt-4o', 'gpt-4-turbo', etc with "model not supported when
        # using Codex with a ChatGPT account". Common entry point for
        # HA ai_task / n8n / OpenAI SDK clients that don't know about
        # our codex/* aliases. 'auto' lets Codex pick from its enabled
        # models in config.model_settings.openai_oauth.
        _UNSUPPORTED_PREFIXES = ("gpt-3.5", "gpt-4o", "gpt-4-", "gpt-4.", "gpt-5o", "gpt-5-")
        if codex_model and any(codex_model.startswith(p) for p in _UNSUPPORTED_PREFIXES):
            logger.info({"event": "codex_model_mapped", "from": codex_model, "to": "auto"})
            codex_model = "auto"
        # Drop keys we pass explicitly so **body doesn't double-bind them
        # (raises "got multiple values for keyword argument" otherwise).
        body_extras = {k: v for k, v in body.items()
                       if k not in {"model", "messages", "stream", "tools", "tool_choice", "access_token"}}
        # codex_oauth.chat_completions signature: (access_token, messages, model=..., ...)
        # — access_token is the FIRST positional arg, not auto-fetched.
        return openai_oauth.codex_oauth.chat_completions(
            token, messages, model=codex_model, stream=stream, tools=tools, tool_choice=tool_choice, **body_extras
        )

    if is_openai_api:
        # OpenAI API — native tools, all architectures
        logger.info({"event": "chatgpt_openai_api_routed"})
        default_model = config.openai_default_model or "gpt-4o"

        if model == "auto" or model == "chatgpt/auto":
            # Pick from enabled chatgpt models, or fall back to default_model
            ms = config.data.get("model_settings") or {}
            all_enabled = (ms.get("enabled_models") or {}).get("chatgpt") if isinstance(ms, dict) else None
            # Filter out auto placeholders, strip chatgpt/ prefix for comparison
            enabled = []
            for m in (all_enabled or []):
                m = m.strip()
                if m in ("auto", "chatgpt/auto"):
                    continue
                if m.startswith("chatgpt/"):
                    m = m[len("chatgpt/"):]
                if m:
                    enabled.append(m)
            if enabled and default_model not in enabled:
                openai_model = enabled[0]  # First real enabled model
            else:
                openai_model = default_model
        else:
            openai_model = model
        if openai_model.startswith("chatgpt/"):
            openai_model = openai_model[len("chatgpt/"):]
        stream = bool(body.get("stream"))

        messages = _restore_tool_messages(messages)
        messages = _convert_images_for_openai(messages)
        _ensure_openai_provider()

        return _handle_custom_openai_chat(
            "custom:openai", openai_model, messages, tools, tool_choice, stream, body,
            force_token=token,
        )

    # chatgpt.com backend (free account — no openai token)
    from services.config import _IS_ADDON
    if _IS_ADDON:
        # Addon: XML tool call parsing + force hint for HA
        if stream:
            return _stream_chatgpt_addon(text_backend(), messages, model, tools, tool_choice)
        return _chatgpt_addon_completion(model, messages, tools, tool_choice)

    # Docker: original behavior, no XML parsing
    if stream:
        return stream_text_chat_completion(text_backend(), messages, model, tools, tool_choice)
    request = ConversationRequest(model=model, messages=messages, tools=tools, tool_choice=tool_choice)
    return completion_response(model, collect_text(text_backend(), request), messages=messages)


# Device keywords that should trigger tool call forcing
_FORCE_TOOL_KEYWORDS = [
    "trạng thái", "bật", "tắt", "mở", "đóng", "kiểm tra",
    "đèn", "quạt", "cửa", "điều hòa", "máy lạnh", "camera",
    "cảm biến", "công tắc", "ổ cắm", "rèm", "bình nóng lạnh",
    "tivi", "ti vi", "loa", "máy bơm", "nhiệt độ", "độ ẩm",
    "phòng khách", "phòng ngủ", "phòng học", "phòng bếp",
    "ban công", "nhà tắm", "nhà vệ sinh", "hành lang", "sân",
    "tầng", "cầu thang", "garage", "cổng",
]


def _has_device_keyword(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in _FORCE_TOOL_KEYWORDS)


def _inject_tool_force_hint(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    # Legacy: No longer used since HA redesigned
    return messages


def _stream_chatgpt_addon(backend, messages, model, tools, tool_choice):
    """Stream from chatgpt.com backend, extracting XML tool calls from response."""
    messages = _inject_tool_force_hint(messages, tools)
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    sent_role = False
    accumulated = ""
    request = ConversationRequest(model=model, messages=messages, tools=tools, tool_choice=tool_choice)
    for delta_text in stream_text_deltas(backend, request):
        accumulated += delta_text
        if not sent_role:
            sent_role = True
            yield completion_chunk(model, {"role": "assistant", "content": delta_text}, None, completion_id, created)
        else:
            yield completion_chunk(model, {"content": delta_text}, None, completion_id, created)

    if tools:
        tool_calls = _extract_xml_tool_calls_from_text(accumulated)
        if tool_calls:
            yield {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"tool_calls": tool_calls}, "finish_reason": None}],
            }

    if not sent_role:
        yield completion_chunk(model, {"role": "assistant", "content": ""}, None, completion_id, created)
    yield completion_chunk(model, {}, "stop", completion_id, created)


def _chatgpt_addon_completion(model, messages, tools, tool_choice):
    """Non-streaming chatgpt.com backend, extracting XML tool calls from response."""
    messages = _inject_tool_force_hint(messages, tools)
    backend = text_backend()
    request = ConversationRequest(model=model, messages=messages, tools=tools, tool_choice=tool_choice)
    content = collect_text(backend, request)

    if tools:
        tool_calls = _extract_xml_tool_calls_from_text(content)
        if tool_calls:
            return {
                "id": f"chatcmpl-{uuid.uuid4().hex}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": tool_calls,
                    },
                    "finish_reason": "stop",
                }],
                "usage": {
                    "prompt_tokens": count_message_tokens(messages, model),
                    "completion_tokens": count_text_tokens(content, model),
                    "total_tokens": count_message_tokens(messages, model) + count_text_tokens(content, model),
                },
            }

    return completion_response(model, content, messages=messages)


def _handle_opencode_chat(
    model: str,
    messages: list[dict[str, Any]],
    stream: bool,
    body: dict[str, Any],
) -> dict[str, Any] | Iterator[dict[str, Any]]:
    """OpenCode chat — no 24KB payload limit, no auth required."""
    from services.providers.opencode import opencode_provider

    # Strip oc/ prefix if present
    opencode_model = model
    if model.startswith("oc/"):
        opencode_model = model[3:]
    elif model == "auto":
        opencode_model = "auto"

    # Resolve auto using enabled_models order from settings
    if opencode_model == "auto" or not opencode_model:
        ms = config.data.get("model_settings") or {}
        enabled = (ms.get("enabled_models") or {}).get("opencode") if isinstance(ms, dict) else None
        if isinstance(enabled, list):
            for m in enabled:
                m = str(m).strip()
                if not m or m == "auto":
                    continue
                if m.startswith("oc/"):
                    m = m[3:]
                if m:
                    opencode_model = m
                    break

    logger.info({
        "event": "opencode_chat_routed",
        "model": opencode_model,
        "stream": stream,
        "message_count": len(messages),
    })

    temperature = float(body.get("temperature") or 0.7)
    max_tokens = body.get("max_tokens")

    if stream:
        return _stream_opencode_response(opencode_model, messages, temperature, max_tokens, body)
    else:
        return _opencode_completion_response(opencode_model, messages, temperature, max_tokens)


def _stream_opencode_response(
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int | None,
    body: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """Stream response from OpenCode — extract tool calls from text if present."""
    from services.providers.opencode import opencode_provider

    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    sent_role = False
    accumulated = ""

    try:
        sse_stream = opencode_provider.chat_completions(
            messages=messages, model=model, stream=True,
            temperature=temperature, max_tokens=max_tokens,
        )

        for line in sse_stream:
            if line.startswith("data: "):
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    delta_text = ""
                    choices = chunk.get("choices", [])
                    if choices and isinstance(choices[0], dict):
                        delta_text = str(choices[0].get("delta", {}).get("content", "") or "")
                    accumulated += delta_text
                    chunk["id"] = completion_id
                    chunk["created"] = created
                    chunk["model"] = model
                    if delta_text and not sent_role:
                        chunk["choices"][0]["delta"] = {"role": "assistant", "content": delta_text}
                        sent_role = True
                    yield chunk
                except Exception:
                    continue

        # On completion, check if response contains tool calls
        tool_calls = _extract_tool_calls_from_text(accumulated)
        if tool_calls:
            yield {
                "id": completion_id, "object": "chat.completion.chunk",
                "created": created, "model": model,
                "choices": [{"index": 0, "delta": {"tool_calls": tool_calls}, "finish_reason": None}],
            }

        if not sent_role:
            yield completion_chunk(model, {"role": "assistant", "content": ""}, None, completion_id, created)
        yield completion_chunk(model, {}, "stop", completion_id, created)

    except Exception as exc:
        logger.error({"event": "opencode_stream_fatal", "error": str(exc)})
        yield completion_chunk(model, {"role": "assistant", "content": f"OpenCode error: {exc}"}, "stop", completion_id, created)


def _opencode_completion_response(
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int | None,
) -> dict[str, Any]:
    """Non-streaming response from OpenCode — parse text JSON into native tool_calls."""
    from services.providers.opencode import opencode_provider

    try:
        result = opencode_provider.chat_completions(
            messages=messages,
            model=model,
            stream=False,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = ""
        choices = result.get("choices", [])
        if choices and isinstance(choices[0], dict):
            content = str(choices[0].get("message", {}).get("content", "") or "")

        # Parse text JSON tool calls into native format
        tool_calls = _extract_tool_calls_from_text(content)
        message = {"role": "assistant", "content": ""}
        if tool_calls:
            message["tool_calls"] = tool_calls
        else:
            message["content"] = content

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": count_message_tokens(messages, model),
                "completion_tokens": count_text_tokens(content, model),
                "total_tokens": count_message_tokens(messages, model) + count_text_tokens(content, model),
            },
        }

    except Exception as exc:
        logger.error({"event": "opencode_completion_error", "error": str(exc)})
        return completion_response(
            model=model,
            content=f"OpenCode error: {exc}",
            messages=messages,
        )


# ── Helper for entity_id → domain conversion ──

def _convert_params(params):
    """Convert OpenCode params to HA-compatible format (entity_ids → domain)."""
    if isinstance(params, dict) and "entity_ids" in params:
        eids = params["entity_ids"]
        if isinstance(eids, list) and eids:
            domains = list(set(eid.split(".")[0] for eid in eids if isinstance(eid, str)))
            return {"domain": domains}
    if isinstance(params, list):
        if all(isinstance(x, str) for x in params):
            if any("." in str(x) for x in params):
                domains = list(set(str(x).split(".")[0] for x in params))
                return {"domain": domains}
            return {"entities": params}
        return {"entities": params}
    if not isinstance(params, dict):
        return {}
    return params


def _extract_tool_calls_from_text(text: str) -> list[dict[str, Any]] | None:
    """Parse text tool calls from OpenCode response.

    Only extract if the response is PURELY a tool call (no conversational answer).
    If there's text after the tool call JSON, assume it's already a complete answer.
    """
    if not text:
        return None
    import re as _re

    # Check if this is a pure tool call — first non-whitespace is a tool name or JSON
    stripped = text.strip()

    # If text contains both a tool call AND a conversational answer (after the JSON),
    # the answer is the main intent — don't extract tool call
    # Pattern: "ToolName\n{json}\n\nAnswer text..." → already answered, skip

    # Format 1: JSON with "action" key
    match = _re.search(r'\{[^{}]*"action"\s*:\s*"([^"]+)"\s*[,}][^{}]*\}', stripped)
    if match:
        # Only use if this is MOSTLY a tool call (not followed by long text)
        after_json = stripped[match.end():].strip()
        if len(after_json) < 50:  # Short or no follow-up text → pure tool call
            try:
                data = json.loads(match.group(0))
                action = data.get("action", "")
                params = _convert_params(data.get("params") or data.get("entity_ids") or data.get("domain") or {})
                if action:
                    return [{"id": f"call_{uuid.uuid4().hex[:12]}", "type": "function",
                             "function": {"name": action, "arguments": json.dumps(params, ensure_ascii=False)}}]
            except (json.JSONDecodeError, AttributeError):
                pass

    # Format 2: ToolName\n{JSON}
    match = _re.search(r'^([A-Z][A-Za-z0-9_]+)\s*\n\s*(\[[^\]]*\]|\{[^{}]*\})', stripped)
    if match:
        after_json = stripped[match.end():].strip()
        if len(after_json) < 50:
            try:
                tool_name = match.group(1)
                params = _convert_params(json.loads(match.group(2)))
                if not isinstance(params, dict): params = {}
                return [{"id": f"call_{uuid.uuid4().hex[:12]}", "type": "function",
                         "function": {"name": tool_name, "arguments": json.dumps(params, ensure_ascii=False)}}]
            except (json.JSONDecodeError, AttributeError):
                pass

    # Format 3: {"tool": "X"} or {"name": "X"}
    match = _re.search(r'\{\s*"(?:tool|name)"\s*:\s*"([^"]+)"\s*,\s*"parameters"\s*:\s*(\{.*?\}|\[.*?\])\s*\}', stripped, _re.DOTALL)
    if match:
        after_json = stripped[match.end():].strip()
        if len(after_json) < 50:
            try:
                tool_name = match.group(1)
                params = _convert_params(json.loads(match.group(2)))
                if not isinstance(params, dict): params = {}
                return [{"id": f"call_{uuid.uuid4().hex[:12]}", "type": "function",
                         "function": {"name": tool_name, "arguments": json.dumps(params, ensure_ascii=False)}}]
            except (json.JSONDecodeError, AttributeError):
                pass

    return None


def _extract_xml_tool_calls_from_text(text: str) -> list[dict[str, Any]] | None:
    """Parse XML-wrapped tool calls from chatgpt.com backend text responses.

    The AI is instructed by _build_tool_prompt to wrap tool calls in:
    ```xml
    <tool_call name="tool_name">{"arg": "value"}</tool_call>
    ```

    Returns OpenAI-format tool_calls list, or None if no tool calls found.
    """
    if not text or not text.strip():
        return None

    import re as _re

    # Prefer matches inside ```xml ... ``` fenced blocks
    fence_pattern = _re.compile(r'```(?:xml)?\s*\n?(.*?)```', _re.DOTALL)
    fence_matches = fence_pattern.findall(text)
    search_text = " ".join(fence_matches) if fence_matches else text

    tool_calls = []
    seen_names: set[str] = set()

    for match in TOOL_CALL_RE.finditer(search_text):
        name = match.group(1).strip()
        args_text = match.group(2).strip()
        try:
            args = json.loads(args_text) if args_text else {}
            if not isinstance(args, dict):
                args = {}
        except (json.JSONDecodeError, TypeError):
            logger.warning({"event": "xml_tool_call_parse_failed", "name": name, "args_raw": args_text[:200]})
            continue

        if name in seen_names:
            continue
        seen_names.add(name)

        tool_calls.append({
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(args, ensure_ascii=False),
            },
        })

    # Self-closing <tool_call name="X"/>
    for match in TOOL_CALL_SELF_CLOSING_RE.finditer(search_text):
        name = match.group(1).strip()
        if name not in seen_names:
            seen_names.add(name)
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {"name": name, "arguments": "{}"},
            })

    return tool_calls if tool_calls else None


def _handle_openai_oauth_chat(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    tool_choice: Any,
    stream: bool,
    body: dict[str, Any],
) -> dict[str, Any] | Iterator[dict[str, Any]]:
    """Use Codex OAuth token to call chatgpt.com/backend-api/codex/responses — same as 9router."""
    from services.providers.openai_oauth import codex_oauth

    pure_model = model[3:] if model.startswith("cx/") else model
    if not pure_model or pure_model == "auto":
        pure_model = "auto"

    logger.info({
        "event": "openai_oauth_chat",
        "model": pure_model,
        "stream": stream,
    })

    temperature = body.get("temperature")
    max_tokens = body.get("max_tokens")

    attempted: set[str] = set()
    last_error = ""

    while True:
        try:
            token = codex_oauth.get_token_for_request(attempted)
        except RuntimeError as exc:
            raise RuntimeError(str(exc))  # Raise so combo can fallback

        if token in attempted:
            break
        attempted.add(token)

        try:
            if stream:
                return codex_oauth.chat_completions(
                    access_token=token, messages=messages, model=pure_model,
                    stream=True, temperature=temperature, max_tokens=max_tokens,
                    tools=tools, tool_choice=tool_choice,
                )
            else:
                result = codex_oauth.chat_completions(
                    access_token=token, messages=messages, model=pure_model,
                    stream=False, temperature=temperature, max_tokens=max_tokens,
                    tools=tools, tool_choice=tool_choice,
                )
                account_service.mark_text_used(token)
                return result
        except Exception as exc:
            last_error = str(exc)
            # On 401 → skip this token, try next (don't set error)
            if any(x in last_error.lower() for x in ("expired", "401")):
                continue
            # On 400/429 → try next token (don't remove, might be temporary)
            if any(x in last_error.lower() for x in ("400", "429", "rate")):
                continue
            break

    # Raise exception so combo fallback can try next provider
    raise RuntimeError(f"OpenAI OAuth error: {last_error}")


def _handle_gemini_chat(
    model: str,
    messages: list[dict[str, Any]],
    stream: bool,
    body: dict[str, Any],
) -> dict[str, Any] | Iterator[dict[str, Any]]:
    """Gemini AI Studio chat — native function calling support."""
    from services.providers.gemini_free import gemini_provider, GEMINI_DEFAULT_MODEL

    pure_model = model
    for prefix in ("gemini/", "gemini_free/"):
        if model.startswith(prefix):
            pure_model = model[len(prefix):]
            break
    if not pure_model or pure_model == "auto":
        # Try enabled_models order first, then provider config, then default
        ms = config.data.get("model_settings") or {}
        enabled = (ms.get("enabled_models") or {}).get("gemini_free") if isinstance(ms, dict) else None
        chosen = ""
        if isinstance(enabled, list):
            for m in enabled:
                m = str(m).strip()
                if not m or m == "auto":
                    continue
                for prefix in ("gemini/", "gemini_free/"):
                    if m.startswith(prefix):
                        m = m[len(prefix):]
                        break
                if m:
                    chosen = m
                    break
        if not chosen:
            provider_cfg = (config.data.get("providers") or {}).get("gemini_free") or {}
            chosen = str(provider_cfg.get("model") or "") or GEMINI_DEFAULT_MODEL
        pure_model = chosen

    logger.info({"event": "gemini_chat", "model": pure_model})

    temperature = body.get("temperature")
    max_tokens = body.get("max_tokens")
    tools = body.get("tools")
    tool_choice = body.get("tool_choice")

    try:
        # Gemini always streams via SSE API — iterator handles both cases
        result_iter = gemini_provider.chat_completions(
            messages=messages, model=pure_model,
            temperature=temperature, max_tokens=max_tokens,
            tools=tools, tool_choice=tool_choice,
        )
        if stream:
            return result_iter
        else:
            # Collect stream into single response
            content = ""
            tc = []
            for chunk in result_iter:
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content += delta.get("content", "")
                if delta.get("tool_calls"):
                    tc = delta["tool_calls"]
            msg = {"role": "assistant", "content": content}
            if tc:
                msg["tool_calls"] = tc
            return {
                "id": f"chatcmpl-{uuid.uuid4().hex}", "object": "chat.completion",
                "created": int(time.time()), "model": pure_model,
                "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
    except Exception as exc:
        logger.error({"event": "gemini_fatal", "error": str(exc)})
        return completion_response(model=model, content=f"Gemini error: {exc}", messages=messages)


def _handle_nvidia_chat(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    tool_choice: Any,
    stream: bool,
    body: dict[str, Any],
) -> dict[str, Any] | Iterator[dict[str, Any]]:
    """NVIDIA NIM chat — OpenAI-compatible proxy, no format conversion needed."""
    from services.providers.nvidia_nim import nvidia_nim_provider

    pure_model = model
    if model.startswith("nv/"):
        pure_model = model[3:]

    logger.info({"event": "nvidia_nim_chat", "model": pure_model, "stream": stream})

    temperature = body.get("temperature")
    max_tokens = body.get("max_tokens")

    try:
        result = nvidia_nim_provider.chat_completions(
            messages=messages, model=pure_model, stream=stream,
            temperature=temperature, max_tokens=max_tokens,
            tools=tools, tool_choice=tool_choice,
            top_p=body.get("top_p"),
            frequency_penalty=body.get("frequency_penalty"),
            presence_penalty=body.get("presence_penalty"),
        )
        if stream:
            return result
        else:
            return result
    except Exception as exc:
        logger.error({"event": "nvidia_nim_fatal", "error": str(exc)})
        return completion_response(
            model=model,
            content=f"NVIDIA NIM error: {exc}",
            messages=messages,
        )


def _handle_custom_openai_chat(
    provider_key: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    tool_choice: Any,
    stream: bool,
    body: dict[str, Any],
    force_token: str = "",
) -> dict[str, Any] | Iterator[dict[str, Any]]:
    """Custom OpenAI-compatible provider — generic proxy.

    If force_token is provided, it overrides the provider's configured API key.
    """
    from services.providers.custom_openai import CustomOpenAIProvider, get_custom_providers

    # Extract provider ID from "custom:deepseek" format
    provider_id = provider_key[len("custom:"):]

    providers = get_custom_providers()
    cfg = dict(providers.get(provider_id) or {})
    if not cfg:
        return completion_response(
            model=model,
            content=f"Custom provider '{provider_id}' not found or disabled",
            messages=messages,
        )

    if force_token:
        cfg["api_key"] = force_token

    provider = CustomOpenAIProvider(cfg)

    logger.info({"event": "custom_openai_chat", "provider": provider.name, "model": model})

    temperature = body.get("temperature")
    max_tokens = body.get("max_tokens")

    try:
        result = provider.chat_completions(
            messages=messages, model=model, stream=stream,
            temperature=temperature, max_tokens=max_tokens,
            tools=tools, tool_choice=tool_choice,
            top_p=body.get("top_p"),
            frequency_penalty=body.get("frequency_penalty"),
            presence_penalty=body.get("presence_penalty"),
        )
        if stream:
            return result
        else:
            return result
    except Exception as exc:
        logger.error({"event": "custom_openai_fatal", "provider": provider.name, "error": str(exc)})
        return completion_response(
            model=model,
            content=f"[{provider.name}] Error: {exc}",
            messages=messages,
        )


def _handle_antigravity_chat(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    tool_choice: Any,
    stream: bool,
    body: dict[str, Any],
) -> dict[str, Any] | Iterator[dict[str, Any]]:
    """Use Antigravity rotated Google Cloud companion tokens for chat completions."""
    from services.providers.antigravity import antigravity_provider

    pure_model = model[3:] if model.startswith("ag/") else model
    if not pure_model or pure_model == "auto":
        ms = config.data.get("model_settings") or {}
        enabled = (ms.get("enabled_models") or {}).get("antigravity") if isinstance(ms, dict) else None
        chosen = ""
        if isinstance(enabled, list):
            for m in enabled:
                m = str(m).strip()
                if not m or m == "auto":
                    continue
                if m.startswith("ag/"):
                    m = m[3:]
                if m:
                    chosen = m
                    break
        pure_model = chosen or "gemini-3.1-pro-high"

    logger.info({
        "event": "antigravity_chat",
        "model": pure_model,
        "stream": stream,
    })

    temperature = body.get("temperature")
    max_tokens = body.get("max_tokens")

    attempted: set[str] = set()
    last_error = ""

    while True:
        try:
            account = antigravity_provider.get_token_for_request(attempted)
        except RuntimeError as exc:
            raise RuntimeError(str(exc))

        token = account.get("access_token", "")
        if not token or token in attempted:
            break
        attempted.add(token)

        try:
            if stream:
                return antigravity_provider.chat_completions(
                    account=account, messages=messages, model=pure_model,
                    stream=True, temperature=temperature, max_tokens=max_tokens,
                    tools=tools, tool_choice=tool_choice,
                )
            else:
                result = antigravity_provider.chat_completions(
                    account=account, messages=messages, model=pure_model,
                    stream=False, temperature=temperature, max_tokens=max_tokens,
                    tools=tools, tool_choice=tool_choice,
                )
                account_service.mark_text_used(token)
                return result
        except Exception as exc:
            last_error = str(exc)
            # On 401/expired → skip this token, try next
            if any(x in last_error.lower() for x in ("expired", "401", "unauthorized")):
                continue
            # On 400/429/quota → try next
            if any(x in last_error.lower() for x in ("400", "429", "rate", "quota")):
                continue
            break

    raise RuntimeError(f"Antigravity error: {last_error}")


def _messages_size(messages: list[dict[str, Any]] | None) -> int:
    """Total character count across all message content — used to detect
    whether search_service or HA context injected anything new."""
    if not messages:
        return 0
    total = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            total += len(c)
        elif isinstance(c, list):
            for part in c:
                if isinstance(part, dict):
                    total += len(str(part.get("text", "")))
    return total


def _messages_have_images(messages: list[dict[str, Any]] | None) -> bool:
    """True when any message carries an image_url / input_image part.

    Used to detect vision requests so we can skip MCP/HA tool injection — a
    "phân tích ảnh" task never needs Wikipedia / weather / device control,
    and the 60+ tool definitions just bloat the prompt + slow vision models
    that have to scan the tool list before answering.
    """
    for m in messages or []:
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") in ("image_url", "input_image"):
                return True
    return False


def _inject_mcp_tools(
    tools: list[dict[str, Any]] | None,
    skip_ha_search: bool = False,
    is_vision: bool = False,
    search_injected: bool = False,
) -> list[dict[str, Any]] | None:
    """Inject tools from enabled MCP servers + HA into the tools list.

    Args:
        skip_ha_search: When True, the full HA device registry (names + states)
            has already been added to the system prompt by inject_ha_context().
            In that case we strip every READ-ONLY HA tool (ha_search_entities,
            ha_get_state, HA-native GetLiveContext) AND skip MCP injection
            entirely — none of Wikipedia / Exa / etc. is useful for a "trạng
            thái đèn" query, and dropping them removes ~23 distracting tools
            plus the 2.5s MCP discovery cost on cache miss. Control tools
            (ha_call_service, HassTurn*) are preserved.
        is_vision: When True the request carries image attachments (camera
            snapshot, ai_task.generate_data, etc.). Vision tasks never use
            search/control tools, so we skip the entire injection — saves
            ~2.5s of MCP discovery on cache miss and prevents the LLM from
            scanning a 60+ tool list before answering "what's in this image".
        search_injected: When True search_service has already executed MCP
            searches + grounding and dropped the results into the prompt.
            The LLM's only job left is to summarize — adding 60+ more MCP
            tools just bloats the prompt and tempts the LLM into a second
            search round-trip. Skip injection.
    """
    logger.info({"event": "mcp_inject_start", "input_tools": len(tools or [])})
    try:
        # Vision request — skip all injection. Return the caller's tools as-is.
        if is_vision:
            logger.info({"event": "mcp_inject_skipped", "reason": "vision_request"})
            return tools if tools else None

        # Search results already injected — LLM just needs to summarize.
        if search_injected:
            logger.info({"event": "mcp_inject_skipped", "reason": "search_injected"})
            return tools if tools else None

        from services.mcp_client import get_enabled_mcp_tools
        from services.ha_client import get_ha_tools

        # Skip the MCP discovery + injection when the prompt already carries the
        # HA registry — those tools won't be useful here and the LLM may waste
        # a round-trip calling one.
        if skip_ha_search:
            mcp_tools = []
            logger.info({"event": "mcp_inject_skipped", "reason": "ha_context_injected"})
        else:
            mcp_tools = get_enabled_mcp_tools()
            logger.info({"event": "mcp_inject_got_tools", "count": len(mcp_tools)})

        tools = list(tools or [])
        existing_names = {t.get("function", {}).get("name", "") for t in tools}

        client_is_ha = any(name.startswith("Hass") or name == "GetLiveContext" for name in existing_names)
        ha_tools = [] if client_is_ha else get_ha_tools()

        # Only skip MCP for HA-native clients (Hass* tools already in context)
        # For normal chat: include all tools, let the model decide
        if client_is_ha:
            mcp_tools = []

        # When HA context is in the prompt, strip every read-only HA tool so the
        # LLM answers from context in 1 round instead of 2-3. Keep ha_call_service
        # / HassTurn* — control still needs a round-trip.
        if skip_ha_search:
            drop_ha_tool_names = {"ha_search_entities", "ha_get_state"}
            if ha_tools:
                ha_tools = [
                    t for t in ha_tools
                    if t.get("function", {}).get("name", "") not in drop_ha_tool_names
                ]
            # Strip HA-native GetLiveContext from the incoming tools array too
            # (HA's auto_ai_agent always sends it; without this the LLM still
            # calls it even though state is in context).
            if "GetLiveContext" in existing_names:
                tools = [
                    t for t in tools
                    if t.get("function", {}).get("name", "") != "GetLiveContext"
                ]
            logger.info({"event": "ha_read_tools_stripped", "reason": "registry_in_context"})

        all_new_tools = mcp_tools + ha_tools
        if not all_new_tools:
            return tools if tools else None

        for mt in all_new_tools:
            if mt.get("function", {}).get("name", "") not in existing_names:
                tools.append(mt)
        logger.info({"event": "mcp_tools_injected", "mcp_count": len(mcp_tools),
                     "ha_count": len(ha_tools), "total_tools": len(tools)})
        return tools
    except Exception as exc:
        logger.warning({"event": "mcp_tools_inject_failed", "error": str(exc)})
        return tools


def _execute_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> str | None:
    """Execute an MCP or HA tool call and return the result text."""
    # Try MCP first
    try:
        from services.mcp_client import call_mcp_tool
        result = call_mcp_tool(tool_name, arguments)
        if result is not None:
            return result
    except Exception as exc:
        logger.warning({"event": "mcp_tool_call_failed", "tool": tool_name, "error": str(exc)})
    # Try HA tools
    try:
        from services.ha_client import execute_ha_tool
        result = execute_ha_tool(tool_name, arguments)
        if result is not None:
            return result
    except Exception as exc:
        logger.warning({"event": "ha_tool_call_failed", "tool": tool_name, "error": str(exc)})
    return None
