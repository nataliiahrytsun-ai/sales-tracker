"""Integration tests for browser-facing security controls."""

import asyncio
from collections.abc import Generator
import logging
from pathlib import Path
import re

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

from app.config import Settings
from app.database import create_db_engine, get_session
from app.main import create_app
from app.models import User
from app.security import (
    CONTENT_SECURITY_POLICY,
    LoginRateLimiter,
)
from app.services.passwords import hash_password

ACTIVE_EMAIL = "security-user@example.com"
UNKNOWN_EMAIL = "unknown-security-user@example.com"
TEST_PASSWORD = "security-test-password"
WRONG_PASSWORD = "security-wrong-password-never-log"
SESSION_SECRET = "security-session-secret-with-at-least-32-characters"
CSRF_PATTERN = re.compile(
    r'name="csrf_token"\s+value="(?P<token>[^"]+)"',
)


class FakeClock:
    """Deterministic monotonic clock for limiter tests."""

    def __init__(self) -> None:
        self.value = 10_000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@pytest.fixture
def security_application(
    tmp_path: Path,
) -> Generator[tuple[FastAPI, Engine], None, None]:
    """Create an isolated secured app with one active user."""
    database_url = f"sqlite:///{(tmp_path / 'security.db').as_posix()}"
    engine = create_db_engine(database_url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            User(
                name="Security User",
                email=ACTIVE_EMAIL,
                password_hash=hash_password(TEST_PASSWORD),
            ),
        )
        session.commit()

    application = create_app(
        Settings(
            database_url=database_url,
            environment="test",
            session_secret=SESSION_SECRET,
            session_cookie_secure=False,
            login_rate_limit_max_attempts=2,
            login_rate_limit_window_seconds=60,
            login_rate_limit_block_seconds=120,
        ),
    )
    application.state.login_rate_limiter.clock = FakeClock()

    def override_get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_session] = override_get_session
    try:
        yield application, engine
    finally:
        limiter: LoginRateLimiter = application.state.login_rate_limiter
        limiter.clear_all()
        application.dependency_overrides.clear()
        engine.dispose()


def csrf_token(response: httpx.Response) -> str:
    """Extract a rendered synchronizer token."""
    match = CSRF_PATTERN.search(response.text)
    assert match is not None
    return match.group("token")


async def login(
    client: httpx.AsyncClient,
    *,
    email: str = ACTIVE_EMAIL,
    password: str = TEST_PASSWORD,
) -> httpx.Response:
    """Submit the protected login form through the shared browser helper."""
    return await client.post(
        "/login",
        data={"email": email, "password": password},
    )


def test_login_form_contains_csrf_token_and_valid_login_works(
    security_application: tuple[FastAPI, Engine],
) -> None:
    """Login receives a strong session token and accepts that exact token."""
    application, _ = security_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            page = await client.get("/login")
            token = csrf_token(page)
            response = await client.post(
                "/login",
                data={
                    "csrf_token": token,
                    "email": ACTIVE_EMAIL,
                    "password": TEST_PASSWORD,
                },
            )

        assert len(token) >= 32
        assert response.status_code == 303
        assert response.headers["location"] == "/"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "submitted_token",
    [None, "", "incorrect-session-token"],
)
def test_login_rejects_missing_empty_or_wrong_csrf_token(
    security_application: tuple[FastAPI, Engine],
    submitted_token: str | None,
) -> None:
    """Invalid login CSRF submissions return a generic 403."""
    application, _ = security_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await client.get("/login")
            data = {"email": ACTIVE_EMAIL, "password": TEST_PASSWORD}
            if submitted_token is not None:
                data["csrf_token"] = submitted_token
            return await client.post("/login", data=data, csrf=False)

    response = asyncio.run(scenario())
    assert response.status_code == 403
    assert response.json() == {"detail": "Request could not be validated."}
    assert TEST_PASSWORD not in response.text


def test_csrf_token_from_another_session_is_rejected(
    security_application: tuple[FastAPI, Engine],
) -> None:
    """A valid token cannot be replayed from a different signed session."""
    application, _ = security_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with (
            httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as first_client,
            httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as second_client,
        ):
            foreign_token = csrf_token(await first_client.get("/login"))
            await second_client.get("/login")
            return await second_client.post(
                "/login",
                data={
                    "csrf_token": foreign_token,
                    "email": ACTIVE_EMAIL,
                    "password": TEST_PASSWORD,
                },
                csrf=False,
            )

    assert asyncio.run(scenario()).status_code == 403


def test_authenticated_state_changing_routes_require_csrf(
    security_application: tuple[FastAPI, Engine],
) -> None:
    """Every audited private POST route rejects a missing token."""
    application, _ = security_application

    async def scenario() -> list[tuple[str, int]]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            assert (await login(client)).status_code == 303
            paths = (
                "/change-password",
                "/logout",
                "/meetings",
                "/meetings/999",
                "/meetings/999/delete",
                "/meetings/999/undo",
                "/outreach/today",
                "/outreach/2026-07-23",
                "/targets",
            )
            return [
                (path, (await client.request("POST", path)).status_code)
                for path in paths
            ]

    assert asyncio.run(scenario()) == [
        ("/change-password", 403),
        ("/logout", 403),
        ("/meetings", 403),
        ("/meetings/999", 403),
        ("/meetings/999/delete", 403),
        ("/meetings/999/undo", 403),
        ("/outreach/today", 403),
        ("/outreach/2026-07-23", 403),
        ("/targets", 403),
    ]


def test_logout_with_current_csrf_token_works(
    security_application: tuple[FastAPI, Engine],
) -> None:
    """The protected logout remains a POST and removes authentication."""
    application, _ = security_application

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            assert (await login(client)).status_code == 303
            logout_response = await client.post("/logout")
            private_response = await client.get("/")
            return logout_response, private_response

    logout_response, private_response = asyncio.run(scenario())
    assert logout_response.status_code == 303
    assert private_response.status_code == 303
    assert private_response.headers["location"] == "/login"


def test_validation_error_preserves_working_csrf_form(
    security_application: tuple[FastAPI, Engine],
) -> None:
    """A 400 form response retains a token that can be resubmitted."""
    application, _ = security_application

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            assert (await login(client)).status_code == 303
            invalid = await client.post("/meetings", data={})
            token = csrf_token(invalid)
            valid = await client.post(
                "/meetings",
                data={
                    "csrf_token": token,
                    "customer_engagement": "High",
                    "need_identified": "Yes",
                    "outcome": "Request sent",
                    "company_name": "CSRF Test Company",
                },
            )
            return invalid, valid

    invalid, valid = asyncio.run(scenario())
    assert invalid.status_code == 400
    assert valid.status_code == 303


def test_health_remains_available_without_csrf(
    security_application: tuple[FastAPI, Engine],
) -> None:
    """The public GET health endpoint is not subject to CSRF."""
    application, _ = security_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/health")

    response = asyncio.run(scenario())
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_login_rate_limit_allows_configured_failures_then_returns_429(
    security_application: tuple[FastAPI, Engine],
) -> None:
    """Only the attempt exceeding the configured allowance is throttled."""
    application, _ = security_application

    async def scenario() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return [
                await login(client, password=WRONG_PASSWORD)
                for _ in range(3)
            ]

    first, second, blocked = asyncio.run(scenario())
    assert first.status_code == second.status_code == 401
    assert "Invalid email or password." in first.text
    assert "Invalid email or password." in second.text
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "120"
    assert "Too many login attempts. Please try again later." in blocked.text
    assert WRONG_PASSWORD not in blocked.text


def test_rate_limit_does_not_mix_client_or_identifier_buckets(
    security_application: tuple[FastAPI, Engine],
) -> None:
    """Direct peer IP and normalized identifier jointly scope failures."""
    application, _ = security_application

    async def scenario() -> tuple[int, int, int]:
        first_transport = httpx.ASGITransport(
            app=application,
            client=("192.0.2.10", 41000),
        )
        second_transport = httpx.ASGITransport(
            app=application,
            client=("192.0.2.11", 41001),
        )
        async with (
            httpx.AsyncClient(
                transport=first_transport,
                base_url="http://testserver",
            ) as first_client,
            httpx.AsyncClient(
                transport=second_transport,
                base_url="http://testserver",
            ) as second_client,
        ):
            for _ in range(2):
                assert (
                    await login(first_client, password=WRONG_PASSWORD)
                ).status_code == 401
            other_ip = await login(
                second_client,
                password=WRONG_PASSWORD,
            )
            other_identifier = await login(
                first_client,
                email=UNKNOWN_EMAIL,
                password=WRONG_PASSWORD,
            )
            blocked = await login(
                first_client,
                password=WRONG_PASSWORD,
            )
            return (
                other_ip.status_code,
                other_identifier.status_code,
                blocked.status_code,
            )

    assert asyncio.run(scenario()) == (401, 401, 429)


def test_successful_login_clears_failed_attempts(
    security_application: tuple[FastAPI, Engine],
) -> None:
    """A success before blocking resets the matching limiter bucket."""
    application, _ = security_application

    async def scenario() -> tuple[int, int]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            for _ in range(2):
                assert (
                    await login(client, password=WRONG_PASSWORD)
                ).status_code == 401
            assert (await login(client)).status_code == 303
            await client.post("/logout")
            first = await login(client, password=WRONG_PASSWORD)
            second = await login(client, password=WRONG_PASSWORD)
            return first.status_code, second.status_code

    assert asyncio.run(scenario()) == (401, 401)


def test_login_failures_do_not_log_or_render_password(
    security_application: tuple[FastAPI, Engine],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Passwords stay out of response, log, and exception text."""
    application, _ = security_application
    caplog.set_level(logging.DEBUG)

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await login(client, password=WRONG_PASSWORD)

    response = asyncio.run(scenario())
    assert response.status_code == 401
    assert WRONG_PASSWORD not in response.text
    assert WRONG_PASSWORD not in caplog.text


def test_unknown_and_existing_users_receive_same_login_error(
    security_application: tuple[FastAPI, Engine],
) -> None:
    """Authentication failures do not disclose account existence."""
    application, _ = security_application

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            existing = await login(client, password=WRONG_PASSWORD)
            unknown = await login(
                client,
                email=UNKNOWN_EMAIL,
                password=WRONG_PASSWORD,
            )
            return existing, unknown

    existing, unknown = asyncio.run(scenario())
    assert existing.status_code == unknown.status_code == 401
    assert "Invalid email or password." in existing.text
    assert "Invalid email or password." in unknown.text


def test_trusted_host_allows_configured_host_and_rejects_unknown_host(
    security_application: tuple[FastAPI, Engine],
) -> None:
    """Development/test allowlist accepts testserver and rejects other hosts."""
    application, _ = security_application

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with (
            httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as allowed_client,
            httpx.AsyncClient(
                transport=transport,
                base_url="http://untrusted.example",
            ) as denied_client,
        ):
            return (
                await allowed_client.get("/health"),
                await denied_client.get("/health"),
            )

    allowed, denied = asyncio.run(scenario())
    assert allowed.status_code == 200
    assert denied.status_code == 400
    assert denied.text == "Invalid host header"


def test_trusted_host_supports_leading_subdomain_wildcard() -> None:
    """A configured leading wildcard accepts only that domain suffix."""
    application = create_app(
        Settings(
            database_url="sqlite:///./unused-security-test.db",
            environment="test",
            session_secret=SESSION_SECRET,
            session_cookie_secure=False,
            allowed_hosts=("*.example.test",),
        ),
    )

    async def scenario() -> tuple[int, int]:
        transport = httpx.ASGITransport(app=application)
        async with (
            httpx.AsyncClient(
                transport=transport,
                base_url="http://pilot.example.test",
            ) as allowed_client,
            httpx.AsyncClient(
                transport=transport,
                base_url="http://example.invalid",
            ) as denied_client,
        ):
            return (
                (await allowed_client.get("/health")).status_code,
                (await denied_client.get("/health")).status_code,
            )

    assert asyncio.run(scenario()) == (200, 400)


@pytest.mark.parametrize("path", ["/login", "/missing", "/health"])
def test_security_headers_cover_success_and_error_responses(
    security_application: tuple[FastAPI, Engine],
    path: str,
) -> None:
    """Baseline headers are present on HTML, 404, and application responses."""
    application, _ = security_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(path)

    response = asyncio.run(scenario())
    assert response.headers["x-content-type-options"] == "nosniff"
    assert (
        response.headers["referrer-policy"]
        == "strict-origin-when-cross-origin"
    )
    assert response.headers["x-frame-options"] == "DENY"
    assert "camera=()" in response.headers["permissions-policy"]
    assert (
        response.headers["content-security-policy"]
        == CONTENT_SECURITY_POLICY
    )
    assert "strict-transport-security" not in response.headers


def test_security_headers_cover_csrf_403_and_trusted_host_400(
    security_application: tuple[FastAPI, Engine],
) -> None:
    """Outermost header middleware also covers security rejection responses."""
    application, _ = security_application

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with (
            httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as csrf_client,
            httpx.AsyncClient(
                transport=transport,
                base_url="http://untrusted.example",
            ) as host_client,
        ):
            csrf_response = await csrf_client.post(
                "/login",
                data={"email": ACTIVE_EMAIL, "password": TEST_PASSWORD},
                csrf=False,
            )
            return csrf_response, await host_client.get("/health")

    for response in asyncio.run(scenario()):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers[
            "content-security-policy"
        ]


def test_csp_matches_current_local_static_resources(
    security_application: tuple[FastAPI, Engine],
) -> None:
    """CSP permits local scripts/styles and required data-image CSS only."""
    application, _ = security_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/login")

    response = asyncio.run(scenario())
    csp = response.headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "img-src 'self' data:" in csp
    assert 'src="http://testserver/static/js/' in response.text
    assert 'href="http://testserver/static/css/app.css"' in response.text
    assert "onsubmit=" not in response.text
