"""Database engine and session configuration."""

from collections.abc import Generator
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from app.config import DATABASE_URL_ENV_VAR, settings


def create_db_engine(database_url: str) -> Engine:
    """Create an engine with the required SQLite connection settings."""
    if not database_url.startswith("sqlite"):
        raise ValueError(
            f"{DATABASE_URL_ENV_VAR} must use a SQLite database URL",
        )

    connect_args: dict[str, Any] = {"check_same_thread": False}
    db_engine = create_engine(database_url, connect_args=connect_args)

    @event.listens_for(db_engine, "connect")
    def set_sqlite_pragmas(
        dbapi_connection: Any,
        _connection_record: Any,
    ) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()

    return db_engine


engine = create_db_engine(settings.database_url)


def create_session(db_engine: Engine = engine) -> Session:
    """Create a database session bound to the supplied engine."""
    return Session(db_engine)


def get_session() -> Generator[Session, None, None]:
    """Provide a database session for a FastAPI dependency."""
    with create_session() as session:
        yield session
