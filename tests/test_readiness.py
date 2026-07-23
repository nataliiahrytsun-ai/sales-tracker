"""Tests for safe readiness checks and minimal application logging."""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
import logging
from pathlib import Path
import sqlite3

from fastapi import FastAPI
import httpx
import pytest

from app.config import Settings
from app.logging_config import APPLICATION_LOGGER_NAME
from app.main import create_app
from app.services.readiness import (
    DATABASE_UNAVAILABLE,
    SCHEMA_REVISION_MISMATCH,
    SCHEMA_REVISION_UNAVAILABLE,
    ReadinessChecker,
    ReadinessError,
    project_alembic_head,
)

TEST_SESSION_SECRET = "readiness-test-session-secret-value"
STALE_REVISION = "19000101_stale_private_revision"


def sqlite_url(path: Path) -> str:
    """Build a SQLAlchemy-style URL for a temporary SQLite file."""
    return f"sqlite:///{path.as_posix()}"


def create_database(
    path: Path,
    *,
    revisions: tuple[str, ...] | None = None,
) -> None:
    """Create a minimal test-only SQLite database."""
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE protected_records "
            "(id INTEGER PRIMARY KEY, value TEXT NOT NULL)",
        )
        connection.execute(
            "INSERT INTO protected_records (value) VALUES (?)",
            ("private-user-data",),
        )
        if revisions is not None:
            connection.execute(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(32) NOT NULL)",
            )
            connection.executemany(
                "INSERT INTO alembic_version (version_num) VALUES (?)",
                ((revision,) for revision in revisions),
            )
        connection.commit()
    finally:
        connection.close()


def readiness_settings(
    database_path: Path,
    *,
    log_level: str = "WARNING",
) -> Settings:
    """Return isolated settings for one temporary readiness database."""
    return Settings(
        database_url=sqlite_url(database_path),
        environment="test",
        session_secret=TEST_SESSION_SECRET,
        session_cookie_secure=False,
        log_level=log_level,
    )


async def get(application: FastAPI, path: str) -> httpx.Response:
    """Issue an isolated public ASGI request."""
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.get(path)


@contextmanager
def capture_application_logs(
    caplog: pytest.LogCaptureFixture,
    level: int,
) -> Iterator[None]:
    """Attach pytest's capture handler to the non-propagating app logger."""
    logger = logging.getLogger(APPLICATION_LOGGER_NAME)
    logger.addHandler(caplog.handler)
    caplog.set_level(level, logger=APPLICATION_LOGGER_NAME)
    try:
        yield
    finally:
        logger.removeHandler(caplog.handler)


def test_health_is_live_when_readiness_database_is_unavailable(
    tmp_path: Path,
) -> None:
    """Liveness remains independent from database readiness."""
    missing_database = tmp_path / "missing.db"
    application = create_app(readiness_settings(missing_database))

    health = asyncio.run(get(application, "/health"))
    ready = asyncio.run(get(application, "/ready"))

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 503
    assert not missing_database.exists()


def test_ready_returns_exact_public_success_for_current_head(
    tmp_path: Path,
) -> None:
    """A current temporary schema is publicly ready without authentication."""
    database = tmp_path / "ready.db"
    create_database(database, revisions=(project_alembic_head(),))
    application = create_app(readiness_settings(database))

    response = asyncio.run(get(application, "/ready"))

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.parametrize(
    ("revisions", "expected_category"),
    [
        (None, SCHEMA_REVISION_UNAVAILABLE),
        ((), SCHEMA_REVISION_UNAVAILABLE),
        ((STALE_REVISION,), SCHEMA_REVISION_MISMATCH),
        (
            (project_alembic_head(), STALE_REVISION),
            SCHEMA_REVISION_UNAVAILABLE,
        ),
    ],
)
def test_ready_rejects_missing_empty_stale_or_multiple_revisions(
    tmp_path: Path,
    revisions: tuple[str, ...] | None,
    expected_category: str,
) -> None:
    """Invalid migration state has one safe internal failure category."""
    database = tmp_path / "not-ready.db"
    create_database(database, revisions=revisions)
    checker = ReadinessChecker(sqlite_url(database))
    application = create_app(readiness_settings(database))

    with pytest.raises(ReadinessError) as error:
        checker.check()
    response = asyncio.run(get(application, "/ready"))

    assert error.value.category == expected_category
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_ready_failure_response_hides_internal_details(
    tmp_path: Path,
) -> None:
    """The 503 body never exposes paths, SQL, tracebacks, or revisions."""
    database = tmp_path / "private-internal-database-name.db"
    create_database(database, revisions=(STALE_REVISION,))
    application = create_app(readiness_settings(database))

    response = asyncio.run(get(application, "/ready"))
    response_text = response.text

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert str(database) not in response_text
    assert database.name not in response_text
    assert "SELECT" not in response_text
    assert "Traceback" not in response_text
    assert STALE_REVISION not in response_text


def test_ready_requires_neither_authentication_nor_csrf(
    tmp_path: Path,
) -> None:
    """A fresh client can call readiness without credentials or a token."""
    database = tmp_path / "public-ready.db"
    create_database(database, revisions=(project_alembic_head(),))
    application = create_app(readiness_settings(database))

    response = asyncio.run(get(application, "/ready"))

    assert response.status_code == 200


def test_readiness_does_not_change_application_data(tmp_path: Path) -> None:
    """The checker performs read-only operations."""
    database = tmp_path / "unchanged.db"
    create_database(database, revisions=(project_alembic_head(),))
    before = database.read_bytes()

    ReadinessChecker(sqlite_url(database)).check()

    assert database.read_bytes() == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM protected_records",
        ).fetchall() == [("private-user-data",)]


def test_readiness_does_not_create_missing_database(tmp_path: Path) -> None:
    """A missing configured file fails without SQLite creating it."""
    database = tmp_path / "must-not-be-created.db"

    with pytest.raises(ReadinessError) as error:
        ReadinessChecker(sqlite_url(database)).check()

    assert error.value.category == DATABASE_UNAVAILABLE
    assert not database.exists()


def test_readiness_closes_its_connection(tmp_path: Path) -> None:
    """Windows can rename the database immediately after a successful check."""
    database = tmp_path / "connection-closes.db"
    renamed = tmp_path / "renamed-after-ready.db"
    create_database(database, revisions=(project_alembic_head(),))

    ReadinessChecker(sqlite_url(database)).check()
    database.replace(renamed)

    assert renamed.exists()
    assert not database.exists()


def test_readiness_failure_log_is_safe_and_categorized(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Failure logs contain a category but no configuration or user data."""
    database = tmp_path / "secret-database-path.db"
    create_database(database, revisions=(STALE_REVISION,))
    settings = readiness_settings(database)
    application = create_app(settings)

    with capture_application_logs(caplog, logging.WARNING):
        response = asyncio.run(get(application, "/ready"))

    assert response.status_code == 503
    assert f"category={SCHEMA_REVISION_MISMATCH}" in caplog.text
    assert str(database) not in caplog.text
    assert settings.database_url not in caplog.text
    assert settings.session_secret not in caplog.text
    assert "private-user-data" not in caplog.text
    assert STALE_REVISION not in caplog.text


def test_startup_log_contains_only_safe_operational_fields(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Startup confirms the profile without logging secrets or DB locations."""
    database = tmp_path / "startup-private-path.db"
    create_database(database, revisions=(project_alembic_head(),))
    settings = readiness_settings(database, log_level="INFO")
    application = create_app(settings)

    async def run_lifespan() -> None:
        async with application.router.lifespan_context(application):
            assert (await get(application, "/health")).status_code == 200

    with capture_application_logs(caplog, logging.INFO):
        asyncio.run(run_lifespan())

    assert "Sales Tracker started" in caplog.text
    assert "environment=test" in caplog.text
    assert "log_level=INFO" in caplog.text
    assert "database=sqlite" in caplog.text
    assert settings.session_secret not in caplog.text
    assert settings.database_url not in caplog.text
    assert str(database) not in caplog.text
    assert database.name not in caplog.text


def test_validation_error_is_not_logged_as_application_error(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Normal FastAPI request validation remains a client response."""
    database = tmp_path / "validation.db"
    application = create_app(readiness_settings(database))

    @application.get("/validation-probe")
    def validation_probe(required_number: int) -> dict[str, int]:
        return {"required_number": required_number}

    with capture_application_logs(caplog, logging.ERROR):
        response = asyncio.run(
            get(application, "/validation-probe?required_number=invalid"),
        )

    assert response.status_code == 422
    assert not [
        record
        for record in caplog.records
        if (
            record.name == APPLICATION_LOGGER_NAME
            and record.levelno >= logging.ERROR
        )
    ]
