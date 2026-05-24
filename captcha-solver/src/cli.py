"""Captcha-solver CLI — run common operations without the chatgpt2api UI.

Inside the container (or via the `cs-cli` bash wrapper on the host):

    python -m src.cli onboard <profile> <email> <password>
        Full onboarding: auto-login Google + create Flow project +
        print {profile, project_id, action} as JSON. Paste straight
        into chatgpt2api Settings → Flow accounts.

    python -m src.cli login <profile> <email> <password>
        Just re-establish Google session for an existing profile (use
        after profile data loss or session expiry).

    python -m src.cli gen <profile> <project_id> "<prompt>"
        Generate one image with the given profile / project; prints
        the CDN URL. Useful for smoke-testing a freshly-added account
        without going through chatgpt2api.

    python -m src.cli list
        Show all profiles (name, size, loaded status).

    python -m src.cli status <profile>
        Detailed status of one profile (load state, cookies count).

    python -m src.cli close <profile>
        Close the cached Chromium context (free RAM, force re-launch
        on next operation).

The CLI uses the same BrowserPool / auto_login / flow_google code that
powers the HTTP API, so behavior is identical. Output is JSON when
useful (onboard, gen) and plain text when human-friendly (list, status).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from .auto_login import (
    get_session as get_login_session,
    start_auto_login,
    submit_2fa_code,
)
from .browser_pool import pool
from .chatgpt_login import (
    get_session as get_chatgpt_session,
    start_chatgpt_login,
    submit_2fa_code as submit_chatgpt_2fa_code,
)
from .gemini_web_login import (
    get_session as get_gemini_web_session,
    start_gemini_web_login,
    submit_2fa_code as submit_gemini_web_2fa_code,
)
from .settings import settings
from .solvers.flow_google import generate_image, get_or_create_project
from .solvers.gemini_web import (
    analyze_image as gemini_web_analyze_image,
    chat as gemini_web_chat,
    generate_image as gemini_web_generate_image,
    generate_music as gemini_web_generate_music,
)
from .solvers.chatgpt_web import (
    analyze_image as chatgpt_web_analyze_image,
    chat as chatgpt_web_chat,
    generate_image as chatgpt_web_generate_image,
)


def _eprint(*args, **kwargs) -> None:
    """Print to stderr — keeps stdout clean for JSON-consuming callers."""
    print(*args, file=sys.stderr, **kwargs)


async def _await_login(profile: str, timeout: int = 180) -> dict:
    """Poll the auto-login session until terminal state, prompting on TTY
    for SMS / TOTP codes when needed."""
    deadline = time.time() + timeout
    last_state = ""
    while time.time() < deadline:
        s = get_login_session(profile)
        if s is None:
            await asyncio.sleep(0.5)
            continue
        if s.state != last_state:
            _eprint(f"  [{s.state}] {s.message}")
            last_state = s.state
        if s.state == "success":
            return {"ok": True, "elapsed": s.elapsed_sec}
        if s.state == "failed":
            return {"ok": False, "error": s.error or s.message}
        if s.state == "need_tap":
            if s.tap_number:
                _eprint(f"  → Bấm số {s.tap_number} trên điện thoại")
            else:
                _eprint("  → Mở app Gmail/Google + bấm 'Có' để xác minh")
        if s.state == "need_code":
            if sys.stdin.isatty():
                code = input("  Nhập mã 2FA (SMS / TOTP): ").strip()
                if code:
                    submit_2fa_code(profile, code)
            else:
                _eprint("  ⚠ Cần mã 2FA nhưng stdin không phải TTY — "
                        "gọi /v1/session/{profile}/auto-login-2fa-code bằng curl")
        await asyncio.sleep(2)
    return {"ok": False, "error": f"timeout after {timeout}s"}


async def cmd_onboard(args: list[str]) -> int:
    if len(args) < 3:
        _eprint("Usage: onboard <profile> <email> <password>")
        return 2
    profile, email, password = args[0], args[1], args[2]
    _eprint(f"▶ Auto-login {email} → profile {profile}")
    await start_auto_login(profile=profile, email=email, password=password)
    result = await _await_login(profile)
    if not result["ok"]:
        print(json.dumps({"ok": False, "step": "login", "error": result.get("error")}, ensure_ascii=False))
        return 1
    _eprint(f"✓ Login OK in {result.get('elapsed')}s — fetching/creating project")
    try:
        proj = await get_or_create_project(profile=profile, headless=False)
    except Exception as exc:
        print(json.dumps({"ok": False, "step": "project", "error": str(exc)}, ensure_ascii=False))
        return 1
    _eprint(f"✓ Project {proj['action']}: {proj['project_id']}")
    print(json.dumps({
        "ok": True,
        "profile": profile,
        "email": email,
        "project_id": proj["project_id"],
        "action": proj["action"],
        "project_count": proj.get("project_count"),
        "elapsed_ms": proj.get("elapsed_ms"),
        "config_entry": {
            "profile": profile,
            "project_id": proj["project_id"],
            "label": "Backup",  # caller can rename
        },
    }, ensure_ascii=False, indent=2))
    return 0


async def cmd_chatgpt_onboard(args: list[str]) -> int:
    """ChatGPT login via Google → scrape /api/auth/session → print JWT."""
    if len(args) < 3:
        _eprint("Usage: chatgpt-onboard <profile> <email> <google-password>")
        return 2
    profile, email, password = args[0], args[1], args[2]
    _eprint(f"▶ ChatGPT-via-Google login {email} → profile {profile}")
    await start_chatgpt_login(profile=profile, email=email, password=password)
    deadline = time.time() + 240
    last_state = ""
    while time.time() < deadline:
        s = get_chatgpt_session(profile)
        if s is None:
            await asyncio.sleep(0.5)
            continue
        if s.state != last_state:
            _eprint(f"  [{s.state}] {s.message}")
            last_state = s.state
        if s.state == "success":
            _eprint(f"✓ Got access_token (expires={s.expires})")
            print(json.dumps({
                "ok": True,
                "profile": profile,
                "email": s.captured_email or email,
                "access_token": s.access_token,
                "expires": s.expires,
                "config_entry": {
                    "access_token": s.access_token,
                    "type": "free",
                    "label": "ChatGPT-Google",
                },
            }, ensure_ascii=False, indent=2))
            return 0
        if s.state == "failed":
            print(json.dumps({"ok": False, "step": s.message, "error": s.error}, ensure_ascii=False))
            return 1
        if s.state == "need_tap":
            if s.tap_number:
                _eprint(f"  → TAP {s.tap_number} on phone")
        if s.state == "need_code":
            if sys.stdin.isatty():
                code = input("  Nhập mã 2FA (SMS / TOTP): ").strip()
                if code:
                    submit_chatgpt_2fa_code(profile, code)
            else:
                _eprint("  ⚠ Cần 2FA — POST /v1/chatgpt/{profile}/onboard-2fa-code")
        await asyncio.sleep(2)
    print(json.dumps({"ok": False, "error": "timeout after 4 minutes"}, ensure_ascii=False))
    return 1


async def cmd_gemini_web_onboard(args: list[str]) -> int:
    """Gemini Web onboard — log into gemini.google.com via Google."""
    if len(args) < 3:
        _eprint("Usage: gemini-web-onboard <profile> <email> <google-password>")
        return 2
    profile, email, password = args[0], args[1], args[2]
    _eprint(f"▶ Gemini Web onboard {email} → profile {profile}")
    await start_gemini_web_login(profile=profile, email=email, password=password)
    deadline = time.time() + 240
    last_state = ""
    while time.time() < deadline:
        s = get_gemini_web_session(profile)
        if s is None:
            await asyncio.sleep(0.5)
            continue
        if s.state != last_state:
            _eprint(f"  [{s.state}] {s.message}")
            last_state = s.state
        if s.state == "success":
            print(json.dumps({"ok": True, "profile": profile, "email": email,
                              "message": s.message, "elapsed_sec": s.elapsed_sec},
                              ensure_ascii=False, indent=2))
            return 0
        if s.state == "failed":
            print(json.dumps({"ok": False, "error": s.error or s.message},
                              ensure_ascii=False))
            return 1
        if s.state == "need_tap":
            if s.tap_number:
                _eprint(f"  → TAP {s.tap_number} on phone")
        if s.state == "need_code":
            if sys.stdin.isatty():
                code = input("  Nhập mã 2FA: ").strip()
                if code:
                    submit_gemini_web_2fa_code(profile, code)
            else:
                _eprint("  ⚠ Cần 2FA — POST /v1/gemini-web/{profile}/onboard-2fa-code")
        await asyncio.sleep(2)
    print(json.dumps({"ok": False, "error": "timeout"}, ensure_ascii=False))
    return 1


async def cmd_gemini_web_chat(args: list[str]) -> int:
    """One-shot chat with gemini.google.com (DOM-scrape)."""
    if len(args) < 2:
        _eprint("Usage: gemini-web-chat <profile> \"<prompt>\"")
        return 2
    profile, prompt = args[0], args[1]
    _eprint(f"▶ Gemini Web chat (profile={profile})")
    try:
        result = await gemini_web_chat(profile=profile, prompt=prompt,
                                        timeout=120, headless=False)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


async def cmd_gemini_web_image(args: list[str]) -> int:
    """Generate image(s) via gemini.google.com (Imagen)."""
    if len(args) < 2:
        _eprint("Usage: gemini-web-image <profile> \"<prompt>\" [count]")
        return 2
    profile, prompt = args[0], args[1]
    count = int(args[2]) if len(args) > 2 else 1
    _eprint(f"▶ Gemini Web image gen (profile={profile} count={count})")
    try:
        result = await gemini_web_generate_image(
            profile=profile, prompt=prompt, count=count,
            timeout=180, headless=False,
        )
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


async def cmd_gemini_web_music(args: list[str]) -> int:
    """Generate music via Lyria on gemini.google.com."""
    if len(args) < 2:
        _eprint("Usage: gemini-web-music <profile> \"<prompt>\"")
        return 2
    profile, prompt = args[0], args[1]
    _eprint(f"▶ Gemini Web music gen (profile={profile})")
    try:
        result = await gemini_web_generate_music(
            profile=profile, prompt=prompt, timeout=240, headless=False,
        )
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


async def cmd_gemini_web_vision(args: list[str]) -> int:
    """Upload an image to Gemini and ask a question."""
    if len(args) < 2:
        _eprint("Usage: gemini-web-vision <profile> <image-url-or-data> [\"<prompt>\"]")
        return 2
    profile, image = args[0], args[1]
    prompt = args[2] if len(args) > 2 else "Phân tích nội dung ảnh này một cách chi tiết."
    _eprint(f"▶ Gemini Web vision (profile={profile})")
    try:
        result = await gemini_web_analyze_image(
            profile=profile, image=image, prompt=prompt,
            timeout=180, headless=False,
        )
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


async def cmd_chatgpt_web_chat(args: list[str]) -> int:
    """Plain chat via chatgpt.com (DOM scrape)."""
    if len(args) < 2:
        _eprint("Usage: chatgpt-web-chat <profile> \"<prompt>\"")
        return 2
    profile, prompt = args[0], args[1]
    _eprint(f"▶ ChatGPT Web chat (profile={profile})")
    try:
        result = await chatgpt_web_chat(profile=profile, prompt=prompt, timeout=120, headless=False)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


async def cmd_chatgpt_web_image(args: list[str]) -> int:
    """Image gen via DALL-E (Tạo hình ảnh tool)."""
    if len(args) < 2:
        _eprint("Usage: chatgpt-web-image <profile> \"<prompt>\"")
        return 2
    profile, prompt = args[0], args[1]
    _eprint(f"▶ ChatGPT Web image (profile={profile})")
    try:
        result = await chatgpt_web_generate_image(profile=profile, prompt=prompt, timeout=240, headless=False)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


async def cmd_chatgpt_web_vision(args: list[str]) -> int:
    """Vision via chatgpt.com — upload image + ask."""
    if len(args) < 2:
        _eprint("Usage: chatgpt-web-vision <profile> <image-url-or-data> [\"<prompt>\"]")
        return 2
    profile, image = args[0], args[1]
    prompt = args[2] if len(args) > 2 else "Phân tích chi tiết nội dung ảnh này."
    _eprint(f"▶ ChatGPT Web vision (profile={profile})")
    try:
        result = await chatgpt_web_analyze_image(profile=profile, image=image, prompt=prompt, timeout=180, headless=False)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


async def cmd_login(args: list[str]) -> int:
    if len(args) < 3:
        _eprint("Usage: login <profile> <email> <password>")
        return 2
    profile, email, password = args[0], args[1], args[2]
    _eprint(f"▶ Re-login {email} → {profile}")
    await start_auto_login(profile=profile, email=email, password=password)
    result = await _await_login(profile)
    print(json.dumps({"ok": result["ok"], "profile": profile, **result}, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


async def cmd_gen(args: list[str]) -> int:
    if len(args) < 3:
        _eprint("Usage: gen <profile> <project_id> \"<prompt>\"")
        return 2
    profile, project_id, prompt = args[0], args[1], args[2]
    _eprint(f"▶ Generating image with {profile} / {project_id[:8]}...")
    try:
        result = await generate_image(
            project_id=project_id,
            prompt=prompt,
            aspect_ratio="IMAGE_ASPECT_RATIO_LANDSCAPE",
            model="NANO_BANANA_PRO",
            count=1,
            tool="PINHOLE",
            profile=profile,
            headless=False,
            timeout=180,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    images = result.get("images") or []
    if not images:
        print(json.dumps({"ok": False, "error": "no images returned", "raw": result.get("raw")}, ensure_ascii=False))
        return 1
    first = images[0]
    print(json.dumps({
        "ok": True,
        "url": first.get("url"),
        "model": result.get("model"),
        "seed": first.get("seed"),
        "elapsed_ms": result.get("elapsed_ms"),
    }, ensure_ascii=False, indent=2))
    return 0


async def cmd_list(args: list[str]) -> int:
    root: Path = settings.data_dir / "profiles"
    if not root.exists():
        _eprint("(no profiles directory)")
        return 0
    rows = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        try:
            size = sum(p.stat().st_size for p in child.rglob("*") if p.is_file())
        except Exception:
            size = 0
        rows.append((child.name, size, pool.is_loaded(child.name)))
    if not rows:
        _eprint("(no profiles)")
        return 0
    name_w = max(len(r[0]) for r in rows)
    print(f"{'PROFILE'.ljust(name_w)}  {'SIZE':>10}  {'LOADED':>8}")
    for name, size, loaded in rows:
        print(f"{name.ljust(name_w)}  {size/1024/1024:>9.1f}M  {'yes' if loaded else 'no':>8}")
    return 0


async def cmd_status(args: list[str]) -> int:
    if not args:
        _eprint("Usage: status <profile>")
        return 2
    profile = args[0]
    ctx = pool.get_cached(profile)
    if ctx is None:
        print(json.dumps({"profile": profile, "loaded": False}, ensure_ascii=False, indent=2))
        return 0
    try:
        cookies = await ctx.cookies()
        cookie_count = len(cookies)
        pages = len(ctx.pages)
    except Exception as exc:
        print(json.dumps({"profile": profile, "loaded": True, "stale": True, "error": str(exc)},
                          ensure_ascii=False, indent=2))
        return 0
    print(json.dumps({
        "profile": profile,
        "loaded": True,
        "pages": pages,
        "cookies": cookie_count,
    }, ensure_ascii=False, indent=2))
    return 0


async def cmd_close(args: list[str]) -> int:
    if not args:
        _eprint("Usage: close <profile>")
        return 2
    profile = args[0]
    closed = await pool.close_profile(profile)
    print(json.dumps({"profile": profile, "closed": closed}, ensure_ascii=False))
    return 0 if closed else 1


_COMMANDS = {
    "onboard": cmd_onboard,
    "chatgpt-onboard": cmd_chatgpt_onboard,
    "gemini-web-onboard": cmd_gemini_web_onboard,
    "gemini-web-chat": cmd_gemini_web_chat,
    "gemini-web-image": cmd_gemini_web_image,
    "gemini-web-music": cmd_gemini_web_music,
    "gemini-web-vision": cmd_gemini_web_vision,
    "chatgpt-web-chat": cmd_chatgpt_web_chat,
    "chatgpt-web-image": cmd_chatgpt_web_image,
    "chatgpt-web-vision": cmd_chatgpt_web_vision,
    "login": cmd_login,
    "gen": cmd_gen,
    "list": cmd_list,
    "status": cmd_status,
    "close": cmd_close,
}


def _print_help() -> None:
    print(__doc__)


async def _main_async() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        _print_help()
        return 0
    cmd = argv[0]
    if cmd not in _COMMANDS:
        _eprint(f"Unknown command: {cmd}")
        _eprint("Run with --help for usage.")
        return 2
    try:
        return await _COMMANDS[cmd](argv[1:])
    finally:
        # Don't drop the cached contexts — leaving them open lets the
        # next call (HTTP API or another CLI invocation) re-use sessions
        # without re-launching Chrome. Just close the Playwright runtime
        # if this is a one-shot CLI invocation.
        try:
            await pool.stop()
        except Exception:
            pass


def main() -> None:
    sys.exit(asyncio.run(_main_async()))


if __name__ == "__main__":
    main()
