from config import get_settings


def test_settings_are_cached() -> None:
    assert get_settings() is get_settings()


def test_default_environment_is_development() -> None:
    assert get_settings().environment == "development"
