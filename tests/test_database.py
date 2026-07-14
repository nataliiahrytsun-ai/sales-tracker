"""Tests for database configuration."""

from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from app.config import (
    DATABASE_URL_ENV_VAR,
    DEFAULT_DATABASE_URL,
    load_settings,
)
from app.database import create_db_engine, create_session


def sqlite_url(path: Path) -> str:
    """Build a SQLAlchemy SQLite URL for a local path."""
    return f"sqlite:///{path.as_posix()}"


def test_default_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """The application uses the documented local SQLite database by default."""
    monkeypatch.delenv(DATABASE_URL_ENV_VAR, raising=False)

    assert DATABASE_URL_ENV_VAR == "SALES_TRACKER_DATABASE_URL"
    assert DEFAULT_DATABASE_URL == "sqlite:///./sales_tracker.db"
    assert load_settings().database_url == "sqlite:///./sales_tracker.db"


def test_database_url_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The database URL can be supplied through the environment."""
    database_url = "sqlite:///./custom.db"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)

    assert load_settings().database_url == database_url


def test_non_sqlite_database_url_is_rejected() -> None:
    """The configured database backend remains SQLite-only."""
    with pytest.raises(ValueError, match="requires a SQLite database URL"):
        create_db_engine("postgresql://localhost/sales_vibes")


def test_sqlite_connection_enables_required_pragmas(tmp_path: Path) -> None:
    """Every SQLite engine enables foreign keys and WAL mode."""
    db_engine = create_db_engine(sqlite_url(tmp_path / "configured.db"))

    try:
        with db_engine.connect() as connection:
            foreign_keys = connection.exec_driver_sql(
                "PRAGMA foreign_keys",
            ).scalar_one()
            journal_mode = connection.exec_driver_sql(
                "PRAGMA journal_mode",
            ).scalar_one()
    finally:
        db_engine.dispose()

    assert foreign_keys == 1
    assert journal_mode == "wal"


def test_create_session_binds_supplied_engine(tmp_path: Path) -> None:
    """Sessions are created against the requested engine."""
    db_engine: Engine = create_db_engine(
        sqlite_url(tmp_path / "session.db"),
    )

    try:
        with create_session(db_engine) as session:
            assert session.get_bind() is db_engine
    finally:
        db_engine.dispose()
