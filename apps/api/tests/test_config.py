import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from config import Settings, get_settings

_REAL_FERNET_KEY = Fernet.generate_key().decode()


def test_settings_are_cached() -> None:
    assert get_settings() is get_settings()


def test_environment_is_test_under_pytest() -> None:
    # tests/conftest.py sets ENVIRONMENT=test before any project module
    # imports, so db.py picks NullPool — see db.py's comment on why.
    assert get_settings().environment == "test"


def test_placeholder_secret_is_allowed_outside_production() -> None:
    # get_settings() itself is fine (environment=test) — the guard only
    # fires for environment="production", verified directly below.
    assert get_settings().secret_key


def test_placeholder_secret_key_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY is still the placeholder"):
        Settings(environment="production", jwt_secret="a-real-secret-that-is-long-enough")


def test_placeholder_jwt_secret_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET is still the placeholder"):
        Settings(
            environment="production",
            secret_key="a-real-secret-that-is-long-enough",
            mfa_encryption_key=_REAL_FERNET_KEY,
        )


def test_placeholder_mfa_key_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="MFA_ENCRYPTION_KEY is still the placeholder"):
        Settings(
            environment="production",
            secret_key="a-real-secret-that-is-long-enough",
            jwt_secret="another-real-secret-that-is-long-enough",
        )


def test_placeholder_storage_secret_key_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="STORAGE_SECRET_KEY is still the placeholder"):
        Settings(
            environment="production",
            secret_key="a-real-secret-that-is-long-enough",
            jwt_secret="another-real-secret-that-is-long-enough",
            mfa_encryption_key=_REAL_FERNET_KEY,
        )


def test_real_secrets_accepted_in_production() -> None:
    settings = Settings(
        environment="production",
        secret_key="a-real-secret-that-is-long-enough",
        jwt_secret="another-real-secret-that-is-long-enough",
        mfa_encryption_key=_REAL_FERNET_KEY,
        storage_secret_key="a-real-storage-credential",
    )
    assert settings.environment == "production"
