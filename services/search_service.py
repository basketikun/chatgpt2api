"""
Search Service — cấu hình chọn backend search ngay trong chatgpt2api.

Port pattern from 9router web search providers.
Supports: chatgpt (built-in), gemini (Google Grounding), serper, searxng, brave.

Flow:
1. auto_detect: analyze user intent → cần search không?
2. If needed → call configured search backend
3. Format results → inject vào messages
4. Send enriched messages to LLM
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from typing import Any

from curl_cffi import requests

from services.config import config
from utils.log import logger

# Vietnamese word character class (includes diacritics)
_VI_WORD = r"[a-zA-ZàáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]+"

# Keywords that trigger search intent detection
SEARCH_INTENT_PATTERNS = [
    rf"(?:giá|bao nhiêu|mấy nghìn|mấy triệu)\s+{_VI_WORD}",
    rf"(?:hôm nay|hôm qua|tuần này|tháng này|năm nay)\s+{_VI_WORD}",
    rf"(?:thời tiết|nhiệt độ|dự báo)\s+{_VI_WORD}",
    rf"(?:tin tức|tin mới|báo chí)\s+{_VI_WORD}",
    rf"(?:kết quả|tỉ số|trận đấu)\s+{_VI_WORD}",
    r"\b(?:search|tìm kiếm|tìm hiểu|tra cứu)\b",
    r"\b(?:ai là|ở đâu|khi nào|thế nào|làm sao)\b",
    r"\b(?:giá|hỏi\s+giá)\b",
]


class SearchBackend:
    """Base class for search backends."""

    def search(self, query: str, max_results: int = 3) -> list[dict[str, str]]:
        raise NotImplementedError


class ChatGPTSearch(SearchBackend):
    """Passthrough — let ChatGPT handle search internally (built-in web search tool)."""

    def search(self, query: str, max_results: int = 3) -> list[dict[str, str]]:
        return []  # ChatGPT handles search internally, no injection needed


class SerperSearch(SearchBackend):
    """Serper.dev Google Search API (free 2,500 req/month)."""

    BASE_URL = "https://google.serper.dev/search"

    def search(self, query: str, max_results: int = 3) -> list[dict[str, str]]:
        provider_config = (config.data.get("providers") or {}).get("serper") or {}
        api_key = str(provider_config.get("api_key") or "").strip()

        if not api_key:
            logger.warning({"event": "serper_no_api_key"})
            return []

        try:
            resp = requests.post(
                self.BASE_URL,
                headers={
                    "X-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": max_results},
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning({"event": "serper_error", "status": resp.status_code})
                return []

            data = resp.json()
            results: list[dict[str, str]] = []
            for item in (data.get("organic") or [])[:max_results]:
                results.append({
                    "title": str(item.get("title") or ""),
                    "snippet": str(item.get("snippet") or ""),
                    "url": str(item.get("link") or ""),
                })
            return results

        except Exception as exc:
            logger.warning({"event": "serper_exception", "error": str(exc)})
            return []


class SearXNGSearcher(SearchBackend):
    """SearXNG self-hosted search (no API key, no limits)."""

    def search(self, query: str, max_results: int = 3) -> list[dict[str, str]]:
        provider_config = (config.data.get("providers") or {}).get("searxng") or {}
        base_url = str(provider_config.get("base_url") or "http://localhost:8080").strip().rstrip("/")

        try:
            resp = requests.get(
                f"{base_url}/search",
                params={"q": query, "format": "json", "categories": "general"},
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning({"event": "searxng_error", "status": resp.status_code})
                return []

            data = resp.json()
            results: list[dict[str, str]] = []
            for item in (data.get("results") or [])[:max_results]:
                results.append({
                    "title": str(item.get("title") or ""),
                    "snippet": str(item.get("content") or item.get("snippet") or ""),
                    "url": str(item.get("url") or ""),
                })
            return results

        except Exception as exc:
            logger.warning({"event": "searxng_exception", "error": str(exc)})
            return []


class BraveSearch(SearchBackend):
    """Brave Search API (free 2,000 req/month)."""

    BASE_URL = "https://api.search.brave.com/res/v1/web/search"

    def search(self, query: str, max_results: int = 3) -> list[dict[str, str]]:
        provider_config = (config.data.get("providers") or {}).get("brave") or {}
        api_key = str(provider_config.get("api_key") or "").strip()

        if not api_key:
            logger.warning({"event": "brave_no_api_key"})
            return []

        try:
            resp = requests.get(
                self.BASE_URL,
                headers={
                    "X-Subscription-Token": api_key,
                    "Accept": "application/json",
                },
                params={"q": query, "count": max_results},
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning({"event": "brave_error", "status": resp.status_code})
                return []

            data = resp.json()
            results: list[dict[str, str]] = []
            for item in (data.get("web", {}).get("results") or [])[:max_results]:
                results.append({
                    "title": str(item.get("title") or ""),
                    "snippet": str(item.get("description") or ""),
                    "url": str(item.get("url") or ""),
                })
            return results

        except Exception as exc:
            logger.warning({"event": "brave_exception", "error": str(exc)})
            return []


class GeminiGrounding(SearchBackend):
    """Google Search grounding via Gemini API. Uses model from providers.gemini_free.model."""

    def __init__(self):
        self._key_index = 0
        self._rate_limited: dict[str, float] = {}

    def _get_model(self) -> str:
        cfg = (config.data.get("providers") or {}).get("gemini_free") or {}
        # Use search-specific model if set, otherwise use chat model
        return str(cfg.get("search_model") or cfg.get("model") or "gemini-2.5-flash")

    def _get_keys(self) -> list[str]:
        provider_config = (config.data.get("providers") or {}).get("gemini_free") or {}
        single = str(provider_config.get("api_key") or "").strip()
        multi = provider_config.get("api_keys") or []
        if not isinstance(multi, list):
            multi = []
        keys = [k.strip() for k in multi if k.strip()]
        if single and single not in keys:
            keys.insert(0, single)
        return keys

    def _next_key(self) -> str | None:
        keys = self._get_keys()
        if not keys:
            return None
        import time
        now = time.time()
        for _ in range(len(keys)):
            key = keys[self._key_index % len(keys)]
            self._key_index += 1
            locked_until = self._rate_limited.get(key, 0)
            if now < locked_until:
                continue
            return key
        return keys[0]  # all limited, return first anyway

    def _mark_limited(self, key: str) -> None:
        import time
        self._rate_limited[key] = time.time() + 60
        # Log only once per key per minute
        last_log = getattr(self, '_last_log', {})
        now = time.time()
        if key not in last_log or now - last_log[key] > 60:
            last_log[key] = now
            self._last_log = last_log
            logger.warning({"event": "gemini_rate_limited", "key_prefix": key[:10]})

    def search(self, query: str, max_results: int = 3) -> list[dict[str, str]]:
        api_key = self._next_key()
        if not api_key:
            logger.warning({"event": "gemini_no_api_key"})
            return []

        try:
            kwargs = {"timeout": 30}
            proxy = str(config.data.get("proxy") or "").strip()
            if proxy:
                kwargs["proxies"] = {"http": proxy, "https": proxy}

            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self._get_model()}:generateContent?key={api_key}",
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                json={"contents": [{"parts": [{"text": query}]}], "tools": [{"google_search": {}}]},
                **kwargs
            )

            if resp.status_code in (429, 403):
                self._mark_limited(api_key)
                now = time.time()
                available = [k for k in self._get_keys() if self._rate_limited.get(k, 0) < now]
                if available:
                    return self.search(query, max_results)
                logger.warning({"event": "gemini_all_keys_blocked", "status": resp.status_code})
                return []

            if resp.status_code != 200:
                logger.warning({"event": "gemini_error", "status": resp.status_code, "body": resp.text[:200]})
                return []

            data = resp.json()
            results: list[dict[str, str]] = []
            candidates = data.get("candidates") or []

            # Get the model's search-grounded text for actual data
            model_text = ""
            for c in candidates:
                parts = (c.get("content") or {}).get("parts") or []
                model_text = " ".join(p.get("text", "") for p in parts if isinstance(p, dict))

            if model_text:
                results.append({
                    "title": "Tổng hợp Google Search (Gemini)",
                    "snippet": model_text[:2000],
                    "url": ""
                })

            for c in candidates:
                grounding = c.get("groundingMetadata") or {}
                chunks = grounding.get("groundingChunks") or []
                sources = grounding.get("webSearchQueries") or []
                for chunk in chunks[:max_results]:
                    web = chunk.get("web") or {}
                    snippet = str(web.get("snippet") or "")
                    if snippet:
                        results.append({
                            "title": str(web.get("title") or (sources[0] if sources else query)),
                            "snippet": snippet,
                            "url": str(web.get("uri") or ""),
                        })
            return results[:max_results + 1]

        except Exception as exc:
            logger.warning({"event": "gemini_exception", "error": str(exc)})
            return []


class CustomProviderSearch(SearchBackend):
    """Use a custom provider's chat model for search (e.g., Gemini API server).

    Sends the query as a chat message with search instruction. Useful for
    Gemini-compatible APIs that support Google grounding natively.
    """

    def __init__(self, provider_id: str = ""):
        self.provider_id = provider_id

    def search(self, query: str, max_results: int = 3) -> list[dict[str, str]]:
        if not self.provider_id:
            return []

        from services.providers.custom_openai import get_custom_providers, CustomOpenAIProvider
        providers = get_custom_providers()
        cfg = providers.get(self.provider_id)
        if not cfg:
            return []

        provider = CustomOpenAIProvider(cfg)
        prefix = str(cfg.get("prefix") or self.provider_id)

        # Get first available model from this provider
        models = provider.list_models()
        if not models:
            return []

        # Pick the first model (usually the best/fastest one)
        model_id = str(models[0].get("id") or "").replace(f"{prefix}/", "")
        if not model_id:
            return []

        try:
            result = provider.chat_completions(
                messages=[{
                    "role": "user",
                    "content": (
                        f"Tìm kiếm trên Google: {query}\n\n"
                        f"Hãy trả lời với thông tin thực tế, cập nhật mới nhất. "
                        f"Trả về tối đa {max_results} kết quả với định dạng:\n"
                        f"1. [Tiêu đề](URL): mô tả ngắn\n"
                        f"2. [Tiêu đề](URL): mô tả ngắn"
                    ),
                }],
                model=model_id,
                stream=False,
                max_tokens=1000,
                temperature=0.3,
            )

            content = ""
            if isinstance(result, dict):
                choices = result.get("choices") or []
                if choices:
                    content = str(choices[0].get("message", {}).get("content") or "")

            if not content:
                return []

            # Parse the response into structured results
            results: list[dict[str, str]] = []
            import re
            lines = content.strip().split("\n")
            for line in lines[:max_results]:
                # Parse "1. [Title](URL): description" or "1. Title: description"
                match = re.match(r"\d+\.\s*\[?(.+?)\]?(?:\((.+?)\))?:\s*(.*)", line.strip())
                if match:
                    results.append({
                        "title": match.group(1).strip(),
                        "url": match.group(2) or "",
                        "snippet": match.group(3).strip(),
                    })
                elif line.strip() and len(results) < max_results:
                    # Fallback: use whole line as snippet
                    text = re.sub(r"^\d+\.\s*", "", line.strip())
                    if text and len(text) > 10:
                        results.append({
                            "title": text[:80],
                            "url": "",
                            "snippet": text,
                        })

            if results:
                logger.info({
                    "event": "custom_provider_search_ok",
                    "provider": self.provider_id,
                    "model": model_id,
                    "results": len(results),
                })
            return results

        except Exception as exc:
            logger.warning({
                "event": "custom_provider_search_error",
                "provider": self.provider_id,
                "error": str(exc),
            })
            return []


class MCPSearch(SearchBackend):
    """Search via enabled MCP search tools (vn_search, federated_search, etc.)."""

    @property
    def name(self) -> str:
        return "mcp"

    def search(self, query: str, max_results: int = 3) -> list[dict[str, str]]:
        """Use MCP search tools as fallback search backend."""
        try:
            from services.mcp_client import get_enabled_mcp_tools, call_mcp_tool
        except ImportError:
            return []

        search_tools = ["search_web", "search_all", "search", "get_news", "get_current_weather"]
        results: list[dict[str, str]] = []
        for tool in search_tools:
            try:
                text = call_mcp_tool(tool, {"query": query, "limit": max_results})
                if text and len(text) > 10:
                    results.append({"title": tool, "snippet": text[:1500], "url": ""})
            except Exception:
                continue
        return results


# Backend registry
SEARCH_BACKENDS: dict[str, SearchBackend] = {
    "chatgpt": ChatGPTSearch(),
    "gemini": GeminiGrounding(),
    "serper": SerperSearch(),
    "searxng": SearXNGSearcher(),
    "brave": BraveSearch(),
    "mcp": MCPSearch(),
}


def get_all_search_backends() -> dict[str, dict[str, str]]:
    """Get all available search backends including custom providers."""
    backends = dict(SEARCH_BACKENDS)
    # Add custom providers as potential search backends
    from services.providers.custom_openai import get_custom_providers
    for cp_id, cp_cfg in get_custom_providers().items():
        key = f"custom:{cp_id}"
        if key not in backends:
            backends[key] = CustomProviderSearch(cp_id)
    return {k: {"name": getattr(v, "provider_id", k) if hasattr(v, "provider_id") else k,
                "label": _get_backend_label(k)} for k, v in backends.items()}


def _get_backend_label(key: str) -> str:
    labels = {
        "chatgpt": "ChatGPT (có sẵn)",
        "gemini": "Gemini Google Search",
        "serper": "Serper.dev",
        "searxng": "SearXNG (tự cài)",
        "brave": "Brave Search",
    }
    if key.startswith("custom:"):
        cp_id = key[len("custom:"):]
        from services.providers.custom_openai import get_custom_providers
        providers = get_custom_providers()
        cfg = providers.get(cp_id) or {}
        return f"{cfg.get('name', cp_id)} (Custom API)"
    return labels.get(key, key)

def needs_search(messages: list[dict[str, Any]]) -> bool:
    """Analyze last user message to detect search intent.

    Returns True if the user is likely asking for real-time information.
    """
    if not messages:
        return False

    # Get last user message
    last_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_text = str(msg.get("content") or "").strip().lower()
            break

    if not last_text:
        return False

    # Skip AI task / image analysis prompts (long prompts with JSON templates)
    if len(last_text) > 500 and ("{" in last_text and "}" in last_text and "json" in last_text.lower()):
        return False

    # Check against search intent patterns
    for pattern in SEARCH_INTENT_PATTERNS:
        if re.search(pattern, last_text):
            return True

    return False


def inject_search_results(
    messages: list[dict[str, Any]],
    results: list[dict[str, str]],
    inject_as: str = "user_message",
) -> list[dict[str, Any]]:
    """Inject search results into the message list.

    Args:
        messages: Current message list
        results: Search results [{title, snippet, url}, ...]
        inject_as: How to inject — 'user_message' or 'system_message'

    Returns:
        Modified message list with search results injected
    """
    if not results:
        return messages

    # Format search results
    lines = ["Dưới đây là kết quả tìm kiếm Google MỚI NHẤT. Hãy trả lời DỰA TRÊN các thông tin này, trích dẫn số liệu cụ thể:"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        lines.append(f"{i}. {title}: {snippet}")

    search_text = "\n".join(lines)

    result = list(messages)

    if inject_as == "system_message":
        # Add as system message before the last user message
        insert_pos = len(result)
        for i in range(len(result) - 1, -1, -1):
            if result[i].get("role") == "user":
                insert_pos = i
                break
        result.insert(insert_pos, {"role": "system", "content": search_text})
    else:
        # Add to last user message content
        for i in range(len(result) - 1, -1, -1):
            if result[i].get("role") == "user":
                content = result[i].get("content", "")
                if isinstance(content, str):
                    result[i] = dict(result[i])
                    result[i]["content"] = f"{search_text}\n\n---\nCâu hỏi của người dùng: {content}"
                elif isinstance(content, list):
                    # HA format: [{"type":"text","text":"..."}]
                    result[i] = dict(result[i])
                    # Prepend search as a separate text part
                    search_part = {"type": "text", "text": search_text}
                    result[i]["content"] = [search_part] + [dict(c) for c in content]
                break

    return result


class SearchService:
    """Orchestrates search across configured backend."""

    def __init__(self):
        self._config_cache: dict[str, Any] = {}

    def _get_config(self) -> dict[str, Any]:
        search_config = config.data.get("search")
        if isinstance(search_config, dict):
            return dict(search_config)
        return {}

    @property
    def backend_name(self) -> str:
        cfg = self._get_config()
        return str(cfg.get("backend") or "chatgpt").strip()

    @property
    def is_enabled(self) -> bool:
        cfg = self._get_config()
        if isinstance(cfg.get("enabled"), bool):
            return cfg["enabled"]
        return True  # Default enabled

    @property
    def auto_detect(self) -> bool:
        cfg = self._get_config()
        if isinstance(cfg.get("auto_detect"), bool):
            return cfg["auto_detect"]
        return True

    @property
    def max_results(self) -> int:
        cfg = self._get_config()
        try:
            return max(1, min(10, int(cfg.get("max_results") or 3)))
        except (TypeError, ValueError):
            return 3

    @property
    def inject_as(self) -> str:
        cfg = self._get_config()
        return str(cfg.get("inject_as") or "user_message").strip()

    @property
    def search_combo(self) -> list[str]:
        """Ordered list of search backends to try (combo/fallback)."""
        cfg = self._get_config()
        combo = cfg.get("search_combo")
        if isinstance(combo, list) and combo:
            valid = set(SEARCH_BACKENDS.keys())
            # Also allow custom provider backends
            from services.providers.custom_openai import get_custom_providers
            for cp_id in get_custom_providers():
                valid.add(f"custom:{cp_id}")
            return [str(b).strip() for b in combo if str(b).strip() in valid]
        # Default: single backend from config
        backend = self._get_active_backend()
        return [backend] if backend in SEARCH_BACKENDS else ["chatgpt"]

    def _get_backend(self, name: str):
        """Get a search backend by name, including custom providers."""
        if name in SEARCH_BACKENDS:
            return SEARCH_BACKENDS[name]
        if name.startswith("custom:"):
            cp_id = name[len("custom:"):]
            return CustomProviderSearch(cp_id)
        return None

    def _get_active_backend(self) -> str:
        """Get actual search backend to use."""
        backend = self.backend_name
        if backend == "chatgpt":
            from services.providers.gemini_free import gemini_provider
            if gemini_provider.api_key:
                return "gemini"
        return backend

    def search(self, query: str) -> list[dict[str, str]]:
        """Execute search using configured backends in combo order. Falls back on failure."""
        combo = self.search_combo

        for backend_name in combo:
            backend = self._get_backend(backend_name)
            if not backend:
                continue

            # Skip chatgpt backend — it's passthrough (no injection)
            if backend_name == "chatgpt" or backend_name.startswith("custom:"):
                # ChatGPT handles search internally via chat model — skip injection
                # Custom providers: let's inject their search results
                if backend_name == "chatgpt":
                    logger.info({"event": "search_combo_chatgpt_skip", "reason": "passthrough"})
                    return []
                # custom provider — search and inject results
                pass

            logger.info({"event": "search_try_backend", "backend": backend_name, "query_len": len(query)})
            try:
                results = backend.search(query, self.max_results)
                if results:
                    logger.info({"event": "search_success", "backend": backend_name, "results": len(results)})
                    return results
                logger.warning({"event": "search_empty", "backend": backend_name})
            except Exception as exc:
                logger.warning({"event": "search_backend_error", "backend": backend_name, "error": str(exc)})

        logger.warning({"event": "search_all_backends_failed", "tried": combo})
        return []

    def search_all(self, query: str) -> list[dict[str, str]]:
        """Run search on combo backends + MCP search tools.

        Respects user's search_combo config. Falls back to active backend.
        """
        all_results: list[dict[str, str]] = []
        seen = set()

        # Only use backends in the user's combo (or active backend)
        combo = self.search_combo
        if not combo or combo == ["chatgpt"]:
            combo = [self._get_active_backend()]

        for name in combo:
            if name in ("chatgpt",):  # skip passthrough
                continue
            backend = self._get_backend(name)
            if not backend:
                continue
            try:
                results = backend.search(query, max(2, self.max_results // 2))
                for r in results:
                    key = r.get("url") or r.get("title", "")
                    if key and key not in seen:
                        seen.add(key)
                        all_results.append(r)
            except Exception as exc:
                logger.debug("search_all: %s skipped: %s", name, exc)

        # 2. MCP search tools (query MCP servers directly)
        try:
            from services.mcp_client import call_mcp_tool
            mcp_tools = ["search_web", "search_all", "search", "get_news"]
            for tool in mcp_tools:
                try:
                    text = call_mcp_tool(tool, {"query": query, "limit": max(2, self.max_results // 2)})
                    if text and len(text) > 20:
                        all_results.append({"title": f"[MCP] {tool}", "snippet": text[:1500], "url": ""})
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("search_all: mcp skipped: %s", exc)

        logger.info({"event": "search_all_done", "total": len(all_results)})
        return all_results[:self.max_results * 3]

    def curate_response(self, query: str, response: str, collection: str = "") -> bool:
        """Store a Q&A pair to vn-mcp-hub RAG. Best-effort, non-blocking."""
        if not response or len(response) < 50:
            return False
        hub_url = config.data.get("mcp_hub_url", "http://vn-mcp-hub:8005")
        if not collection:
            collection = "kb_general"
        try:
            import threading
            def _post():
                try:
                    req = urllib.request.Request(
                        f"{hub_url}/api/rag/curate/{collection}",
                        data=json.dumps({"title": query[:200], "text": response[:3000],
                                        "source": "chatgpt2api_curate"}).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    urllib.request.urlopen(req, timeout=10)
                except Exception:
                    pass
            threading.Thread(target=_post, daemon=True).start()
            return True
        except Exception:
            return False

    def process_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process messages: detect if search needed, execute, inject results.

        If backend is 'chatgpt', this is a no-op — ChatGPT handles search internally.
        """
        if not self.is_enabled:
            return messages

        if self.backend_name == "chatgpt":
            # Auto-detect Gemini if key configured, otherwise skip
            from services.providers.gemini_free import gemini_provider
            if not gemini_provider.api_key:
                return messages  # No search backend available
            # else: fall through to use Gemini search

        if self.auto_detect and not needs_search(messages):
            return messages

        # Extract query from last user message
        query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                # Handle list content format [{"type":"text","text":"..."}]
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            query = str(part.get("text") or "").strip()
                            break
                elif isinstance(content, str):
                    query = content.strip()
                break

        if not query:
            return messages

        logger.info({
            "event": "search_executing",
            "backend": self.backend_name,
            "query": query[:200],
        })

        results = self.search_all(query)  # Use all backends + MCP tools in parallel
        if results:
            logger.info({
                "event": "search_results",
                "backend": self.backend_name,
                "count": len(results),
            })
            return inject_search_results(messages, results, self.inject_as)

        return messages


# Singleton
search_service = SearchService()
