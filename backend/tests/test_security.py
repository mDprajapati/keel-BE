"""Crypto roundtrips (spec 001 / 010)."""

from __future__ import annotations

import pytest
from app.core.errors import UnauthorizedError
from app.core.security import (
    API_KEY_PREFIX,
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_password,
    sha256_hex,
    verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong password entirely", h)


def test_password_supports_long_inputs():
    long_pw = "x" * 200  # > bcrypt's 72-byte limit; pre-hash makes this safe
    h = hash_password(long_pw)
    assert verify_password(long_pw, h)


def test_access_token_roundtrip():
    token = create_access_token(user_id="u1", workspace_id="w1", role="admin")
    claims = decode_access_token(token)
    assert claims["sub"] == "u1"
    assert claims["workspace_id"] == "w1"
    assert claims["role"] == "admin"


def test_decode_rejects_garbage():
    with pytest.raises(UnauthorizedError):
        decode_access_token("not.a.jwt")


def test_api_key_shape():
    raw, prefix, key_hash = generate_api_key()
    assert raw.startswith(API_KEY_PREFIX)
    assert prefix == raw[: len(prefix)]
    assert key_hash == sha256_hex(raw)
