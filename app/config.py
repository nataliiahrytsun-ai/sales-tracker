"""Application configuration."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
import os
import secrets

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

DEFAULT_DATABASE_URL = "sqlite:///./sales_tracker.db"
DEFAULT_SESSION_MAX_AGE_SECONDS = 14 * 24 * 60 * 60
DATABASE_URL_ENV_VAR = "SALES_TRACKER_DATABASE_URL"
ENVIRONMENT_ENV_VAR = "SALES_TRACKER_ENVIRONMENT"
SESSION_SECRET_ENV_VAR = "SALES_TRACKER_SESSION_SECRET"
SESSION_COOKIE_SECURE_ENV_VAR = "SALES_TRACKER_SESSION_COOKIE_SECURE"
SESSION_MAX_AGE_ENV_VAR = "SALES_TRACKER_SESSION_MAX_AGE_SECONDS"
ALLOWED_ENVIRONMENTS = frozenset({"development", "test", "production"})


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


def parse_environment() -> str:
    """Return a normalized, explicitly supported application profile."""
    raw_value = os.getenv(ENVIRONMENT_ENV_VAR)
    if raw_value is None:
        return "development"

    environment = raw_value.strip().lower()
    if environment not in ALLOWED_ENVIRONMENTS:
        allowed_values = ", ".join(sorted(ALLOWED_ENVIRONMENTS))
        raise RuntimeError(
            f"{ENVIRONMENT_ENV_VAR} must be one of: {allowed_values}",
        )
    return environment


def sqlite_database_path(database_url: str) -> str:
    """Extract the filesystem path from a SQLite URL."""
    try:
        url = make_url(database_url)
    except ArgumentError as error:
        raise RuntimeError(
            f"{DATABASE_URL_ENV_VAR} must be a valid SQLite database URL",
        ) from error

    if url.get_backend_name() != "sqlite":
        raise RuntimeError(
            f"{DATABASE_URL_ENV_VAR} must use a SQLite database URL",
        )
    if not url.database or url.database == ":memory:":
        raise RuntimeError(
            f"{DATABASE_URL_ENV_VAR} must identify a SQLite database file",
        )
    return url.database


def is_absolute_database_path(database_path: str) -> bool:
    """Recognize absolute POSIX and Windows paths on every host platform."""
    return (
        PurePosixPath(database_path).is_absolute()
        or PureWindowsPath(database_path).is_absolute()
    )


def validate_production_database(database_url: str) -> None:
    """Validate that production SQLite storage is explicit and persistent."""
    database_path = sqlite_database_path(database_url)
    if not is_absolute_database_path(database_path):
        raise RuntimeError(
            f"{DATABASE_URL_ENV_VAR} must contain an absolute SQLite "
            "database path in production",
        )

    parent_directory = Path(database_path).parent
    if not parent_directory.exists():
        raise RuntimeError(
            f"{DATABASE_URL_ENV_VAR} parent directory does not exist",
        )
    if not parent_directory.is_dir():
        raise RuntimeError(
            f"{DATABASE_URL_ENV_VAR} parent path is not a directory",
        )
    if not os.access(parent_directory, os.W_OK):
        raise RuntimeError(
            f"{DATABASE_URL_ENV_VAR} parent directory is not writable",
        )

    database_file = Path(database_path)
    if database_file.exists() and (
        not database_file.is_file() or not os.access(database_file, os.W_OK)
    ):
        raise RuntimeError(
            f"{DATABASE_URL_ENV_VAR} database file is not writable",
        )


def load_settings() -> Settings:
    """Load application settings from environment variables."""
    environment = parse_environment()
    configured_secret = os.getenv(SESSION_SECRET_ENV_VAR)
    secure_cookie = parse_boolean_environment(
        SESSION_COOKIE_SECURE_ENV_VAR,
        default=environment == "production",
    )
    session_max_age_seconds = parse_positive_integer_environment(
        SESSION_MAX_AGE_ENV_VAR,
        DEFAULT_SESSION_MAX_AGE_SECONDS,
    )
    database_url = os.getenv(DATABASE_URL_ENV_VAR, DEFAULT_DATABASE_URL)

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
        if DATABASE_URL_ENV_VAR not in os.environ:
            raise RuntimeError(
                f"{DATABASE_URL_ENV_VAR} is required in production",
            )
        validate_production_database(database_url)

    return Settings(
        database_url=database_url,
        environment=environment,
        session_secret=configured_secret or secrets.token_urlsafe(48),
        session_cookie_secure=secure_cookie,
        session_max_age_seconds=session_max_age_seconds,
    )


settings = load_settings()
