"""Application configuration."""

from dataclasses import dataclass
import os

DEFAULT_DATABASE_URL = "sqlite:///./sales_tracker.db"
DATABASE_URL_ENV_VAR = "SALES_TRACKER_DATABASE_URL"


@dataclass(frozen=True)
class Settings:
    """Configuration values loaded from the process environment."""

    database_url: str


def load_settings() -> Settings:
    """Load application settings from environment variables."""
    return Settings(
        database_url=os.getenv(DATABASE_URL_ENV_VAR, DEFAULT_DATABASE_URL),
    )


settings = load_settings()
