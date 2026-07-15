"""Unit and integration tests for session authentication."""

import asyncio
from base64 import b64decode, b64encode
from collections.abc import Generator
from datetime import date
import json
import logging
from pathlib import Path
import re

from fastapi import FastAPI
import httpx
from itsdangerous import TimestampSigner
import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, select

from app import cli
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
TEMPORARY_EMAIL = "temporary@example.com"
TEST_PASSWORD = "correct-test-password"
TEMPORARY_PASSWORD = "temporary-test-password"
NEW_PASSWORD = "new-secure-password"
SESSION_COOKIE_NAME = "sales_tracker_session"
TEST_SESSION_SECRET = "test-session-secret-with-at-least-32-characters"
TEST_SESSION_MAX_AGE_SECONDS = 3_600
STYLESHEET_PATH = Path("app/static/css/app.css")


def css_rule(css: str, selector: str) -> str:
    """Return declarations for one selector from a CSS source section."""
    match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>[^}}]+)\}}", css)
    assert match is not None
    return match.group("body")


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
                name="Temporary User",
                email=TEMPORARY_EMAIL,
                password_hash=hash_password(TEMPORARY_PASSWORD),
                must_change_password=True,
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


def test_authenticated_home_renders_scoped_actions(
    auth_application: tuple[FastAPI, Engine],
) -> None:
    """Home renders four scoped cards with integrated record management."""
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
        for heading in (
            "Meeting Entry",
            "Outreach Entry",
            "My Week",
            "Dashboard",
        ):
            assert f"<h2>{heading}</h2>" in response.text
        for action in (
            "Record meeting",
            "Update today’s outreach",
            "View / edit meetings",
            "View / edit outreach",
        ):
            assert action in response.text
        assert response.text.count('class="action-card"') == 4
        assert response.text.count(" disabled") == 2
        assert response.text.count("Coming soon") == 2
        assert 'href="http://testserver/meetings/new"' in response.text
        assert 'href="http://testserver/outreach/today"' in response.text
        assert 'href="http://testserver/meetings/recent"' in response.text
        assert 'href="http://testserver/outreach/recent"' in response.text
        assert response.text.count('href="http://testserver/meetings/recent"') == 1
        assert response.text.count('href="http://testserver/outreach/recent"') == 1
        assert 'href="http://testserver/change-password"' in response.text
        assert "View this week" not in response.text
        assert "Open dashboard" not in response.text
        assert "/dashboard" not in response.text

    asyncio.run(scenario())


def test_home_navigation_has_accessible_active_state() -> None:
    """Home uses a distinct active treatment with hover and focus states."""
    css = STYLESHEET_PATH.read_text(encoding="utf-8")
    base_template = Path("app/templates/base.html").read_text(encoding="utf-8")
    mobile_css, _desktop_css = css.split("@media (min-width: 48rem)", 1)
    home_link = css_rule(mobile_css, ".header-home-link")
    active = css_rule(mobile_css, ".header-home-link-active")
    focus = css_rule(mobile_css, ".header-home-link:focus-visible")
    hover = css_rule(mobile_css, ".header-home-link-active:hover")
    inactive_hover = css_rule(mobile_css, ".header-home-link:hover")
    keyboard_focus = css_rule(mobile_css, ":focus-visible")

    assert "request.url.path == '/'" in base_template
    assert "header-home-link-active" in base_template
    assert "min-height: 2.75rem" in home_link
    assert "padding: 0.55rem 0.8rem" in home_link
    assert "border-radius: 0.5rem" in home_link
    assert "text-decoration: none" in home_link
    assert "background: #edf2ff" in active
    assert "background: #dfe7ff" in focus
    assert "color: #12337f" in focus
    assert "@media (hover: hover)" in mobile_css
    assert "background: #dfe7ff" in hover
    assert "color: #12337f" in hover
    assert "background: var(--background)" in inactive_hover
    assert "color: var(--primary-hover)" in inactive_hover
    assert "outline: 0.2rem solid var(--focus)" in keyboard_focus


def test_home_navigation_is_active_only_on_home(
    auth_application: tuple[FastAPI, Engine],
) -> None:
    """Only the exact home path marks the Home navigation link as current."""
    application, _ = auth_application

    async def scenario() -> tuple[httpx.Response, list[httpx.Response]]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await client.post(
                "/login",
                data={"email": ACTIVE_EMAIL, "password": TEST_PASSWORD},
            )
            created = await client.post(
                "/meetings",
                data={
                    "customer_engagement": "High",
                    "need_identified": "Yes",
                    "outcome": "Follow-up",
                },
            )
            meeting_id = int(created.headers["location"].rsplit("=", 1)[-1])
            non_home_pages = [
                await client.get("/meetings/new"),
                await client.get("/outreach/today"),
                await client.get("/meetings/recent"),
                await client.get("/outreach/recent"),
                await client.get(f"/meetings/{meeting_id}/edit"),
                await client.get(f"/outreach/{date.today().isoformat()}"),
            ]
            return await client.get("/"), non_home_pages

    home, non_home_pages = asyncio.run(scenario())
    assert home.status_code == 200
    assert re.search(
        r'<a\s+class="header-home-link header-home-link-active"\s+'
        r'href="http://testserver/"\s+aria-current="page"\s*>Home</a>',
        home.text,
    )
    for response in non_home_pages:
        assert response.status_code == 200
        assert re.search(
            r'<a\s+class="header-home-link"\s+'
            r'href="http://testserver/"\s*>Home</a>',
            response.text,
        )
        assert "header-home-link-active" not in response.text


def test_home_layout_and_actions_are_structurally_responsive() -> None:
    """Home shares centered gutters and uses equal responsive actions."""
    css = STYLESHEET_PATH.read_text(encoding="utf-8")
    home_template = Path("app/templates/home.html").read_text(encoding="utf-8")
    mobile_css, desktop_css = css.split("@media (min-width: 48rem)", 1)

    shell = css_rule(mobile_css, ".shell")
    page_content = css_rule(mobile_css, ".page-content")
    action_grid = css_rule(mobile_css, ".action-grid")
    action_card = css_rule(mobile_css, ".action-card")
    action_children = css_rule(mobile_css, ".action-card > *")
    action_text = css_rule(mobile_css, ".action-card p")
    action_button = css_rule(mobile_css, ".action-card .button")
    card_actions = css_rule(mobile_css, ".home-card-actions")
    home_action_button = css_rule(mobile_css, ".home-action-button")
    shared_button = css_rule(mobile_css, ".button")

    assert "width: calc(100% - 2rem)" in shell
    assert "max-width: 68rem" in shell
    assert "margin-inline: auto" in shell
    assert "width: 100%" not in page_content

    assert "display: grid" in action_grid
    assert "display: grid" in action_card
    assert "grid-template-rows: 1fr auto" in action_card
    assert "max-width: 100%" in action_children
    assert "min-width: 0" in action_children
    assert "overflow-wrap: anywhere" in action_text
    assert "display: grid" in card_actions
    assert "min-width: 0" in card_actions

    assert "width: 100%" in action_button
    assert "max-width: 100%" in action_button
    assert "min-height: 2.75rem" in action_button
    assert "justify-self: stretch" in action_button
    assert "padding: 0.45rem 0.875rem" in action_button
    assert "font-size: 0.92rem" in action_button
    assert "line-height: 1.2" in action_button
    assert "min-height: 2.75rem" in shared_button
    assert home_template.count('class="action-card"') == 4
    assert home_template.count("home-action-button") == 4
    assert "min-height: 2.75rem" in home_action_button
    assert "align-self: end" in home_action_button
    assert "padding: 0.45rem 0.875rem" in home_action_button
    assert "line-height: 1.2" in home_action_button

    assert re.search(
        r"\.action-grid\s*\{[^}]*grid-template-columns:\s*"
        r"repeat\(2,\s*minmax\(0,\s*1fr\)\)",
        desktop_css,
    )
    assert "width: 18rem" not in desktop_css


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


def test_session_cookie_contains_only_required_authentication_state(
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

        assert payload == {
            "user_id": user.id,
            "auth_version": user.auth_version,
        }
        assert "password" not in payload
        assert "password_hash" not in payload
        assert "email" not in payload

    asyncio.run(scenario())


@pytest.mark.parametrize("method", ("GET", "POST"))
def test_change_password_requires_authentication(
    auth_application: tuple[FastAPI, Engine],
    method: str,
) -> None:
    """Anonymous users cannot read or submit the password-change form."""
    application, _ = auth_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.request(method, "/change-password")

        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("form_overrides", "expected_error"),
    [
        (
            {"current_password": "wrong-current-password"},
            "Current password is incorrect.",
        ),
        (
            {"confirm_new_password": "different-new-password"},
            "New passwords do not match.",
        ),
        (
            {"new_password": "short", "confirm_new_password": "short"},
            "New password must be at least 10 characters.",
        ),
        (
            {
                "new_password": TEST_PASSWORD,
                "confirm_new_password": TEST_PASSWORD,
            },
            "New password must be different from current password.",
        ),
    ],
)
def test_change_password_rejects_invalid_values_without_repopulating_secrets(
    auth_application: tuple[FastAPI, Engine],
    form_overrides: dict[str, str],
    expected_error: str,
) -> None:
    """Every password rule is enforced without echoing submitted secrets."""
    application, engine = auth_application
    form_data = {
        "current_password": TEST_PASSWORD,
        "new_password": NEW_PASSWORD,
        "confirm_new_password": NEW_PASSWORD,
    }
    form_data.update(form_overrides)

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await client.post(
                "/login",
                data={"email": ACTIVE_EMAIL, "password": TEST_PASSWORD},
            )
            return await client.post("/change-password", data=form_data)

    response = asyncio.run(scenario())
    assert response.status_code == 400
    assert expected_error in response.text
    assert response.text.count('type="password"') == 3
    for submitted_secret in set(form_data.values()):
        assert submitted_secret not in response.text

    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == ACTIVE_EMAIL)).one()
        assert verify_password(TEST_PASSWORD, user.password_hash)
        assert user.auth_version == 1


def test_successful_password_change_replaces_password_and_current_session(
    auth_application: tuple[FastAPI, Engine],
) -> None:
    """A successful change updates the hash and keeps only this session valid."""
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
            old_cookie = login_response.cookies[SESSION_COOKIE_NAME]
            changed = await client.post(
                "/change-password",
                data={
                    "current_password": TEST_PASSWORD,
                    "new_password": NEW_PASSWORD,
                    "confirm_new_password": NEW_PASSWORD,
                },
            )
            home = await client.get("/")

        assert changed.status_code == 303
        assert changed.headers["location"] == "/"
        assert changed.cookies[SESSION_COOKIE_NAME] != old_cookie
        assert home.status_code == 200

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as login_client:
            old_login = await login_client.post(
                "/login",
                data={"email": ACTIVE_EMAIL, "password": TEST_PASSWORD},
            )
            new_login = await login_client.post(
                "/login",
                data={"email": ACTIVE_EMAIL, "password": NEW_PASSWORD},
            )
        assert old_login.status_code == 401
        assert new_login.status_code == 303

    asyncio.run(scenario())
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == ACTIVE_EMAIL)).one()
        assert verify_password(NEW_PASSWORD, user.password_hash)
        assert user.must_change_password is False
        assert user.auth_version == 2


def test_password_change_invalidates_another_existing_session(
    auth_application: tuple[FastAPI, Engine],
) -> None:
    """A copied or second old-version session is rejected after a change."""
    application, _ = auth_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with (
            httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as changing_client,
            httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as old_client,
        ):
            for client in (changing_client, old_client):
                response = await client.post(
                    "/login",
                    data={"email": ACTIVE_EMAIL, "password": TEST_PASSWORD},
                )
                assert response.status_code == 303

            changed = await changing_client.post(
                "/change-password",
                data={
                    "current_password": TEST_PASSWORD,
                    "new_password": NEW_PASSWORD,
                    "confirm_new_password": NEW_PASSWORD,
                },
            )
            stale_response = await old_client.get("/")

        assert changed.status_code == 303
        assert stale_response.status_code == 303
        assert stale_response.headers["location"] == "/login"

    asyncio.run(scenario())


def test_temporary_password_forces_change_and_blocks_private_routes(
    auth_application: tuple[FastAPI, Engine],
) -> None:
    """Temporary-password users can access only password change and logout."""
    application, engine = auth_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            login_response = await client.post(
                "/login",
                data={
                    "email": TEMPORARY_EMAIL,
                    "password": TEMPORARY_PASSWORD,
                },
            )
            assert login_response.status_code == 303
            assert login_response.headers["location"] == "/change-password"

            for path in ("/", "/meetings/new", "/outreach/today"):
                blocked = await client.get(path)
                assert blocked.status_code == 303
                assert blocked.headers["location"] == "/change-password"

            form = await client.get("/change-password")
            assert form.status_code == 200
            assert "Replace your temporary password" in form.text
            assert ">Home</a>" not in form.text

            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as logout_client:
                await logout_client.post(
                    "/login",
                    data={
                        "email": TEMPORARY_EMAIL,
                        "password": TEMPORARY_PASSWORD,
                    },
                )
                logged_out = await logout_client.post("/logout")
                assert logged_out.status_code == 303
                assert logged_out.headers["location"] == "/login"

            changed = await client.post(
                "/change-password",
                data={
                    "current_password": TEMPORARY_PASSWORD,
                    "new_password": NEW_PASSWORD,
                    "confirm_new_password": NEW_PASSWORD,
                },
            )
            home = await client.get("/")

        assert changed.status_code == 303
        assert home.status_code == 200

    asyncio.run(scenario())
    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.email == TEMPORARY_EMAIL),
        ).one()
        assert user.must_change_password is False
        assert user.auth_version == 2


def test_cli_password_reset_invalidates_existing_web_session(
    auth_application: tuple[FastAPI, Engine],
) -> None:
    """A CLI reset revokes cookies issued before the auth-version increment."""
    application, engine = auth_application
    reset_password = "reset-temporary-password"

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

            passwords = iter([reset_password, reset_password])
            with Session(engine) as session:
                result = cli.reset_password(
                    session,
                    prompt=lambda _message: ACTIVE_EMAIL,
                    secret_prompt=lambda _message: next(passwords),
                    output=lambda _message: None,
                )
            assert result == 0

            stale_response = await client.get("/")
            assert stale_response.status_code == 303
            assert stale_response.headers["location"] == "/login"

            reset_login = await client.post(
                "/login",
                data={"email": ACTIVE_EMAIL, "password": reset_password},
            )
            assert reset_login.status_code == 303
            assert reset_login.headers["location"] == "/change-password"

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
