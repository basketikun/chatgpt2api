from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from curl_cffi import requests

from services.account_service import account_service
from services.openai_backend_api import OpenAIBackendAPI
from services.config import config, DATA_DIR
from utils.helper import IMAGE_MODELS, anonymize_token
from utils.log import logger


# Fallback static models — used when API fetch fails
FALLBACK_MODELS = {
    "opencode": [
        "oc/auto",
        "oc/nemotron-3-super-free",
        "oc/minimax-m2.5-free",
        "oc/ring-2.6-1t-free",
        "oc/trinity-large-preview-free",
    ],
    "gemini_free": [
        "gemini_free/auto",
        "gemini_free/gemini-2.5-flash",
    ],
    "chatgpt": [
        "chatgpt/auto",
        "chatgpt/free/auto",
        "chatgpt/gpt-4.1-mini",
        "chatgpt/gpt-4.1-nano",
        "chatgpt/gpt-4o",
        "chatgpt/gpt-4o-mini",
        "chatgpt/o3-mini",
        "chatgpt/o4-mini",
    ],
    "openai_oauth": [
        "cx/auto",
        # GPT 5.5
        "cx/gpt-5.5", "cx/gpt-5.5-review",
        # GPT 5.4
        "cx/gpt-5.4", "cx/gpt-5.4-review",
        # GPT 5.3 Codex + effort variants
        "cx/gpt-5.3-codex", "cx/gpt-5.3-codex-review",
        "cx/gpt-5.3-codex-xhigh", "cx/gpt-5.3-codex-xhigh-review",
        "cx/gpt-5.3-codex-high", "cx/gpt-5.3-codex-high-review",
        "cx/gpt-5.3-codex-low", "cx/gpt-5.3-codex-low-review",
        "cx/gpt-5.3-codex-none", "cx/gpt-5.3-codex-none-review",
        "cx/gpt-5.3-codex-spark", "cx/gpt-5.3-codex-spark-review",
        # GPT 5.2 Codex
        "cx/gpt-5.2-codex", "cx/gpt-5.2-codex-review",
        "cx/gpt-5.2", "cx/gpt-5.2-review",
        # GPT 5.1 Codex + variants
        "cx/gpt-5.1-codex", "cx/gpt-5.1-codex-review",
        "cx/gpt-5.1-codex-mini", "cx/gpt-5.1-codex-mini-review",
        "cx/gpt-5.1-codex-mini-high", "cx/gpt-5.1-codex-mini-high-review",
        "cx/gpt-5.1-codex-max", "cx/gpt-5.1-codex-max-review",
        "cx/gpt-5.1", "cx/gpt-5.1-review",
        # GPT 5 Codex
        "cx/gpt-5-codex", "cx/gpt-5-codex-review",
        "cx/gpt-5-codex-mini", "cx/gpt-5-codex-mini-review",
    ],
    "nvidia_nim": [
        "nv/auto",
        "nv-image/black-forest-labs/flux.2-klein-4b",
        "nv-image/black-forest-labs/flux.1-dev",
        "nv-image/black-forest-labs/flux_1-schnell",
        "nv-image/stabilityai/stable-diffusion-3-medium",
        "nv-image/stabilityai/stable-diffusion-xl",
    ],
    "chatgpt2api": [],
    "antigravity": [
        "ag/auto",
        "ag/gemini-3.1-pro-high",
        "ag/gemini-3.1-pro-high-thinking",
        "ag/gemini-3.1-flash-high",
    ],
}

GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _gemini_models_url() -> str:
    """Honor providers.gemini_free.base_url for VN-block proxy."""
    try:
        from services.config import config
        cfg = (config.data.get("providers") or {}).get("gemini_free") or {}
        override = str(cfg.get("base_url") or "").rstrip("/")
        if override:
            if not override.endswith("/v1beta"):
                override = override + "/v1beta"
            return override + "/models"
    except Exception:
        pass
    return GEMINI_MODELS_URL
OPENCODE_MODELS_URL = "https://opencode.ai/zen/v1/models"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
NVIDIA_MODELS_URL = "https://integrate.api.nvidia.com/v1/models"


def _get_gemini_keys() -> list[str]:
    cfg = config.data.get("providers") or {}
    gemini_cfg = cfg.get("gemini_free") or {}
    single = str(gemini_cfg.get("api_key") or "").strip()
    multi = gemini_cfg.get("api_keys") or []
    if not isinstance(multi, list):
        multi = []
    keys = [k.strip() for k in multi if k.strip()]
    if single and single not in keys:
        keys.insert(0, single)
    return keys


def _fetch_gemini_models() -> set[str]:
    """Fetch available models from Gemini API. Returns set of model IDs with gemini_free/ prefix."""
    keys = _get_gemini_keys()
    if not keys:
        logger.info({"event": "list_models_gemini_skip", "reason": "no_api_key"})
        return set()

    for key in keys:
        try:
            resp = requests.get(f"{_gemini_models_url()}?key={key}", timeout=10)
            if resp.status_code != 200:
                continue
            models = set()
            for item in resp.json().get("models", []):
                name = str(item.get("name", "")).replace("models/", "")
                methods = item.get("supportedGenerationMethods") or []
                if "generateContent" in methods:
                    models.add(f"gemini_free/{name}")
            if models:
                logger.info({"event": "list_models_gemini_fetched", "count": len(models)})
                return models
        except Exception as exc:
            logger.warning({"event": "list_models_gemini_error", "error": str(exc)})
            continue

    return set()


def _fetch_opencode_models() -> set[str]:
    """Fetch available free models from OpenCode API. Returns set of model IDs with oc/ prefix."""
    try:
        resp = requests.get(
            OPENCODE_MODELS_URL,
            headers={"Authorization": "Bearer public", "x-opencode-client": "desktop"},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning({"event": "list_models_opencode_failed", "status": resp.status_code})
            return set()

        models = set()
        for item in resp.json().get("data", []):
            slug = str(item.get("id") or "").strip()
            if not slug:
                continue
            # Only include free models (ending in -free)
            if slug.endswith("-free"):
                models.add(f"oc/{slug}")
        if models:
            logger.info({"event": "list_models_opencode_fetched", "count": len(models)})
            return models
    except Exception as exc:
        logger.warning({"event": "list_models_opencode_error", "error": str(exc)})

    return set()


def _fetch_openrouter_models() -> set[str]:
    """Fetch available models from OpenRouter API. Returns set of model IDs with openrouter/ prefix."""
    cfg = config.data.get("providers") or {}
    or_cfg = cfg.get("openrouter") or {}
    api_key = str(or_cfg.get("api_key") or "").strip()
    if not api_key:
        return set()

    try:
        resp = requests.get(
            OPENROUTER_MODELS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning({"event": "list_models_openrouter_failed", "status": resp.status_code})
            return set()

        models = set()
        for item in resp.json().get("data", []):
            slug = str(item.get("id") or "").strip()
            if slug:
                models.add(f"openrouter/{slug}")
        if models:
            logger.info({"event": "list_models_openrouter_fetched", "count": len(models)})
            return models
    except Exception as exc:
        logger.warning({"event": "list_models_openrouter_error", "error": str(exc)})

    return set()


def _fetch_nvidia_models() -> set[str]:
    """Fetch available models from NVIDIA NIM API. Returns set of model IDs with nv/ prefix."""
    cfg = config.data.get("providers") or {}
    nv_cfg = cfg.get("nvidia_nim") or {}
    single = str(nv_cfg.get("api_key") or "").strip()
    multi = nv_cfg.get("api_keys") or []
    if not isinstance(multi, list):
        multi = []
    keys = [k.strip() for k in multi if k.strip()]
    if single and single not in keys:
        keys.insert(0, single)

    if not keys:
        logger.info({"event": "list_models_nvidia_skip", "reason": "no_api_key"})
        return set()

    for key in keys:
        try:
            resp = requests.get(
                f"{NVIDIA_MODELS_URL}",
                headers={"Authorization": f"Bearer {key}"},
                timeout=15,
            )
            if resp.status_code != 200:
                continue
            models = set()
            for item in resp.json().get("data", []):
                slug = str(item.get("id") or "").strip()
                if slug:
                    models.add(f"nv/{slug}")

            # NVIDIA image gen models are on a separate API (ai.api.nvidia.com/v1/genai/)
            # There's no list endpoint, so we hardcode known models with nv-image/ prefix
            nv_image_models = [
                "nv-image/black-forest-labs/flux.2-klein-4b",
                "nv-image/black-forest-labs/flux.1-dev",
                "nv-image/black-forest-labs/flux_1-schnell",
                "nv-image/stabilityai/stable-diffusion-3-medium",
                "nv-image/stabilityai/stable-diffusion-xl",
                "nv-image/stabilityai/stable-video-diffusion",
            ]
            cfg = config.data.get("providers") or {}
            nv_cfg = cfg.get("nvidia_nim") or {}
            if nv_cfg.get("enabled", True):
                models.update(nv_image_models)

            if models:
                logger.info({"event": "list_models_nvidia_fetched", "count": len(models)})
                return models
        except Exception as exc:
            logger.warning({"event": "list_models_nvidia_error", "error": str(exc)})
            continue

    return set()


def _fetch_codex_models() -> set[str]:
    """Fetch models from Codex OAuth tokens + hardcoded 9router models."""
    from services.openai_backend_api import OpenAIBackendAPI

    # Always include hardcoded Codex models (not returned by API)
    models = set(_apply_fallback("openai_oauth"))

    codex_tokens: list[str] = []
    with account_service._lock:
        for token, account in account_service._accounts.items():
            if not token or token == "public":
                continue
            status = str(account.get("status") or "")
            if status in {"disabled", "error"}:
                continue
            if str(account.get("type") or "") == "codex" and token.startswith("eyJ"):
                codex_tokens.append(token)

    if not codex_tokens:
        logger.info({"event": "list_models_codex_skip", "reason": "no_codex_tokens",
                      "hardcoded_count": len(models)})
        return models

    for token in codex_tokens[:3]:
        try:
            api = OpenAIBackendAPI(access_token=token)
            result = api.list_models()
            for item in result.get("data", []):
                slug = str(item.get("id") or "").strip()
                if slug:
                    models.add(f"cx/{slug}")
            # Add reasoning effort variants for each Codex model so user can pick
            # different effort tiers from UI. Suffix is parsed client-side in
            # openai_oauth.chat_completions to set body["reasoning"]["effort"].
            base_models = [m for m in list(models) if m.startswith("cx/")]
            for base in base_models:
                slug = base[3:]
                # Skip variants that already have effort/review suffix
                if any(slug.endswith(f"-{eff}") for eff in ("low", "high", "xhigh", "none", "medium")):
                    continue
                if slug.endswith("-review"):
                    continue
                for effort in ("low", "high"):
                    models.add(f"{base}-{effort}")
            logger.info({"event": "list_models_codex_fetched",
                          "api_count": len(models) - len(_apply_fallback("openai_oauth")),
                          "total": len(models)})
            return models
        except Exception as exc:
            logger.warning({"event": "list_models_codex_token_failed", "error": str(exc)})
            continue

    return models


def _fetch_chatgpt_token_models() -> set[str]:
    """Fetch models from all ChatGPT tokens, compute intersection."""
    active_tokens: list[str] = []
    with account_service._lock:
        for token, account in account_service._accounts.items():
            if not token or token == "public":
                continue
            status = str(account.get("status") or "")
            if status in {"disabled", "error"}:
                continue
            if str(account.get("type") or "") == "codex" and token.startswith("eyJ"):
                continue
            active_tokens.append(token)

    if not active_tokens:
        # Fallback: anon
        try:
            result = OpenAIBackendAPI().list_models()
            models = set()
            for item in result.get("data", []):
                if isinstance(item, dict) and item.get("id"):
                    models.add(f"chatgpt/{str(item['id'])}")
            logger.info({"event": "list_models_chatgpt_anon", "count": len(models)})
            return models
        except Exception as exc:
            logger.warning({"event": "list_models_anon_failed", "error": str(exc)})
            return set()

    # Parallel fetch from all tokens
    token_sets: list[set[str]] = []
    with ThreadPoolExecutor(max_workers=min(8, len(active_tokens))) as executor:
        futures = {
            executor.submit(_fetch_models_for_token, token): token
            for token in active_tokens
        }
        for future in as_completed(futures):
            _, model_set = future.result()
            if model_set is not None:
                token_sets.append(model_set)

    if not token_sets:
        return set()

    # Intersection — add chatgpt/ prefix
    common = {f"chatgpt/{m}" for m in token_sets[0]}
    for s in token_sets[1:]:
        prefixed = {f"chatgpt/{m}" for m in s}
        common &= prefixed

    logger.info({
        "event": "list_models_chatgpt_intersection",
        "total_tokens": len(active_tokens),
        "successful": len(token_sets),
        "common_count": len(common),
    })
    return common


def _fetch_models_for_token(token: str) -> tuple[str, set[str] | None]:
    try:
        api = OpenAIBackendAPI(access_token=token)
        result = api.list_models()
        models = set()
        for item in result.get("data", []):
            if isinstance(item, dict) and item.get("id"):
                models.add(str(item["id"]))
        return (anonymize_token(token), models)
    except Exception as exc:
        logger.warning({"event": "list_models_token_failed", "token": anonymize_token(token), "error": str(exc)})
        return (anonymize_token(token), None)


def _apply_fallback(provider: str) -> set[str]:
    """Get fallback models for a provider when API fetch fails."""
    return set(FALLBACK_MODELS.get(provider, []))


# ── Persistent model cache (disk) ──
import os as _os
_CACHE_FILE = DATA_DIR / "models_cache.json"
_models_cache: dict[str, Any] | None = None
_cache_config_hash: str = ""


def _load_cache_from_disk() -> dict[str, Any] | None:
    """Load cached model list from disk. Returns None if not found or corrupted."""
    try:
        if _CACHE_FILE.exists():
            data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "data" in data:
                # Verify cache consistency: combo_models in cache should match config
                cache_combos = set()
                for m in data.get("data", []):
                    mid = str(m.get("id") or "")
                    # Check if this is a combo model (owned_by == "chatgpt2api" and in combos)
                    if m.get("owned_by") == "chatgpt2api":
                        cache_combos.add(mid)
                current_combos = set((config.data.get("combo_models") or {}).keys())
                if cache_combos != current_combos:
                    logger.info({"event": "models_cache_stale_combos", "cache": list(cache_combos), "config": list(current_combos)})
                    return None
                logger.info({"event": "models_cache_disk_loaded", "count": len(data.get("data", []))})
                return data
    except Exception:
        pass
    return None


def _save_cache_to_disk(data: dict[str, Any]):
    """Persist model list to disk."""
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning({"event": "models_cache_save_error", "error": str(exc)})


def _config_hash() -> str:
    import hashlib, json as _json
    raw = _json.dumps({
        "cp": config.data.get("custom_providers") or {},
        "ms": config.data.get("model_settings") or {},
    }, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


def invalidate_models_cache():
    """Clear cache when config changes. Call from API endpoints after save."""
    global _models_cache, _cache_config_hash
    _models_cache = None
    _cache_config_hash = ""
    try:
        if _CACHE_FILE.exists():
            _CACHE_FILE.unlink()
    except Exception:
        pass


def _apply_enabled_filter(data: list[dict]) -> list[dict]:
    """Filter model list by model_settings.enabled_models. Used for HA /v1/models."""
    model_settings = config.data.get("model_settings") or {}
    if not isinstance(model_settings, dict):
        return data
    enabled_by_provider = model_settings.get("enabled_models") or {}
    if not isinstance(enabled_by_provider, dict) or not enabled_by_provider:
        return data

    all_enabled: set[str] = set()
    for provider_models in enabled_by_provider.values():
        if isinstance(provider_models, list):
            for m in provider_models:
                if isinstance(m, str) and m.strip():
                    all_enabled.add(m.strip())

    always_allow = {
        "cx/auto", "oc/auto", "chatgpt/auto", "chatgpt/free/auto",
        "gemini_free/auto", "ag/auto",
    }
    all_enabled |= always_allow

    combos = config.data.get("combo_models") or {}
    if isinstance(combos, dict):
        all_enabled |= set(combos.keys())

    all_enabled |= set(IMAGE_MODELS)

    from services.providers.custom_openai import get_custom_providers, CustomOpenAIProvider
    custom_providers = get_custom_providers()
    for cp_id, cp_cfg in custom_providers.items():
        try:
            provider = CustomOpenAIProvider(cp_cfg)
            for m in provider.list_models():
                mid = str(m.get("id") or "").strip()
                if mid:
                    all_enabled.add(mid)
        except Exception:
            pass

    before = len(data)
    filtered = [item for item in data if str(item.get("id") or "").strip() in all_enabled]
    logger.info({"event": "list_models_filtered", "before": before, "after": len(filtered)})
    return filtered


def list_models(force_refresh: bool = False, apply_filter: bool = False) -> dict[str, Any]:
    """Return available models — cached to disk. apply_filter=True for HA /v1/models.
    Cache always stores UNFILTERED data; filter is applied at read time so the UI
    (which needs all models for toggle UI) and HA (which needs only enabled) share
    the same cache without one polluting the other."""
    global _models_cache, _cache_config_hash

    # Load from disk on first access
    if _models_cache is None:
        _models_cache = _load_cache_from_disk()
        _cache_config_hash = _config_hash()

    current_hash = _config_hash()
    config_changed = _cache_config_hash != current_hash

    # Use cache if: loaded from disk, not forced, and config hasn't changed
    if _models_cache is not None and not force_refresh and not config_changed:
        logger.info({"event": "list_models_cache_hit"})
        cached = dict(_models_cache)  # type: ignore[arg-type]
        if apply_filter:
            cached = {"object": "list", "data": _apply_enabled_filter(list(cached.get("data") or []))}
        return cached

    if force_refresh:
        logger.info({"event": "list_models_manual_refresh"})
    elif config_changed:
        logger.info({"event": "list_models_config_changed"})
    else:
        logger.info({"event": "list_models_first_load"})

    data: list[dict[str, Any]] = []

    # Fetch from all built-in providers in parallel
    provider_fetchers = {
        "chatgpt": _fetch_chatgpt_token_models,
        "openai_oauth": _fetch_codex_models,
        "gemini_free": _fetch_gemini_models,
        "opencode": _fetch_opencode_models,
        "openrouter": _fetch_openrouter_models,
        "nvidia_nim": _fetch_nvidia_models,
    }

    # Add custom providers dynamically
    from services.providers.custom_openai import get_custom_providers, CustomOpenAIProvider
    custom_providers = get_custom_providers()
    for cp_id, cp_cfg in custom_providers.items():
        def make_fetcher(cfg=cp_cfg):
            provider = CustomOpenAIProvider(cfg)
            def fetcher():
                models = set()
                for m in provider.list_models():
                    mid = str(m.get("id") or "").strip()
                    if mid:
                        models.add(mid)
                if models:
                    logger.info({"event": "list_models_custom", "provider": provider.name, "count": len(models)})
                return models
            return fetcher
        provider_fetchers[f"custom:{cp_id}"] = make_fetcher()

    all_models: dict[str, set[str]] = {}
    with ThreadPoolExecutor(max_workers=len(provider_fetchers)) as executor:
        futures = {
            executor.submit(fetcher): name
            for name, fetcher in provider_fetchers.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                models = future.result()
                if models:
                    all_models[name] = models
            except Exception as exc:
                logger.warning({"event": "list_models_provider_failed", "provider": name, "error": str(exc)})

    # Build seen set to avoid duplicates
    seen: set[str] = set()

    # Add dynamically fetched models
    for provider_name, models in sorted(all_models.items()):
        for model_id in sorted(models):
            if model_id not in seen:
                seen.add(model_id)
                data.append({
                    "id": model_id,
                    "object": "model",
                    "created": 0,
                    "owned_by": provider_name,
                })

    # Apply fallbacks for providers that returned nothing
    for provider_name in ["opencode", "gemini_free", "chatgpt", "openai_oauth", "nvidia_nim", "chatgpt2api", "antigravity"]:
        if provider_name not in all_models:
            for model_id in sorted(_apply_fallback(provider_name)):
                if model_id not in seen:
                    seen.add(model_id)
                    data.append({
                        "id": model_id,
                        "object": "model",
                        "created": 0,
                        "owned_by": provider_name,
                    })

    # Always add OpenAI API models to chatgpt (for web session routing).
    # chatgpt/free/auto pins the free pool; cx/auto already covers codex
    # (handled by openai_oauth provider), so we don't duplicate it here.
    openai_extra = ["chatgpt/free/auto",
                    "chatgpt/gpt-4o", "chatgpt/gpt-4o-mini", "chatgpt/gpt-4.1-mini",
                    "chatgpt/gpt-4.1-nano", "chatgpt/o3-mini", "chatgpt/o4-mini"]
    for mid in openai_extra:
        if mid not in seen:
            seen.add(mid)
            data.append({"id": mid, "object": "model", "created": 0, "owned_by": "chatgpt"})

    # Add image models — group by their natural prefix so the UI shows
    # them under their own provider section (e.g. flow/* under "Google
    # Labs Flow", gemini-image/* under Gemini) instead of all dumped into
    # the generic "chatgpt2api" combo bucket.
    def _model_owner(mid: str) -> str:
        if "/" in mid:
            prefix = mid.split("/", 1)[0]
            if prefix.startswith("gemini-image"):
                return "gemini_free"
            return prefix
        return "chatgpt2api"

    for model in sorted(IMAGE_MODELS):
        if model not in seen:
            seen.add(model)
            data.append({
                "id": model, "object": "model", "created": 0,
                "owned_by": _model_owner(model), "permission": [],
                "root": model, "parent": None,
            })

    # Add combo models from config
    combos = config.data.get("combo_models") or {}
    if isinstance(combos, dict):
        for combo_name in combos:
            if combo_name not in seen:
                seen.add(combo_name)
                data.append({
                    "id": combo_name, "object": "model", "created": 0,
                    "owned_by": "chatgpt2api",
                })

    # Add image provider models from config
    providers = config.data.get("providers") or {}
    if isinstance(providers, dict):
        for provider_name, provider_cfg in providers.items():
            if isinstance(provider_cfg, dict) and provider_cfg.get("enabled"):
                provider_id = f"{provider_name}/auto"
                if provider_id not in seen and provider_name not in ("gemini_free", "openrouter", "serper", "searxng", "brave"):
                    seen.add(provider_id)
                    data.append({
                        "id": provider_id, "object": "model", "created": 0,
                        "owned_by": provider_name,
                    })

    logger.info({"event": "list_models_done", "total_models": len(data)})
    # Save to persistent disk cache (always UNFILTERED — apply_filter is applied at read time)
    result = {"object": "list", "data": data}
    _models_cache = result
    _cache_config_hash = current_hash
    _save_cache_to_disk(result)
    logger.info({"event": "list_models_cached_to_disk", "total": len(data)})

    if apply_filter:
        return {"object": "list", "data": _apply_enabled_filter(list(data))}
    return result
