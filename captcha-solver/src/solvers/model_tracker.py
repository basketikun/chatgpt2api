"""Passive model-name learning for Gemini Web + ChatGPT Web.

The picker scrapes only catch chat tiers; image/music/video generation
models live behind tool activations and never appear in the dropdown.
But the upstream `wrb.fr` envelopes (Gemini) and the chatgpt.com
streaming responses *do* expose the actual model name in the footer of
every successful call (`"Nano Banana 2"`, `"Lyria"`, `"3.5 Flash
Extended"`, ...).

This tracker:
1. Stores every model name we've seen for a given (provider, profile)
   pair in a JSON file under `<data_dir>/model_tracker.json`.
2. Lets `list_models` merge the persisted set with the live picker
   scrape — so the catalogue grows automatically the first time a
   user actually generates an image / piece of music / etc.
3. Survives restart (file-backed).

No probes, no extra outbound traffic — pure passive observation of
what the user's account is already using.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Iterable

from ..settings import settings

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_TRACKER_FILE: Path = settings.data_dir / "model_tracker.json"


def _load() -> dict:
    try:
        if _TRACKER_FILE.exists():
            return json.loads(_TRACKER_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("model_tracker load failed: %s", exc)
    return {}


def _save(data: dict) -> None:
    try:
        _TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TRACKER_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning("model_tracker save failed: %s", exc)


def _key(provider: str, profile: str) -> str:
    return f"{provider}::{profile}"


def record(provider: str, profile: str, model_name: str) -> None:
    """Persist a freshly-observed model name for the given identity.

    Cheap on the happy path: if the name is already in the set we just
    return without rewriting the file.
    """
    name = (model_name or "").strip()
    if not name or len(name) > 80:
        return
    with _LOCK:
        data = _load()
        key = _key(provider, profile)
        existing = set(data.get(key) or [])
        if name in existing:
            return
        existing.add(name)
        data[key] = sorted(existing)
        _save(data)
        logger.info(
            "model_tracker: learned %s/%s/%s (total=%d)",
            provider, profile, name, len(existing),
        )


def list_seen(provider: str, profile: str) -> list[str]:
    with _LOCK:
        data = _load()
        return list(data.get(_key(provider, profile)) or [])


# Regexes that pluck the model-name field out of an upstream response.
# The Gemini `wrb.fr` envelope embeds the model name as a JSON string a
# few fields before `,true,` near the end of the response. There's no
# stable schema we can rely on so we match on the model-name vocabulary.
_GEMINI_MODEL_RE = re.compile(
    r'"((?:\d+(?:\.\d+)?\s+)?(?:Flash(?:[- ](?:Lite|Extended))?|Pro(?: Thinking)?|Deep Think|Imagen\s+\d+|Nano Banana(?:\s+\d+| Pro)?|Lyria))"',
    re.IGNORECASE,
)


def extract_gemini_models(raw: str) -> Iterable[str]:
    """Yield every model name found in a Gemini Web RPC payload.

    Returns each match once even if it shows up multiple times in the
    streaming envelope (the same wrb.fr frame is repeated per token).
    """
    if not raw:
        return ()
    seen: set[str] = set()
    for m in _GEMINI_MODEL_RE.finditer(raw):
        name = " ".join(m.group(1).split())
        if name and name not in seen:
            seen.add(name)
            yield name
