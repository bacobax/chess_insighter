from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from backend.models import AuthUser, RegisterResponse
from backend.services.database_service import JsonDatabase
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


class AuthRepository:
    def __init__(self, database: JsonDatabase | None = None):
        self.database = database or JsonDatabase()

    def prepare_registration(self, email: str, password: str) -> tuple[RegisterResponse, str, str]:
        current = now_utc()
        verification_token = secrets.token_urlsafe(32)
        socket_token = secrets.token_urlsafe(32)
        registration_id = str(uuid4())
        user_id = str(uuid4())
        expires_at = current + timedelta(hours=settings.auth_verification_hours)
        email_key = normalized_email(email)

        def operation(data: dict[str, Any]) -> tuple[RegisterResponse, str, str]:
            nonlocal user_id
            existing = next((user for user in data["users"] if user["email"] == email_key), None)
            if existing and existing["status"] == "active":
                raise EmailAlreadyRegistered("An account already exists for this email.")
            if existing:
                user_id = existing["id"]
                existing.update(
                    password_hash=PASSWORD_HASHER.hash(password),
                    updated_at=iso(current),
                )
                for record in data["email_verifications"]:
                    if record["user_id"] == user_id and record.get("consumed_at") is None:
                        record["consumed_at"] = iso(current)
                        record["status"] = "superseded"
            else:
                data["users"].append(
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
            data["email_verifications"].append(
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
            data["audit_events"].append(
                {"id": str(uuid4()), "kind": "auth.registration_started", "user_id": user_id, "created_at": iso(current)}
            )
            return (
                RegisterResponse(
                    registration_id=registration_id,
                    socket_token=socket_token,
                    expires_at=iso(expires_at),
                ),
                verification_token,
                email_key,
            )

        return self.database.transaction(operation)

    def rotate_verification(self, registration_id: str, socket_token: str) -> tuple[str, str, str]:
        current = now_utc()
        new_token = secrets.token_urlsafe(32)

        def operation(data: dict[str, Any]) -> tuple[str, str, str]:
            record = next((item for item in data["email_verifications"] if item["id"] == registration_id), None)
            if record is None or not secrets.compare_digest(record["socket_token_digest"], token_digest(socket_token)):
                raise InvalidVerification("This registration link is invalid.")
            record_status = record.get("status")
            if record_status not in {None, "pending"} or record.get("consumed_at") is not None or parse_iso(record["expires_at"]) <= current:
                raise InvalidVerification("This registration has expired.")
            if parse_iso(record["last_sent_at"]) + timedelta(seconds=60) > current:
                raise VerificationCooldown("Wait 60 seconds before sending another email.")
            user = next(user for user in data["users"] if user["id"] == record["user_id"])
            record.update(
                token_digest=token_digest(new_token),
                last_sent_at=iso(current),
                send_count=int(record.get("send_count", 1)) + 1,
            )
            return new_token, user["email"], record["expires_at"]

        return self.database.transaction(operation)

    def verify_email(self, token: str) -> AuthUser:
        current = now_utc()
        digest = token_digest(token)

        def operation(data: dict[str, Any]) -> AuthUser:
            record = next((item for item in data["email_verifications"] if secrets.compare_digest(item["token_digest"], digest)), None)
            if record is None:
                raise InvalidVerification("This verification link is invalid or expired.")
            user = next(user for user in data["users"] if user["id"] == record["user_id"])
            legacy_verified = (
                record.get("status") is None
                and record.get("consumed_at") is not None
                and user.get("verified_at") == record.get("consumed_at")
            )
            if record.get("status") == "verified" or legacy_verified:
                if user.get("status") == "active" and user.get("verified_at"):
                    record["status"] = "verified"
                    return public_user(user)
                raise InvalidVerification("This verification link is invalid or expired.")
            if record.get("status") == "superseded" or record.get("consumed_at") is not None or parse_iso(record["expires_at"]) <= current:
                raise InvalidVerification("This verification link is invalid or expired.")
            record["consumed_at"] = iso(current)
            record["status"] = "verified"
            user.update(status="active", verified_at=iso(current), updated_at=iso(current))
            data["audit_events"].append(
                {"id": str(uuid4()), "kind": "auth.email_verified", "user_id": user["id"], "created_at": iso(current)}
            )
            return public_user(user)

        return self.database.transaction(operation)

    def registration_status(self, registration_id: str, socket_token: str) -> str:
        current = now_utc()
        data = self.database.read()
        record = next((item for item in data["email_verifications"] if item["id"] == registration_id), None)
        if record is None or not secrets.compare_digest(record["socket_token_digest"], token_digest(socket_token)):
            raise InvalidVerification("This registration channel is invalid.")
        user = next((user for user in data["users"] if user["id"] == record["user_id"]), None)
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
        data = self.database.read()
        user = next((item for item in data["users"] if item["email"] == email_key), None)
        if user is None:
            raise InvalidCredentials("Email or password is incorrect.")
        try:
            PASSWORD_HASHER.verify(user["password_hash"], password)
        except (VerificationError, InvalidHashError) as exc:
            raise InvalidCredentials("Email or password is incorrect.") from exc
        if user["status"] != "active" or not user.get("verified_at"):
            raise EmailNotVerified("Verify your email before signing in.")
        if PASSWORD_HASHER.check_needs_rehash(user["password_hash"]):
            replacement = PASSWORD_HASHER.hash(password)

            def update_hash(db: dict[str, Any]) -> None:
                stored = next(item for item in db["users"] if item["id"] == user["id"])
                stored["password_hash"] = replacement
                stored["updated_at"] = iso(now_utc())

            self.database.transaction(update_hash)
        return public_user(user), user

    def create_session(self, user_id: str) -> tuple[str, str]:
        current = now_utc()
        expires = current + timedelta(days=settings.auth_session_days)
        session_id = str(uuid4())
        csrf_token = secrets.token_urlsafe(24)

        def operation(data: dict[str, Any]) -> None:
            data["sessions"].append(
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

        self.database.transaction(operation)
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
        data = self.database.read()
        session = next((item for item in data["sessions"] if item["id"] == claims["jti"]), None)
        if (
            session is None
            or session.get("revoked_at") is not None
            or parse_iso(session["expires_at"]) <= now_utc()
            or session["user_id"] != claims["sub"]
        ):
            raise InvalidSession("Your session is invalid or expired.")
        user = next((item for item in data["users"] if item["id"] == session["user_id"] and item["status"] == "active"), None)
        if user is None:
            raise InvalidSession("Your session is invalid or expired.")
        return public_user(user), session

    def validate_csrf(self, session: dict[str, Any], cookie_token: str | None, header_token: str | None) -> None:
        if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
            raise CsrfError("CSRF validation failed.")
        if not secrets.compare_digest(session["csrf_digest"], token_digest(cookie_token)):
            raise CsrfError("CSRF validation failed.")

    def revoke_session(self, session_id: str) -> None:
        current = iso(now_utc())

        def operation(data: dict[str, Any]) -> None:
            session = next((item for item in data["sessions"] if item["id"] == session_id), None)
            if session is not None and session.get("revoked_at") is None:
                session["revoked_at"] = current

        self.database.transaction(operation)

    def resolve_user(self, user_id: str) -> AuthUser:
        data = self.database.read()
        user = next((item for item in data["users"] if item["id"] == user_id and item["status"] == "active"), None)
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
