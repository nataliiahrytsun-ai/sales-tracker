"""Integration and calculation tests for the personal My Week view."""

import asyncio
from collections.abc import Generator
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

from app.config import Settings
from app.database import create_db_engine, get_session
from app.main import create_app
from app.models import (
    CustomerEngagement,
    DailyOutreach,
    NeedIdentified,
    PipelineMeeting,
    PipelineOutcome,
    Target,
    User,
)
from app.routes.outreach import current_local_date
from app.services.my_week import build_week_metric, get_my_week_summary
from app.services.passwords import hash_password
from app.services.targets import TARGET_METRICS

ACTIVE_EMAIL = "my-week-user@example.com"
OTHER_EMAIL = "other-my-week-user@example.com"
TEST_PASSWORD = "my-week-test-password"
TEST_DATE = date(2026, 7, 15)


@pytest.fixture
def my_week_application(
    tmp_path: Path,
) -> Generator[tuple[FastAPI, Engine, int, int], None, None]:
    """Create an isolated app with two users and a deterministic Wednesday."""
    database_url = f"sqlite:///{(tmp_path / 'my-week.db').as_posix()}"
    engine = create_db_engine(database_url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        active_user = User(
            name="My Week User",
            email=ACTIVE_EMAIL,
            password_hash=hash_password(TEST_PASSWORD),
        )
        other_user = User(
            name="Other Week User",
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
            session_secret="my-week-session-secret-with-at-least-32-characters",
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


def add_outreach(
    session: Session,
    *,
    user_id: int,
    activity_date: date,
    total: int,
    companies: int,
    replies: int | None = None,
    positive_replies: int | None = None,
    meetings_booked: int | None = None,
) -> None:
    """Persist one outreach record for weekly aggregation tests."""
    session.add(
        DailyOutreach(
            user_id=user_id,
            activity_date=activity_date,
            total_activities=total,
            unique_companies=companies,
            replies=replies,
            positive_replies=positive_replies,
            meetings_booked=meetings_booked,
        ),
    )


def add_meeting(session: Session, *, user_id: int, occurred_at: datetime) -> None:
    """Persist one meeting for weekly boundary and ownership tests."""
    session.add(
        PipelineMeeting(
            user_id=user_id,
            occurred_at=occurred_at,
            customer_engagement=CustomerEngagement.HIGH,
            need_identified=NeedIdentified.YES,
            outcome=PipelineOutcome.FOLLOW_UP,
        ),
    )


def test_my_week_requires_authentication(
    my_week_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """The personal week page is private."""
    application, _, _, _ = my_week_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/my-week")

    response = asyncio.run(scenario())
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_weekly_totals_boundaries_targets_and_ownership(
    my_week_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Only owned Monday-Sunday records feed the six metric comparisons."""
    application, engine, active_user_id, other_user_id = my_week_application
    targets = {
        "total_activities": 60,
        "companies_contacted": 25,
        "replies": 5,
        "positive_replies": 0,
        "meetings_booked": 1,
        "meetings_held": 1,
    }
    with Session(engine) as session:
        add_outreach(
            session,
            user_id=active_user_id,
            activity_date=date(2026, 7, 13),
            total=10,
            companies=3,
        )
        add_outreach(
            session,
            user_id=active_user_id,
            activity_date=date(2026, 7, 19),
            total=20,
            companies=7,
            replies=5,
            positive_replies=2,
            meetings_booked=1,
        )
        for outside_date in (date(2026, 7, 12), date(2026, 7, 20)):
            add_outreach(
                session,
                user_id=active_user_id,
                activity_date=outside_date,
                total=500,
                companies=500,
                replies=500,
                positive_replies=500,
                meetings_booked=500,
            )
        add_outreach(
            session,
            user_id=other_user_id,
            activity_date=date(2026, 7, 15),
            total=900,
            companies=900,
            replies=900,
            positive_replies=900,
            meetings_booked=900,
        )
        for occurred_at in (
            datetime(2026, 7, 13, 12, tzinfo=UTC),
            datetime(2026, 7, 19, 12, tzinfo=UTC),
        ):
            add_meeting(session, user_id=active_user_id, occurred_at=occurred_at)
        add_meeting(
            session,
            user_id=active_user_id,
            occurred_at=datetime(2026, 7, 12, 12, tzinfo=UTC),
        )
        add_meeting(
            session,
            user_id=active_user_id,
            occurred_at=datetime(2026, 7, 20, 12, tzinfo=UTC),
        )
        add_meeting(
            session,
            user_id=other_user_id,
            occurred_at=datetime(2026, 7, 15, 12, tzinfo=UTC),
        )
        for metric in TARGET_METRICS:
            session.add(
                Target(
                    user_id=active_user_id,
                    metric_name=metric,
                    target_value=targets[metric],
                    week_start=date(2026, 7, 13),
                    effective_from=date(2025, 1, 6),
                    effective_until=date(2025, 1, 12),
                ),
            )
            session.add(
                Target(
                    user_id=other_user_id,
                    metric_name=metric,
                    target_value=999,
                    week_start=date(2026, 7, 13),
                    effective_from=date(2026, 7, 13),
                    effective_until=date(2026, 7, 19),
                ),
            )
        session.commit()

        summary = get_my_week_summary(
            session,
            user_id=active_user_id,
            today=TEST_DATE,
        )

    assert summary.week_start == date(2026, 7, 13)
    assert summary.week_end == date(2026, 7, 19)
    assert summary.has_activity
    metrics = {metric.key: metric for metric in summary.metrics}
    assert {key: metric.actual for key, metric in metrics.items()} == {
        "total_activities": 30,
        "companies_contacted": 10,
        "replies": 5,
        "positive_replies": 2,
        "meetings_booked": 1,
        "meetings_held": 2,
    }
    assert (metrics["total_activities"].target, metrics["total_activities"].remaining) == (60, 30)
    assert metrics["total_activities"].percentage == 50
    assert metrics["total_activities"].progress_state == "amber"
    assert metrics["companies_contacted"].progress_state == "orange"
    assert metrics["replies"].progress_state == "green"
    assert metrics["positive_replies"].percentage is None
    assert metrics["positive_replies"].progress_state == "neutral"
    assert metrics["meetings_held"].remaining == 0
    assert metrics["meetings_held"].percentage == 200
    assert metrics["meetings_held"].bar_percentage == 100

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.get("/my-week")

    page = asyncio.run(scenario())
    assert page.status_code == 200
    assert "Current week" in page.text
    assert "13 Jul – 19 Jul 2026" in page.text
    assert 'data-metric="meetings_held"' in page.text
    assert 'data-actual="2"' in page.text
    assert 'data-percentage="200"' in page.text
    assert 'data-bar-percentage="100"' in page.text
    assert "Goal exceeded by 1" in page.text
    assert "No target set" in page.text
    assert 'role="progressbar"' in page.text
    assert 'href="http://testserver/targets"' in page.text


def test_empty_week_and_missing_targets_have_neutral_state(
    my_week_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """An empty owned week renders six zero metrics without division errors."""
    application, _, _, _ = my_week_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.get("/my-week")

    page = asyncio.run(scenario())
    assert page.status_code == 200
    assert "No activity recorded this week" in page.text
    assert page.text.count('class="week-metric-card"') == 6
    assert page.text.count('data-progress-state="neutral"') == 6
    assert page.text.count('class="week-no-target">No target set</p>') == 6
    assert "0 of 0" not in page.text
    assert 'href="http://testserver/"' in page.text
    assert 'href="http://testserver/targets"' in page.text


def test_progress_state_thresholds() -> None:
    """Progress colors follow orange, amber, light-green, and green."""
    assert build_week_metric(key="x", label="X", actual=49, target=100).progress_state == "orange"
    assert build_week_metric(key="x", label="X", actual=50, target=100).progress_state == "amber"
    assert build_week_metric(key="x", label="X", actual=79, target=100).progress_state == "amber"
    assert build_week_metric(key="x", label="X", actual=80, target=100).progress_state == "light-green"
    assert build_week_metric(key="x", label="X", actual=99, target=100).progress_state == "light-green"
    assert build_week_metric(key="x", label="X", actual=100, target=100).progress_state == "green"


def test_my_week_layout_is_responsive_and_accessible() -> None:
    """Metric cards use mobile-first safe sizing and accessible progress bars."""
    template = Path("app/templates/my_week.html").read_text(encoding="utf-8")
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")
    mobile_css, desktop_css = css.split("@media (min-width: 48rem)", 1)

    assert "Back to Home" in template
    assert "Set weekly targets" in template
    assert 'role="progressbar"' in template
    assert 'aria-valuenow="{{ metric.aria_value }}"' in template
    assert 'class="week-metric-primary"' in template
    assert 'class="metric-primary-row"' in template
    assert 'class="metric-remaining"' in template
    assert 'class="report-heading-row"' in template
    assert 'class="report-period-summary"' in template
    assert (
        'class="page-context-nav" aria-label="My Week actions"'
        in template
    )
    assert 'class="week-metric-percentage"' in template
    assert 'class="week-no-target"' in template
    assert ".week-metric-grid" in mobile_css
    assert ".week-metric-card" in mobile_css
    page_context_nav_css = css.split(".page-context-nav {", 1)[1].split(
        "}",
        1,
    )[0]
    assert ".week-metric-primary" in mobile_css
    assert ".metric-primary-row" in mobile_css
    assert ".metric-remaining" in mobile_css
    assert ".report-heading-row" in mobile_css
    assert ".report-period-summary" in mobile_css
    assert "display: flex" in page_context_nav_css
    assert "flex-wrap: wrap" in page_context_nav_css
    assert "column-gap: 1.25rem" in page_context_nav_css
    assert "row-gap: 0.75rem" in page_context_nav_css
    assert "margin-block: 1.5rem" in page_context_nav_css
    assert ".week-metric-percentage" in mobile_css
    assert ".week-no-target" in mobile_css
    assert ".week-metric-values" not in css
    primary_row = template.split('class="metric-primary-row"', 1)[1].split(
        "</div>",
        1,
    )[0]
    assert "week-metric-primary" in primary_row
    assert "week-metric-percentage" in primary_row
    assert "remaining" not in primary_row
    assert "min-width: 0" in mobile_css
    assert "overflow-wrap: anywhere" in mobile_css
    assert ".week-progress-fill-orange" in mobile_css
    assert ".week-progress-fill-amber" in mobile_css
    assert ".week-progress-fill-light-green" in mobile_css
    assert ".week-progress-fill-green" in mobile_css
    assert ".week-progress-fill-neutral" in mobile_css
    assert ".week-progress-fill-low" not in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in desktop_css
