#!/usr/bin/env python3
"""CloudMail receiving diagnostics.

This script talks directly to CloudMail public APIs:
  - /api/public/genToken
  - /api/public/emailList

Use it to separate two very different failure modes:
  1. raw emailList returns 0 items: the message did not reach CloudMail.
  2. raw emailList has items, filtered count is 0: our recipient matching is wrong.

Credentials are read from data/register.json's first cloudmail_gen provider unless
overridden on the command line.
"""

from __future__ import annotations

import argparse
import json
import random
import string
import time
from pathlib import Path
from typing import Any

from curl_cffi import requests  # noqa: E402


REGISTER_JSON = Path(__file__).resolve().parents[1] / "data" / "register.json"


def _load_cloudmail_entry() -> dict[str, Any]:
    try:
        config = json.loads(REGISTER_JSON.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"[warn] Cannot read {REGISTER_JSON}: {error}")
        return {}
    providers = (config.get("mail") or {}).get("providers") or []
    for item in providers:
        if isinstance(item, dict) and item.get("type") == "cloudmail_gen":
            return item
    print("[warn] No cloudmail_gen provider found in data/register.json")
    return {}


def _session(proxy: str):
    kwargs: dict[str, Any] = {"impersonate": "chrome", "verify": False}
    if proxy:
        kwargs["proxy"] = proxy
    return requests.Session(**kwargs)


def _gen_token(session, api_base: str, admin_email: str, admin_password: str) -> str:
    resp = session.post(
        f"{api_base}/api/public/genToken",
        json={"email": admin_email, "password": admin_password},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    data = resp.json() if resp.text else {}
    if not (isinstance(data, dict) and data.get("code") == 200):
        raise RuntimeError(f"genToken failed: HTTP {resp.status_code}, body={resp.text[:300]}")
    token = str((data.get("data") or {}).get("token") or "").strip()
    if not token:
        raise RuntimeError(f"genToken response missing token: {data}")
    return token


def _email_list(session, api_base: str, token: str, address: str = "", size: int = 20) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {"size": size, "timeSort": "desc"}
    if address:
        payload["toEmail"] = address
    resp = session.post(
        f"{api_base}/api/public/emailList",
        json=payload,
        headers={"Content-Type": "application/json", "Authorization": token},
        timeout=30,
    )
    data = resp.json() if resp.text else {}
    if not (isinstance(data, dict) and data.get("code") == 200):
        raise RuntimeError(f"emailList failed: HTTP {resp.status_code}, body={resp.text[:300]}")
    items = data.get("data") or []
    return [item for item in items if isinstance(item, dict)]


def _field(item: dict[str, Any], *names: str) -> str:
    for name in names:
        value = item.get(name)
        if value is not None:
            return str(value)
    return ""


def _extract_text_candidates(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for key in ("address", "email", "name", "value"):
            if value.get(key):
                out.extend(_extract_text_candidates(value.get(key)))
        return out
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_extract_text_candidates(item))
        return out
    return []


def _message_matches_email(data: dict[str, Any], email: str) -> bool:
    target = str(email or "").strip().lower()
    candidates: list[str] = []
    for key in ("to", "toEmail", "toName", "mailTo", "receiver", "receivers", "address", "email", "envelope_to"):
        if key in data:
            candidates.extend(_extract_text_candidates(data.get(key)))
    return not target or not candidates or any(target in str(item).strip().lower() for item in candidates if str(item).strip())


def _print_item(index: int, item: dict[str, Any], address: str = "") -> None:
    to_email = _field(item, "toEmail", "to", "mailTo", "recipient")
    sender = _field(item, "sendEmail", "from", "sender", "source")
    subject = _field(item, "subject")
    created = _field(item, "createTime", "createdAt", "created_at", "receivedAt", "date", "timestamp")
    email_id = _field(item, "emailId", "id", "_id", "messageId")
    verdict = ""
    if address:
        verdict = " match" if _message_matches_email(item, address) else " filtered"
    print(f"  {index}. id={email_id} to={to_email} from={sender} subject={subject[:90]}{verdict}")
    if created:
        print(f"     time={created}")


def _summarize(items: list[dict[str, Any]], address: str) -> None:
    print(f"[info] raw emailList count: {len(items)}")
    if not items:
        print("[result] Raw count is 0. The message did not reach CloudMail for this address.")
        print("[hint] Focus on OpenAI delivery, domain routing/catch-all, sender reputation, or request fingerprint.")
        return

    matched = [item for item in items if _message_matches_email(item, address)]
    print(f"[info] matched by _message_matches_email: {len(matched)}")
    for index, item in enumerate(items[:8], start=1):
        _print_item(index, item, address)
    if not matched:
        print("[result] Raw messages exist but our filter rejected them. Fix recipient matching.")
    else:
        print("[result] CloudMail receiving and current recipient matching both work.")


def _random_address(domain: str, prefix: str = "") -> str:
    local = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    if prefix:
        local = f"{prefix}_{local}"
    return f"{local}@{domain}"


def _domain_from_entry(entry: dict[str, Any], fallback: str) -> str:
    domains = entry.get("domain") if isinstance(entry.get("domain"), list) else []
    domains = [str(item).strip() for item in domains if str(item).strip()]
    return fallback or (domains[0] if domains else "mail.fxo.me")


def _global_search(items: list[dict[str, Any]], terms: list[str]) -> list[dict[str, Any]]:
    lowered_terms = [term.strip().lower() for term in terms if term.strip()]
    if not lowered_terms:
        return items
    result: list[dict[str, Any]] = []
    fields = ("sendEmail", "sendName", "subject", "toEmail", "toName", "text", "content", "html", "raw")
    for item in items:
        haystack = " ".join(str(item.get(field) or "") for field in fields).lower()
        if any(term in haystack for term in lowered_terms):
            result.append(item)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="CloudMail receive diagnostics")
    parser.add_argument("--address", default="", help="Recipient address to query")
    parser.add_argument("--probe", action="store_true", help="Generate an address and wait for a manual test email")
    parser.add_argument("--global-search", action="store_true", help="Search recent global CloudMail messages")
    parser.add_argument("--terms", default="openai,verification,verify,otp", help="Comma-separated terms for --global-search")
    parser.add_argument("--api-base", default="", help="Override CloudMail base URL")
    parser.add_argument("--admin-email", default="", help="Override CloudMail admin email")
    parser.add_argument("--admin-password", default="", help="Override CloudMail admin password")
    parser.add_argument("--domain", default="", help="Domain to use with --probe")
    parser.add_argument("--prefix", default="", help="Local-part prefix to use with --probe")
    parser.add_argument("--proxy", default="", help="Proxy URL, for example http://127.0.0.1:7890")
    parser.add_argument("--timeout", type=int, default=120, help="Polling timeout for --probe/--address")
    parser.add_argument("--interval", type=float, default=5.0, help="Polling interval in seconds")
    parser.add_argument("--size", type=int, default=100, help="emailList page size")
    parser.add_argument("--once", action="store_true", help="Query once instead of polling for --address")
    args = parser.parse_args()

    entry = _load_cloudmail_entry()
    api_base = (args.api_base or entry.get("api_base") or "").rstrip("/")
    admin_email = args.admin_email or entry.get("admin_email") or ""
    admin_password = args.admin_password or entry.get("admin_password") or ""
    proxy = args.proxy or str(entry.get("proxy") or "")

    if not api_base or not admin_email or not admin_password:
        print("[error] Missing api_base/admin_email/admin_password. Pass flags or configure data/register.json.")
        return 2

    session = _session(proxy)
    try:
        token = _gen_token(session, api_base, admin_email, admin_password)
    except Exception as error:
        print(f"[error] {error}")
        return 1
    print(f"[info] genToken ok: {token[:8]}...")

    if args.global_search:
        try:
            items = _email_list(session, api_base, token, size=max(1, args.size))
        except Exception as error:
            print(f"[error] {error}")
            return 1
        terms = [term for term in args.terms.split(",")]
        matches = _global_search(items, terms)
        print(f"[info] global recent count: {len(items)}")
        print(f"[info] global matches for {terms}: {len(matches)}")
        for index, item in enumerate(matches[:20], start=1):
            _print_item(index, item)
        return 0

    address = args.address.strip()
    if args.probe:
        domain = _domain_from_entry(entry, args.domain.strip())
        address = _random_address(domain, args.prefix.strip())
        print(f"[info] probe address: {address}")
        print("[action] Send any test email to this address now. Polling CloudMail...")

    if not address:
        print("[error] Use --address, --probe, or --global-search.")
        return 2

    deadline = time.time() + max(1, args.timeout)
    while True:
        try:
            items = _email_list(session, api_base, token, address=address, size=max(1, args.size))
        except Exception as error:
            print(f"[error] {error}")
            return 1
        if items or args.once:
            _summarize(items, address)
            return 0 if items else 1
        remaining = int(deadline - time.time())
        if remaining <= 0:
            _summarize([], address)
            return 1
        print(f"[info] no messages yet for {address}; {remaining}s remaining")
        time.sleep(max(0.2, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
