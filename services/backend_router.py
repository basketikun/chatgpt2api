"""
BackendRouter — route requests to the appropriate AI backend.

Port pattern from 9router getProviderCredentials() + combo model routing:
- Model prefix determines provider: oc/ → OpenCode, gw/ → Grok Web, etc.
- Payload > 24KB → ưu tiên provider không giới hạn (opencode, gemini, openrouter)
- Payload ≤ 24KB → dùng ChatGPT free
- Image models stay on ChatGPT DALL-E path
- Combo models fallback qua nhiều provider
"""

from __future__ import annotations

import json
from typing import Any

from services.config import config
from utils.helper import IMAGE_MODELS

# Provider prefixes ported from 9router src/shared/constants/providers.js
PROVIDER_PREFIXES: dict[str, str] = {
    "9r/": "ninerouter",
    "chatgpt/": "chatgpt",
    "cx/": "openai_oauth",
    "codex/": "openai_oauth",
    "oc/": "opencode",
    "ocg/": "opencode_go",
    "gemini_free/": "gemini_free",
    "gemini/": "gemini_free",
    "gw/": "grok_web",
    "pw/": "perplexity_web",
    "gc/": "gemini_cli",
    "kr/": "kiro",
    "qw/": "qwen",
    "if/": "iflow",
    "gh/": "github",
    "cu/": "cursor",
    "cc/": "claude",
    "cx/": "codex",
    "nv/": "nvidia_nim",
    "ag/": "antigravity",
}

# NoAuth providers — no credentials needed (port from 9router FREE_PROVIDERS)
NO_AUTH_PROVIDERS: set[str] = {"opencode"}

# Providers that accept API key (not OAuth)
API_KEY_PROVIDERS: set[str] = {
    "gemini_free",
    "openrouter",
    "deepseek",
    "groq",
    "xai",
    "mistral",
    "perplexity",
    "together",
    "nvidia_nim",
}

# Image providers from 9router image adapter system
IMAGE_PROVIDER_PREFIXES: dict[str, str] = {
    "sdwebui/": "sdwebui",
    "comfyui/": "comfyui",
    "huggingface/": "huggingface",
    "fal-ai/": "fal_ai",
    "stability/": "stability_ai",
    "bfl/": "black_forest_labs",
    "cloudflare/": "cloudflare_ai",
    "recraft/": "recraft",
    "runwayml/": "runwayml",
    "nv-image/": "nvidia_nim_image",
    "gemini-image/": "gemini",
}


class BackendRoute:
    """Result of routing decision."""
    def __init__(
        self,
        provider: str,
        model: str,
        no_auth: bool = False,
        api_key: str = "",
        base_url: str = "",
        is_image: bool = False,
        fallback_providers: list[str] | None = None,
    ):
        self.provider = provider
        self.model = model
        self.no_auth = no_auth
        self.api_key = api_key
        self.base_url = base_url
        self.is_image = is_image
        self.fallback_providers = fallback_providers or []


class BackendRouter:
    """
    Route request đến backend phù hợp nhất:
    - Payload > 24KB → ưu tiên provider không giới hạn (opencode, gemini, openrouter)
    - Payload ≤ 24KB → có thể dùng ChatGPT free
    - Model có prefix oc/ → OpenCode, gw/ → Grok Web, v.v.
    - Combo model → fallback qua nhiều provider
    """

    # Payload threshold for free ChatGPT accounts (24KB)
    FREE_PAYLOAD_LIMIT = 24_000

    # Default model per provider (for "auto" resolution)
    PROVIDER_DEFAULT_MODELS: dict[str, str] = {
        "ninerouter": "auto",
        "openai_oauth": "gpt-5.3-codex",
        "opencode": "nemotron-3-super-free",
        "chatgpt": "auto",
        "gemini_free": "gemini-3-flash-preview",
        "openrouter": "openai/gpt-4o",
        "nvidia_nim": "openai/gpt-oss-120b",
        "antigravity": "gemini-3.1-pro-high",
    }

    @staticmethod
    def resolve_model(model_str: str) -> tuple[str, str]:
        """Parse model string → (provider, model_name).

        Examples:
            "gpt-4" → ("chatgpt", "gpt-4")
            "oc/nemotron-free" → ("opencode", "nemotron-free")
            "sdwebui/sd-v1.5" → ("sdwebui", "sd-v1.5")
            "huggingface/black-forest-labs/FLUX.1-schnell" → ("huggingface", "black-forest-labs/FLUX.1-schnell")
        """
        model_str = str(model_str or "").strip()

        # Check image provider prefixes first
        for prefix, provider in IMAGE_PROVIDER_PREFIXES.items():
            if model_str.startswith(prefix):
                return (provider, model_str[len(prefix):])

        # Check chat provider prefixes
        for prefix, provider in PROVIDER_PREFIXES.items():
            if model_str.startswith(prefix):
                return (provider, model_str[len(prefix):])

        # Check custom providers (dynamic, configured via UI)
        from services.providers.custom_openai import resolve_custom_provider
        custom_cfg, custom_rest = resolve_custom_provider(model_str)
        if custom_cfg is not None:
            provider_id = str(custom_cfg.get("prefix") or "")
            return (f"custom:{provider_id}", custom_rest)

        # Default: use ChatGPT
        return ("chatgpt", model_str)

    @staticmethod
    def is_image_model(model_str: str) -> bool:
        """Check if model is an image generation model."""
        model_str = str(model_str or "").strip()
        if model_str in IMAGE_MODELS:
            return True
        for prefix in IMAGE_PROVIDER_PREFIXES:
            if model_str.startswith(prefix):
                return True
        return False

    @staticmethod
    def get_payload_size(messages: list[dict[str, Any]]) -> int:
        """Calculate JSON payload size in bytes."""
        try:
            payload = json.dumps(messages, ensure_ascii=False, default=str)
            return len(payload.encode("utf-8"))
        except Exception:
            return 0

    @staticmethod
    def _get_enabled_models(provider: str) -> list[str] | None:
        """Return list of enabled model IDs for a provider, or None if no filter."""
        ms = config.data.get("model_settings") or {}
        if not isinstance(ms, dict):
            return None
        enabled = ms.get("enabled_models") or {}
        if not isinstance(enabled, dict) or not enabled:
            return None
        provider_enabled = enabled.get(provider)
        if not provider_enabled:
            return None  # No filter for this provider
        return [m for m in provider_enabled if isinstance(m, str) and m.strip()]

    def route(
        self,
        model: str,
        messages: list[dict[str, Any]] | None = None,
        payload_size: int | None = None,
    ) -> BackendRoute:
        """Determine the best backend for a request.

        Args:
            model: Model string from request
            messages: Normalized messages (for payload size calculation)
            payload_size: Pre-calculated payload size in bytes (optional)

        Returns:
            BackendRoute with provider, model, auth info
        """
        provider, resolved_model = self.resolve_model(model)
        is_image = self.is_image_model(model)

        # Resolve "auto" to provider's default model (check user config first)
        if resolved_model == "auto" or not resolved_model:
            provider_cfg = (config.data.get("providers") or {}).get(provider) or {}
            user_model = str(provider_cfg.get("model") or "").strip()
            resolved_model = user_model or self.PROVIDER_DEFAULT_MODELS.get(provider, "auto")

            # Filter to enabled models only (model_settings)
            enabled = self._get_enabled_models(provider)
            if enabled:
                # Skip auto placeholders, strip provider prefix for matching
                real_models = []
                for m in enabled:
                    m = m.strip()
                    if m in ("auto", f"{provider}/auto"):
                        continue
                    if m.startswith(f"{provider}/"):
                        m = m[len(provider) + 1:]
                    if m:
                        real_models.append(m)
                if real_models and (resolved_model == "auto" or resolved_model not in real_models):
                    resolved_model = real_models[0]  # First real enabled model

        # Calculate payload size if not provided
        if payload_size is None and messages:
            payload_size = self.get_payload_size(messages)

        # Image models always use their configured provider
        if is_image:
            if provider == "chatgpt":
                # ChatGPT DALL-E — existing path
                return BackendRoute(
                    provider="chatgpt",
                    model=model,
                    is_image=True,
                )
            else:
                # External image provider (sdwebui, huggingface, etc.)
                return BackendRoute(
                    provider=provider,
                    model=resolved_model,
                    no_auth=provider in NO_AUTH_PROVIDERS,
                    is_image=True,
                )

        # Text chat routing
        if provider == "chatgpt":
            # If payload is large and we have free providers, suggest fallback
            if payload_size and payload_size > self.FREE_PAYLOAD_LIMIT:
                # Don't redirect if active accounts exist (OpenAI API handles large payloads)
                from services.account_service import account_service as _acct2
                has_active = any(
                    a.get("status") == "active"
                    for a in _acct2._accounts.values()
                )
                if not has_active:
                    opencode_config = (config.data.get("providers") or {}).get("opencode") or {}
                    if opencode_config.get("enabled", True):
                        return BackendRoute(
                            provider="opencode",
                            model=model if model != "auto" else "auto",
                            no_auth=True,
                            fallback_providers=["chatgpt"],
                        )

            # Use ChatGPT as normal
            return BackendRoute(
                provider="chatgpt",
                model=model,
            )

        # Non-ChatGPT provider (opencode, gemini_free, etc.)
        provider_config = (config.data.get("providers") or {}).get(provider) or {}
        return BackendRoute(
            provider=provider,
            model=resolved_model or model,
            no_auth=provider in NO_AUTH_PROVIDERS,
            api_key=str(provider_config.get("api_key") or ""),
            base_url=str(provider_config.get("base_url") or ""),
            fallback_providers=["chatgpt"],
        )

    def route_combo(self, combo_name: str) -> list[BackendRoute]:
        """Resolve a combo model into its fallback chain (case-insensitive)."""
        models = self._get_combo_models(combo_name)
        if not models:
            return []

        routes: list[BackendRoute] = []
        for model_str in models:
            route = self.route(str(model_str))
            routes.append(route)

        return routes

    def is_combo(self, model_str: str) -> bool:
        """Check if a model string is a combo name (case-insensitive)."""
        combos = config.data.get("combo_models") or {}
        if not isinstance(combos, dict):
            return False
        model_lower = model_str.lower().strip()
        return any(k.lower().strip() == model_lower for k in combos)

    def _get_combo_models(self, combo_name: str) -> list[str] | None:
        """Get combo model list by name (case-insensitive)."""
        combos = config.data.get("combo_models") or {}
        if not isinstance(combos, dict):
            return None
        name_lower = combo_name.lower().strip()
        for k, v in combos.items():
            if k.lower().strip() == name_lower and isinstance(v, list):
                return v
        return None


# Singleton
backend_router = BackendRouter()
