"""Application configuration."""

from dataclasses import dataclass
import os
import secrets

DEFAULT_DATABASE_URL = "sqlite:///./sales_tracker.db"
DEFAULT_SESSION_MAX_AGE_SECONDS = 14 * 24 * 60 * 60
DATABASE_URL_ENV_VAR = "SALES_TRACKER_DATABASE_URL"
ENVIRONMENT_ENV_VAR = "SALES_TRACKER_ENVIRONMENT"
SESSION_SECRET_ENV_VAR = "SALES_TRACKER_SESSION_SECRET"
SESSION_COOKIE_SECURE_ENV_VAR = "SALES_TRACKER_SESSION_COOKIE_SECURE"
SESSION_MAX_AGE_ENV_VAR = "SALES_TRACKER_SESSION_MAX_AGE_SECONDS"


@dataclass(frozen=True)
class Settings:
    """Configuration values loaded from the process environment."""

    database_url: str
    environment: str
    session_secret: str
    session_cookie_secure: bool
    session_max_age_seconds: int = DEFAULT_SESSION_MAX_AGE_SECONDS


def parse_boolean_environment(name: str, default: bool) -> bool:
    """Parse a boolean environment variable or raise a clear error."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized_value = raw_value.strip().lower()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false")


def parse_positive_integer_environment(name: str, default: int) -> int:
    """Parse a positive integer environment variable."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive integer") from error
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


def load_settings() -> Settings:
    """Load application settings from environment variables."""
    environment = os.getenv(ENVIRONMENT_ENV_VAR, "development").strip().lower()
    configured_secret = os.getenv(SESSION_SECRET_ENV_VAR)
    secure_cookie = parse_boolean_environment(
        SESSION_COOKIE_SECURE_ENV_VAR,
        default=environment == "production",
    )
    session_max_age_seconds = parse_positive_integer_environment(
        SESSION_MAX_AGE_ENV_VAR,
        DEFAULT_SESSION_MAX_AGE_SECONDS,
    )

    if environment == "production":
        if configured_secret is None or len(configured_secret) < 32:
            raise RuntimeError(
                f"{SESSION_SECRET_ENV_VAR} must contain at least 32 characters "
                "in production",
            )
        if not secure_cookie:
            raise RuntimeError(
                f"{SESSION_COOKIE_SECURE_ENV_VAR} must be true in production",
            )

    return Settings(
        database_url=os.getenv(DATABASE_URL_ENV_VAR, DEFAULT_DATABASE_URL),
        environment=environment,
        session_secret=configured_secret or secrets.token_urlsafe(48),
        session_cookie_secure=secure_cookie,
        session_max_age_seconds=session_max_age_seconds,
    )


settings = load_settings()
