"""Karpathy Guidelines for AI coding behavior.

Loads guidelines from cache, with hardcoded fallback.
Call refresh_guidelines() to fetch latest from upstream GitHub.
"""

import os
import requests

KARPATHY_URL = (
    "https://raw.githubusercontent.com/forrestchang/"
    "andrej-karpathy-skills/main/CLAUDE.md"
)
CACHE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "karpathy_cache.md"
)

HARDCODED_FALLBACK = """\
## Core Principles for AI Coding

### 1. Think Before Coding
- State assumptions explicitly before coding
- If uncertain, ask — don't guess
- Present tradeoffs when multiple approaches exist
- When confused, stop and name what's unclear

### 2. Simplicity First
- Minimum code that solves the problem
- No abstractions for single-use code
- No speculative flexibility or configurability
- If 200 lines could be 50, rewrite it

### 3. Surgical Changes
- Touch only what you must
- Don't "improve" adjacent code, comments, or formatting
- Match existing style
- Every changed line must trace to the user's request

### 4. Goal-Driven Execution
- Define success criteria before coding
- Test first: write test, fix, verify
- For multi-step tasks: brief plan + verify each step\
"""


def load_guidelines() -> str:
    """Return current guidelines — cache preferred, hardcoded fallback."""
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, encoding="utf-8") as f:
                content = f.read()
                if len(content) > 100:
                    return content
    except Exception:
        pass
    return HARDCODED_FALLBACK


def refresh_guidelines() -> bool:
    """Fetch latest from GitHub. Return True if cache was updated."""
    try:
        r = requests.get(KARPATHY_URL, timeout=15)
        if r.status_code == 200 and len(r.text) > 100:
            os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
            old = ""
            if os.path.exists(CACHE_PATH):
                with open(CACHE_PATH, encoding="utf-8") as f:
                    old = f.read()
            if r.text.strip() != old.strip():
                with open(CACHE_PATH, "w", encoding="utf-8") as f:
                    f.write(r.text)
                return True
    except Exception:
        pass
    return False
