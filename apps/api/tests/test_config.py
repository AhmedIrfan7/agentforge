from config import get_settings


def test_settings_are_cached() -> None:
    assert get_settings() is get_settings()


def test_environment_is_test_under_pytest() -> None:
    # tests/conftest.py sets ENVIRONMENT=test before any project module
    # imports, so db.py picks NullPool — see db.py's comment on why.
    assert get_settings().environment == "test"
