"""Integration tests for personal weekly targets."""

import asyncio
from collections.abc import Generator
from datetime import date
from pathlib import Path

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, select

from app.config import Settings
from app.database import create_db_engine, get_session
from app.main import create_app
from app.models import Target, User
from app.routes.outreach import current_local_date
from app.services.passwords import hash_password
from app.services.targets import TARGET_METRICS

ACTIVE_EMAIL = "targets-user@example.com"
OTHER_EMAIL = "other-targets-user@example.com"
TEST_PASSWORD = "targets-test-password"
TEST_DATE = date(2026, 7, 14)


def target_data(**overrides: str) -> dict[str, str]:
    """Return a complete valid target submission."""
    values = {
        "total_activities": "100",
        "companies_contacted": "40",
        "replies": "20",
        "positive_replies": "10",
        "meetings_booked": "5",
        "meetings_held": "4",
    }
    values.update(overrides)
    return values


@pytest.fixture
def targets_application(
    tmp_path: Path,
) -> Generator[tuple[FastAPI, Engine, int, int], None, None]:
    """Create an isolated application with two users and a fixed date."""
    database_url = f"sqlite:///{(tmp_path / 'targets.db').as_posix()}"
    engine = create_db_engine(database_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        active_user = User(
            name="Targets User",
            email=ACTIVE_EMAIL,
            password_hash=hash_password(TEST_PASSWORD),
        )
        other_user = User(
            name="Other Targets User",
            email=OTHER_EMAIL,
            password_hash=hash_password(TEST_PASSWORD),
        )
        session.add(active_user)
        session.add(other_user)
        session.commit()
        session.refresh(active_user)
        session.refresh(other_user)
        assert active_user.id is not None
        assert other_user.id is not None
        active_user_id = active_user.id
        other_user_id = other_user.id

    application = create_app(
        Settings(
            database_url=database_url,
            environment="test",
            session_secret="targets-session-secret-with-at-least-32-characters",
            session_cookie_secure=False,
        ),
    )

    def override_get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_session] = override_get_session
    application.dependency_overrides[current_local_date] = lambda: TEST_DATE
    try:
        yield application, engine, active_user_id, other_user_id
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


async def login(client: httpx.AsyncClient) -> None:
    """Authenticate the active fixture user."""
    response = await client.post(
        "/login",
        data={"email": ACTIVE_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 303


def test_targets_require_authentication(
    targets_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Both weekly-target endpoints are private."""
    application, _, _, _ = targets_application

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/targets"), await client.post("/targets")

    get_response, post_response = asyncio.run(scenario())
    for response in (get_response, post_response):
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


def test_first_save_creates_six_targets_for_monday_to_sunday(
    targets_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """The first save creates one owned row for every supported metric."""
    application, engine, active_user_id, _ = targets_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.post("/targets", data=target_data())

    response = asyncio.run(scenario())
    assert response.status_code == 303
    assert response.headers["location"] == "/targets?saved=true"

    with Session(engine) as session:
        targets = session.exec(
            select(Target).where(Target.user_id == active_user_id),
        ).all()
        assert {target.metric_name for target in targets} == set(TARGET_METRICS)
        assert len(targets) == 6
        assert {target.effective_from for target in targets} == {date(2026, 7, 13)}
        assert {target.effective_until for target in targets} == {date(2026, 7, 19)}


def test_repeated_save_updates_without_duplicates_and_displays_values(
    targets_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """A later save updates the same rows and the GET form shows the values."""
    application, engine, active_user_id, _ = targets_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            await client.post("/targets", data=target_data())
            updated = target_data(total_activities="120", meetings_held="8")
            await client.post("/targets", data=updated)
            return await client.get("/targets?saved=true")

    page = asyncio.run(scenario())
    assert page.status_code == 200
    assert "Weekly targets saved successfully." in page.text
    assert 'name="total_activities"' in page.text
    assert 'value="120"' in page.text
    assert 'name="meetings_held"' in page.text
    assert 'value="8"' in page.text

    with Session(engine) as session:
        targets = session.exec(
            select(Target).where(Target.user_id == active_user_id),
        ).all()
        assert len(targets) == 6
        stored = {target.metric_name: target.target_value for target in targets}
        assert stored["total_activities"] == 120
        assert stored["meetings_held"] == 8


def test_zero_values_are_accepted(
    targets_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Zero is a valid target for every metric."""
    application, engine, active_user_id, _ = targets_application
    zeros = {metric: "0" for metric in TARGET_METRICS}

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.post("/targets", data=zeros)

    assert asyncio.run(scenario()).status_code == 303
    with Session(engine) as session:
        targets = session.exec(
            select(Target).where(Target.user_id == active_user_id),
        ).all()
        assert len(targets) == 6
        assert all(target.target_value == 0 for target in targets)


def test_validation_preserves_entered_values_and_does_not_save(
    targets_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Invalid integers return field errors without clearing safe input."""
    application, engine, active_user_id, _ = targets_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.post(
                "/targets",
                data=target_data(
                    total_activities="-1",
                    replies="1.5",
                    meetings_held="",
                    companies_contacted="37",
                ),
            )

    response = asyncio.run(scenario())
    assert response.status_code == 400
    assert response.text.count("Enter a non-negative whole number.") == 3
    assert 'value="-1"' in response.text
    assert 'value="1.5"' in response.text
    assert 'value="37"' in response.text
    with Session(engine) as session:
        assert session.exec(
            select(Target).where(Target.user_id == active_user_id),
        ).all() == []


def test_targets_are_scoped_to_the_authenticated_owner(
    targets_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """A user neither sees nor overwrites another user's target rows."""
    application, engine, active_user_id, other_user_id = targets_application
    with Session(engine) as session:
        for metric in TARGET_METRICS:
            session.add(
                Target(
                    user_id=other_user_id,
                    metric_name=metric,
                    target_value=91,
                    effective_from=date(2026, 7, 13),
                    effective_until=date(2026, 7, 19),
                ),
            )
        session.commit()

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            page = await client.get("/targets")
            saved = await client.post("/targets", data=target_data())
            return page, saved

    page, saved = asyncio.run(scenario())
    assert page.status_code == 200
    assert 'value="91"' not in page.text
    assert saved.status_code == 303

    with Session(engine) as session:
        own_targets = session.exec(
            select(Target).where(Target.user_id == active_user_id),
        ).all()
        other_targets = session.exec(
            select(Target).where(Target.user_id == other_user_id),
        ).all()
        assert len(own_targets) == 6
        assert len(other_targets) == 6
        assert all(target.target_value == 91 for target in other_targets)


def test_targets_form_is_responsive_and_links_home() -> None:
    """The target form uses the shared responsive, overflow-safe structure."""
    template = Path("app/templates/targets.html").read_text(encoding="utf-8")
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")
    mobile_css, desktop_css = css.split("@media (min-width: 48rem)", 1)

    assert "Back to Home" in template
    assert 'class="report-heading-row"' in template
    assert 'class="report-period-summary"' in template
    assert 'class="report-navigation-row report-navigation-spaced"' in template
    assert "Current week" in template
    assert "Monday to Sunday" not in template
    assert "week_start.isoformat()" not in template
    assert 'type="number"' in template
    assert 'min="0"' in template
    assert 'step="1"' in template
    assert ".targets-form" in mobile_css
    assert ".targets-grid" in mobile_css
    assert ".report-heading-row" in mobile_css
    assert ".report-period-summary" in mobile_css
    assert ".report-navigation-spaced" in mobile_css
    assert "min-width: 0" in mobile_css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in desktop_css
