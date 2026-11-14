from __future__ import annotations

from typing import Any

from services.account_service import account_service
from services.model_service import model_catalog_service
from utils.helper import CODEX_IMAGE_MODEL, CODEX_IMAGE_MODEL_25


def list_models() -> dict[str, Any]:
    result = model_catalog_service.list_models()
    data = result.get("data")
    if not isinstance(data, list):
        return result
    seen = {str(item.get("id") or "").strip() for item in data if isinstance(item, dict)}
    dynamic_models: set[str] = set()
    accounts = account_service.list_accounts()
    web_image_accounts = [
        account
        for account in accounts
        if isinstance(account, dict)
    ]
    codex_types = {
        normalized
        for account in accounts
        if isinstance(account, dict)
           and account_service._normalize_source_type(account.get("source_type")) == "codex"
           and (normalized := account_service._normalize_account_type(account.get("type")))
    }

    if web_image_accounts:
        dynamic_models.add("gpt-image-2")
        dynamic_models.add("gpt-image-2.5")
    for codex_model in (CODEX_IMAGE_MODEL, CODEX_IMAGE_MODEL_25):
        if codex_types & {"Plus", "Team", "Pro"}:
            dynamic_models.add(codex_model)
        if "Plus" in codex_types:
            dynamic_models.add(f"plus-{codex_model}")
        if "Team" in codex_types:
            dynamic_models.add(f"team-{codex_model}")
        if "Pro" in codex_types:
            dynamic_models.add(f"pro-{codex_model}")

    for model in sorted(dynamic_models):
        if model not in seen:
            data.append({
                "id": model,
                "object": "model",
                "created": 0,
                "owned_by": "chatgpt2api",
                "permission": [],
                "root": model,
                "parent": None,
            })
    return result
