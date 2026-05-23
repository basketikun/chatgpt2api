"""
Image Adapter Registry — port from 9router open-sse/handlers/imageProviders/index.js.

Maps provider keys to adapter instances.
"""

from __future__ import annotations

from typing import Any

from services.image_providers._base import BaseImageAdapter
from services.image_providers.sdwebui import SDWebUIAdapter
from services.image_providers.huggingface import HuggingFaceAdapter
from services.image_providers.cloudflare import CloudflareAIAdapter
from services.image_providers.fal_ai import FalAIAdapter
from services.image_providers.stability import StabilityAIAdapter
from services.image_providers.bfl import BFLAdapter
from services.image_providers.gemini_image import GeminiImageAdapter
from services.image_providers.nvidia_nim_image import NvidiaNimImageAdapter
from services.image_providers.flow_google import FlowImageAdapter


# Registry — matches 9router ADAPTERS mapping
IMAGE_ADAPTERS: dict[str, BaseImageAdapter] = {
    "sdwebui": SDWebUIAdapter(),
    "huggingface": HuggingFaceAdapter(),
    "cloudflare_ai": CloudflareAIAdapter(),
    "fal_ai": FalAIAdapter(),
    "stability_ai": StabilityAIAdapter(),
    "black_forest_labs": BFLAdapter(),
    "gemini": GeminiImageAdapter(),
    "nvidia_nim_image": NvidiaNimImageAdapter(),
    "flow": FlowImageAdapter(),
}


def get_image_adapter(provider: str) -> BaseImageAdapter | None:
    """Look up an image adapter by provider key.

    For custom providers (custom: prefix), returns a generic adapter
    that uses the chat completions endpoint for image generation.
    """
    if provider in IMAGE_ADAPTERS:
        return IMAGE_ADAPTERS[provider]
    if provider.startswith("custom:"):
        from services.image_providers.custom_openai_image import CustomOpenAIImageAdapter
        cp_id = provider[len("custom:"):]
        return CustomOpenAIImageAdapter(cp_id)
    return None


def is_image_provider(provider: str) -> bool:
    """Check if a provider has an image adapter registered."""
    return provider in IMAGE_ADAPTERS


# NoAuth image providers (no API key needed)
NO_AUTH_IMAGE_PROVIDERS: set[str] = {"sdwebui"}


def is_noauth_image_provider(provider: str) -> bool:
    """Check if an image provider requires no authentication."""
    return provider in NO_AUTH_IMAGE_PROVIDERS
