from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base, sessionmaker

from services.config import DATA_DIR

Base = declarative_base()

UserRole = Literal["admin", "user"]
RedeemCodeType = Literal["image_quota", "concurrency", "invitation"]

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
JWT_ALGORITHM = "HS256"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso(value: datetime | None) -> str | None:
    normalized = as_utc(value)
    return normalized.isoformat() if normalized is not None else None


def clean_string(value: object) -> str:
    return str(value or "").strip()


def normalize_email(value: object) -> str:
    return clean_string(value).lower()


def normalize_code(value: object) -> str:
    return re.sub(r"\s+", "", clean_string(value)).upper()


def json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str, fallback: object) -> object:
    try:
        return json.loads(value)
    except Exception:
        return fallback


class UserServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, code: str = "bad_request") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class UserModel(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    role = Column(String(16), nullable=False, default="user", index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    image_quota = Column(Integer, nullable=False, default=0)
    image_concurrency = Column(Integer, nullable=False, default=1)
    active_image_requests = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_login_at = Column(DateTime(timezone=True), nullable=True)


class AuthSettingModel(Base):
    __tablename__ = "auth_settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class EmailVerificationCodeModel(Base):
    __tablename__ = "email_verification_codes"

    id = Column(String(36), primary_key=True)
    email = Column(String(255), nullable=False, index=True)
    purpose = Column(String(32), nullable=False, default="register", index=True)
    code_hash = Column(String(64), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_sent_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class RedeemCodeModel(Base):
    __tablename__ = "redeem_codes"

    id = Column(String(36), primary_key=True)
    code_hash = Column(String(64), unique=True, nullable=False, index=True)
    code_prefix = Column(String(8), nullable=False)
    code_suffix = Column(String(8), nullable=False)
    type = Column(String(32), nullable=False, index=True)
    value = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, default=True)
    used_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class PromoCodeModel(Base):
    __tablename__ = "promo_codes"

    id = Column(String(36), primary_key=True)
    code_hash = Column(String(64), unique=True, nullable=False, index=True)
    code_prefix = Column(String(8), nullable=False)
    code_suffix = Column(String(8), nullable=False)
    image_quota = Column(Integer, nullable=False, default=0)
    max_uses = Column(Integer, nullable=False, default=1)
    used_count = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class PromoCodeUsageModel(Base):
    __tablename__ = "promo_code_usages"
    __table_args__ = (UniqueConstraint("promo_code_id", "user_id", name="uq_promo_user"),)

    id = Column(String(36), primary_key=True)
    promo_code_id = Column(String(36), ForeignKey("promo_codes.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class ImageUsageEventModel(Base):
    __tablename__ = "image_usage_events"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    endpoint = Column(String(128), nullable=False)
    requested_count = Column(Integer, nullable=False, default=0)
    actual_count = Column(Integer, nullable=False, default=0)
    refunded_count = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="reserved", index=True)
    error = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    settled_at = Column(DateTime(timezone=True), nullable=True)


DEFAULT_SETTINGS: dict[str, object] = {
    "site_name": "chatgpt2api",
    "registration_enabled": True,
    "email_verification_enabled": True,
    "invitation_required": False,
    "promo_codes_enabled": True,
    "email_domain_whitelist": [],
    "default_image_quota": 0,
    "default_image_concurrency": 1,
    "verify_code_ttl_seconds": 900,
    "verify_send_cooldown_seconds": 60,
    "verify_max_attempts": 5,
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_username": "",
    "smtp_password": "",
    "smtp_from": "",
    "smtp_tls": True,
}

PUBLIC_SETTING_KEYS = {
    "site_name",
    "registration_enabled",
    "email_verification_enabled",
    "invitation_required",
    "promo_codes_enabled",
    "email_domain_whitelist",
}


@dataclass(frozen=True)
class QuotaReservation:
    event_id: str
    user_id: str
    requested_count: int
    bypass: bool = False


class UserService:
    def __init__(self, database_url: str | None = None) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.database_url = database_url or self._default_database_url()
        connect_args = {"check_same_thread": False} if self.database_url.startswith("sqlite") else {}
        self.engine = create_engine(self.database_url, pool_pre_ping=True, connect_args=connect_args)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self._password_hasher = PasswordHasher()
        self._quota_lock = Lock()
        self._settings_lock = Lock()
        self._ensure_defaults()

    @staticmethod
    def _default_database_url() -> str:
        return (
            os.getenv("CHATGPT2API_USER_DATABASE_URL", "").strip()
            or os.getenv("USER_DATABASE_URL", "").strip()
            or f"sqlite:///{DATA_DIR / 'users.db'}"
        )

    def _ensure_defaults(self) -> None:
        with self.Session() as session:
            changed = False
            for key, value in DEFAULT_SETTINGS.items():
                if session.get(AuthSettingModel, key) is None:
                    session.add(AuthSettingModel(key=key, value=json_dumps(value), updated_at=utc_now()))
                    changed = True
            if session.get(AuthSettingModel, "jwt_secret") is None:
                session.add(AuthSettingModel(key="jwt_secret", value=json_dumps(secrets.token_urlsafe(48)), updated_at=utc_now()))
                changed = True
            if changed:
                session.commit()

    def _settings_from_session(self, session) -> dict[str, object]:
        settings = dict(DEFAULT_SETTINGS)
        for row in session.query(AuthSettingModel).all():
            settings[row.key] = json_loads(row.value, row.value)
        if os.getenv("JWT_SECRET"):
            settings["jwt_secret"] = os.getenv("JWT_SECRET", "")
        return settings

    def get_settings(self) -> dict[str, object]:
        with self.Session() as session:
            return self._settings_from_session(session)

    def get_public_settings(self) -> dict[str, object]:
        settings = self.get_settings()
        return {key: settings.get(key) for key in PUBLIC_SETTING_KEYS}

    def get_admin_settings(self) -> dict[str, object]:
        settings = self.get_settings()
        settings.pop("jwt_secret", None)
        settings["has_smtp_password"] = bool(clean_string(settings.get("smtp_password")))
        settings["smtp_password"] = ""
        return settings

    def update_settings(self, updates: dict[str, object]) -> dict[str, object]:
        allowed = set(DEFAULT_SETTINGS)
        with self._settings_lock, self.Session() as session:
            for key, value in dict(updates or {}).items():
                if key not in allowed:
                    continue
                if key == "smtp_password" and clean_string(value) == "":
                    continue
                if key == "email_domain_whitelist":
                    if isinstance(value, str):
                        value = [item.strip().lower() for item in re.split(r"[\n,]", value) if item.strip()]
                    elif isinstance(value, list):
                        value = [clean_string(item).lower() for item in value if clean_string(item)]
                    else:
                        value = []
                if key in {
                    "default_image_quota",
                    "default_image_concurrency",
                    "verify_code_ttl_seconds",
                    "verify_send_cooldown_seconds",
                    "verify_max_attempts",
                    "smtp_port",
                }:
                    value = max(0, int(value or 0))
                    if key in {"default_image_concurrency", "verify_max_attempts"}:
                        value = max(1, value)
                if key in {
                    "registration_enabled",
                    "email_verification_enabled",
                    "invitation_required",
                    "promo_codes_enabled",
                    "smtp_tls",
                }:
                    value = bool(value)
                row = session.get(AuthSettingModel, key)
                if row is None:
                    row = AuthSettingModel(key=key)
                    session.add(row)
                row.value = json_dumps(value)
                row.updated_at = utc_now()
            session.commit()
        return self.get_admin_settings()

    def has_admin(self) -> bool:
        with self.Session() as session:
            return session.query(UserModel).filter(UserModel.role == "admin").count() > 0

    def setup_status(self) -> dict[str, object]:
        has_admin = self.has_admin()
        return {"has_admin": has_admin, "requires_setup": not has_admin}

    def validate_email(self, email: str) -> str:
        normalized = normalize_email(email)
        if not EMAIL_PATTERN.match(normalized):
            raise UserServiceError("invalid email")
        return normalized

    @staticmethod
    def validate_password(password: str) -> str:
        value = str(password or "")
        if len(value) < 8:
            raise UserServiceError("password must be at least 8 characters")
        return value

    def hash_password(self, password: str) -> str:
        return self._password_hasher.hash(self.validate_password(password))

    def verify_password(self, stored_hash: str, password: str) -> bool:
        try:
            return self._password_hasher.verify(stored_hash, password)
        except (VerifyMismatchError, VerificationError):
            return False

    def code_hash(self, code: str) -> str:
        normalized = normalize_code(code)
        secret = clean_string(self.get_settings().get("jwt_secret"))
        return hmac.new(secret.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()

    def _serialize_user(self, user: UserModel) -> dict[str, object]:
        return {
            "id": user.id,
            "email": user.email,
            "name": user.email,
            "role": user.role,
            "enabled": bool(user.enabled),
            "image_quota": int(user.image_quota or 0),
            "image_concurrency": int(user.image_concurrency or 0),
            "active_image_requests": int(user.active_image_requests or 0),
            "created_at": iso(user.created_at),
            "updated_at": iso(user.updated_at),
            "last_login_at": iso(user.last_login_at),
        }

    def create_token(self, user: UserModel | dict[str, object]) -> str:
        user_id = user.id if isinstance(user, UserModel) else clean_string(user.get("id"))
        now = utc_now()
        payload = {
            "sub": user_id,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=30)).timestamp()),
        }
        secret = clean_string(self.get_settings().get("jwt_secret"))
        return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)

    def authenticate_token(self, token: str) -> dict[str, object] | None:
        candidate = clean_string(token)
        if not candidate:
            return None
        try:
            payload = jwt.decode(candidate, clean_string(self.get_settings().get("jwt_secret")), algorithms=[JWT_ALGORITHM])
        except jwt.PyJWTError:
            return None
        user_id = clean_string(payload.get("sub"))
        if not user_id:
            return None
        with self.Session() as session:
            user = session.get(UserModel, user_id)
            if user is None or not bool(user.enabled):
                return None
            return self._serialize_user(user)

    def create_setup_admin(self, email: str, password: str) -> dict[str, object]:
        with self._settings_lock, self.Session() as session:
            if session.query(UserModel).filter(UserModel.role == "admin").count() > 0:
                raise UserServiceError("setup already completed", status_code=409, code="setup_completed")
            user = UserModel(
                id=str(uuid.uuid4()),
                email=self.validate_email(email),
                password_hash=self.hash_password(password),
                role="admin",
                enabled=True,
                image_quota=0,
                image_concurrency=0,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            session.add(user)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise UserServiceError("email already exists", status_code=409, code="duplicate_email") from exc
            return {"user": self._serialize_user(user), "token": self.create_token(user)}

    def login(self, email: str, password: str) -> dict[str, object]:
        normalized_email = normalize_email(email)
        with self.Session() as session:
            user = session.query(UserModel).filter(UserModel.email == normalized_email).one_or_none()
            if user is None or not self.verify_password(user.password_hash, password):
                raise UserServiceError("invalid email or password", status_code=401, code="invalid_credentials")
            if not bool(user.enabled):
                raise UserServiceError("user is disabled", status_code=403, code="user_disabled")
            user.last_login_at = utc_now()
            user.updated_at = utc_now()
            session.commit()
            return {"user": self._serialize_user(user), "token": self.create_token(user)}

    def get_user(self, user_id: str) -> dict[str, object] | None:
        with self.Session() as session:
            user = session.get(UserModel, clean_string(user_id))
            return self._serialize_user(user) if user is not None else None

    def list_users(self, query: str = "") -> list[dict[str, object]]:
        normalized_query = normalize_email(query)
        with self.Session() as session:
            q = session.query(UserModel).order_by(UserModel.created_at.desc())
            if normalized_query:
                q = q.filter(UserModel.email.contains(normalized_query))
            return [self._serialize_user(user) for user in q.all()]

    def create_user(
        self,
        *,
        email: str,
        password: str,
        role: UserRole = "user",
        enabled: bool = True,
        image_quota: int = 0,
        image_concurrency: int = 1,
    ) -> dict[str, object]:
        if role not in {"admin", "user"}:
            raise UserServiceError("invalid role")
        user = UserModel(
            id=str(uuid.uuid4()),
            email=self.validate_email(email),
            password_hash=self.hash_password(password),
            role=role,
            enabled=bool(enabled),
            image_quota=max(0, int(image_quota or 0)),
            image_concurrency=max(1, int(image_concurrency or 1)) if role == "user" else 0,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        with self.Session() as session:
            session.add(user)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise UserServiceError("email already exists", status_code=409, code="duplicate_email") from exc
            return self._serialize_user(user)

    def update_user(self, user_id: str, updates: dict[str, object]) -> dict[str, object]:
        with self.Session() as session:
            user = session.get(UserModel, clean_string(user_id))
            if user is None:
                raise UserServiceError("user not found", status_code=404, code="not_found")
            if "email" in updates:
                user.email = self.validate_email(str(updates.get("email") or ""))
            if "password" in updates and clean_string(updates.get("password")):
                user.password_hash = self.hash_password(str(updates.get("password") or ""))
            if "role" in updates and updates.get("role") in {"admin", "user"}:
                user.role = str(updates.get("role"))
            if "enabled" in updates:
                user.enabled = bool(updates.get("enabled"))
            if "image_quota" in updates:
                user.image_quota = max(0, int(updates.get("image_quota") or 0))
            if "image_concurrency" in updates:
                user.image_concurrency = max(1, int(updates.get("image_concurrency") or 1)) if user.role == "user" else 0
            user.updated_at = utc_now()
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise UserServiceError("email already exists", status_code=409, code="duplicate_email") from exc
            return self._serialize_user(user)

    def delete_user(self, user_id: str) -> None:
        with self.Session() as session:
            user = session.get(UserModel, clean_string(user_id))
            if user is None:
                raise UserServiceError("user not found", status_code=404, code="not_found")
            session.delete(user)
            session.commit()

    def _check_email_domain(self, email: str, settings: dict[str, object]) -> None:
        whitelist = settings.get("email_domain_whitelist")
        if not isinstance(whitelist, list) or not whitelist:
            return
        domain = email.rsplit("@", 1)[-1]
        allowed = {clean_string(item).lower() for item in whitelist if clean_string(item)}
        if domain not in allowed:
            raise UserServiceError("email domain is not allowed")

    def create_email_verification_code(self, email: str, purpose: str = "register") -> str:
        normalized_email = self.validate_email(email)
        normalized_purpose = clean_string(purpose) or "register"
        now = utc_now()
        with self.Session() as session:
            settings = self._settings_from_session(session)
            cooldown = int(settings.get("verify_send_cooldown_seconds") or 60)
            latest = (
                session.query(EmailVerificationCodeModel)
                .filter(
                    EmailVerificationCodeModel.email == normalized_email,
                    EmailVerificationCodeModel.purpose == normalized_purpose,
                )
                .order_by(EmailVerificationCodeModel.created_at.desc())
                .first()
            )
            if latest is not None and (now - as_utc(latest.last_sent_at)).total_seconds() < cooldown:
                raise UserServiceError("verification code sent too frequently", status_code=429, code="send_cooldown")
            code = f"{secrets.randbelow(1_000_000):06d}"
            row = EmailVerificationCodeModel(
                id=str(uuid.uuid4()),
                email=normalized_email,
                purpose=normalized_purpose,
                code_hash=self.code_hash(code),
                attempts=0,
                max_attempts=int(settings.get("verify_max_attempts") or 5),
                expires_at=now + timedelta(seconds=int(settings.get("verify_code_ttl_seconds") or 900)),
                created_at=now,
                last_sent_at=now,
            )
            session.add(row)
            session.commit()
            return code

    def consume_email_verification_code(self, email: str, code: str, purpose: str = "register") -> None:
        normalized_email = self.validate_email(email)
        normalized_purpose = clean_string(purpose) or "register"
        now = utc_now()
        with self.Session() as session:
            row = (
                session.query(EmailVerificationCodeModel)
                .filter(
                    EmailVerificationCodeModel.email == normalized_email,
                    EmailVerificationCodeModel.purpose == normalized_purpose,
                    EmailVerificationCodeModel.consumed_at.is_(None),
                )
                .order_by(EmailVerificationCodeModel.created_at.desc())
                .first()
            )
            if row is None:
                raise UserServiceError("verification code is invalid")
            if as_utc(row.expires_at) < now:
                raise UserServiceError("verification code expired")
            if row.attempts >= row.max_attempts:
                raise UserServiceError("verification code attempts exceeded")
            if not hmac.compare_digest(row.code_hash, self.code_hash(code)):
                row.attempts += 1
                session.commit()
                raise UserServiceError("verification code is invalid")
            row.consumed_at = now
            session.commit()

    def register(
        self,
        *,
        email: str,
        password: str,
        verification_code: str = "",
        invitation_code: str = "",
        promo_code: str = "",
    ) -> dict[str, object]:
        normalized_email = self.validate_email(email)
        self.validate_password(password)
        with self._settings_lock, self.Session() as session:
            settings = self._settings_from_session(session)
            if not bool(settings.get("registration_enabled", True)):
                raise UserServiceError("registration is disabled", status_code=403, code="registration_disabled")
            self._check_email_domain(normalized_email, settings)
            if session.query(UserModel).filter(UserModel.email == normalized_email).count() > 0:
                raise UserServiceError("email already exists", status_code=409, code="duplicate_email")

            if bool(settings.get("email_verification_enabled", True)):
                self.consume_email_verification_code(normalized_email, verification_code, "register")

            invitation = None
            if bool(settings.get("invitation_required", False)):
                invitation = self._find_valid_redeem_code(session, invitation_code, expected_type="invitation")

            promo = None
            if clean_string(promo_code):
                if not bool(settings.get("promo_codes_enabled", True)):
                    raise UserServiceError("promo code is disabled")
                promo = self._find_valid_promo_code(session, promo_code)

            image_quota = max(0, int(settings.get("default_image_quota") or 0))
            if promo is not None:
                image_quota += max(0, int(promo.image_quota or 0))
            user = UserModel(
                id=str(uuid.uuid4()),
                email=normalized_email,
                password_hash=self.hash_password(password),
                role="user",
                enabled=True,
                image_quota=image_quota,
                image_concurrency=max(1, int(settings.get("default_image_concurrency") or 1)),
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            session.add(user)
            if invitation is not None:
                invitation.used_by_user_id = user.id
                invitation.used_at = utc_now()
            if promo is not None:
                promo.used_count += 1
                session.add(
                    PromoCodeUsageModel(
                        id=str(uuid.uuid4()),
                        promo_code_id=promo.id,
                        user_id=user.id,
                        email=normalized_email,
                        used_at=utc_now(),
                    )
                )
            session.commit()
            return {"user": self._serialize_user(user), "token": self.create_token(user)}

    def generate_redeem_codes(
        self,
        *,
        type: RedeemCodeType,
        value: int = 0,
        count: int = 1,
        expires_at: datetime | None = None,
    ) -> list[dict[str, object]]:
        if type not in {"image_quota", "concurrency", "invitation"}:
            raise UserServiceError("invalid redeem code type")
        normalized_count = max(1, min(500, int(count or 1)))
        normalized_value = 0 if type == "invitation" else max(1, int(value or 1))
        prefix_map = {"image_quota": "IMG", "concurrency": "CON", "invitation": "INV"}
        created: list[dict[str, object]] = []
        with self.Session() as session:
            for _ in range(normalized_count):
                code = f"{prefix_map[type]}-{secrets.token_urlsafe(9).replace('-', '').replace('_', '').upper()[:12]}"
                row = RedeemCodeModel(
                    id=str(uuid.uuid4()),
                    code_hash=self.code_hash(code),
                    code_prefix=code[:4],
                    code_suffix=code[-4:],
                    type=type,
                    value=normalized_value,
                    enabled=True,
                    expires_at=expires_at,
                    created_at=utc_now(),
                )
                session.add(row)
                created.append({"code": code, **self._serialize_redeem_code(row)})
            session.commit()
        return created

    def _serialize_redeem_code(self, row: RedeemCodeModel) -> dict[str, object]:
        return {
            "id": row.id,
            "code_preview": f"{row.code_prefix}...{row.code_suffix}",
            "type": row.type,
            "value": int(row.value or 0),
            "enabled": bool(row.enabled),
            "used": bool(row.used_at),
            "used_by_user_id": row.used_by_user_id,
            "used_at": iso(row.used_at),
            "expires_at": iso(row.expires_at),
            "created_at": iso(row.created_at),
        }

    def list_redeem_codes(self) -> list[dict[str, object]]:
        with self.Session() as session:
            return [
                self._serialize_redeem_code(row)
                for row in session.query(RedeemCodeModel).order_by(RedeemCodeModel.created_at.desc()).all()
            ]

    def update_redeem_code(self, code_id: str, updates: dict[str, object]) -> dict[str, object]:
        with self.Session() as session:
            row = session.get(RedeemCodeModel, clean_string(code_id))
            if row is None:
                raise UserServiceError("redeem code not found", status_code=404, code="not_found")
            if "enabled" in updates:
                row.enabled = bool(updates.get("enabled"))
            if "expires_at" in updates:
                row.expires_at = parse_optional_datetime(updates.get("expires_at"))
            session.commit()
            return self._serialize_redeem_code(row)

    def delete_redeem_code(self, code_id: str) -> None:
        with self.Session() as session:
            row = session.get(RedeemCodeModel, clean_string(code_id))
            if row is None:
                raise UserServiceError("redeem code not found", status_code=404, code="not_found")
            session.delete(row)
            session.commit()

    def _find_valid_redeem_code(
        self,
        session,
        code: str,
        *,
        expected_type: RedeemCodeType | None = None,
    ) -> RedeemCodeModel:
        normalized = normalize_code(code)
        if not normalized:
            raise UserServiceError("redeem code is required")
        row = session.query(RedeemCodeModel).filter(RedeemCodeModel.code_hash == self.code_hash(normalized)).one_or_none()
        if row is None:
            raise UserServiceError("redeem code is invalid")
        if expected_type is not None and row.type != expected_type:
            raise UserServiceError("redeem code type is invalid")
        if not bool(row.enabled):
            raise UserServiceError("redeem code is disabled")
        if row.used_at is not None:
            raise UserServiceError("redeem code has already been used")
        if row.expires_at is not None and as_utc(row.expires_at) < utc_now():
            raise UserServiceError("redeem code expired")
        return row

    def redeem(self, user_id: str, code: str) -> dict[str, object]:
        with self.Session() as session:
            user = session.get(UserModel, clean_string(user_id))
            if user is None or not bool(user.enabled):
                raise UserServiceError("user not found", status_code=404, code="not_found")
            row = self._find_valid_redeem_code(session, code)
            if row.type == "invitation":
                raise UserServiceError("invitation code can only be used during registration")
            if row.type == "image_quota":
                user.image_quota += max(1, int(row.value or 1))
            elif row.type == "concurrency":
                user.image_concurrency += max(1, int(row.value or 1))
            row.used_by_user_id = user.id
            row.used_at = utc_now()
            user.updated_at = utc_now()
            session.commit()
            return {"redeem": self._serialize_redeem_code(row), "user": self._serialize_user(user)}

    def redeem_history(self, user_id: str) -> list[dict[str, object]]:
        with self.Session() as session:
            rows = (
                session.query(RedeemCodeModel)
                .filter(RedeemCodeModel.used_by_user_id == clean_string(user_id))
                .order_by(RedeemCodeModel.used_at.desc())
                .all()
            )
            return [self._serialize_redeem_code(row) for row in rows]

    def _serialize_promo_code(self, row: PromoCodeModel) -> dict[str, object]:
        return {
            "id": row.id,
            "code_preview": f"{row.code_prefix}...{row.code_suffix}",
            "image_quota": int(row.image_quota or 0),
            "max_uses": int(row.max_uses or 0),
            "used_count": int(row.used_count or 0),
            "enabled": bool(row.enabled),
            "expires_at": iso(row.expires_at),
            "created_at": iso(row.created_at),
        }

    def create_promo_code(
        self,
        *,
        code: str,
        image_quota: int,
        max_uses: int,
        expires_at: datetime | None = None,
        enabled: bool = True,
    ) -> dict[str, object]:
        normalized = normalize_code(code)
        if not normalized:
            raise UserServiceError("promo code is required")
        row = PromoCodeModel(
            id=str(uuid.uuid4()),
            code_hash=self.code_hash(normalized),
            code_prefix=normalized[:4],
            code_suffix=normalized[-4:],
            image_quota=max(0, int(image_quota or 0)),
            max_uses=max(1, int(max_uses or 1)),
            used_count=0,
            enabled=bool(enabled),
            expires_at=expires_at,
            created_at=utc_now(),
        )
        with self.Session() as session:
            session.add(row)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise UserServiceError("promo code already exists", status_code=409, code="duplicate_code") from exc
            return self._serialize_promo_code(row)

    def _find_valid_promo_code(self, session, code: str) -> PromoCodeModel:
        normalized = normalize_code(code)
        if not normalized:
            raise UserServiceError("promo code is required")
        row = session.query(PromoCodeModel).filter(PromoCodeModel.code_hash == self.code_hash(normalized)).one_or_none()
        if row is None:
            raise UserServiceError("promo code is invalid")
        if not bool(row.enabled):
            raise UserServiceError("promo code is disabled")
        if row.expires_at is not None and as_utc(row.expires_at) < utc_now():
            raise UserServiceError("promo code expired")
        if int(row.used_count or 0) >= int(row.max_uses or 0):
            raise UserServiceError("promo code usage limit reached")
        return row

    def list_promo_codes(self) -> list[dict[str, object]]:
        with self.Session() as session:
            return [
                self._serialize_promo_code(row)
                for row in session.query(PromoCodeModel).order_by(PromoCodeModel.created_at.desc()).all()
            ]

    def update_promo_code(self, code_id: str, updates: dict[str, object]) -> dict[str, object]:
        with self.Session() as session:
            row = session.get(PromoCodeModel, clean_string(code_id))
            if row is None:
                raise UserServiceError("promo code not found", status_code=404, code="not_found")
            if "image_quota" in updates:
                row.image_quota = max(0, int(updates.get("image_quota") or 0))
            if "max_uses" in updates:
                row.max_uses = max(1, int(updates.get("max_uses") or 1))
            if "enabled" in updates:
                row.enabled = bool(updates.get("enabled"))
            if "expires_at" in updates:
                row.expires_at = parse_optional_datetime(updates.get("expires_at"))
            session.commit()
            return self._serialize_promo_code(row)

    def delete_promo_code(self, code_id: str) -> None:
        with self.Session() as session:
            row = session.get(PromoCodeModel, clean_string(code_id))
            if row is None:
                raise UserServiceError("promo code not found", status_code=404, code="not_found")
            session.delete(row)
            session.commit()

    def reserve_image_quota(self, identity: dict[str, object], requested_count: int, endpoint: str) -> QuotaReservation:
        if identity.get("role") == "admin":
            return QuotaReservation(event_id="", user_id=clean_string(identity.get("id")), requested_count=requested_count, bypass=True)
        user_id = clean_string(identity.get("id"))
        amount = max(1, int(requested_count or 1))
        with self._quota_lock, self.Session() as session:
            user = session.get(UserModel, user_id)
            if user is None or not bool(user.enabled):
                raise UserServiceError("user not found", status_code=401, code="invalid_token")
            if int(user.active_image_requests or 0) >= int(user.image_concurrency or 1):
                raise UserServiceError("image concurrency limit exceeded", status_code=429, code="rate_limit_exceeded")
            if int(user.image_quota or 0) < amount:
                raise UserServiceError("insufficient image quota", status_code=429, code="insufficient_quota")
            user.image_quota -= amount
            user.active_image_requests += 1
            user.updated_at = utc_now()
            event = ImageUsageEventModel(
                id=str(uuid.uuid4()),
                user_id=user.id,
                endpoint=endpoint,
                requested_count=amount,
                status="reserved",
                created_at=utc_now(),
            )
            session.add(event)
            session.commit()
            return QuotaReservation(event_id=event.id, user_id=user.id, requested_count=amount)

    def settle_image_quota(
        self,
        reservation: QuotaReservation | None,
        *,
        success: bool,
        actual_count: int = 0,
        error: str = "",
    ) -> None:
        if reservation is None or reservation.bypass:
            return
        with self._quota_lock, self.Session() as session:
            user = session.get(UserModel, reservation.user_id)
            event = session.get(ImageUsageEventModel, reservation.event_id)
            if user is None or event is None or event.status != "reserved":
                return
            actual = max(0, min(int(actual_count or 0), int(reservation.requested_count or 0))) if success else 0
            refund = max(0, int(reservation.requested_count or 0) - actual)
            user.image_quota += refund
            user.active_image_requests = max(0, int(user.active_image_requests or 0) - 1)
            user.updated_at = utc_now()
            event.actual_count = actual
            event.refunded_count = refund
            event.status = "success" if success else "failed"
            event.error = clean_string(error)
            event.settled_at = utc_now()
            session.commit()


def parse_optional_datetime(value: object) -> datetime | None:
    text = clean_string(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise UserServiceError("invalid datetime") from exc
    return as_utc(parsed)


user_service = UserService()
