"""手动 OAuth 桥服务

让用户用自己浏览器走一遍 OpenAI 的标准 OAuth + PKCE 授权码流程：
  1. 后端生成 code_verifier / code_challenge / state，构造 authorize URL。
  2. 用户在浏览器登录，浏览器最终被 OpenAI 重定向到 platform.openai.com 的
     callback 地址；用户从地址栏或 devtools 抓出 code，回填到前端。
  3. 后端拿之前存好的 code_verifier + 回填的 code 调用 /api/accounts/oauth/token
     得到 {access_token, refresh_token, id_token}。

得到的 refresh_token 跟 account_service 自动刷新机制用的 client_id 是同一个
（app_2SKx67EdpoN0G6j64rFvigXD），所以落盘后能直接进入 keepalive 周期。
"""
from __future__ import annotations

import secrets
import threading
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from curl_cffi import requests

from services.openai_oauth import (
    auth_base,
    common_headers,
    platform_auth0_client,
    platform_base,
    platform_oauth_audience,
    platform_oauth_client_id,
    platform_oauth_redirect_uri,
    sec_ch_ua,
    user_agent,
)
from services.proxy_service import proxy_settings


class OAuthLoginError(Exception):
    """OAuth 桥流程中的可预期错误，会被 API 层翻译成 400。"""


class OAuthLoginService:
    """维护 PKCE 临时会话，并完成 code → token 的兑换。"""

    _SESSION_TTL_SECONDS = 10 * 60  # 用户点开浏览器 + 拿 code 给的时间上限
    _MAX_SESSIONS = 64               # 防止异常累积；超过容量时清理最老的

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _generate_pkce() -> tuple[str, str]:
        """生成 PKCE code_verifier 与对应的 code_challenge（S256）。"""
        from utils.pkce import generate_pkce
        return generate_pkce()

    def _purge_expired_locked(self) -> None:
        """清理过期或溢出容量的会话，必须在持锁状态下调用。"""
        now = time.time()
        expired = [sid for sid, item in self._sessions.items() if now - item["created_at"] > self._SESSION_TTL_SECONDS]
        for sid in expired:
            self._sessions.pop(sid, None)
        if len(self._sessions) > self._MAX_SESSIONS:
            ordered = sorted(self._sessions.items(), key=lambda kv: kv[1]["created_at"])
            for sid, _ in ordered[: len(self._sessions) - self._MAX_SESSIONS]:
                self._sessions.pop(sid, None)

    def start(self, email_hint: str = "") -> dict[str, str]:
        """登记一个新的 PKCE 会话，返回 session_id 与可让用户打开的 authorize_url。

        state 形如 "<session_id>.<nonce>"，让 callback URL 自带 session_id，
        finish 时即便前端 React 状态被覆盖也能从 URL 恢复正确的 verifier。
        """
        verifier, challenge = self._generate_pkce()
        nonce = secrets.token_urlsafe(32)
        device_id = str(uuid.uuid4())
        session_id = uuid.uuid4().hex
        state = f"{session_id}.{secrets.token_urlsafe(16)}"

        params = {
            "issuer": auth_base,
            "client_id": platform_oauth_client_id,
            "audience": platform_oauth_audience,
            "redirect_uri": platform_oauth_redirect_uri,
            "device_id": device_id,
            "screen_hint": "login_or_signup",
            "max_age": "0",
            "scope": "openid profile email offline_access",
            "response_type": "code",
            "response_mode": "query",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "auth0Client": platform_auth0_client,
        }
        email_hint = str(email_hint or "").strip()
        if email_hint:
            params["login_hint"] = email_hint

        authorize_url = f"{auth_base}/api/accounts/authorize?{urlencode(params)}"

        with self._lock:
            self._purge_expired_locked()
            self._sessions[session_id] = {
                "code_verifier": verifier,
                "state": state,
                "created_at": time.time(),
                "redirect_uri": platform_oauth_redirect_uri,
            }

        return {
            "session_id": session_id,
            "authorize_url": authorize_url,
            "expires_in": str(self._SESSION_TTL_SECONDS),
            "redirect_uri_prefix": platform_oauth_redirect_uri,
        }

    @staticmethod
    def _extract_code_from_callback(value: str) -> tuple[str, str]:
        """从 callback URL 或 raw code 中提取 (code, state)。

        既允许用户粘贴整段 platform.openai.com/auth/callback?code=...&state=... 的 URL，
        也允许只粘 code 本身。
        """
        raw = str(value or "").strip()
        if not raw:
            return "", ""
        if raw.startswith("http://") or raw.startswith("https://"):
            try:
                parsed = parse_qs(urlparse(raw).query)
            except Exception as exc:
                raise OAuthLoginError(f"无法解析 callback URL: {exc}") from exc
            code = str((parsed.get("code") or [""])[0]).strip()
            state = str((parsed.get("state") or [""])[0]).strip()
            if not code:
                err = str((parsed.get("error_description") or parsed.get("error") or [""])[0]).strip()
                raise OAuthLoginError(err or "callback URL 中没有 code 参数")
            return code, state
        # 用户可能直接粘了 code 字符串
        return raw, ""

    def finish(self, session_id: str, callback: str) -> dict[str, str]:
        """用 session_id 配对的 code_verifier 把 callback 里的 code 换成 token 三件套。

        - 优先用 callback URL 自带 state 里的 session_id（更可靠），
          找不到才用前端传来的 session_id；
        - 失败时不立刻销毁 session（OAuth code 错配换 token 失败通常不会消耗 code），
          只有成功兑换才 pop，便于用户用同一 verifier 重试。
        """
        body_sid = str(session_id or "").strip()
        code, state = self._extract_code_from_callback(callback)
        if not code:
            raise OAuthLoginError("缺少 code 或 callback URL")

        # state 里嵌的 session_id 优先级最高
        state_sid = state.split(".", 1)[0] if state else ""
        candidate_sids = [sid for sid in (state_sid, body_sid) if sid]
        if not candidate_sids:
            raise OAuthLoginError("既未提供 session_id，callback URL 中也未携带 state")

        with self._lock:
            self._purge_expired_locked()
            session = None
            picked_sid = ""
            for sid in candidate_sids:
                cur = self._sessions.get(sid)
                if cur is not None:
                    session = cur
                    picked_sid = sid
                    break
        if session is None:
            raise OAuthLoginError(
                "OAuth 会话已过期或不存在，请回到导入对话框点\"重新生成\"再走一次"
            )

        if state and session.get("state") and state != session["state"]:
            raise OAuthLoginError(
                "state 不匹配。常见原因：你点过两次\"打开授权页面\"，但浏览器里登录的还是前一次的窗口。请点\"重新生成\"重来。"
            )

        tokens = self._exchange_code(
            code,
            session["code_verifier"],
            session.get("redirect_uri") or platform_oauth_redirect_uri,
        )
        # 仅在成功兑换之后才消耗 session
        with self._lock:
            self._sessions.pop(picked_sid, None)
        return tokens

    @staticmethod
    def _exchange_code(code: str, code_verifier: str, redirect_uri: str) -> dict[str, str]:
        """调用 /api/accounts/oauth/token 用 code+verifier 换 token 三件套。"""
        kwargs = proxy_settings.build_session_kwargs(
            impersonate="chrome",
            require_tls_verification=True,
        )
        session = requests.Session(**kwargs)
        try:
            response = session.post(
                f"{auth_base}/api/accounts/oauth/token",
                headers={
                    **common_headers,
                    "referer": f"{platform_base}/",
                    "origin": platform_base,
                    "auth0-client": platform_auth0_client,
                    "sec-ch-ua": sec_ch_ua,
                    "user-agent": user_agent,
                },
                json={
                    "client_id": platform_oauth_client_id,
                    "code_verifier": code_verifier,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                timeout=60,
            )
        except Exception as exc:
            raise OAuthLoginError(f"换 token 网络异常: {exc}") from exc
        finally:
            session.close()

        try:
            data = response.json() if response.text else {}
        except Exception:
            data = {}

        if response.status_code != 200 or not isinstance(data, dict) or not data.get("access_token"):
            detail = ""
            if isinstance(data, dict):
                detail = str(data.get("error_description") or data.get("error") or data.get("message") or "")
            if not detail:
                try:
                    detail = str(response.text or "")[:300]
                except Exception:
                    detail = ""
            # 打到 docker logs 方便排错——OAuth 换 token 的失败原因往往只有这里能看到
            print(
                f"[oauth-login] /api/accounts/oauth/token rejected: "
                f"status={response.status_code} detail={detail!r} "
                f"raw_body={(getattr(response, 'text', '') or '')[:500]!r}",
                flush=True,
            )
            raise OAuthLoginError(
                f"OpenAI 拒绝换 token (HTTP {response.status_code}){': ' + detail if detail else ''}"
            )

        access_token = str(data.get("access_token") or "").strip()
        refresh_token = str(data.get("refresh_token") or "").strip()
        id_token = str(data.get("id_token") or "").strip()

        if not access_token:
            raise OAuthLoginError("OpenAI 返回的 access_token 为空")
        if not refresh_token:
            # scope 含 offline_access 时正常会下发 refresh_token；这里给出明确提示
            raise OAuthLoginError(
                "OpenAI 没有返回 refresh_token（可能 scope 未包含 offline_access 或 code 已使用过）"
            )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "id_token": id_token,
        }


oauth_login_service = OAuthLoginService()
