from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from backend.models import AuthUser, RegisterResponse
from backend.services.mongo_service import get_database
from backend.settings import settings


PASSWORD_HASHER = PasswordHasher()


class AuthError(ValueError):
    code = "auth_error"


class EmailAlreadyRegistered(AuthError):
    code = "email_already_registered"


class InvalidCredentials(AuthError):
    code = "invalid_credentials"


class EmailNotVerified(AuthError):
    code = "email_not_verified"


class InvalidVerification(AuthError):
    code = "invalid_verification"


class VerificationCooldown(AuthError):
    code = "verification_cooldown"


class InvalidSession(AuthError):
    code = "invalid_session"


class CsrfError(InvalidSession):
    code = "csrf_failed"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.isoformat()


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalized_email(email: str) -> str:
    return email.strip().lower()


def public_user(user: dict[str, Any]) -> AuthUser:
    return AuthUser(
        id=user["id"],
        email=user["email"],
        created_at=user["created_at"],
        verified_at=user["verified_at"],
    )


NO_ID = {"_id": 0}


def _document(record: dict[str, Any]) -> dict[str, Any]:
    return {"_id": record["id"], **record}


class AuthRepository:
    def __init__(self, database: Database | None = None):
        self.db = database if database is not None else get_database()

    def _audit(self, kind: str, user_id: str, current: datetime, **extra: Any) -> None:
        record = {"id": str(uuid4()), "kind": kind, "user_id": user_id, "created_at": iso(current), **extra}
        self.db.audit_events.insert_one(_document(record))

    def prepare_registration(self, email: str, password: str) -> tuple[RegisterResponse, str, str]:
        current = now_utc()
        verification_token = secrets.token_urlsafe(32)
        socket_token = secrets.token_urlsafe(32)
        registration_id = str(uuid4())
        user_id = str(uuid4())
        expires_at = current + timedelta(hours=settings.auth_verification_hours)
        email_key = normalized_email(email)

        existing = self.db.users.find_one({"email": email_key}, NO_ID)
        if existing and existing["status"] == "active":
            raise EmailAlreadyRegistered("An account already exists for this email.")
        if existing:
            user_id = existing["id"]
            self.db.users.update_one(
                {"_id": user_id, "status": {"$ne": "active"}},
                {"$set": {"password_hash": PASSWORD_HASHER.hash(password), "updated_at": iso(current)}},
            )
            self.db.email_verifications.update_many(
                {"user_id": user_id, "consumed_at": None},
                {"$set": {"consumed_at": iso(current), "status": "superseded"}},
            )
        else:
            try:
                self.db.users.insert_one(
                    _document(
                        {
                            "id": user_id,
                            "email": email_key,
                            "password_hash": PASSWORD_HASHER.hash(password),
                            "status": "pending",
                            "created_at": iso(current),
                            "updated_at": iso(current),
                            "verified_at": None,
                        }
                    )
                )
            except DuplicateKeyError as exc:
                raise EmailAlreadyRegistered("An account already exists for this email.") from exc
        self.db.email_verifications.insert_one(
            _document(
                {
                    "id": registration_id,
                    "user_id": user_id,
                    "token_digest": token_digest(verification_token),
                    "socket_token_digest": token_digest(socket_token),
                    "created_at": iso(current),
                    "last_sent_at": iso(current),
                    "expires_at": iso(expires_at),
                    "consumed_at": None,
                    "status": "pending",
                    "send_count": 1,
                }
            )
        )
        self._audit("auth.registration_started", user_id, current)
        return (
            RegisterResponse(
                registration_id=registration_id,
                socket_token=socket_token,
                expires_at=iso(expires_at),
            ),
            verification_token,
            email_key,
        )

    def rotate_verification(self, registration_id: str, socket_token: str) -> tuple[str, str, str]:
        current = now_utc()
        new_token = secrets.token_urlsafe(32)
        record = self.db.email_verifications.find_one({"_id": registration_id}, NO_ID)
        if record is None or not secrets.compare_digest(record["socket_token_digest"], token_digest(socket_token)):
            raise InvalidVerification("This registration link is invalid.")
        record_status = record.get("status")
        if record_status not in {None, "pending"} or record.get("consumed_at") is not None or parse_iso(record["expires_at"]) <= current:
            raise InvalidVerification("This registration has expired.")
        if parse_iso(record["last_sent_at"]) + timedelta(seconds=60) > current:
            raise VerificationCooldown("Wait 60 seconds before sending another email.")
        user = self.db.users.find_one({"_id": record["user_id"]}, NO_ID)
        if user is None:
            raise InvalidVerification("This registration link is invalid.")
        updated = self.db.email_verifications.update_one(
            # Guard on last_sent_at so two concurrent resends cannot both pass the cooldown.
            {"_id": registration_id, "last_sent_at": record["last_sent_at"], "consumed_at": None},
            {
                "$set": {"token_digest": token_digest(new_token), "last_sent_at": iso(current)},
                "$inc": {"send_count": 1},
            },
        )
        if updated.modified_count != 1:
            raise VerificationCooldown("Wait 60 seconds before sending another email.")
        return new_token, user["email"], record["expires_at"]

    def verify_email(self, token: str) -> AuthUser:
        current = now_utc()
        digest = token_digest(token)
        record = self.db.email_verifications.find_one({"token_digest": digest}, NO_ID)
        if record is None:
            raise InvalidVerification("This verification link is invalid or expired.")
        user = self.db.users.find_one({"_id": record["user_id"]}, NO_ID)
        if user is None:
            raise InvalidVerification("This verification link is invalid or expired.")
        legacy_verified = (
            record.get("status") is None
            and record.get("consumed_at") is not None
            and user.get("verified_at") == record.get("consumed_at")
        )
        if record.get("status") == "verified" or legacy_verified:
            if user.get("status") == "active" and user.get("verified_at"):
                if record.get("status") != "verified":
                    self.db.email_verifications.update_one({"_id": record["id"]}, {"$set": {"status": "verified"}})
                return public_user(user)
            if record.get("status") == "verified" and record.get("consumed_at"):
                # A concurrent request consumed this token but has not activated the user yet;
                # only a successful consume sets "verified", so finishing the activation is safe.
                verified_at = record["consumed_at"]
                self.db.users.update_one(
                    {"_id": user["id"], "status": {"$ne": "active"}},
                    {"$set": {"status": "active", "verified_at": verified_at, "updated_at": verified_at}},
                )
                user.update(status="active", verified_at=verified_at, updated_at=verified_at)
                return public_user(user)
            raise InvalidVerification("This verification link is invalid or expired.")
        if record.get("status") == "superseded" or record.get("consumed_at") is not None or parse_iso(record["expires_at"]) <= current:
            raise InvalidVerification("This verification link is invalid or expired.")
        consumed = self.db.email_verifications.update_one(
            {"_id": record["id"], "consumed_at": None, "status": {"$in": [None, "pending"]}},
            {"$set": {"consumed_at": iso(current), "status": "verified"}},
        )
        if consumed.modified_count != 1:
            # Lost a race: another request consumed or superseded this token first.
            return self.verify_email(token)
        self.db.users.update_one(
            {"_id": user["id"]},
            {"$set": {"status": "active", "verified_at": iso(current), "updated_at": iso(current)}},
        )
        self._audit("auth.email_verified", user["id"], current)
        user.update(status="active", verified_at=iso(current), updated_at=iso(current))
        return public_user(user)

    def registration_status(self, registration_id: str, socket_token: str) -> str:
        current = now_utc()
        record = self.db.email_verifications.find_one({"_id": registration_id}, NO_ID)
        if record is None or not secrets.compare_digest(record["socket_token_digest"], token_digest(socket_token)):
            raise InvalidVerification("This registration channel is invalid.")
        user = self.db.users.find_one({"_id": record["user_id"]}, NO_ID)
        legacy_verified = (
            record.get("status") is None
            and record.get("consumed_at") is not None
            and user is not None
            and user.get("verified_at") == record.get("consumed_at")
        )
        if user and user["status"] == "active" and (record.get("status") == "verified" or legacy_verified):
            return "verified"
        if record.get("status") == "superseded" or record.get("consumed_at") is not None or parse_iso(record["expires_at"]) <= current:
            return "expired"
        return "pending"

    def authenticate(self, email: str, password: str) -> tuple[AuthUser, dict[str, Any]]:
        email_key = normalized_email(email)
        user = self.db.users.find_one({"email": email_key}, NO_ID)
        if user is None:
            raise InvalidCredentials("Email or password is incorrect.")
        try:
            PASSWORD_HASHER.verify(user["password_hash"], password)
        except (VerificationError, InvalidHashError) as exc:
            raise InvalidCredentials("Email or password is incorrect.") from exc
        if user["status"] != "active" or not user.get("verified_at"):
            raise EmailNotVerified("Verify your email before signing in.")
        if PASSWORD_HASHER.check_needs_rehash(user["password_hash"]):
            self.db.users.update_one(
                {"_id": user["id"]},
                {"$set": {"password_hash": PASSWORD_HASHER.hash(password), "updated_at": iso(now_utc())}},
            )
        return public_user(user), user

    def create_session(self, user_id: str) -> tuple[str, str]:
        current = now_utc()
        expires = current + timedelta(days=settings.auth_session_days)
        session_id = str(uuid4())
        csrf_token = secrets.token_urlsafe(24)
        self.db.sessions.insert_one(
            _document(
                {
                    "id": session_id,
                    "user_id": user_id,
                    "csrf_digest": token_digest(csrf_token),
                    "created_at": iso(current),
                    "last_seen_at": iso(current),
                    "expires_at": iso(expires),
                    "revoked_at": None,
                }
            )
        )
        encoded = jwt.encode(
            {"sub": user_id, "jti": session_id, "iss": settings.auth_jwt_issuer, "iat": current, "exp": expires},
            settings.auth_jwt_secret,
            algorithm="HS256",
        )
        return encoded, csrf_token

    def resolve_session(self, encoded: str) -> tuple[AuthUser, dict[str, Any]]:
        try:
            claims = jwt.decode(
                encoded,
                settings.auth_jwt_secret,
                algorithms=["HS256"],
                issuer=settings.auth_jwt_issuer,
                options={"require": ["sub", "jti", "iss", "iat", "exp"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidSession("Your session is invalid or expired.") from exc
        session = self.db.sessions.find_one({"_id": claims["jti"]}, NO_ID)
        if (
            session is None
            or session.get("revoked_at") is not None
            or parse_iso(session["expires_at"]) <= now_utc()
            or session["user_id"] != claims["sub"]
        ):
            raise InvalidSession("Your session is invalid or expired.")
        user = self.db.users.find_one({"_id": session["user_id"], "status": "active"}, NO_ID)
        if user is None:
            raise InvalidSession("Your session is invalid or expired.")
        return public_user(user), session

    def validate_csrf(self, session: dict[str, Any], cookie_token: str | None, header_token: str | None) -> None:
        if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
            raise CsrfError("CSRF validation failed.")
        if not secrets.compare_digest(session["csrf_digest"], token_digest(cookie_token)):
            raise CsrfError("CSRF validation failed.")

    def revoke_session(self, session_id: str) -> None:
        self.db.sessions.update_one(
            {"_id": session_id, "revoked_at": None},
            {"$set": {"revoked_at": iso(now_utc())}},
        )

    def resolve_user(self, user_id: str) -> AuthUser:
        user = self.db.users.find_one({"_id": user_id, "status": "active"}, NO_ID)
        if user is None:
            raise InvalidSession("User not found.")
        return public_user(user)


def session_cookie_options() -> dict[str, Any]:
    return {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": "lax",
        "path": "/",
        "max_age": settings.auth_session_days * 24 * 60 * 60,
    }
