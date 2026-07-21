"""Integration tests for personal weekly targets."""

import asyncio
from collections.abc import Generator
from datetime import date
from html import unescape
from pathlib import Path
import re

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, select

from app.config import Settings
from app.database import create_db_engine, get_session
from app.main import create_app
from app.models import Target, User
from app.routes.outreach import current_local_date
from app.services.passwords import hash_password
from app.services.targets import TARGET_METRICS, resolve_target_week

ACTIVE_EMAIL = "targets-user@example.com"
OTHER_EMAIL = "other-targets-user@example.com"
TEST_PASSWORD = "targets-test-password"
TEST_DATE = date(2026, 7, 14)


def visible_text(response: httpx.Response) -> str:
    """Return normalized user-visible text for presentation assertions."""
    without_tags = re.sub(r"<[^>]+>", " ", response.text)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


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
    assert response.headers["location"] == "/targets?week=2026-W29&saved=true"

    with Session(engine) as session:
        targets = session.exec(
            select(Target).where(Target.user_id == active_user_id),
        ).all()
        assert {target.metric_name for target in targets} == set(TARGET_METRICS)
        assert len(targets) == 6
        assert {target.week_start for target in targets} == {date(2026, 7, 13)}
        assert {target.effective_from for target in targets} == {date(2026, 7, 13)}
        assert {target.effective_until for target in targets} == {date(2026, 7, 19)}


def test_weekly_target_current_week_default_and_iso_boundary_is_server_derived(
    targets_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = targets_application

    async def scenario() -> tuple[
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
    ]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return (
                await client.get("/targets"),
                await client.get("/targets?week=2026-W01"),
                await client.get("/targets?week=2026-W28"),
                await client.get("/targets?week=2026-W30"),
                await client.get("/targets?week=2026-W31"),
            )

    current, boundary, previous, following, other = asyncio.run(scenario())
    assert 'value="2026-W29"' in current.text
    assert "Current week · Week 29 · 13 Jul – 19 Jul 2026" in visible_text(current)
    assert 'value="2026-W01"' in boundary.text
    assert "Week 1 · 29 Dec 2025 – 4 Jan 2026" in visible_text(boundary)
    assert "Previous week · Week 28 · 6 Jul – 12 Jul 2026" in visible_text(
        previous,
    )
    assert "Next week · Week 30 · 20 Jul – 26 Jul 2026" in visible_text(
        following,
    )
    assert "Week 31 · 27 Jul – 2 Aug 2026" in visible_text(other)
    assert "KW" not in current.text
    assert 'type="week"' not in current.text

    week, error = resolve_target_week("2026-W01", today=TEST_DATE)
    assert error is None and week is not None
    assert (week.start_date, week.end_date) == (
        date(2025, 12, 29),
        date(2026, 1, 4),
    )


def test_weekly_target_future_post_redirect_and_reload_preserve_week(
    targets_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, active_user_id, _ = targets_application

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            await client.post(
                "/targets",
                data=target_data(week="2026-W29", total_activities="100"),
            )
            saved = await client.post(
                "/targets",
                data=target_data(week="2026-W30", total_activities="230"),
            )
            reloaded = await client.get(saved.headers["location"])
            return saved, reloaded

    saved, reloaded = asyncio.run(scenario())
    assert saved.status_code == 303
    assert saved.headers["location"] == "/targets?week=2026-W30&saved=true"
    assert reloaded.status_code == 200
    assert "Weekly targets saved successfully." in reloaded.text
    assert 'name="week"' in reloaded.text
    assert 'value="2026-W30"' in reloaded.text
    assert "Next week · Week 30 · 20 Jul – 26 Jul 2026" in visible_text(
        reloaded,
    )
    assert 'name="total_activities"' in reloaded.text
    assert 'value="230"' in reloaded.text

    with Session(engine) as session:
        rows = session.exec(
            select(Target).where(
                Target.user_id == active_user_id,
                Target.metric_name == "total_activities",
            ),
        ).all()
        assert {(row.week_start, row.target_value) for row in rows} == {
            (date(2026, 7, 13), 100),
            (date(2026, 7, 20), 230),
        }


def test_weekly_target_validation_retains_future_week_and_values(
    targets_application: tuple[FastAPI, Engine, int, int],
) -> None:
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
                    week="2026-W30",
                    total_activities="-1",
                    companies_contacted="37",
                ),
            )

    response = asyncio.run(scenario())
    assert response.status_code == 400
    assert 'name="week"' in response.text
    assert 'value="2026-W30"' in response.text
    assert "Next week · Week 30 · 20 Jul – 26 Jul 2026" in visible_text(
        response,
    )
    assert 'value="-1"' in response.text
    assert 'value="37"' in response.text
    with Session(engine) as session:
        assert session.exec(
            select(Target).where(Target.user_id == active_user_id),
        ).all() == []


def test_weekly_target_invalid_iso_week_is_rejected_without_saving(
    targets_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, active_user_id, _ = targets_application

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.get("/targets?week=2026-W99"), await client.post(
                "/targets",
                data=target_data(week="2026-W99"),
            )

    get_response, post_response = asyncio.run(scenario())
    assert get_response.status_code == 400
    assert post_response.status_code == 400
    assert "Select a valid ISO calendar week." in get_response.text
    assert "Select a valid ISO calendar week." in post_response.text
    with Session(engine) as session:
        assert session.exec(
            select(Target).where(Target.user_id == active_user_id),
        ).all() == []


def test_different_weeks_keep_independent_values_and_past_is_read_only(
    targets_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, active_user_id, _ = targets_application

    async def scenario() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            current = await client.post(
                "/targets",
                data=target_data(week="2026-W29", total_activities="100"),
            )
            future = await client.post(
                "/targets",
                data=target_data(week="2026-W30", total_activities="200"),
            )
            await client.post(
                "/targets",
                data=target_data(week="2026-W29", total_activities="120"),
            )
            past = await client.post(
                "/targets",
                data=target_data(week="2026-W28", total_activities="999"),
            )
            return current, future, past

    current, future, past = asyncio.run(scenario())
    assert current.status_code == 303
    assert future.status_code == 303
    assert past.status_code == 400
    assert "Past weekly targets are read-only." in past.text

    with Session(engine) as session:
        rows = session.exec(
            select(Target).where(
                Target.user_id == active_user_id,
                Target.metric_name == "total_activities",
            ),
        ).all()
        assert {(row.week_start, row.target_value) for row in rows} == {
            (date(2026, 7, 13), 120),
            (date(2026, 7, 20), 200),
        }


def test_target_unique_constraint_is_per_user_week_and_metric(
    targets_application: tuple[FastAPI, Engine, int, int],
) -> None:
    _, engine, active_user_id, _ = targets_application
    with Session(engine) as session:
        for value in (10, 20):
            session.add(
                Target(
                    user_id=active_user_id,
                    metric_name="meetings_held",
                    target_value=value,
                    week_start=date(2026, 7, 13),
                    effective_from=date(2026, 7, 13),
                    effective_until=date(2026, 7, 19),
                ),
            )
        with pytest.raises(IntegrityError):
            session.commit()


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
                    week_start=date(2026, 7, 13),
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
    assert 'class="page-context-nav" aria-label="Weekly targets actions"' in template
    script = Path("app/static/js/targets_week.js").read_text(encoding="utf-8")

    assert 'class="target-week-trigger"' in template
    assert 'class="target-week-calendar-icon"' in template
    assert 'role="dialog"' in template
    assert 'role="grid"' in template
    assert "Mon</span><span>Tue" in template
    assert "data-target-week-value" in template
    assert 'type="hidden" name="week"' in template
    assert "data-calendar-previous" in template
    assert "data-calendar-next" in template
    assert "aria-expanded" in template
    assert "aria-controls" in template
    assert 'type="week"' not in template
    assert "data-target-week-form" in template
    assert "targets_week.js" in template
    assert "week_presentation.relative_label" in template
    assert "week_presentation.week_label" in template
    assert "week_presentation.date_range" in template
    assert "Past weekly targets are read-only." in template
    assert "Monday to Sunday" not in template
    assert "week_start.isoformat()" not in template
    assert 'type="number"' in template
    assert 'min="0"' in template
    assert 'step="1"' in template
    assert ".targets-form" in mobile_css
    assert ".targets-grid" in mobile_css
    assert ".report-heading-row" in mobile_css
    assert ".report-period-summary" in mobile_css
    assert ".page-context-nav" in mobile_css
    assert "min-width: 0" in mobile_css
    assert ".target-week-picker" in mobile_css
    assert ".target-week-trigger" in mobile_css
    assert ".target-week-calendar" in mobile_css
    assert "max-width: 100%" in mobile_css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in desktop_css
    assert "calendarMonths" in script
    assert "January" in script
    assert "Неделя" not in script
    assert "KW" not in script
    assert "ArrowLeft" in script
    assert "ArrowRight" in script
    assert "ArrowUp" in script
    assert "ArrowDown" in script
    assert 'event.key === "Escape"' in script
