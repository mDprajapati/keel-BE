"""The ONLY place cryptography lives (v3 §6, timeline 'all crypto here').

bcrypt password hashing, JWT access tokens, opaque refresh/API-key tokens.
Security-critical — review line by line. No other module performs crypto.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings
from app.core.errors import UnauthorizedError

API_KEY_PREFIX = "keel_sk_"


# ---------------------------------------------------------------------------
# Passwords (bcrypt). Pre-hash with sha256→base64 so inputs >72 bytes are
# supported safely (bcrypt's 72-byte limit) without silent truncation.
# ---------------------------------------------------------------------------
def _bcrypt_input(password: str) -> bytes:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(_bcrypt_input(password), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_bcrypt_input(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# JWT access tokens (15 min). Claims: sub, workspace_id, role, jti, iat, exp.
# ---------------------------------------------------------------------------
def create_access_token(
    *, user_id: str, workspace_id: str, role: str, ttl_minutes: int | None = None
) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=ttl_minutes or settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "workspace_id": str(workspace_id),
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": secrets.token_urlsafe(8),
    }
    return jwt.encode(
        payload, settings.secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token expired", error_code="TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid access token") from exc
    if claims.get("type") != "access":
        raise UnauthorizedError("Wrong token type")
    return claims


# ---------------------------------------------------------------------------
# Opaque tokens — refresh tokens & API keys. Only the SHA-256 hash is stored.
# ---------------------------------------------------------------------------
def sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_refresh_token() -> tuple[str, str, datetime]:
    """Return (raw_token, token_hash, expires_at)."""
    raw = secrets.token_urlsafe(48)
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    return raw, sha256_hex(raw), expires_at


def generate_api_key() -> tuple[str, str, str]:
    """Return (raw_secret, key_prefix, key_hash). Secret is shown to the user once."""
    raw = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, raw[: len(API_KEY_PREFIX) + 6], sha256_hex(raw)
