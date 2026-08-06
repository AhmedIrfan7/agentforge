import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest

from auth.jwt import (
    TokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from config import settings


def test_create_and_decode_roundtrip() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    assert decode_access_token(token) == user_id


def test_decode_rejects_garbage_token() -> None:
    with pytest.raises(TokenError):
        decode_access_token("not.a.valid.jwt")


def test_decode_rejects_expired_token() -> None:
    now = datetime.now(UTC)
    expired_payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": now - timedelta(hours=1),
        "exp": now - timedelta(minutes=1),
    }
    expired_token = pyjwt.encode(expired_payload, settings.jwt_secret, algorithm="HS256")
    with pytest.raises(TokenError):
        decode_access_token(expired_token)


def test_decode_rejects_wrong_token_type() -> None:
    now = datetime.now(UTC)
    refresh_shaped_payload = {
        "sub": str(uuid.uuid4()),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    token = pyjwt.encode(refresh_shaped_payload, settings.jwt_secret, algorithm="HS256")
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_decode_rejects_token_signed_with_wrong_secret() -> None:
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    forged_token = pyjwt.encode(payload, "not-the-real-secret", algorithm="HS256")
    with pytest.raises(TokenError):
        decode_access_token(forged_token)


def test_refresh_token_is_high_entropy_and_hash_is_deterministic() -> None:
    raw1, hash1, expires1 = generate_refresh_token()
    raw2, hash2, _ = generate_refresh_token()

    assert raw1 != raw2
    assert hash1 != hash2
    assert len(raw1) >= 32
    assert hash_refresh_token(raw1) == hash1
    assert expires1 > datetime.now(UTC)
