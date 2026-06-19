#!/usr/bin/env python3
"""One-shot OpenAI signup delivery probe.

It reuses the production registration flow, but lets us switch the OAuth entry
between the current Platform client and ChatGPT web's NextAuth/OpenAI client.
The goal is to verify whether CloudMail delivery depends on the OAuth client.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.register import openai_register  # noqa: E402
from services.register.mail_provider import create_mailbox, release_mailbox, wait_for_code  # noqa: E402


REGISTER_JSON = Path(__file__).resolve().parents[1] / "data" / "register.json"

CHATGPT_CLIENT_ID = "app_X8zY6vW2pQ9tR3dE7nK1jL5gH"
CHATGPT_REDIRECT_URI = "https://chatgpt.com/api/auth/callback/openai"


def _load_config(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "mail" not in data:
        raise RuntimeError(f"{path} does not contain mail config")
    return data


def _config_from_args(args: argparse.Namespace) -> dict:
    domains = [item.strip() for item in str(args.domain or "").split(",") if item.strip()]
    if not (args.api_base and args.admin_email and args.admin_password and domains):
        missing = [
            name
            for name, value in (
                ("--api-base", args.api_base),
                ("--admin-email", args.admin_email),
                ("--admin-password", args.admin_password),
                ("--domain", domains),
            )
            if not value
        ]
        raise RuntimeError(f"missing CloudMail flags: {', '.join(missing)}")
    return {
        "mail": {
            "request_timeout": 30,
            "wait_timeout": args.wait_timeout or 120,
            "wait_interval": 3,
            "providers": [
                {
                    "enable": True,
                    "type": "cloudmail_gen",
                    "api_base": args.api_base.rstrip("/"),
                    "admin_email": args.admin_email,
                    "admin_password": args.admin_password,
                    "domain": domains,
                    "subdomain": [],
                    "email_prefix": args.email_prefix or "",
                }
            ],
        },
        "proxy": args.proxy or "",
    }


def _use_chatgpt_entry() -> None:
    openai_register.platform_base = "https://chatgpt.com"
    openai_register.platform_oauth_client_id = CHATGPT_CLIENT_ID
    openai_register.platform_oauth_redirect_uri = CHATGPT_REDIRECT_URI


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe OpenAI signup delivery to CloudMail")
    parser.add_argument("--entry", choices=("platform", "chatgpt"), default="platform")
    parser.add_argument("--proxy", default=None)
    parser.add_argument("--mail-proxy", default=None)
    parser.add_argument("--email-prefix", default=None)
    parser.add_argument("--username", default=None, help="Force CloudMail local-part for the generated mailbox")
    parser.add_argument("--wait-timeout", type=int, default=None)
    parser.add_argument("--passwordless-probe", action="store_true")
    parser.add_argument("--register-json", default=str(REGISTER_JSON), help="Path to register.json")
    parser.add_argument("--api-base", default="", help="CloudMail base URL; allows running without register.json")
    parser.add_argument("--admin-email", default="", help="CloudMail admin email; allows running without register.json")
    parser.add_argument("--admin-password", default="", help="CloudMail admin password; allows running without register.json")
    parser.add_argument("--domain", default="", help="Comma-separated CloudMail domains; allows running without register.json")
    args = parser.parse_args()

    if args.api_base or args.admin_email or args.admin_password or args.domain:
        cfg = _config_from_args(args)
    else:
        cfg = _load_config(Path(args.register_json))
    mail = cfg["mail"]
    selected_proxy = cfg.get("proxy", "") if args.proxy is None else args.proxy
    if args.email_prefix is not None:
        for provider in mail.get("providers") or []:
            if isinstance(provider, dict) and provider.get("type") == "cloudmail_gen":
                provider["email_prefix"] = args.email_prefix
    if args.wait_timeout is not None:
        mail["wait_timeout"] = args.wait_timeout

    mail_config = dict(mail)
    if args.mail_proxy is not None:
        mail_config["proxy"] = args.mail_proxy
    openai_register.config.update(
        {
            "mail": mail_config,
            "proxy": selected_proxy,
            "total": 1,
            "threads": 1,
        }
    )
    if args.entry == "chatgpt":
        _use_chatgpt_entry()

    print(f"[info] entry={args.entry}")
    print(f"[info] client_id={openai_register.platform_oauth_client_id}")
    print(f"[info] redirect_uri={openai_register.platform_oauth_redirect_uri}")
    registrar = openai_register.PlatformRegistrar(openai_register.config.get("proxy", ""))
    try:
        if args.passwordless_probe:
            mailbox = create_mailbox(openai_register.config["mail"], args.username or None)
            email = str(mailbox.get("address") or "").strip()
            print(f"[info] mailbox={email}")
            try:
                registrar._platform_authorize(email, 1)
                registrar._send_otp(1)
                code = wait_for_code(openai_register.config["mail"], mailbox)
                if not code:
                    raise RuntimeError(
                        "wait_otp_timeout"
                        f" (cloudmail_raw={mailbox.get('_cloudmail_last_raw_count', 'unknown')},"
                        f" matched={mailbox.get('_cloudmail_last_matched_count', 'unknown')})"
                    )
                print(f"[result] received_code={code}")
                return 0
            except Exception:
                release_mailbox(mailbox)
                raise
        if args.username:
            original_create_mailbox = openai_register.create_mailbox

            def create_fixed_mailbox():
                return original_create_mailbox(args.username)

            openai_register.create_mailbox = create_fixed_mailbox
        result = registrar.register(1)
        print("[result] success")
        print(json.dumps({k: result.get(k) for k in ("email", "source_type", "created_at")}, ensure_ascii=False))
        return 0
    except Exception as error:
        print(f"[result] failed: {error}")
        return 1
    finally:
        registrar.close()


if __name__ == "__main__":
    raise SystemExit(main())
