"""Unit and integration tests for session authentication."""

import asyncio
from base64 import b64decode, b64encode
from collections.abc import Generator
import json
import logging
from pathlib import Path

from fastapi import FastAPI
import httpx
from itsdangerous import TimestampSigner
import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, select

from app.config import (
    DEFAULT_SESSION_MAX_AGE_SECONDS,
    Settings,
    load_settings,
)
from app.database import create_db_engine, get_session
from app.main import create_app
from app.models import User
from app.services.passwords import hash_password, verify_password

ACTIVE_EMAIL = "active@example.com"
INACTIVE_EMAIL = "inactive@example.com"
TEST_PASSWORD = "correct-test-password"
SESSION_COOKIE_NAME = "sales_tracker_session"
TEST_SESSION_SECRET = "test-session-secret-with-at-least-32-characters"
TEST_SESSION_MAX_AGE_SECONDS = 3_600


def encode_session(payload: dict[str, object]) -> str:
    """Encode a signed Starlette session cookie for boundary tests."""
    data = b64encode(json.dumps(payload).encode("utf-8"))
    return TimestampSigner(TEST_SESSION_SECRET).sign(data).decode("utf-8")


def decode_session(cookie_value: str) -> dict[str, object]:
    """Verify and decode a Starlette session cookie payload."""
    signed_data = TimestampSigner(TEST_SESSION_SECRET).unsign(cookie_value)
    return json.loads(b64decode(signed_data))


@pytest.fixture
def auth_application(
    tmp_path: Path,
) -> Generator[tuple[FastAPI, Engine], None, None]:
    """Create an application with isolated users and database sessions."""
    database_url = f"sqlite:///{(tmp_path / 'auth.db').as_posix()}"
    engine = create_db_engine(database_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            User(
                name="Active User",
                email=ACTIVE_EMAIL,
                password_hash=hash_password(TEST_PASSWORD),
            ),
        )
        session.add(
            User(
                name="Inactive User",
                email=INACTIVE_EMAIL,
                password_hash=hash_password(TEST_PASSWORD),
                active=False,
            ),
        )
        session.commit()

    application = create_app(
        Settings(
            database_url=database_url,
            environment="test",
            session_secret=TEST_SESSION_SECRET,
            session_cookie_secure=False,
            session_max_age_seconds=TEST_SESSION_MAX_AGE_SECONDS,
        ),
    )

    def override_get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_session] = override_get_session
    try:
        yield application, engine
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


def test_passwords_are_hashed_and_verified() -> None:
    """Password hashing never returns or requires stored plaintext."""
    password_hash = hash_password(TEST_PASSWORD)

    assert password_hash != TEST_PASSWORD
    assert password_hash.startswith("$argon2")
    assert verify_password(TEST_PASSWORD, password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_database_contains_only_password_hash(
    auth_application: tuple[FastAPI, Engine],
) -> None:
    """Persisted credentials contain a verifiable hash, not plaintext."""
    _, engine = auth_application
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == ACTIVE_EMAIL)).one()

        assert user.password_hash != TEST_PASSWORD
        assert user.password_hash.startswith("$argon2")
        assert verify_password(TEST_PASSWORD, user.password_hash)


def test_anonymous_user_is_redirected_to_login(
    auth_application: tuple[FastAPI, Engine],
) -> None:
    """Private routes enforce authentication on the server."""
    application, _ = auth_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get("/")

        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    asyncio.run(scenario())


def test_login_page_uses_shared_responsive_layout(
    auth_application: tuple[FastAPI, Engine],
) -> None:
    """The public login page uses the shared layout and mobile metadata."""
    application, _ = auth_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get("/login")
            stylesheet = await client.get("/static/css/app.css")

        assert response.status_code == 200
        assert '<meta name="viewport"' in response.text
        assert 'href="http://testserver/static/css/app.css"' in response.text
        assert 'action="http://testserver/login"' in response.text
        assert 'type="password"' in response.text
        assert 'aria-label="User navigation"' not in response.text
        assert stylesheet.status_code == 200
        assert "@media (min-width: 48rem)" in stylesheet.text
        assert "grid-template-columns" in stylesheet.text

    asyncio.run(scenario())


def test_authenticated_home_renders_only_expected_disabled_actions(
    auth_application: tuple[FastAPI, Engine],
) -> None:
    """Home renders shared navigation and only the four scoped actions."""
    application, _ = auth_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await client.post(
                "/login",
                data={"email": ACTIVE_EMAIL, "password": TEST_PASSWORD},
            )
            response = await client.get("/")

        assert response.status_code == 200
        assert 'aria-label="User navigation"' in response.text
        assert 'action="http://testserver/logout"' in response.text
        for action in (
            "Record meeting",
            "Update today's outreach",
            "View this week",
            "Open dashboard",
        ):
            assert action in response.text
        assert response.text.count(" disabled") == 4
        assert "/meetings/new" not in response.text
        assert "/outreach/today" not in response.text
        assert "/dashboard" not in response.text

    asyncio.run(scenario())


def test_successful_login_sets_httponly_session_cookie(
    auth_application: tuple[FastAPI, Engine],
) -> None:
    """Valid credentials start a usable HttpOnly session."""
    application, _ = auth_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/login",
                data={"email": ACTIVE_EMAIL, "password": TEST_PASSWORD},
            )
            private_response = await client.get("/")

        assert response.status_code == 303
        assert response.headers["location"] == "/"
        set_cookie = response.headers["set-cookie"].lower()
        assert "httponly" in set_cookie
        assert f"max-age={TEST_SESSION_MAX_AGE_SECONDS}" in set_cookie
        assert private_response.status_code == 200
        assert "Active User" in private_response.text

    asyncio.run(scenario())


def test_session_cookie_contains_only_user_id(
    auth_application: tuple[FastAPI, Engine],
) -> None:
    """The signed client session contains no credentials or user profile data."""
    application, engine = auth_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/login",
                data={"email": ACTIVE_EMAIL, "password": TEST_PASSWORD},
            )

        cookie_value = response.cookies[SESSION_COOKIE_NAME]
        payload = decode_session(cookie_value)
        with Session(engine) as session:
            user = session.exec(
                select(User).where(User.email == ACTIVE_EMAIL),
            ).one()

        assert payload == {"user_id": user.id}
        assert "password" not in payload
        assert "password_hash" not in payload
        assert "email" not in payload

    asyncio.run(scenario())


def test_failed_login_does_not_render_or_log_password(
    auth_application: tuple[FastAPI, Engine],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A rejected password is absent from HTML, logs, and error messages."""
    application, _ = auth_application
    submitted_password = "unique-rejected-password-do-not-expose"

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        with caplog.at_level(logging.DEBUG):
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                response = await client.post(
                    "/login",
                    data={
                        "email": ACTIVE_EMAIL,
                        "password": submitted_password,
                    },
                )

        assert response.status_code == 401
        assert submitted_password not in response.text
        assert submitted_password not in caplog.text
        assert response.text.count('type="password"') == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("email", "password"),
    [
        (ACTIVE_EMAIL, "wrong-password"),
        (INACTIVE_EMAIL, TEST_PASSWORD),
    ],
)
def test_login_rejects_invalid_or_inactive_user(
    auth_application: tuple[FastAPI, Engine],
    email: str,
    password: str,
) -> None:
    """Wrong passwords and inactive accounts receive the same rejection."""
    application, _ = auth_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/login",
                data={"email": email, "password": password},
            )
            private_response = await client.get("/")

        assert response.status_code == 401
        assert "Invalid email or password." in response.text
        assert "set-cookie" not in response.headers
        assert private_response.status_code == 303

    asyncio.run(scenario())


def test_logout_clears_session(
    auth_application: tuple[FastAPI, Engine],
) -> None:
    """Logout clears the session and restores private-route protection."""
    application, _ = auth_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            login_response = await client.post(
                "/login",
                data={"email": ACTIVE_EMAIL, "password": TEST_PASSWORD},
            )
            old_cookie = login_response.cookies[SESSION_COOKIE_NAME]
            response = await client.post("/logout")
            private_response = await client.get("/")

        assert response.status_code == 303
        assert response.headers["location"] == "/login"
        clear_cookie = response.headers["set-cookie"].lower()
        assert f"{SESSION_COOKIE_NAME}=null" in clear_cookie
        assert "expires=thu, 01 jan 1970 00:00:00 gmt" in clear_cookie
        assert client.cookies.get(SESSION_COOKIE_NAME) != old_cookie
        assert private_response.status_code == 303
        assert private_response.headers["location"] == "/login"

    asyncio.run(scenario())


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Stateless signed-cookie sessions have no server-side revocation "
        "for a copied pre-logout cookie"
    ),
)
def test_logout_rejects_replayed_pre_logout_cookie(
    auth_application: tuple[FastAPI, Engine],
) -> None:
    """A copied pre-logout cookie should not restore access after logout."""
    application, _ = auth_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            login_response = await client.post(
                "/login",
                data={"email": ACTIVE_EMAIL, "password": TEST_PASSWORD},
            )
            copied_cookie = login_response.cookies[SESSION_COOKIE_NAME]
            await client.post("/logout")

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as replay_client:
            replay_client.cookies.set(SESSION_COOKIE_NAME, copied_cookie)
            replay_response = await replay_client.get("/")

        assert replay_response.status_code == 303
        assert replay_response.headers["location"] == "/login"

    asyncio.run(scenario())


def test_session_with_missing_user_is_rejected(
    auth_application: tuple[FastAPI, Engine],
) -> None:
    """A validly signed session cannot authenticate a nonexistent user."""
    application, _ = auth_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            client.cookies.set(
                SESSION_COOKIE_NAME,
                encode_session({"user_id": 999_999}),
            )
            response = await client.get("/")

        assert response.status_code == 303
        assert response.headers["location"] == "/login"
        assert f"{SESSION_COOKIE_NAME}=null" in response.headers[
            "set-cookie"
        ].lower()

    asyncio.run(scenario())


@pytest.mark.parametrize("account_change", ["delete", "deactivate"])
def test_existing_session_rejects_deleted_or_deactivated_user(
    auth_application: tuple[FastAPI, Engine],
    account_change: str,
) -> None:
    """Every private request revalidates user existence and active state."""
    application, engine = auth_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            login_response = await client.post(
                "/login",
                data={"email": ACTIVE_EMAIL, "password": TEST_PASSWORD},
            )
            assert login_response.status_code == 303

            with Session(engine) as session:
                user = session.exec(
                    select(User).where(User.email == ACTIVE_EMAIL),
                ).one()
                if account_change == "delete":
                    session.delete(user)
                else:
                    user.active = False
                    session.add(user)
                session.commit()

            response = await client.get("/")

        assert response.status_code == 303
        assert response.headers["location"] == "/login"
        assert f"{SESSION_COOKIE_NAME}=null" in response.headers[
            "set-cookie"
        ].lower()

    asyncio.run(scenario())


def test_production_rejects_missing_short_or_insecure_session_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production startup fails clearly without secure session settings."""
    monkeypatch.setenv("SALES_TRACKER_ENVIRONMENT", "development")
    monkeypatch.delenv("SALES_TRACKER_SESSION_SECRET", raising=False)
    development_secret = load_settings().session_secret
    assert len(development_secret) >= 32

    monkeypatch.setenv("SALES_TRACKER_ENVIRONMENT", "production")
    monkeypatch.delenv("SALES_TRACKER_SESSION_SECRET", raising=False)
    monkeypatch.setenv("SALES_TRACKER_SESSION_COOKIE_SECURE", "true")
    with pytest.raises(
        RuntimeError,
        match="SALES_TRACKER_SESSION_SECRET.*at least 32 characters",
    ):
        load_settings()

    monkeypatch.setenv("SALES_TRACKER_SESSION_SECRET", "too-short")
    with pytest.raises(
        RuntimeError,
        match="SALES_TRACKER_SESSION_SECRET.*at least 32 characters",
    ):
        load_settings()

    monkeypatch.setenv(
        "SALES_TRACKER_SESSION_SECRET",
        "production-session-secret-with-at-least-32-characters",
    )
    monkeypatch.setenv("SALES_TRACKER_SESSION_COOKIE_SECURE", "false")
    with pytest.raises(RuntimeError, match="COOKIE_SECURE"):
        load_settings()


def test_session_max_age_has_finite_default_and_is_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session cookies always receive a configurable positive lifetime."""
    monkeypatch.setenv("SALES_TRACKER_ENVIRONMENT", "development")
    monkeypatch.delenv("SALES_TRACKER_SESSION_MAX_AGE_SECONDS", raising=False)
    assert (
        load_settings().session_max_age_seconds
        == DEFAULT_SESSION_MAX_AGE_SECONDS
    )

    monkeypatch.setenv("SALES_TRACKER_SESSION_MAX_AGE_SECONDS", "7200")
    assert load_settings().session_max_age_seconds == 7_200

    for invalid_value in ("0", "-1", "not-an-integer"):
        monkeypatch.setenv(
            "SALES_TRACKER_SESSION_MAX_AGE_SECONDS",
            invalid_value,
        )
        with pytest.raises(
            RuntimeError,
            match="SALES_TRACKER_SESSION_MAX_AGE_SECONDS.*positive integer",
        ):
            load_settings()
