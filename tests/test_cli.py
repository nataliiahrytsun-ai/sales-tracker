"""Tests for local administrative CLI commands."""

from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, select

from app import cli
from app.database import create_db_engine
from app.models import User
from app.services.passwords import hash_password, verify_password


@pytest.fixture
def cli_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    """Create an isolated database for CLI tests."""
    database_url = f"sqlite:///{(tmp_path / 'cli.db').as_posix()}"
    engine = create_db_engine(database_url)
    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def test_create_user_stores_only_argon2_hash(
    cli_engine: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Successful creation persists an active user and no plaintext password."""
    answers = iter(["  local@example.com  ", "Local Admin"])
    passwords = iter(["local-test-password", "local-test-password"])

    with Session(cli_engine) as session:
        result = cli.create_user(
            session,
            prompt=lambda _message: next(answers),
            secret_prompt=lambda _message: next(passwords),
        )

    with Session(cli_engine) as session:
        user = session.exec(
            select(User).where(User.email == "local@example.com"),
        ).one()

    captured = capsys.readouterr()
    assert result == 0
    assert captured.out == "User created successfully.\n"
    assert captured.err == ""
    assert user.name == "Local Admin"
    assert user.active is True
    assert user.must_change_password is True
    assert user.auth_version == 1
    assert user.password_hash != "local-test-password"
    assert user.password_hash.startswith("$argon2")
    assert verify_password("local-test-password", user.password_hash)
    assert "local@example.com" not in captured.out
    assert "local-test-password" not in captured.out


def test_create_user_rejects_password_mismatch(
    cli_engine: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Mismatched password confirmation creates no user."""
    answers = iter(["local@example.com", "Local Admin"])
    passwords = iter(["first-password", "different-password"])

    with Session(cli_engine) as session:
        result = cli.create_user(
            session,
            prompt=lambda _message: next(answers),
            secret_prompt=lambda _message: next(passwords),
        )

    with Session(cli_engine) as session:
        assert session.exec(select(User)).all() == []

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert "passwords do not match" in captured.err
    assert "first-password" not in captured.err
    assert "different-password" not in captured.err


def test_create_user_rejects_duplicate_before_password_prompt(
    cli_engine: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An existing email is rejected without requesting a password."""
    with Session(cli_engine) as session:
        session.add(
            User(
                name="Existing User",
                email="existing@example.com",
                password_hash=hash_password("existing-password"),
            ),
        )
        session.commit()

    def unexpected_secret_prompt(_message: str) -> str:
        raise AssertionError("Password must not be requested for a duplicate")

    with Session(cli_engine) as session:
        result = cli.create_user(
            session,
            prompt=lambda _message: "existing@example.com",
            secret_prompt=unexpected_secret_prompt,
        )

    with Session(cli_engine) as session:
        assert len(session.exec(select(User)).all()) == 1

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert "email already exists" in captured.err
    assert "existing@example.com" not in captured.err


def test_main_dispatches_exact_create_user_subcommand(
    cli_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The documented module invocation dispatches the create-user command."""
    calls: list[Session] = []

    monkeypatch.setattr(cli, "create_session", lambda: Session(cli_engine))

    def record_create_user(session: Session) -> int:
        calls.append(session)
        return 0

    monkeypatch.setattr(cli, "create_user", record_create_user)

    assert cli.main(["create-user"]) == 0
    assert len(calls) == 1


def test_reset_password_sets_temporary_hash_and_revokes_sessions(
    cli_engine: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reset replaces the hash, forces a change, and increments auth version."""
    old_password = "old-test-password"
    temporary_password = "new-temporary-password"
    with Session(cli_engine) as session:
        session.add(
            User(
                name="Existing User",
                email="existing@example.com",
                password_hash=hash_password(old_password),
            ),
        )
        session.commit()

    passwords = iter([temporary_password, temporary_password])
    with Session(cli_engine) as session:
        result = cli.reset_password(
            session,
            prompt=lambda _message: "  existing@example.com  ",
            secret_prompt=lambda _message: next(passwords),
        )

    with Session(cli_engine) as session:
        user = session.exec(
            select(User).where(User.email == "existing@example.com"),
        ).one()

    captured = capsys.readouterr()
    assert result == 0
    assert captured.out == "Password reset successfully.\n"
    assert captured.err == ""
    assert not verify_password(old_password, user.password_hash)
    assert verify_password(temporary_password, user.password_hash)
    assert user.must_change_password is True
    assert user.auth_version == 2
    assert temporary_password not in captured.out


def test_reset_password_rejects_unknown_email_before_password_prompt(
    cli_engine: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unknown account receives a clear error without requesting secrets."""

    def unexpected_secret_prompt(_message: str) -> str:
        raise AssertionError("Password must not be requested for an unknown user")

    with Session(cli_engine) as session:
        result = cli.reset_password(
            session,
            prompt=lambda _message: "missing@example.com",
            secret_prompt=unexpected_secret_prompt,
        )

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert "user was not found" in captured.err
    assert "missing@example.com" not in captured.err


def test_main_dispatches_exact_reset_password_subcommand(
    cli_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The documented reset-password command dispatches to its handler."""
    calls: list[Session] = []
    monkeypatch.setattr(cli, "create_session", lambda: Session(cli_engine))

    def record_reset_password(session: Session) -> int:
        calls.append(session)
        return 0

    monkeypatch.setattr(cli, "reset_password", record_reset_password)

    assert cli.main(["reset-password"]) == 0
    assert len(calls) == 1
