"""Tests for strict application configuration profiles."""

from pathlib import Path

from fastapi import FastAPI
import pytest

from app.config import (
    ALLOWED_ENVIRONMENTS,
    DATABASE_URL_ENV_VAR,
    ENVIRONMENT_ENV_VAR,
    SESSION_COOKIE_SECURE_ENV_VAR,
    SESSION_MAX_AGE_ENV_VAR,
    SESSION_SECRET_ENV_VAR,
    is_absolute_database_path,
    load_settings,
)
from app.main import create_app

PRODUCTION_SECRET = "production-session-secret-with-at-least-32-characters"
CONFIG_ENVIRONMENT_VARIABLES = (
    DATABASE_URL_ENV_VAR,
    ENVIRONMENT_ENV_VAR,
    SESSION_COOKIE_SECURE_ENV_VAR,
    SESSION_MAX_AGE_ENV_VAR,
    SESSION_SECRET_ENV_VAR,
)


@pytest.fixture(autouse=True)
def isolated_configuration_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prevent process configuration from leaking between config tests."""
    for variable_name in CONFIG_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable_name, raising=False)


def production_database_url(path: Path) -> str:
    """Build an absolute SQLite URL for a test-only database path."""
    return f"sqlite:///{path.as_posix()}"


def configure_production(
    monkeypatch: pytest.MonkeyPatch,
    database_path: Path,
) -> None:
    """Set the minimum valid production environment."""
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, "production")
    monkeypatch.setenv(SESSION_SECRET_ENV_VAR, PRODUCTION_SECRET)
    monkeypatch.setenv(SESSION_COOKIE_SECURE_ENV_VAR, "true")
    monkeypatch.setenv(
        DATABASE_URL_ENV_VAR,
        production_database_url(database_path),
    )


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("development", "development"),
        ("test", "test"),
        ("production", "production"),
        ("  DEVELOPMENT  ", "development"),
        (" Test ", "test"),
    ],
)
def test_allowed_environment_values_are_normalized(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    raw_value: str,
    expected: str,
) -> None:
    """Only documented profiles are accepted, with safe normalization."""
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, raw_value)
    if expected == "production":
        monkeypatch.setenv(SESSION_SECRET_ENV_VAR, PRODUCTION_SECRET)
        monkeypatch.setenv(SESSION_COOKIE_SECURE_ENV_VAR, "true")
        monkeypatch.setenv(
            DATABASE_URL_ENV_VAR,
            production_database_url(tmp_path / "production.db"),
        )

    assert ALLOWED_ENVIRONMENTS == {
        "development",
        "test",
        "production",
    }
    assert load_settings().environment == expected


@pytest.mark.parametrize("raw_value", ["", "staging", "prod", "unknown"])
def test_unknown_or_empty_environment_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
) -> None:
    """An explicit invalid profile never falls back to development."""
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, raw_value)

    with pytest.raises(RuntimeError, match=ENVIRONMENT_ENV_VAR):
        load_settings()


def test_missing_environment_keeps_development_compatibility() -> None:
    """An omitted profile retains the documented local default."""
    settings = load_settings()

    assert settings.environment == "development"
    assert settings.session_cookie_secure is False
    assert len(settings.session_secret) >= 32


def test_test_profile_keeps_local_compatibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test mode does not require production-only configuration."""
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, "test")

    settings = load_settings()

    assert settings.environment == "test"
    assert settings.session_cookie_secure is False
    assert len(settings.session_secret) >= 32


def test_production_requires_session_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production rejects a missing session secret."""
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, "production")

    with pytest.raises(RuntimeError, match=SESSION_SECRET_ENV_VAR):
        load_settings()


def test_production_rejects_short_secret_without_exposing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Secret validation names the variable but never echoes its value."""
    short_secret = "short-private-value"
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, "production")
    monkeypatch.setenv(SESSION_SECRET_ENV_VAR, short_secret)

    with pytest.raises(RuntimeError, match=SESSION_SECRET_ENV_VAR) as error:
        load_settings()

    assert short_secret not in str(error.value)


def test_production_rejects_insecure_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production cannot explicitly disable Secure on its session cookie."""
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, "production")
    monkeypatch.setenv(SESSION_SECRET_ENV_VAR, PRODUCTION_SECRET)
    monkeypatch.setenv(SESSION_COOKIE_SECURE_ENV_VAR, "false")

    with pytest.raises(RuntimeError, match=SESSION_COOKIE_SECURE_ENV_VAR):
        load_settings()


@pytest.mark.parametrize("invalid_ttl", ["0", "-1", "not-a-number"])
def test_invalid_session_ttl_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    invalid_ttl: str,
) -> None:
    """Session TTL must always be a positive whole number of seconds."""
    monkeypatch.setenv(SESSION_MAX_AGE_ENV_VAR, invalid_ttl)

    with pytest.raises(RuntimeError, match=SESSION_MAX_AGE_ENV_VAR):
        load_settings()


def test_production_requires_explicit_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production cannot inherit the relative development database default."""
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, "production")
    monkeypatch.setenv(SESSION_SECRET_ENV_VAR, PRODUCTION_SECRET)

    with pytest.raises(RuntimeError, match=DATABASE_URL_ENV_VAR):
        load_settings()


def test_production_rejects_relative_sqlite_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production SQLite storage cannot depend on the working directory."""
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, "production")
    monkeypatch.setenv(SESSION_SECRET_ENV_VAR, PRODUCTION_SECRET)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, "sqlite:///./relative.db")

    with pytest.raises(
        RuntimeError,
        match=rf"{DATABASE_URL_ENV_VAR}.*absolute",
    ):
        load_settings()


def test_absolute_windows_sqlite_path_is_recognized() -> None:
    """Windows drive paths are absolute regardless of the test host."""
    assert is_absolute_database_path(r"C:\persistent\sales_tracker.db")


def test_absolute_posix_sqlite_path_is_recognized() -> None:
    """POSIX root paths are absolute regardless of the test host."""
    assert is_absolute_database_path("/persistent/sales_tracker.db")


def test_production_rejects_missing_database_parent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Production does not silently create a missing storage directory."""
    configure_production(
        monkeypatch,
        tmp_path / "missing-parent" / "production.db",
    )

    with pytest.raises(
        RuntimeError,
        match=rf"{DATABASE_URL_ENV_VAR}.*parent directory does not exist",
    ):
        load_settings()

    assert not (tmp_path / "missing-parent").exists()


def test_application_starts_with_valid_production_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A complete safe production profile creates the application."""
    configure_production(monkeypatch, tmp_path / "production.db")

    settings = load_settings()
    application = create_app(settings)

    assert isinstance(application, FastAPI)
    assert settings.environment == "production"
    assert settings.session_cookie_secure is True
    assert application.debug is False
