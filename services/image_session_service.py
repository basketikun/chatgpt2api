from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
import time
import uuid
from typing import Any

from services.account_service import AccountService
from services.image_service import (
    ImageGenerationError,
    edit_image_result,
    generate_image_result,
    is_token_invalid_error,
)

SESSION_TTL_SECONDS = 2 * 60 * 60
SESSION_EXPIRED_MESSAGE = "连续对话会话已失效，请从当前结果图重新开始编辑"


class ImageSessionExpiredError(Exception):
    pass


@dataclass
class ImageSessionState:
    session_id: str
    access_token: str
    upstream_conversation_id: str | None = None
    upstream_parent_message_id: str | None = None
    updated_at: float = 0.0
    turn_lock: Any = field(default_factory=Lock, repr=False, compare=False)

    def touch(self) -> None:
        self.updated_at = time.time()


class ImageSessionService:
    """Process-local web session handles for continuous image conversations."""

    def __init__(self, account_service: AccountService):
        self.account_service = account_service
        self._lock = Lock()
        self._sessions: dict[str, ImageSessionState] = {}

    def _prune_expired_locked(self, now: float) -> None:
        expired_session_ids = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.updated_at >= SESSION_TTL_SECONDS
        ]
        for session_id in expired_session_ids:
            self._sessions.pop(session_id, None)

    def _get_session_locked(self, session_id: str, now: float) -> ImageSessionState:
        self._prune_expired_locked(now)
        session = self._sessions.get(session_id)
        if session is None:
            raise ImageSessionExpiredError(SESSION_EXPIRED_MESSAGE)
        return session

    def _invalidate_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def _run_turn(
        self,
        session: ImageSessionState,
        prompt: str,
        model: str,
        images: list[tuple[bytes, str, str]] | None,
    ) -> dict:
        if images:
            result = edit_image_result(
                session.access_token,
                prompt,
                images,
                model,
                conversation_id=session.upstream_conversation_id,
                parent_message_id=session.upstream_parent_message_id,
            )
        else:
            result = generate_image_result(
                session.access_token,
                prompt,
                model,
                conversation_id=session.upstream_conversation_id,
                parent_message_id=session.upstream_parent_message_id,
            )
        self.account_service.mark_image_result(session.access_token, success=True)
        session.upstream_conversation_id = str(result.get("upstream_conversation_id") or "").strip() or None
        session.upstream_parent_message_id = str(result.get("upstream_parent_message_id") or "").strip() or None
        session.touch()
        return result

    def create_session(
        self,
        prompt: str,
        model: str,
        images: list[tuple[bytes, str, str]] | None = None,
    ) -> tuple[ImageSessionState, dict]:
        access_token = self.account_service.get_available_access_token()
        session = ImageSessionState(
            session_id=str(uuid.uuid4()),
            access_token=access_token,
            updated_at=time.time(),
        )
        try:
            result = self._run_turn(session, prompt, model, images)
        except ImageGenerationError:
            self.account_service.mark_image_result(access_token, success=False)
            raise

        with self._lock:
            self._prune_expired_locked(time.time())
            self._sessions[session.session_id] = session
        return session, result

    def create_turn(
        self,
        session_id: str,
        prompt: str,
        model: str,
        images: list[tuple[bytes, str, str]] | None = None,
    ) -> tuple[ImageSessionState, dict]:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            raise ImageSessionExpiredError(SESSION_EXPIRED_MESSAGE)

        with self._lock:
            session = self._get_session_locked(normalized_session_id, time.time())

        with session.turn_lock:
            with self._lock:
                self._get_session_locked(normalized_session_id, time.time())
            try:
                result = self._run_turn(session, prompt, model, images)
            except ImageGenerationError as exc:
                self.account_service.mark_image_result(session.access_token, success=False)
                if is_token_invalid_error(str(exc)):
                    self.account_service.remove_token(session.access_token)
                    self._invalidate_session(normalized_session_id)
                    raise ImageSessionExpiredError(SESSION_EXPIRED_MESSAGE) from exc
                raise

            with self._lock:
                self._sessions[session.session_id] = session
            return session, result


def serialize_image_session_response(session: ImageSessionState, result: dict) -> dict[str, object]:
    expires_at = datetime.fromtimestamp(session.updated_at + SESSION_TTL_SECONDS, tz=UTC)
    updated_at = datetime.fromtimestamp(session.updated_at, tz=UTC)
    return {
        "session_id": session.session_id,
        "created": int(result.get("created") or 0),
        "data": result.get("data") if isinstance(result.get("data"), list) else [],
        "updated_at": updated_at.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
    }
