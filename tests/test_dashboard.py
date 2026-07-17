"""Integration and calculation tests for the company Dashboard."""

import asyncio
from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from math import ceil
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
from app.models import (
    CustomerEngagement,
    DailyOutreach,
    NeedIdentified,
    OutreachCountry,
    PipelineMeeting,
    PipelineOutcome,
    Target,
    User,
    UserMood,
)
from app.routes.outreach import current_local_date
from app.services.dashboard import (
    CURRENT_MONTH,
    CURRENT_WEEK,
    CUSTOM_RANGE,
    DASHBOARD_TARGET_ATTENTION_RATIO,
    PREVIOUS_WEEK,
    ACTIVITY_GRANULARITY_MONTH,
    ACTIVITY_GRANULARITY_PERIOD,
    USER_SCOPE_SELECTED,
    DashboardUserFilter,
    _activity_bucket_granularity,
    ACTIVITY_HEADINGS,
    _build_dashboard_metric,
    _activity_buckets,
    get_dashboard_summary,
    resolve_dashboard_filter,
)
from app.services.passwords import hash_password
from app.services.targets import TARGET_FIELDS, TARGET_METRICS

ACTIVE_EMAIL = "dashboard-user@example.com"
TEST_PASSWORD = "dashboard-test-password"
TEST_DATE = date(2026, 7, 15)
TARGET_CALCULATION_NOTICE = (
    "Weekly goals are prorated to the selected period."
)


def add_outreach(
    session: Session,
    *,
    user_id: int,
    activity_date: date,
    total: int,
    companies: int,
    replies: int | None = None,
    positive: int | None = None,
    booked: int | None = None,
    mood: UserMood | None = None,
    blocker: str | None = None,
    note: str | None = None,
    countries: tuple[tuple[str, int], ...] = (),
) -> None:
    record = DailyOutreach(
        user_id=user_id,
        activity_date=activity_date,
        total_activities=total,
        unique_companies=companies,
        replies=replies,
        positive_replies=positive,
        meetings_booked=booked,
        user_mood=mood,
        blocker_tag=blocker,
        note=note,
    )
    session.add(record)
    session.flush()
    assert record.id is not None
    for country_code, count in countries:
        session.add(
            OutreachCountry(
                outreach_daily_id=record.id,
                country_code=country_code,
                companies_contacted=count,
            ),
        )


def add_meeting(
    session: Session,
    *,
    user_id: int,
    occurred_at: datetime,
    company: str = "Private company",
    note: str = "Private meeting note",
    engagement: CustomerEngagement = CustomerEngagement.HIGH,
    need: NeedIdentified = NeedIdentified.YES,
    outcome: PipelineOutcome = PipelineOutcome.FOLLOW_UP,
) -> None:
    session.add(
        PipelineMeeting(
            user_id=user_id,
            occurred_at=occurred_at,
            customer_engagement=engagement,
            need_identified=need,
            outcome=outcome,
            company_name=company,
            note=note,
            user_mood=UserMood.OKAY,
            blocker_tag="Meeting-only blocker",
        ),
    )


@pytest.fixture
def dashboard_application(
    tmp_path: Path,
) -> Generator[tuple[FastAPI, Engine, int, int], None, None]:
    """Create two users with current, previous, and monthly aggregate data."""
    database_url = f"sqlite:///{(tmp_path / 'dashboard.db').as_posix()}"
    engine = create_db_engine(database_url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        first = User(
            name="Dashboard User",
            email=ACTIVE_EMAIL,
            password_hash=hash_password(TEST_PASSWORD),
        )
        second = User(
            name="Foreign Employee Name",
            email="foreign-dashboard@example.com",
            password_hash=hash_password(TEST_PASSWORD),
        )
        session.add(first)
        session.add(second)
        session.flush()
        assert first.id is not None and second.id is not None

        add_outreach(
            session,
            user_id=first.id,
            activity_date=date(2026, 7, 13),
            total=10,
            companies=3,
            booked=1,
            mood=UserMood.GOOD,
            blocker="No response",
            note="Private outreach note",
            countries=(("BR", 2), ("DE", 1)),
        )
        add_outreach(
            session,
            user_id=second.id,
            activity_date=date(2026, 7, 14),
            total=20,
            companies=5,
            replies=4,
            positive=2,
            mood=UserMood.DIFFICULT,
            blocker="No response",
            note="Foreign private note",
            countries=(("BR", 3), ("AT", 2)),
        )
        add_outreach(
            session,
            user_id=first.id,
            activity_date=date(2026, 7, 6),
            total=7,
            companies=2,
            replies=1,
        )
        add_outreach(
            session,
            user_id=second.id,
            activity_date=date(2026, 7, 12),
            total=9,
            companies=4,
            positive=1,
        )
        add_outreach(
            session,
            user_id=first.id,
            activity_date=date(2026, 7, 1),
            total=3,
            companies=1,
        )
        add_outreach(
            session,
            user_id=first.id,
            activity_date=date(2026, 6, 30),
            total=99,
            companies=99,
        )
        for user_id, day in (
            (first.id, 13),
            (second.id, 14),
            (second.id, 14),
        ):
            add_meeting(
                session,
                user_id=user_id,
                occurred_at=datetime(2026, 7, day, 12, tzinfo=UTC),
                company="Do not expose company",
                note="Do not expose meeting note",
            )
        add_meeting(
            session,
            user_id=first.id,
            occurred_at=datetime(2026, 7, 6, 12, tzinfo=UTC),
        )
        for user_id in (first.id, second.id):
            for metric in TARGET_METRICS:
                value = 0 if metric == "companies_contacted" else 2
                session.add(
                    Target(
                        user_id=user_id,
                        metric_name=metric,
                        target_value=value,
                        week_start=date(2026, 7, 13),
                        effective_from=date(2026, 7, 13),
                        effective_until=date(2026, 7, 19),
                    ),
                )
                session.add(
                    Target(
                        user_id=user_id,
                        metric_name=metric,
                        target_value=7 if user_id == first.id else 9,
                        week_start=date(2026, 7, 6),
                        effective_from=date(2026, 7, 6),
                        effective_until=date(2026, 7, 12),
                    ),
                )
        session.commit()
        first_id, second_id = first.id, second.id

    application = create_app(
        Settings(
            database_url=database_url,
            environment="test",
            session_secret="dashboard-session-secret-with-at-least-32-characters",
            session_cookie_secure=False,
        ),
    )

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_session] = override_session
    application.dependency_overrides[current_local_date] = lambda: TEST_DATE
    try:
        yield application, engine, first_id, second_id
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


async def login(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/login",
        data={"email": ACTIVE_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 303


def get_dashboard(application: FastAPI, url: str = "/dashboard") -> httpx.Response:
    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.get(url)

    return asyncio.run(scenario())


def metric_card(response: httpx.Response, metric: str) -> str:
    """Return one rendered metric card for focused assertions."""
    start = response.text.index(f'data-metric="{metric}"')
    end = response.text.index("</article>", start)
    return response.text[start:end]


def pipeline_conversion_section(response: httpx.Response) -> str:
    marker = response.text.index("data-pipeline-conversions")
    start = response.text.rfind("<section", 0, marker)
    end = response.text.index("</section>", start)
    return response.text[start:end]


def pipeline_rate(response: httpx.Response, metric: str) -> str:
    section = pipeline_conversion_section(response)
    start = section.index(f'data-pipeline-rate="{metric}"')
    end = section.index("</div>", start)
    return section[start:end]


def outreach_conversion_section(response: httpx.Response) -> str:
    marker = response.text.index("data-outreach-conversions")
    start = response.text.rfind("<section", 0, marker)
    end = response.text.index("</section>", start)
    return response.text[start:end]


def outreach_rate(response: httpx.Response, metric: str) -> str:
    section = outreach_conversion_section(response)
    start = section.index(f'data-outreach-rate="{metric}"')
    end = section.index("</div>", start)
    return section[start:end]


def assert_empty_selected_dashboard(response: httpx.Response) -> None:
    """Assert a selected scope with no valid users cannot expose aggregates."""
    assert response.status_code == 200
    assert "Select at least one user to view data." in response.text
    assert TARGET_CALCULATION_NOTICE in response.text
    assert 'data-users-summary>Select users</span>' in response.text
    assert response.text.count('class="week-metric-card dashboard-metric-card"') == 6
    for metric, _label in TARGET_FIELDS:
        card = metric_card(response, metric)
        assert 'data-actual="0"' in card
        assert 'data-target="0"' in card
        assert 'data-remaining="0"' in card
        assert 'data-percentage="none"' in card
        assert 'class="dashboard-kpi-status' in card
        assert 'class="dashboard-circular-progress' in card
    assert response.text.count('role="progressbar"') == 6
    assert response.text.count("No target") >= 6
    assert "No activity to display." in response.text
    assert 'class="dashboard-chart-group"' not in response.text
    assert 'data-country=' not in response.text
    assert 'data-blocker=' not in response.text
    assert 'data-mood=' not in response.text
    assert "No country activity for this period." in response.text
    assert "No Daily Outreach blockers for this period." in response.text
    assert response.text.count("No recorded mood for this period.") == 1
    assert "Outreach activities: 10" not in response.text
    assert "Outreach activities: 20" not in response.text


def add_pipeline_conversion_records(
    engine: Engine,
    *,
    first_id: int,
    second_id: int,
) -> None:
    """Add known Pipeline inputs on one included and one excluded date."""
    included = (
        (
            first_id,
            CustomerEngagement.HIGH,
            NeedIdentified.YES,
            PipelineOutcome.FOLLOW_UP,
        ),
        (
            first_id,
            CustomerEngagement.HIGH,
            NeedIdentified.NO,
            PipelineOutcome.PROPOSAL_REQUESTED,
        ),
        (
            first_id,
            CustomerEngagement.LOW,
            NeedIdentified.YES,
            PipelineOutcome.NO_FIT,
        ),
        (
            second_id,
            CustomerEngagement.MEDIUM,
            NeedIdentified.YES,
            PipelineOutcome.OPPORTUNITY_IDENTIFIED,
        ),
        (
            second_id,
            CustomerEngagement.LOW,
            NeedIdentified.NO,
            PipelineOutcome.INTRODUCTION,
        ),
    )
    with Session(engine) as session:
        for user_id, engagement, need, outcome in included:
            add_meeting(
                session,
                user_id=user_id,
                occurred_at=datetime(2026, 7, 2, 12, tzinfo=UTC),
                engagement=engagement,
                need=need,
                outcome=outcome,
            )
        add_meeting(
            session,
            user_id=first_id,
            occurred_at=datetime(2026, 7, 3, 12, tzinfo=UTC),
            engagement=CustomerEngagement.HIGH,
            need=NeedIdentified.YES,
            outcome=PipelineOutcome.OPPORTUNITY_IDENTIFIED,
        )
        session.commit()


def add_outreach_conversion_records(
    engine: Engine,
    *,
    first_id: int,
    second_id: int,
) -> None:
    """Add known Outreach inputs on included and excluded dates."""
    with Session(engine) as session:
        add_outreach(
            session,
            user_id=first_id,
            activity_date=date(2026, 7, 2),
            total=10,
            companies=4,
            replies=5,
            positive=2,
            booked=1,
        )
        add_outreach(
            session,
            user_id=second_id,
            activity_date=date(2026, 7, 2),
            total=30,
            companies=6,
            replies=3,
            positive=1,
            booked=3,
        )
        add_outreach(
            session,
            user_id=first_id,
            activity_date=date(2026, 7, 3),
            total=20,
            companies=5,
            replies=20,
            positive=10,
            booked=0,
        )
        add_outreach(
            session,
            user_id=second_id,
            activity_date=date(2026, 7, 3),
            total=10,
            companies=5,
        )
        add_outreach(
            session,
            user_id=first_id,
            activity_date=date(2026, 7, 4),
            total=0,
            companies=0,
        )
        session.commit()


def test_dashboard_requires_authentication(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/dashboard")

    response = asyncio.run(scenario())
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_pipeline_conversion_known_rates_and_safe_html(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, first_id, second_id = dashboard_application
    add_pipeline_conversion_records(
        engine,
        first_id=first_id,
        second_id=second_id,
    )

    response = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-02&to=2026-07-02",
    )
    section = pipeline_conversion_section(response)

    assert response.status_code == 200
    assert 'data-total-meetings="5"' in section
    expected = {
        "high_engagement": (2, 40),
        "need_identification": (3, 60),
        "concrete_next_step": (4, 80),
        "proposal": (1, 20),
        "opportunity_identification": (1, 20),
    }
    for metric, (numerator, percentage) in expected.items():
        row = pipeline_rate(response, metric)
        assert f'data-numerator="{numerator}"' in row
        assert 'data-denominator="5"' in row
        assert f'data-percentage="{percentage}"' in row
        assert f"{numerator} of 5" in row
        assert f"{percentage}%" in row
    assert "nan" not in section.lower()
    assert "infinity" not in section.lower()
    assert "performance" not in section.lower()


def test_pipeline_conversion_filters_users_and_duplicate_ids(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, first_id, second_id = dashboard_application
    add_pipeline_conversion_records(
        engine,
        first_id=first_id,
        second_id=second_id,
    )
    base = "/dashboard?period=custom&from=2026-07-02&to=2026-07-02"
    all_users = get_dashboard(application, base)
    first_user = get_dashboard(
        application,
        f"{base}&user_scope=selected&user_id={first_id}",
    )
    multiple = get_dashboard(
        application,
        f"{base}&user_scope=selected&user_id={first_id}&user_id={second_id}",
    )
    duplicate = get_dashboard(
        application,
        f"{base}&user_scope=selected&user_id={first_id}&user_id={first_id}",
    )

    assert 'data-total-meetings="5"' in pipeline_conversion_section(all_users)
    assert 'data-total-meetings="3"' in pipeline_conversion_section(first_user)
    assert 'data-percentage="67"' in pipeline_rate(
        first_user,
        "high_engagement",
    )
    assert 'data-percentage="33"' in pipeline_rate(first_user, "proposal")
    assert 'data-total-meetings="5"' in pipeline_conversion_section(multiple)
    assert 'data-total-meetings="3"' in pipeline_conversion_section(duplicate)


def test_pipeline_conversion_date_filter_excludes_other_dates(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, first_id, second_id = dashboard_application
    add_pipeline_conversion_records(
        engine,
        first_id=first_id,
        second_id=second_id,
    )

    included = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-02&to=2026-07-02",
    )
    next_day = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-03&to=2026-07-03",
    )

    assert 'data-total-meetings="5"' in pipeline_conversion_section(included)
    assert 'data-total-meetings="1"' in pipeline_conversion_section(next_day)
    assert 'data-numerator="1"' in pipeline_rate(
        next_day,
        "opportunity_identification",
    )
    assert 'data-percentage="100"' in pipeline_rate(
        next_day,
        "opportunity_identification",
    )


def test_pipeline_conversion_zero_denominator_is_safe(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    _, engine, _, _ = dashboard_application
    selected, error = resolve_dashboard_filter(
        today=TEST_DATE,
        period=CUSTOM_RANGE,
        from_value="2026-07-04",
        to_value="2026-07-04",
    )
    assert error is None and selected is not None
    with Session(engine) as session:
        summary = get_dashboard_summary(session, selected_period=selected)

    assert summary.pipeline_conversions.total_meetings == 0
    assert len(summary.pipeline_conversions.metrics) == 5
    assert all(
        metric.denominator == 0
        and metric.numerator == 0
        and metric.percentage is None
        and metric.percentage_text == "No data"
        for metric in summary.pipeline_conversions.metrics
    )


def test_pipeline_conversion_empty_period_renders_no_data(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    response = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-04&to=2026-07-04",
    )
    section = pipeline_conversion_section(response)

    assert response.status_code == 200
    assert 'data-total-meetings="0"' in section
    assert section.count('data-pipeline-rate="') == 5
    assert section.count("No data") == 5
    for metric in (
        "high_engagement",
        "need_identification",
        "concrete_next_step",
        "proposal",
        "opportunity_identification",
    ):
        row = pipeline_rate(response, metric)
        assert "0 of 0" in row
        assert "No data" in row
    assert "division" not in section.lower()
    assert "warning" not in section.lower()


def test_outreach_conversion_known_rates_and_distinct_denominators(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, first_id, second_id = dashboard_application
    add_outreach_conversion_records(
        engine,
        first_id=first_id,
        second_id=second_id,
    )

    response = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-02&to=2026-07-02",
    )
    section = outreach_conversion_section(response)

    assert response.status_code == 200
    assert 'data-outreach-record-count="2"' in section
    expected = {
        "reply": (8, 40, 20),
        "positive_reply": (3, 40, 8),
        "meeting_booking": (4, 10, 40),
    }
    for metric, (numerator, denominator, percentage) in expected.items():
        row = outreach_rate(response, metric)
        assert f'data-numerator="{numerator}"' in row
        assert f'data-denominator="{denominator}"' in row
        assert f'data-percentage="{percentage}"' in row
        assert f"{numerator} of {denominator}" in row
        assert f"{percentage}%" in row
    assert "nan" not in section.lower()
    assert "infinity" not in section.lower()
    assert "performance" not in section.lower()
    assert "warning" not in section.lower()


def test_outreach_conversion_filters_users_and_duplicate_ids(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, first_id, second_id = dashboard_application
    add_outreach_conversion_records(
        engine,
        first_id=first_id,
        second_id=second_id,
    )
    base = "/dashboard?period=custom&from=2026-07-02&to=2026-07-02"
    all_users = get_dashboard(application, base)
    first_user = get_dashboard(
        application,
        f"{base}&user_scope=selected&user_id={first_id}",
    )
    multiple = get_dashboard(
        application,
        f"{base}&user_scope=selected&user_id={first_id}&user_id={second_id}",
    )
    duplicate = get_dashboard(
        application,
        f"{base}&user_scope=selected&user_id={first_id}&user_id={first_id}",
    )

    assert 'data-outreach-record-count="2"' in outreach_conversion_section(
        all_users,
    )
    assert 'data-percentage="20"' in outreach_rate(all_users, "reply")
    assert 'data-outreach-record-count="1"' in outreach_conversion_section(
        first_user,
    )
    assert 'data-percentage="50"' in outreach_rate(first_user, "reply")
    assert 'data-percentage="25"' in outreach_rate(
        first_user,
        "meeting_booking",
    )
    assert 'data-outreach-record-count="2"' in outreach_conversion_section(
        multiple,
    )
    assert 'data-outreach-record-count="1"' in outreach_conversion_section(
        duplicate,
    )
    assert 'data-percentage="50"' in outreach_rate(duplicate, "reply")


def test_outreach_conversion_date_filter_and_missing_values(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, first_id, second_id = dashboard_application
    add_outreach_conversion_records(
        engine,
        first_id=first_id,
        second_id=second_id,
    )

    first_day = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-02&to=2026-07-02",
    )
    second_day = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-03&to=2026-07-03",
    )

    assert 'data-numerator="8"' in outreach_rate(first_day, "reply")
    assert 'data-numerator="20"' in outreach_rate(second_day, "reply")
    assert 'data-denominator="30"' in outreach_rate(second_day, "reply")
    assert 'data-percentage="67"' in outreach_rate(second_day, "reply")
    assert 'data-numerator="10"' in outreach_rate(
        second_day,
        "positive_reply",
    )
    assert 'data-percentage="33"' in outreach_rate(
        second_day,
        "positive_reply",
    )
    assert 'data-numerator="0"' in outreach_rate(
        second_day,
        "meeting_booking",
    )
    assert 'data-percentage="0"' in outreach_rate(
        second_day,
        "meeting_booking",
    )


def test_outreach_conversion_zero_denominators_show_no_data(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, first_id, second_id = dashboard_application
    add_outreach_conversion_records(
        engine,
        first_id=first_id,
        second_id=second_id,
    )
    response = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-04&to=2026-07-04",
    )
    section = outreach_conversion_section(response)

    assert response.status_code == 200
    assert 'data-outreach-record-count="1"' in section
    for metric in ("reply", "positive_reply", "meeting_booking"):
        row = outreach_rate(response, metric)
        assert 'data-numerator="0"' in row
        assert 'data-denominator="0"' in row
        assert 'data-percentage="none"' in row
        assert "No data" in row
    assert "nan" not in section.lower()
    assert "infinity" not in section.lower()


def test_outreach_conversion_empty_period_renders_no_data(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    response = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-05&to=2026-07-05",
    )
    section = outreach_conversion_section(response)

    assert response.status_code == 200
    assert 'data-outreach-record-count="0"' in section
    assert section.count('data-outreach-rate="') == 3
    assert section.count("No data") == 3
    for metric in ("reply", "positive_reply", "meeting_booking"):
        row = outreach_rate(response, metric)
        assert "0 of 0" in row
        assert "No data" in row
    assert "warning" not in section.lower()


def test_conversion_sections_share_compact_responsive_mini_metrics(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    response = get_dashboard(application)
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")

    for section in (
        pipeline_conversion_section(response),
        outreach_conversion_section(response),
    ):
        assert "<dl class=\"dashboard-mini-metric-grid " in section
        assert 'class="dashboard-mini-metric"' in section
        assert 'class="dashboard-mini-metric-result"' in section
        assert 'class="dashboard-mini-metric-rate"' in section
        assert "Result: " in section
        assert "Rate: " in section
        assert "<table" not in section
        assert 'role="progressbar"' not in section

    template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    assert "Company metrics" not in template
    assert "Activity &amp; target progress" in template
    assert template.count("dashboard-section-heading") == 8
    assert template.count("dashboard-conversion-card") == 3
    activity_heading = template.index('id="company-metrics-heading"')
    activity_section = template.rfind("<section", 0, activity_heading)
    activity_section_tag = template[
        activity_section:template.index(">", activity_section)
    ]
    assert "dashboard-analysis-card dashboard-conversion-card" in (
        activity_section_tag
    )
    assert "dashboard-conversion-grid" not in template
    assert "dashboard-mini-metric-grid-pipeline" in template
    assert "dashboard-mini-metric-grid-outreach" in template
    assert "dashboard-conversion-table-wrap" not in template
    assert "dashboard-conversion-table" not in template
    assert "dashboard-conversion-column-" not in template
    assert ".dashboard-conversion-grid" not in css
    assert ".dashboard-mini-metric-grid" in css
    assert ".dashboard-mini-metric" in css
    assert ".dashboard-conversion-table-wrap" not in css
    assert ".dashboard-conversion-table" not in css
    assert ".dashboard-conversion-column-" not in css
    shared_heading_css = css.split(
        ".dashboard-section-heading {",
        1,
    )[1].split("}", 1)[0]
    assert "font-size: 1.15rem" in shared_heading_css
    assert "font-weight: 700" in shared_heading_css
    assert "line-height: 1.3" in shared_heading_css
    assert "margin: 0" in shared_heading_css
    tablet_css = css.split("@media (min-width: 48rem)", 1)[1].split(
        "@media (min-width: 64rem)",
        1,
    )[0]
    assert ".dashboard-mini-metric-grid" in tablet_css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in tablet_css
    assert "grid-column: 1 / -1" in tablet_css
    desktop_css = css.split("@media (min-width: 64rem)", 1)[1]
    assert ".dashboard-mini-metric-grid-pipeline" in desktop_css
    assert "grid-template-columns: repeat(5, minmax(0, 1fr))" in desktop_css
    assert ".dashboard-mini-metric-grid-outreach" in desktop_css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in desktop_css


def test_current_week_aggregates_all_users_without_private_details(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    response = get_dashboard(application)
    assert response.status_code == 200
    assert "13 Jul – 19 Jul 2026" in response.text
    expected = {
        "total_activities": 30,
        "companies_contacted": 8,
        "replies": 4,
        "positive_replies": 2,
        "meetings_booked": 1,
        "meetings_held": 3,
    }
    for metric, actual in expected.items():
        assert f'data-metric="{metric}"' in response.text
        assert f'data-actual="{actual}"' in response.text
    for private_value in (
        "Do not expose company",
        ACTIVE_EMAIL,
        "foreign-dashboard@example.com",
    ):
        assert private_value not in response.text


@pytest.mark.parametrize("grouping", ("employee", "date", "source"))
def test_comment_grouping_preserves_records_and_marks_active_control(
    dashboard_application: tuple[FastAPI, Engine, int, int],
    grouping: str,
) -> None:
    application, _, _, _ = dashboard_application
    response = get_dashboard(application, f"/dashboard?comment_group={grouping}")

    assert response.status_code == 200
    assert response.text.count("Private outreach note") == 1
    assert response.text.count("Foreign private note") == 1
    assert response.text.count("Do not expose meeting note") == 3
    active_link = re.search(
        rf'<a[^>]+class="dashboard-group-button is-active"[^>]*'
        rf'href="[^"]*comment_group={grouping}'
        rf'#comments-overview"[^>]*aria-current="true"',
        response.text,
    )
    assert active_link is not None

    outreach_row_start = response.text.index(
        'data-comment-source="daily-outreach"',
    )
    outreach_row_end = response.text.index("</tr>", outreach_row_start)
    assert ">—</td>" in response.text[outreach_row_start:outreach_row_end]


def test_current_week_company_targets_are_summed_and_progress_is_safe(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    response = get_dashboard(application)
    assert 'data-metric="total_activities"' in response.text
    assert 'data-target="4"' in response.text
    assert 'data-remaining="0"' in response.text
    assert 'data-percentage="750"' in response.text
    assert 'data-bar-percentage="100"' in response.text
    assert "Goal exceeded by 26" in response.text
    assert 'data-metric="companies_contacted"' in response.text
    assert 'data-target="0"' in response.text
    assert "No target" in response.text
    assert TARGET_CALCULATION_NOTICE in response.text


def test_selected_user_filters_actuals_meetings_and_target(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, first_id, _ = dashboard_application
    response = get_dashboard(
        application,
        f"/dashboard?user_scope=selected&user_id={first_id}",
    )

    assert response.status_code == 200
    assert 'data-actual="10"' in metric_card(response, "total_activities")
    assert 'data-target="2"' in metric_card(response, "total_activities")
    assert 'data-actual="1"' in metric_card(response, "meetings_held")
    assert "2026-07-13 — Outreach activities: 10; Meetings held: 1" in response.text
    assert "2026-07-14 — Outreach activities: 0; Meetings held: 0" in response.text
    assert 'data-country="BR"' in response.text
    assert 'data-country="DE"' in response.text
    assert 'data-country="AT"' not in response.text
    assert 'data-blocker="No response"' in response.text
    assert 'data-mood="good"' in response.text
    assert 'data-mood="difficult"' not in response.text


def test_multiple_and_duplicate_user_ids_use_each_user_once(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, first_id, second_id = dashboard_application
    multiple = get_dashboard(
        application,
        "/dashboard?user_scope=selected"
        f"&user_id={first_id}&user_id={second_id}",
    )
    duplicate = get_dashboard(
        application,
        "/dashboard?user_scope=selected"
        f"&user_id={first_id}&user_id={first_id}",
    )

    assert 'data-actual="30"' in metric_card(multiple, "total_activities")
    assert 'data-target="4"' in metric_card(multiple, "total_activities")
    assert 'data-actual="10"' in metric_card(duplicate, "total_activities")
    assert 'data-target="2"' in metric_card(duplicate, "total_activities")


def test_period_and_selected_users_filter_together_with_prorated_targets(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, first_id, second_id = dashboard_application
    previous = get_dashboard(
        application,
        "/dashboard?period=previous-week&user_scope=selected"
        f"&user_id={first_id}",
    )
    month = get_dashboard(
        application,
        "/dashboard?period=current-month&user_scope=selected"
        f"&user_id={second_id}",
    )
    custom = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-14&to=2026-07-14"
        f"&user_scope=selected&user_id={second_id}",
    )

    assert 'data-actual="7"' in metric_card(previous, "total_activities")
    assert 'data-target="7"' in metric_card(previous, "total_activities")
    assert 'data-actual="29"' in metric_card(month, "total_activities")
    assert 'data-target="11"' in metric_card(month, "total_activities")
    assert 'data-actual="20"' in metric_card(custom, "total_activities")
    assert 'data-target="0.3"' in metric_card(custom, "total_activities")
    for response in (previous, month, custom):
        assert response.status_code == 200
        assert TARGET_CALCULATION_NOTICE in response.text
        assert "Select at least one user to view data." not in response.text
        assert response.text.count('role="progressbar"') == 6


def test_unknown_and_malformed_user_ids_are_safe(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, second_id = dashboard_application
    with_valid_user = get_dashboard(
        application,
        "/dashboard?user_scope=selected&user_id=invalid&user_id=999999"
        f"&user_id={second_id}",
    )
    no_valid_user = get_dashboard(
        application,
        "/dashboard?user_scope=selected&user_id=invalid&user_id=999999",
    )

    assert with_valid_user.status_code == 200
    assert 'data-actual="20"' in metric_card(
        with_valid_user,
        "total_activities",
    )
    assert_empty_selected_dashboard(no_valid_user)


def test_empty_selected_scope_is_applied_and_user_can_be_selected_afterward(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, first_id, _ = dashboard_application
    empty = get_dashboard(application, "/dashboard?user_scope=selected")
    selected = get_dashboard(
        application,
        f"/dashboard?user_scope=selected&user_id={first_id}",
    )

    assert_empty_selected_dashboard(empty)
    assert "Select at least one user to view data." not in selected.text
    assert 'data-actual="10"' in metric_card(selected, "total_activities")
    assert 'data-target="2"' in metric_card(selected, "total_activities")
    assert 'data-country="AT"' not in selected.text
    assert 'data-mood="difficult"' not in selected.text


def test_selected_checkboxes_persist_and_reset_restores_all_users(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, first_id, second_id = dashboard_application
    selected = get_dashboard(
        application,
        f"/dashboard?user_scope=selected&user_id={second_id}",
    )
    reset = get_dashboard(
        application,
        "/dashboard?period=previous-week&user_scope=selected"
        f"&user_id={first_id}&reset=true",
    )

    selected_tag = re.search(
        rf'<input[^>]+id="dashboard-user-{second_id}"[^>]*>',
        selected.text,
    )
    unselected_tag = re.search(
        rf'<input[^>]+id="dashboard-user-{first_id}"[^>]*>',
        selected.text,
    )
    assert selected_tag is not None and "checked" in selected_tag.group()
    assert unselected_tag is not None and "checked" not in unselected_tag.group()
    assert 'data-initial-user-scope="selected"' in selected.text

    assert reset.status_code == 200
    assert 'data-initial-period="current-week"' in reset.text
    assert 'data-initial-user-scope="all"' in reset.text
    assert 'id="dashboard-users-all"' in reset.text
    assert "13 Jul – 19 Jul 2026" in reset.text


def test_user_filter_lists_only_names_sorted_case_insensitively(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    response = get_dashboard(application)

    assert response.text.index("Dashboard User</label>") < response.text.index(
        "Foreign Employee Name</label>",
    )
    assert ACTIVE_EMAIL not in response.text
    assert "foreign-dashboard@example.com" not in response.text
    assert "@username" not in response.text
    assert "(user #" not in response.text


def test_user_filter_is_an_accessible_overlay_dropdown(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, second_id = dashboard_application
    all_users = get_dashboard(application)
    one_user = get_dashboard(
        application,
        f"/dashboard?user_scope=selected&user_id={second_id}",
    )
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")
    script = Path("app/static/js/dashboard_filter.js").read_text(encoding="utf-8")

    assert 'class="dashboard-users-trigger"' in all_users.text
    assert 'aria-expanded="false"' in all_users.text
    assert 'aria-controls="dashboard-users-panel"' in all_users.text
    assert 'id="dashboard-users-panel"' in all_users.text
    assert re.search(r"data-users-panel\s+hidden", all_users.text)
    assert 'data-users-summary>All users</span>' in all_users.text
    assert (
        'data-users-summary>Foreign Employee Name</span>'
        in one_user.text
    )
    panel_css = css.split(".dashboard-users-panel {", 1)[1].split("}", 1)[0]
    assert "position: absolute" in panel_css
    assert "width: 100%" in panel_css
    assert "max-width: 100%" in panel_css
    assert "z-index: 20" in panel_css
    options_css = css.split(".dashboard-user-options {", 1)[1].split("}", 1)[0]
    assert "max-height:" in options_css
    assert "overflow-y: auto" in options_css
    assert 'event.key === "Escape"' in script
    assert 'event.key === "ArrowDown"' in script
    assert "usersDropdown.contains(event.target)" in script
    assert 'setAttribute("aria-expanded", String(open))' in script
    assert "checkbox.checked = allUsers.checked" in script
    assert "applyUsersFilter()" in script
    assert 'window.sessionStorage.setItem(usersOpenStorageKey, "true")' in script
    assert 'usersSummary.textContent = "Select users"' in script
    assert "data-user-validation" not in all_users.text
    assert "Select at least one user." not in all_users.text


def test_user_filter_navigation_preserves_applied_period_query_parameters(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, first_id, second_id = dashboard_application
    script = Path("app/static/js/dashboard_filter.js").read_text(encoding="utf-8")
    custom_urls = (
        f"&user_id={first_id}",
        f"&user_id={first_id}&user_id={second_id}",
        "",
    )
    for user_ids in custom_urls:
        response = get_dashboard(
            application,
            "/dashboard?period=custom&from=2026-07-13&to=2026-07-14"
            f"&user_scope=selected{user_ids}",
        )
        assert response.status_code == 200
        assert 'data-initial-period="custom"' in response.text
        assert 'data-initial-from="2026-07-13"' in response.text
        assert 'data-initial-to="2026-07-14"' in response.text

    for period in ("previous-week", "current-month"):
        response = get_dashboard(
            application,
            f"/dashboard?period={period}&user_scope=selected&user_id={first_id}",
        )
        assert response.status_code == 200
        assert f'data-initial-period="{period}"' in response.text
        assert 'data-initial-user-scope="selected"' in response.text

    url_helper = script.split("const currentUrlAndParams", 1)[1].split(
        "const navigateWithParams",
        1,
    )[0]
    assert "new URL(form.action, window.location.origin)" in url_helper
    assert "new URLSearchParams(window.location.search)" in url_helper
    assert "window.location.href" not in url_helper

    fragment_cleanup = script.split(
        "const removeCommentsFragmentAfterNativeScroll",
        1,
    )[1].split(
        'document.querySelectorAll("[data-dashboard-filter]")',
        1,
    )[0]
    assert fragment_cleanup.count(
        'window.location.hash === "#comments-overview"',
    ) == 2
    assert "window.requestAnimationFrame" in fragment_cleanup
    assert 'document.addEventListener(\n    "DOMContentLoaded"' in fragment_cleanup
    assert "window.history.replaceState(" in fragment_cleanup
    assert "window.location.pathname + window.location.search" in fragment_cleanup
    assert "scrollTo" not in fragment_cleanup
    assert script.count('"#comments-overview"') == 2

    navigation_logic = script.split("const navigateWithParams", 1)[1].split(
        "const replaceUserParams",
        1,
    )[0]
    assert 'url.hash = ""' in navigation_logic
    assert navigation_logic.index('url.hash = ""') < navigation_logic.index(
        "window.location.assign",
    )

    users_logic = script.split("const replaceUserParams", 1)[1].split(
        "const update =",
        1,
    )[0]
    assert 'params.delete("user_scope")' in users_logic
    assert 'params.delete("user_id")' in users_logic
    assert 'params.set("user_scope", scope)' in users_logic
    assert 'params.append("user_id", checkbox.value)' in users_logic
    assert 'params.delete("period")' not in users_logic
    assert 'params.delete("from")' not in users_logic
    assert 'params.delete("to")' not in users_logic

    users_apply = script.split("const applyUsersFilter", 1)[1].split(
        "const applyPresetPeriod",
        1,
    )[0]
    assert "currentUrlAndParams()" in users_apply
    assert "replaceUserParams(params)" in users_apply
    assert "period.value" not in users_apply
    assert "fromInput.value" not in users_apply
    assert "toInput.value" not in users_apply

    period_apply = script.split("const applyPresetPeriod", 1)[1].split(
        "const applyCustomRange",
        1,
    )[0]
    assert 'params.set("period", period.value)' in period_apply
    assert 'params.delete("user_scope")' not in period_apply
    assert 'params.delete("user_id")' not in period_apply

    custom_apply = script.split("const applyCustomRange", 1)[1].split(
        "allUsers.addEventListener",
        1,
    )[0]
    assert 'params.set("period", "custom")' in custom_apply
    assert 'params.set("from", fromInput.value)' in custom_apply
    assert 'params.set("to", toInput.value)' in custom_apply
    assert "replaceUserParams(params)" in custom_apply

    template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    filter_form = template.split("data-dashboard-filter", 1)[0].rsplit(
        "<form",
        1,
    )[1]
    assert 'method="get"' in filter_form
    assert 'action="{{ url_for(\'dashboard_page\') }}"' in filter_form
    assert "#comments-overview" not in filter_form
    reset_link = template.split("dashboard-reset-filters", 1)[1].split(
        "</a>",
        1,
    )[0]
    assert "period=current-week" in reset_link
    assert "user_scope=all" in reset_link
    assert "from=" not in reset_link
    assert "to=" not in reset_link
    assert "#comments-overview" not in reset_link
    reset_logic = script.split('resetFilters.addEventListener("click"', 1)[
        1
    ].split('form.addEventListener("submit"', 1)[0]
    assert 'resetUrl.hash = ""' in reset_logic
    assert "resetFilters.href = resetUrl.toString()" in reset_logic
    submit_logic = script.split('form.addEventListener("submit"', 1)[1].split(
        "  update();\n  try",
        1,
    )[0]
    assert 'actionUrl.hash = ""' in submit_logic
    assert "form.action = actionUrl.toString()" in submit_logic

    response = get_dashboard(
        application,
        f"/dashboard?period=custom&from=2026-07-13&to=2026-07-14"
        f"&user_scope=selected&user_id={first_id}&comment_group=date",
    )
    filter_action = re.search(
        r'<form(?=[^>]+data-dashboard-filter)[^>]+action="([^"]+)"',
        response.text,
    )
    assert filter_action is not None
    assert filter_action.group(1).endswith("/dashboard")
    assert "#" not in filter_action.group(1)
    reset_href = re.search(
        r'<a[^>]+class="dashboard-reset-filters"[^>]+href="([^"]+)"',
        response.text,
    )
    assert reset_href is not None
    assert "#" not in reset_href.group(1)
    for grouping in ("employee", "date", "source"):
        assert re.search(
            rf'href="[^"]*period=custom[^"]*user_scope=selected'
            rf'[^"]*from=2026-07-13[^"]*to=2026-07-14'
            rf'[^"]*user_id={first_id}[^"]*comment_group={grouping}'
            r'#comments-overview"',
            response.text,
        )


def test_activity_country_blocker_and_mood_aggregates_use_required_sources(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    response = get_dashboard(application)
    assert 'data-start="2026-07-13"' in response.text
    assert "Outreach activities" in response.text
    assert "Meetings held" in response.text
    assert "Outreach activities: 10; Meetings held: 1" in response.text
    assert 'aria-label="Chart legend"' in response.text
    assert 'class="visually-hidden"' in response.text
    assert 'class="dashboard-chart-value">10</span>' in response.text
    assert 'class="dashboard-chart-value">1</span>' in response.text
    assert 'data-country="BR"' in response.text
    assert "Brazil" in response.text
    assert 'data-blocker="No response"' in response.text
    assert 'data-blocker="Meeting-only blocker"' not in response.text
    assert 'data-mood="difficult"' in response.text
    assert 'data-mood="okay"' not in response.text
    assert 'data-mood="good"' in response.text
    assert "Mood distribution" in response.text
    assert "Blockers" in response.text


def test_analysis_grid_preserves_values_empty_states_and_responsive_markup(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    response = get_dashboard(application)
    template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")

    section_positions = [
        template.index('id="company-metrics-heading"'),
        template.index('id="daily-activity-heading"'),
        template.index('id="pipeline-conversion-heading"'),
        template.index('id="outreach-conversion-heading"'),
        template.index('id="mood-summary-heading"'),
        template.index('class="dashboard-analysis-grid"'),
        template.index('id="comments-overview-heading"'),
    ]
    assert section_positions == sorted(section_positions)
    for heading in (
        "daily-activity-heading",
        "comments-overview-heading",
    ):
        heading_tag = template.split(f'id="{heading}"', 1)[1].split(">", 1)[0]
        assert "dashboard-section-heading" in heading_tag
    for heading in ("Countries", "Blockers", "Mood summary"):
        heading_tag = template.split(f">{heading}</h2>", 1)[0].rsplit("<h2", 1)[1]
        assert "dashboard-section-heading" in heading_tag

    assert 'class="dashboard-analysis-grid"' in response.text
    assert response.text.count("dashboard-analysis-section") == 2
    assert '>Countries</h2>' in response.text
    assert '>Blockers</h2>' in response.text
    assert '>Mood summary</h2>' in response.text
    assert '>Mood distribution</h3>' in response.text
    assert '>Daily mood trend</h3>' in response.text
    assert "Country" in response.text
    assert "Companies" in response.text
    countries_section = response.text.split(">Countries</h2>", 1)[1].split(
        "</article>",
        1,
    )[0]
    assert "Replies" not in countries_section
    assert "Positive" not in countries_section
    assert "<table" not in countries_section
    assert re.search(
        r'data-country="BR"[\s\S]*?<span>Brazil</span>'
        r'[\s\S]*?width: 100%[\s\S]*?<strong>5</strong>',
        response.text,
    )
    assert re.search(
        r'data-blocker="No response"[\s\S]*?<strong>2</strong>',
        response.text,
    )
    blockers_section = response.text.split(">Blockers</h2>", 1)[1].split(
        "</article>",
        1,
    )[0]
    rendered_blockers = re.findall(r'data-blocker="([^"]+)"', blockers_section)
    assert rendered_blockers == ["No response"]
    assert 'data-blocker-count="0"' not in blockers_section
    assert 'data-blocker-count="2"' in blockers_section
    assert "No blocker" not in blockers_section
    assert "dashboard-bar" not in blockers_section
    assert blockers_section.count("dashboard-blocker-item") == 1

    assert response.text.count('class="dashboard-mood-donut') == 1
    assert 'aria-label="Mood distribution: 2 recorded mood entries"' in response.text
    assert "--mood-difficult-percentage: 50" in response.text
    assert "--mood-okay-percentage: 0" in response.text
    assert ">recorded</span>" in response.text
    assert response.text.count("data-mood-legend=") == 3
    for mood, count, percentage in (
        ("difficult", 1, 50),
        ("okay", 0, 0),
        ("good", 1, 50),
    ):
        legend_item = response.text.split(
            f'data-mood-legend="{mood}"',
            1,
        )[1].split("</div>", 1)[0]
        assert f"<strong>{count} <small>{percentage}%</small></strong>" in (
            legend_item
        )


def test_blockers_render_only_positive_counts_descending_with_stable_ties(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, first_user_id, second_user_id = dashboard_application
    with Session(engine) as session:
        for user_id, activity_date, blocker in (
            (first_user_id, date(2026, 7, 15), "Competitor"),
            (second_user_id, date(2026, 7, 15), "Competitor"),
            (first_user_id, date(2026, 7, 16), "Technical limitation"),
            (second_user_id, date(2026, 7, 16), "Other"),
        ):
            add_outreach(
                session,
                user_id=user_id,
                activity_date=activity_date,
                total=1,
                companies=1,
                blocker=blocker,
            )
        session.commit()

    response = get_dashboard(application)
    blockers_section = response.text.split(">Blockers</h2>", 1)[1].split(
        "</article>",
        1,
    )[0]
    rendered_blockers = re.findall(r'data-blocker="([^"]+)"', blockers_section)
    assert rendered_blockers == [
        "Competitor",
        "No response",
        "Technical limitation",
        "Other",
    ]
    assert re.findall(r'data-blocker-count="(\d+)"', blockers_section) == [
        "2",
        "2",
        "1",
        "1",
    ]
    assert "No blocker" not in blockers_section

    empty = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-05-01&to=2026-05-02",
    )
    assert "No country activity for this period." in empty.text
    assert "No Daily Outreach blockers for this period." in empty.text
    assert empty.text.count("No recorded mood for this period.") == 1
    assert 'class="dashboard-mood-donut' not in empty.text
    assert "data-mood-legend=" not in empty.text
    empty_blockers = empty.text.split(">Blockers</h2>", 1)[1].split(
        "</article>",
        1,
    )[0]
    assert 'data-blocker-count="0"' not in empty_blockers

    css = Path("app/static/css/app.css").read_text(encoding="utf-8")
    mobile_css = css.split("@media (max-width: 47.999rem)", 1)[1].split(
        "@media (hover: hover)",
        1,
    )[0]
    assert ".dashboard-analysis-grid" in mobile_css
    assert "grid-template-columns: minmax(0, 1fr)" in mobile_css
    analysis_css = css.split(
        ".dashboard-analysis-grid {\n  margin-top:",
        1,
    )[1].split(
        "}",
        1,
    )[0]
    assert "grid-template-columns: minmax(0, 1fr)" in analysis_css
    assert "align-items: stretch" in analysis_css
    tablet_css = css.split("@media (min-width: 48rem)", 1)[1].split(
        "@media (min-width: 64rem)",
        1,
    )[0]
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in tablet_css
    desktop_css = css.split("@media (min-width: 64rem)", 1)[1]
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in desktop_css
    assert "align-items: start" in desktop_css
    desktop_card_css = desktop_css.split(
        ".dashboard-analysis-grid .dashboard-analysis-card {", 1,
    )[1].split("}", 1)[0]
    assert "min-height:" not in desktop_card_css
    assert "align-self: stretch" in desktop_card_css
    assert "min-height: 26rem" not in desktop_css
    assert ".dashboard-mood-summary-layout" in tablet_css
    assert ".dashboard-mood-summary-layout" in desktop_css
    assert "--mood-difficult-color: #71809a" in css
    assert "--mood-good-color: #78a967" in css
    assert "var(--mood-difficult-color)" in css
    assert "var(--mood-good-color)" in css
    mood_note_css = css.split(".dashboard-mood-note {", 1)[1].split("}", 1)[0]
    assert "border-top: 1px solid var(--border)" in mood_note_css
    mood_content_css = css.split(".dashboard-mood-content {", 1)[1].split(
        "}",
        1,
    )[0]
    assert "grid-template-columns: auto minmax(7.5rem, 1fr)" in mood_content_css
    ranked_item_css = css.split(".dashboard-ranked-item {", 1)[1].split(
        "}",
        1,
    )[0]
    assert "border-bottom: 1px solid var(--border)" in ranked_item_css
    assert "grid-template-columns:" in ranked_item_css
    assert response.text.count('data-country="BR"') == 1
    assert response.text.count('data-blocker="No response"') == 1
    assert response.text.count("data-mood-legend=") == 3


def test_aggregate_breakdown_values_and_separate_daily_series(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Daily series and outreach-only breakdowns retain their exact counts."""
    _, engine, _, _ = dashboard_application
    selected, error = resolve_dashboard_filter(
        today=TEST_DATE,
        period=CURRENT_WEEK,
    )
    assert error is None and selected is not None
    with Session(engine) as session:
        summary = get_dashboard_summary(session, selected_period=selected)

    daily = {
        bucket.start_date: (bucket.outreach_activities, bucket.meetings_held)
        for bucket in summary.activity_buckets
    }
    assert set(daily) == {
        date(2026, 7, day)
        for day in range(13, 20)
    }
    assert daily[date(2026, 7, 13)] == (10, 1)
    assert daily[date(2026, 7, 14)] == (20, 2)
    assert daily[date(2026, 7, 19)] == (0, 0)
    assert {item.key: item.value for item in summary.countries} == {
        "AT": 2,
        "BR": 5,
        "DE": 1,
    }
    assert {item.key: item.value for item in summary.blockers} == {
        "No response": 2,
    }
    assert {item.label: item.value for item in summary.moods} == {
        "Difficult": 1,
        "Good": 1,
    }


def test_activity_chart_groups_long_periods_by_calendar_week(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Weeks stay daily while month and long custom ranges use week buckets."""
    _, engine, _, _ = dashboard_application
    with Session(engine) as session:
        current_week, error = resolve_dashboard_filter(
            today=TEST_DATE,
            period=CURRENT_WEEK,
        )
        assert error is None and current_week is not None
        week_summary = get_dashboard_summary(session, selected_period=current_week)
        assert len(week_summary.activity_buckets) == 7
        assert all(
            bucket.start_date == bucket.end_date
            for bucket in week_summary.activity_buckets
        )

        previous_week, error = resolve_dashboard_filter(
            today=TEST_DATE,
            period=PREVIOUS_WEEK,
        )
        assert error is None and previous_week is not None
        previous_summary = get_dashboard_summary(
            session,
            selected_period=previous_week,
        )
        assert len(previous_summary.activity_buckets) == 7
        assert all(
            bucket.start_date == bucket.end_date
            for bucket in previous_summary.activity_buckets
        )

        current_month, error = resolve_dashboard_filter(
            today=TEST_DATE,
            period=CURRENT_MONTH,
        )
        assert error is None and current_month is not None
        month_summary = get_dashboard_summary(session, selected_period=current_month)
        month_values = [
            (
                bucket.start_date,
                bucket.end_date,
                bucket.outreach_activities,
                bucket.meetings_held,
            )
            for bucket in month_summary.activity_buckets
        ]
        assert month_values == [
            (date(2026, 7, 1), date(2026, 7, 5), 3, 0),
            (date(2026, 7, 6), date(2026, 7, 12), 16, 1),
            (date(2026, 7, 13), date(2026, 7, 19), 30, 3),
            (date(2026, 7, 20), date(2026, 7, 26), 0, 0),
            (date(2026, 7, 27), date(2026, 7, 31), 0, 0),
        ]

        short_custom, error = resolve_dashboard_filter(
            today=TEST_DATE,
            period=CUSTOM_RANGE,
            from_value="2026-07-01",
            to_value="2026-07-14",
        )
        assert error is None and short_custom is not None
        short_summary = get_dashboard_summary(session, selected_period=short_custom)
        assert len(short_summary.activity_buckets) == 14

        long_custom, error = resolve_dashboard_filter(
            today=TEST_DATE,
            period=CUSTOM_RANGE,
            from_value="2026-07-01",
            to_value="2026-07-15",
        )
        assert error is None and long_custom is not None
        long_summary = get_dashboard_summary(session, selected_period=long_custom)
        assert len(long_summary.activity_buckets) == 3


def test_activity_heading_uses_backend_bucket_granularity(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """The section title follows aggregation metadata, not the period preset."""
    _, engine, _, _ = dashboard_application
    with Session(engine) as session:
        current_week, error = resolve_dashboard_filter(
            today=TEST_DATE,
            period=CURRENT_WEEK,
        )
        assert error is None and current_week is not None
        daily_summary = get_dashboard_summary(session, selected_period=current_week)
        assert daily_summary.activity_granularity == "day"
        assert daily_summary.activity_heading == "Activity by day"

        current_month, error = resolve_dashboard_filter(
            today=TEST_DATE,
            period=CURRENT_MONTH,
        )
        assert error is None and current_month is not None
        weekly_summary = get_dashboard_summary(session, selected_period=current_month)
        assert weekly_summary.activity_granularity == "week"
        assert weekly_summary.activity_heading == "Activity by week"

    assert ACTIVITY_HEADINGS[ACTIVITY_GRANULARITY_MONTH] == "Activity by month"
    assert (
        ACTIVITY_HEADINGS[ACTIVITY_GRANULARITY_PERIOD]
        == "Activity for selected period"
    )
    assert _activity_bucket_granularity(current_month) == "week"


def test_activity_heading_is_rendered_from_summary_metadata(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    response = get_dashboard(application, f"/dashboard?period={CURRENT_MONTH}")

    assert response.status_code == 200
    assert "Activity by week" in response.text
    assert "Activity by day</h2>" not in response.text
    template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    assert "{{ summary.activity_heading }}" in template


def test_activity_chart_long_range_uses_compact_week_labels_and_sparse_axis() -> None:
    selected, error = resolve_dashboard_filter(
        today=TEST_DATE,
        period=CUSTOM_RANGE,
        from_value="2025-08-04",
        to_value="2025-11-30",
    )
    assert error is None and selected is not None

    buckets = _activity_buckets(selected, [], [])
    assert len(buckets) > 7
    assert buckets[0].label == "Aug 4–10"
    assert any(bucket.label == "Sep 29–Oct 5" for bucket in buckets)
    assert buckets[-1].label == "Nov 24–30"
    stride = max(1, ceil(len(buckets) / 7))
    visible_indexes = [
        index
        for index in range(len(buckets))
        if index % stride == 0 or index == len(buckets) - 1
    ]
    assert visible_indexes[0] == 0
    assert visible_indexes[-1] == len(buckets) - 1
    assert len(visible_indexes) < len(buckets)

    template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")
    script = Path("app/static/js/dashboard_filter.js").read_text(encoding="utf-8")
    assert 'data-label-stride="{{ summary.activity_label_stride }}"' in template
    assert "dashboard-chart-label{% if loop.index0" in template
    assert "--chart-label-stride" in script
    label_css = css.split(".dashboard-chart-label {", 1)[1].split("}", 1)[0]
    assert "overflow-wrap: normal" in label_css
    assert "word-break: normal" in label_css
    assert "hyphens: none" in label_css
    assert ".dashboard-chart-label.is-visible" in css
    assert "-webkit-line-clamp: 2" in css
    assert "overflow-x: auto" not in css.split(".dashboard-grouped-chart {", 1)[1].split(
        ".dashboard-chart-group", 1
    )[0]


@pytest.mark.parametrize(
    ("period", "expected_start", "expected_end"),
    (
        (CURRENT_WEEK, date(2026, 7, 13), date(2026, 7, 19)),
        (PREVIOUS_WEEK, date(2026, 7, 6), date(2026, 7, 12)),
        (CURRENT_MONTH, date(2026, 7, 1), date(2026, 7, 31)),
    ),
)
def test_dashboard_preset_boundaries(
    period: str,
    expected_start: date,
    expected_end: date,
) -> None:
    selected, error = resolve_dashboard_filter(today=TEST_DATE, period=period)
    assert error is None
    assert selected is not None
    assert (selected.start_date, selected.end_date) == (expected_start, expected_end)


def test_previous_week_and_month_use_saved_and_prorated_targets(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    previous = get_dashboard(application, "/dashboard?period=previous-week")
    assert 'data-metric="total_activities"' in previous.text
    assert 'data-actual="16"' in previous.text
    assert 'data-actual="19"' not in previous.text
    assert 'data-target="16"' in metric_card(previous, "total_activities")
    assert 'data-percentage="100"' in metric_card(previous, "total_activities")
    assert TARGET_CALCULATION_NOTICE in previous.text
    assert previous.text.count('role="progressbar"') == 6

    month = get_dashboard(application, "/dashboard?period=current-month")
    assert 'data-metric="total_activities"' in month.text
    assert 'data-actual="49"' in month.text
    assert 'data-actual="148"' not in month.text
    assert 'data-target="20"' in metric_card(month, "total_activities")
    assert 'data-percentage="245"' in metric_card(month, "total_activities")
    assert "Goal exceeded by 29" in metric_card(month, "total_activities")


def test_custom_targets_prorate_one_and_multiple_overlapping_weeks(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    one_day = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-13&to=2026-07-13",
    )
    two_weeks = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-12&to=2026-07-13",
    )

    one_day_card = metric_card(one_day, "total_activities")
    assert 'data-target="0.6"' in one_day_card
    assert 'data-percentage="1750"' in one_day_card
    assert "Goal exceeded by 9.4" in one_day_card

    two_week_card = metric_card(two_weeks, "total_activities")
    assert 'data-target="2.9"' in two_week_card
    assert 'data-percentage="665"' in two_week_card
    assert "Goal exceeded by 16.1" in two_week_card


def test_month_prorates_partial_first_and_last_weeks(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, first_id, _ = dashboard_application
    with Session(engine) as session:
        session.add(
            Target(
                user_id=first_id,
                metric_name="total_activities",
                target_value=14,
                week_start=date(2026, 6, 29),
                effective_from=date(2026, 6, 29),
                effective_until=date(2026, 7, 5),
            ),
        )
        session.add(
            Target(
                user_id=first_id,
                metric_name="total_activities",
                target_value=21,
                week_start=date(2026, 7, 27),
                effective_from=date(2026, 7, 27),
                effective_until=date(2026, 8, 2),
            ),
        )
        session.commit()

    response = get_dashboard(
        application,
        f"/dashboard?period=current-month&user_scope=selected&user_id={first_id}",
    )
    card = metric_card(response, "total_activities")
    # 14 * 5/7 + 7 + 2 + 21 * 5/7 = 34.
    assert 'data-target="34"' in card
    assert 'data-actual="20"' in card
    assert 'data-remaining="14"' in card
    assert 'data-percentage="59"' in card
    assert "14 remaining" in card


def test_proration_crosses_month_and_iso_year_boundaries(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, first_id, _ = dashboard_application
    with Session(engine) as session:
        for week_start in (date(2025, 12, 29), date(2026, 6, 29)):
            session.add(
                Target(
                    user_id=first_id,
                    metric_name="total_activities",
                    target_value=14,
                    week_start=week_start,
                    effective_from=week_start,
                    effective_until=week_start + timedelta(days=6),
                ),
            )
        session.commit()

    iso_year = get_dashboard(
        application,
        "/dashboard?period=custom&from=2025-12-31&to=2026-01-02"
        f"&user_scope=selected&user_id={first_id}",
    )
    month_boundary = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-06-30&to=2026-07-01"
        f"&user_scope=selected&user_id={first_id}",
    )
    assert 'data-target="6"' in metric_card(iso_year, "total_activities")
    assert 'data-target="4"' in metric_card(month_boundary, "total_activities")
    assert 'data-actual="102"' in metric_card(
        month_boundary,
        "total_activities",
    )


def test_user_without_target_does_not_inherit_another_users_target(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, first_id, _ = dashboard_application
    with Session(engine) as session:
        no_target_user = User(
            name="No Target User",
            email="no-target@example.com",
            password_hash=hash_password(TEST_PASSWORD),
        )
        session.add(no_target_user)
        session.flush()
        assert no_target_user.id is not None
        no_target_id = no_target_user.id
        add_outreach(
            session,
            user_id=no_target_id,
            activity_date=date(2026, 7, 15),
            total=11,
            companies=1,
        )
        session.commit()

    only_no_target = get_dashboard(
        application,
        f"/dashboard?user_scope=selected&user_id={no_target_id}",
    )
    with_target = get_dashboard(
        application,
        "/dashboard?user_scope=selected"
        f"&user_id={first_id}&user_id={no_target_id}",
    )
    all_users = get_dashboard(application)

    assert 'data-target="0"' in metric_card(only_no_target, "total_activities")
    assert 'data-actual="11"' in metric_card(only_no_target, "total_activities")
    assert "No target" in metric_card(only_no_target, "total_activities")
    assert 'data-target="2"' in metric_card(with_target, "total_activities")
    assert 'data-actual="21"' in metric_card(with_target, "total_activities")
    assert 'data-target="4"' in metric_card(all_users, "total_activities")
    assert 'data-actual="41"' in metric_card(all_users, "total_activities")


def test_prorated_remaining_and_zero_target_progress_states(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, first_id, _ = dashboard_application
    with Session(engine) as session:
        session.add(
            Target(
                user_id=first_id,
                metric_name="total_activities",
                target_value=14,
                week_start=date(2026, 6, 29),
                effective_from=date(2026, 6, 29),
                effective_until=date(2026, 7, 5),
            ),
        )
        session.commit()

    remaining = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-02&to=2026-07-02"
        f"&user_scope=selected&user_id={first_id}",
    )
    remaining_card = metric_card(remaining, "total_activities")
    assert 'data-target="2"' in remaining_card
    assert 'data-remaining="2"' in remaining_card
    assert 'data-percentage="0"' in remaining_card
    assert 'data-bar-percentage="0"' in remaining_card
    assert "2 remaining" in remaining_card
    assert "Needs attention" in remaining_card

    zero_target = get_dashboard(application)
    zero_card = metric_card(zero_target, "companies_contacted")
    assert 'data-target="0"' in zero_card
    assert 'data-percentage="none"' in zero_card
    assert 'data-progress-state="neutral"' in zero_card
    assert 'data-bar-percentage="0"' in zero_card
    assert "No target" in zero_card


def test_dashboard_kpi_states_attention_threshold_and_progress_cap() -> None:
    """KPI presentation keeps exact calculations while exposing quiet states."""
    incomplete = _build_dashboard_metric(
        key="x", label="X", actual=49, target=Decimal("100")
    )
    exact = _build_dashboard_metric(
        key="x", label="X", actual=100, target=Decimal("100")
    )
    exceeded = _build_dashboard_metric(
        key="x", label="X", actual=193, target=Decimal("100")
    )

    assert DASHBOARD_TARGET_ATTENTION_RATIO == Decimal("0.5")
    assert incomplete.status_text == "51 remaining"
    assert incomplete.status_state == "muted"
    assert incomplete.needs_attention is True
    assert incomplete.progress_state == "standard"
    assert exact.status_text == "Goal reached"
    assert exact.status_state == "success"
    assert exact.needs_attention is False
    assert exact.progress_state == "success"
    assert exceeded.status_text == "Goal exceeded by 93"
    assert exceeded.status_state == "success"
    assert exceeded.percentage == 193
    assert exceeded.bar_percentage == 100


def test_dashboard_kpi_template_uses_circular_progress_without_comparison_ui() -> None:
    template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")

    assert 'class="dashboard-kpi-value-row"' in template
    assert 'class="dashboard-kpi-actual"' in template
    assert "of {{ metric.target_text }} target" in template
    assert 'class="dashboard-circular-progress' in template
    assert 'stroke-dasharray="{{ metric.bar_percentage }} 100"' in template
    assert "{{ metric.percentage_text if metric.target > 0 else '—' }}" in template
    assert "{{ metric.status_text }}" in template
    assert "Needs attention" in template
    assert "previous period" not in template.lower()
    assert "#d66a0a" not in css.split(".dashboard-kpi-main-row", 1)[1].split(
        ".dashboard-analysis-grid", 1
    )[0]
    assert ".dashboard-circular-progress-success" in css
    assert "stroke-linecap: round" in css
    progress_css = css.split(".dashboard-circular-progress {", 1)[1].split(
        "}", 1
    )[0]
    assert "width: 3.9rem" in progress_css
    assert "height: 3.9rem" in progress_css
    assert "stroke-width: 4" in css
    assert "font-size: 0.65rem" in css
    actual_css = css.split(".dashboard-kpi-actual {", 1)[1].split("}", 1)[0]
    assert "font-size: 1.42rem" in actual_css
    assert "font-weight: 750" in actual_css
    assert "margin-top: auto" not in css.split(".dashboard-kpi-status {", 1)[1].split(
        "}", 1
    )[0]
    assert 'class="dashboard-kpi-status-row"' in template
    assert " · Needs attention" in template
    assert "position: absolute" in progress_css


def test_dashboard_secondary_dashboard_typography_uses_quiet_weights() -> None:
    template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")

    report_note_rules = re.findall(r"\.report-section-note \{([^}]*)\}", css)
    target_css = css.split(".dashboard-kpi-target {", 1)[1].split("}", 1)[0]
    status_css = css.split(".dashboard-kpi-status {", 1)[1].split("}", 1)[0]
    success_status_css = css.split(
        ".dashboard-kpi-status-success {",
        1,
    )[1].split("}", 1)[0]
    attention_css = css.split(".dashboard-kpi-attention {", 1)[1].split("}", 1)[0]
    mini_result_css = css.split(
        ".dashboard-mini-metric-result {",
        1,
    )[1].split("}", 1)[0]

    assert any(
        "color: var(--muted)" in rule and "font-weight: 400" in rule
        for rule in report_note_rules
    )
    assert "font-weight: 500" in target_css
    assert "font-weight: 500" in status_css
    assert "font-weight: 600" in success_status_css
    assert "font-weight: 500" in attention_css
    assert "font-size: 0.78rem" in attention_css
    assert "var(--primary) 40%" in attention_css
    assert "text-decoration: none" in attention_css
    assert "background:" not in attention_css
    assert "border:" not in attention_css
    assert "font-weight: 400" in mini_result_css
    assert "Total meetings <span>" in template
    assert "Total meetings <strong>" not in template


def test_dashboard_analytics_numeric_typography_is_compact_and_hierarchical() -> None:
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")

    mini_rate_css = css.split(".dashboard-mini-metric-rate {", 1)[1].split(
        "}", 1
    )[0]
    average_css = css.split(".dashboard-mood-average-value {", 1)[1].split(
        "}", 1
    )[0]
    average_suffix_css = css.split(
        ".dashboard-mood-average-value span {", 1
    )[1].split("}", 1)[0]
    donut_total_css = css.split(".dashboard-mood-total strong {", 1)[1].split(
        "}", 1
    )[0]

    assert "font-size: 1.1rem" in mini_rate_css
    assert "font-weight: 750" in mini_rate_css
    assert "font-size: 1.78rem" in average_css
    assert "font-weight: 750" in average_css
    assert "font-size: 0.92rem" in average_suffix_css
    assert "font-weight: 500" in average_suffix_css
    assert "font-size: 1.42rem" in donut_total_css


def test_custom_range_and_validation_preserve_dates(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    custom = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-01&to=2026-07-01",
    )
    assert custom.status_code == 200
    assert custom.text.count("1 Jul – 1 Jul 2026") == 1
    assert 'data-actual="3"' in custom.text
    assert TARGET_CALCULATION_NOTICE in custom.text
    assert 'data-target="0"' in metric_card(custom, "total_activities")
    assert 'data-custom-applied="true"' in custom.text
    assert "Edit dates" in custom.text
    custom_dates_tag = re.search(
        r'<div class="dashboard-custom-dates"[^>]*>',
        custom.text,
    )
    assert custom_dates_tag is not None and "hidden" in custom_dates_tag.group()

    invalid = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-10&to=2026-07-01",
    )
    assert invalid.status_code == 400
    assert "From cannot be later than To." in invalid.text
    assert 'value="2026-07-10"' in invalid.text
    assert 'value="2026-07-01"' in invalid.text
    assert 'data-custom-applied="false"' in invalid.text
    invalid_dates_tag = re.search(
        r'<div class="dashboard-custom-dates"[^>]*>',
        invalid.text,
    )
    assert invalid_dates_tag is not None
    assert "hidden" not in invalid_dates_tag.group()

    future = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-15&to=2026-07-16",
    )
    assert future.status_code == 400
    assert "To cannot be in the future." in future.text


def test_empty_dashboard_and_reset(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    empty = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-05-01&to=2026-05-02",
    )
    assert "No company activity recorded for this period" in empty.text
    assert 'data-actual="0"' in empty.text
    assert empty.text.count('class="dashboard-chart-group"') == 2
    assert 'class="visually-hidden"' in empty.text

    reset = get_dashboard(
        application,
        "/dashboard?period=previous-week&reset=true",
    )
    assert "Current week" in reset.text
    assert "13 Jul – 19 Jul 2026" in reset.text
    assert "Reset filters" in reset.text
    assert "?period=current-week&amp;user_scope=all" in reset.text
    assert 'data-initial-user-scope="all"' in reset.text
    assert 'data-actual="30"' in metric_card(reset, "total_activities")


def test_home_links_to_dashboard_and_filter_is_responsive(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application

    async def home_page() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.get("/")

    home = asyncio.run(home_page())
    assert 'href="http://testserver/dashboard"' in home.text
    assert "Open Dashboard" in home.text
    assert home.text.count('class="action-card"') == 4

    template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")
    script = Path("app/static/js/dashboard_filter.js").read_text(encoding="utf-8")
    _mobile_css, responsive_css = css.split("@media (min-width: 48rem)", 1)
    tablet_css, desktop_css = responsive_css.split("@media (min-width: 64rem)", 1)
    assert 'data-apply disabled' in template
    assert 'name="reset"' not in template
    assert template.count("data-apply") == 1
    assert "Reset filters" in template
    assert "?period=current-week&amp;user_scope=all" in template
    assert 'type="date"' in template
    assert template.index("dashboard-period-group") < template.index(
        "dashboard-custom-dates",
    ) < template.index("dashboard-users-fieldset") < template.index(
        "dashboard-reset-filters",
    )
    assert ".dashboard-filter" in css
    assert 'class="dashboard-results"' in template
    assert template.index('class="dashboard-results"') > template.index(
        "dashboard-filter",
    )
    results_css = css.split(".dashboard-results {", 1)[1].split("}", 1)[0]
    assert "margin-top: 0.85rem" in results_css
    dashboard_topbar_css = css.split(".dashboard-topbar {", 1)[1].split(
        "}",
        1,
    )[0]
    assert "gap: 0.35rem" in dashboard_topbar_css
    dashboard_navigation_css = css.split(".dashboard-navigation-row {", 1)[
        1
    ].split("}", 1)[0]
    assert "margin-top: 0.5rem" in dashboard_navigation_css
    assert "margin-bottom: 0.75rem" in dashboard_navigation_css
    target_helper_css = css.split(
        ".dashboard-metrics-helper {",
        1,
    )[1].split("}", 1)[0]
    assert "color: var(--muted)" in target_helper_css
    assert "background:" not in target_helper_css
    assert "border:" not in target_helper_css
    assert "padding:" not in target_helper_css
    assert template.count('class="dashboard-metrics-helper"') == 1
    metrics_heading_start = template.index('id="company-metrics-heading"')
    metrics_heading_end = template.index("</div>", metrics_heading_start)
    metrics_heading = template[metrics_heading_start:metrics_heading_end]
    assert 'class="report-section-note"' in metrics_heading
    assert TARGET_CALCULATION_NOTICE in metrics_heading
    assert (
        "Targets are calculated from the weekly goals that overlap "
        "the selected period."
    ) not in template
    assert "dashboard-user-selection-notice" not in template
    assert "dashboard-target-decision-notice" not in template
    assert "Decision needed:" not in template
    shell_css = css.split(".shell {", 1)[1].split("}", 1)[0]
    site_header_css = css.split(".site-header {", 1)[1].split("}", 1)[0]
    assert "width: 100%" in shell_css
    assert "max-width: none" in shell_css
    assert "padding-inline: max(1rem, calc((100% - 68rem) / 2))" in shell_css
    assert "margin-inline: 0" in shell_css
    assert "width: 100%" in site_header_css
    assert "max-width: 100%" in site_header_css
    assert "100vw" not in css
    shrink_safe_children = css.split(
        ".header-content > *,",
        1,
    )[1].split("}", 1)[0]
    for selector in (
        ".header-top-row > *",
        ".user-nav > *",
        ".page-content > *",
        ".dashboard-navigation-row > *",
        ".dashboard-filter > *",
        ".dashboard-period-group > *",
        ".dashboard-metric-grid > *",
        ".dashboard-analysis-grid > *",
    ):
        assert selector in shrink_safe_children
    assert "max-width: 100%" in shrink_safe_children
    assert "min-width: 0" in shrink_safe_children
    form_controls_css = css.rsplit("input,\nselect,\ntextarea {", 1)[1].split(
        "}",
        1,
    )[0]
    assert "width: 100%" in form_controls_css
    assert "max-width: 100%" in form_controls_css
    assert "min-width: 0" in form_controls_css
    assert "@media (max-width: 47.999rem)" in css
    mobile_dashboard_css = css.split(
        "@media (max-width: 47.999rem)",
        1,
    )[1].split("@media (hover: hover)", 1)[0]
    dashboard_wrapper_rule = mobile_dashboard_css.split(
        ".page-content > .dashboard-page {",
        1,
    )[1].split("}", 1)[0]
    assert "display: grid" in dashboard_wrapper_rule
    assert "width: 100%" in dashboard_wrapper_rule
    assert "max-width: none" in dashboard_wrapper_rule
    assert "min-width: 0" in dashboard_wrapper_rule
    assert "margin-inline: 0" in dashboard_wrapper_rule
    assert "grid-template-columns: minmax(0, 1fr)" in dashboard_wrapper_rule
    assert "justify-items: stretch" in dashboard_wrapper_rule
    dashboard_children_rule = mobile_dashboard_css.split(
        ".dashboard-page > * {",
        1,
    )[1].split("}", 1)[0]
    assert "grid-column: 1 / -1" in dashboard_children_rule
    assert "justify-self: stretch" in dashboard_children_rule
    assert ".dashboard-navigation-row" in mobile_dashboard_css
    assert "justify-items: stretch" in mobile_dashboard_css
    assert ".dashboard-filter" in mobile_dashboard_css
    assert "justify-self: stretch" in mobile_dashboard_css
    assert ".dashboard-period-select-control select" in mobile_dashboard_css
    assert ".dashboard-custom-apply" in mobile_dashboard_css
    assert ".dashboard-reset-filters" in mobile_dashboard_css
    assert ".dashboard-filter-actions" not in mobile_dashboard_css
    custom_mobile_css = mobile_dashboard_css.split(
        ".dashboard-custom-date-fields {",
        1,
    )[1].split("}", 1)[0]
    assert "grid-template-columns: minmax(0, 1fr)" in custom_mobile_css
    assert ".dashboard-metric-grid" in mobile_dashboard_css
    assert "grid-template-columns: minmax(0, 1fr)" in mobile_dashboard_css
    assert ".dashboard-metric-card" in mobile_dashboard_css
    assert ".dashboard-grouped-chart" in mobile_dashboard_css
    assert ".dashboard-analysis-grid" in mobile_dashboard_css
    assert ".dashboard-metric-grid > *" in mobile_dashboard_css
    assert ".dashboard-analysis-grid > *" in mobile_dashboard_css
    assert "width: 100%" in mobile_dashboard_css
    assert "box-sizing: border-box" in mobile_dashboard_css
    assert ".report-heading-row" in css
    assert ".report-period-summary" in css
    assert 'class="report-section-heading"' in template
    assert 'class="report-section-note"' in template
    assert "Outreach and meetings shown separately." in template
    assert (
        "Outreach activities and Meetings held are separate series."
        not in template
    )
    assert ".report-section-heading" in css
    assert ".report-section-note" in css
    assert 'class="report-navigation-row dashboard-navigation-row"' in template
    navigation_markup = template.split(
        'class="report-navigation-row dashboard-navigation-row"',
        1,
    )[1].split("</div>", 1)[0]
    assert "Back to Home" in navigation_markup
    assert "dashboard-filter" not in navigation_markup
    assert template.index("dashboard-period-summary") < template.index(
        "dashboard-filter",
    )
    assert template.index("dashboard-navigation-row") < template.index(
        "dashboard-filter",
    )
    assert "width: min(18rem, 100%)" not in tablet_css
    assert "margin-inline-start: auto" not in tablet_css
    assert ".dashboard-filter-bar" in css
    assert (
        "grid-template-columns: repeat(2, minmax(0, 1fr)) auto auto"
        in css
    )
    assert 'class="dashboard-export-dropdown"' in template
    assert "Pipeline CSV" in template
    assert "Outreach CSV" in template
    assert "width: 100%" in tablet_css
    assert "grid-template-columns: minmax(0, 1fr)" in tablet_css
    assert "min-height: 2.75rem" in css
    assert ".dashboard-metric-grid" in css
    assert ".dashboard-analysis-grid" in css
    assert 'class="dashboard-kpi-main-row"' in template
    assert 'class="dashboard-kpi-status' in template
    assert 'class="dashboard-circular-progress' in template
    assert "padding-inline-end: 4.7rem" in css
    assert "top: 50%" in css
    assert "align-items: stretch" in css
    assert 'class="dashboard-grouped-chart{% if' in template
    assert 'class="dashboard-chart-legend"' in template
    assert 'class="dashboard-chart-group"' in template
    assert 'class="dashboard-chart-series"' in template
    assert 'class="dashboard-chart-value"' in template
    assert 'data-bar-height="{{ bucket.outreach_bar }}"' in template
    assert 'data-bar-height="{{ bucket.meetings_bar }}"' in template
    assert re.search(
        r'dashboard-chart-bar-group" data-bar-height="\{\{ bucket\.outreach_bar \}\}">'
        r'[\s\S]*?dashboard-chart-value[^>]*>[\s\S]*?bucket\.outreach_activities'
        r'[\s\S]*?dashboard-chart-bar dashboard-chart-bar-outreach',
        template,
    )
    assert re.search(
        r'dashboard-chart-bar-group" data-bar-height="\{\{ bucket\.meetings_bar \}\}">'
        r'[\s\S]*?dashboard-chart-value[^>]*>[\s\S]*?bucket\.meetings_held'
        r'[\s\S]*?dashboard-chart-bar dashboard-chart-bar-meetings',
        template,
    )
    assert 'title="{{ bucket.range_label }}' in template
    assert 'aria-label="{{ bucket.range_label }}' in template
    assert 'class="visually-hidden"' in template
    assert '<table class="visually-hidden">' not in template
    hidden_table_wrapper = template.split(
        '<div class="visually-hidden">',
        1,
    )[1].split("</div>", 1)[0]
    assert "<table>" in hidden_table_wrapper
    assert "Exact company activity values for the selected period" in hidden_table_wrapper
    assert "bucket.outreach_bar" in template
    assert "bucket.meetings_bar" in template
    assert "dashboard-activity-table" not in template
    chart_markup = template.split("data-grouped-chart", 1)[1].split(
        '<div class="visually-hidden">',
        1,
    )[0]
    assert "style=" not in chart_markup
    assert "minmax(0, 1fr)" in css
    assert "overflow-wrap: anywhere" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in tablet_css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in desktop_css
    grouped_chart_css = css.split(".dashboard-grouped-chart {", 1)[1].split(
        "}",
        1,
    )[0]
    assert "height:" not in grouped_chart_css
    assert "min-height: 5.4rem" in css
    assert ".dashboard-grouped-chart {\n    height:" not in tablet_css
    assert "applyButton.disabled = !datesAreValid()" in script
    assert "if (!isCustom()) applyPresetPeriod()" in script
    assert "checkedUsers().length === 0" not in script
    assert 'return "Select both From and To dates."' in script
    assert 'return "From cannot be later than To."' in script
    assert 'return "To cannot be in the future."' in script
    assert "new URL(form.action, window.location.origin)" in script
    assert "new URLSearchParams(window.location.search)" in script
    assert 'form.dataset.customApplied !== "true"' in script
    assert 'editDatesButton.addEventListener("click"' in script
    assert "customDatesEditing = true" in script
    assert "customAppliedSummary.hidden" in script
    assert "replaceUserParams(params)" in script
    assert 'chart.style.setProperty("--chart-columns"' in script
    assert 'chart.style.setProperty("--chart-label-stride"' in script
    assert "barGroup.style.setProperty(" in script
    assert '"--bar-height"' in script
    assert "ResizeObserver" not in script
    assert "scheduleChartLayout" not in script
    assert "debug_layout" not in script
    assert "dashboard-layout-debug" not in script
    assert "console.log" not in script
    assert ".dashboard-layout-debug-panel" not in css
    assert ".dashboard-layout-debug-outline" not in css
    shared_filter_controls = css.split(
        ".dashboard-users-trigger,",
        1,
    )[1].split("}", 1)[0]
    for declaration in (
        "height: 2.75rem",
        "padding: 0.55rem 2.25rem 0.55rem 0.75rem",
        "border: 1px solid #aeb8c7",
        "border-radius: 0.5rem",
        "font-size: 1rem",
        "line-height: 1.5",
    ):
        assert declaration in shared_filter_controls
    assert "appearance: none" in css
    assert ".dashboard-control-arrow" in css
    breakdown_card_css = css.split(
        ".dashboard-analysis-grid .dashboard-analysis-card {",
        1,
    )[1].split("}", 1)[0]
    for declaration in (
        "display: flex",
        "height: auto",
        "padding: 0.85rem",
        "align-self: stretch",
    ):
        assert declaration in breakdown_card_css
    visually_hidden_css = css.split(".visually-hidden {", 1)[1].split(
        "}",
        1,
    )[0]
    for declaration in (
        "position: absolute",
        "width: 1px",
        "inline-size: 1px",
        "height: 1px",
        "block-size: 1px",
        "padding: 0",
        "margin: -1px",
        "overflow: hidden",
        "clip: rect(0 0 0 0)",
        "clip-path: inset(50%)",
        "white-space: nowrap",
        "border: 0",
    ):
        assert declaration in visually_hidden_css
    chart_value_css = css.split(".dashboard-chart-value {", 1)[1].split(
        "}",
        1,
    )[0]
    assert "bottom: calc(100% + 0.3rem)" in chart_value_css
    assert "left: 50%" in chart_value_css
    assert "transform: translateX(-50%)" in chart_value_css
    assert "white-space: nowrap" in chart_value_css
    dense_chart_value_css = css.split(
        ".dashboard-grouped-chart-dense .dashboard-chart-value {",
        1,
    )[1].split("}", 1)[0]
    assert "transform: translateX(-50%) rotate(-90deg)" in dense_chart_value_css
    dashboard_page_css = css.split(".dashboard-page {", 1)[1].split("}", 1)[0]
    assert "width: 100%" in dashboard_page_css
    assert "max-width: 68rem" in dashboard_page_css
    assert "margin-inline: auto" in dashboard_page_css
    assert "margin-top: -0.5rem" in dashboard_page_css


def test_mood_average_daily_trend_filters_rounding_and_missing_rules(
    tmp_path: Path,
) -> None:
    """All mood views use filled outreach user-days and retain daily gaps."""
    engine = create_db_engine(
        f"sqlite:///{(tmp_path / 'mood-summary.db').as_posix()}",
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        users = [
            User(
                name=f"Mood User {index}",
                email=f"mood-{index}@example.com",
                password_hash=hash_password(TEST_PASSWORD),
            )
            for index in range(1, 5)
        ]
        session.add_all(users)
        session.flush()
        user_ids = tuple(user.id for user in users if user.id is not None)
        assert len(user_ids) == 4
        for user_id, mood in zip(
            user_ids,
            (
                UserMood.DIFFICULT,
                UserMood.OKAY,
                UserMood.GOOD,
                UserMood.GOOD,
            ),
            strict=True,
        ):
            add_outreach(
                session,
                user_id=user_id,
                activity_date=date(2026, 7, 10),
                total=1,
                companies=1,
                mood=mood,
            )
        add_outreach(
            session,
            user_id=user_ids[3],
            activity_date=date(2026, 7, 11),
            total=1,
            companies=1,
        )
        for user_id, mood in (
            (user_ids[1], UserMood.GOOD),
            (user_ids[2], UserMood.OKAY),
        ):
            add_outreach(
                session,
                user_id=user_id,
                activity_date=date(2026, 7, 12),
                total=1,
                companies=1,
                mood=mood,
            )
        add_outreach(
            session,
            user_id=user_ids[0],
            activity_date=date(2026, 7, 9),
            total=1,
            companies=1,
            mood=UserMood.GOOD,
        )
        add_outreach(
            session,
            user_id=user_ids[0],
            activity_date=date(2026, 7, 13),
            total=1,
            companies=1,
            mood=UserMood.DIFFICULT,
        )
        add_meeting(
            session,
            user_id=user_ids[0],
            occurred_at=datetime(2026, 7, 10, 12, tzinfo=UTC),
        )
        session.commit()

        selected, error = resolve_dashboard_filter(
            today=TEST_DATE,
            period=CUSTOM_RANGE,
            from_value="2026-07-10",
            to_value="2026-07-12",
        )
        assert error is None and selected is not None
        summary = get_dashboard_summary(session, selected_period=selected)
        mood = summary.mood_summary
        assert mood.recorded_count == 6
        assert mood.average == Decimal(14) / Decimal(6)
        assert mood.average_text == "2.3"
        assert [point.date for point in mood.trend] == [
            date(2026, 7, 10),
            date(2026, 7, 11),
            date(2026, 7, 12),
        ]
        assert mood.trend[0].average == Decimal("2.25")
        assert mood.trend[0].display_average == "2.3"
        assert mood.trend[0].recorded_count == 4
        assert mood.trend[1].average is None
        assert mood.trend[1].display_average is None
        assert mood.trend[2].average == Decimal("2.5")
        assert mood.trend[2].connects_to_previous

        first_day, error = resolve_dashboard_filter(
            today=TEST_DATE,
            period=CUSTOM_RANGE,
            from_value="2026-07-10",
            to_value="2026-07-10",
        )
        assert error is None and first_day is not None

        difficult_okay_good = get_dashboard_summary(
            session,
            selected_period=first_day,
            user_filter=DashboardUserFilter(
                scope=USER_SCOPE_SELECTED,
                user_ids=user_ids[:3],
            ),
        ).mood_summary
        assert difficult_okay_good.trend[0].average == Decimal(2)
        assert difficult_okay_good.trend[0].display_average == "2"

        difficult_good_good = get_dashboard_summary(
            session,
            selected_period=first_day,
            user_filter=DashboardUserFilter(
                scope=USER_SCOPE_SELECTED,
                user_ids=(user_ids[0], user_ids[2], user_ids[3]),
            ),
        ).mood_summary
        assert difficult_good_good.average == Decimal(7) / Decimal(3)
        assert difficult_good_good.average_text == "2.3"
        assert difficult_good_good.recorded_count == 3

        only_missing_period, error = resolve_dashboard_filter(
            today=TEST_DATE,
            period=CUSTOM_RANGE,
            from_value="2026-07-11",
            to_value="2026-07-11",
        )
        assert error is None and only_missing_period is not None
        only_missing = get_dashboard_summary(
            session,
            selected_period=only_missing_period,
        ).mood_summary
        assert only_missing.average is None
        assert only_missing.average_text is None
        assert only_missing.recorded_count == 0
        assert only_missing.trend[0].average is None
    engine.dispose()


def test_country_blocker_shares_sorting_and_view_all_markup(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, engine, first_user_id, second_user_id = dashboard_application
    collapsed = get_dashboard(application)
    assert "data-expand-toggle" not in collapsed.text

    with Session(engine) as session:
        additions = (
            (first_user_id, date(2026, 7, 15), "Competitor", (("CA", 10), ("FR", 5))),
            (second_user_id, date(2026, 7, 15), "No budget", (("IT", 4),)),
            (first_user_id, date(2026, 7, 16), "Technical limitation", (("ES", 3),)),
            (second_user_id, date(2026, 7, 16), "Other", (("GB", 2),)),
        )
        for user_id, activity_date, blocker, countries in additions:
            add_outreach(
                session,
                user_id=user_id,
                activity_date=activity_date,
                total=1,
                companies=sum(count for _code, count in countries),
                blocker=blocker,
                countries=countries,
            )
        session.commit()
        selected, error = resolve_dashboard_filter(
            today=TEST_DATE,
            period=CURRENT_WEEK,
        )
        assert error is None and selected is not None
        summary = get_dashboard_summary(session, selected_period=selected)

    country_values = {
        item.key: (item.value, item.share_percentage, item.bar_percentage)
        for item in summary.countries
    }
    assert [item.key for item in summary.countries] == [
        "CA", "BR", "FR", "IT", "ES", "AT", "GB", "DE",
    ]
    assert country_values["CA"] == (10, 31, 100)
    assert country_values["BR"] == (5, 16, 50)
    assert country_values["FR"] == (5, 16, 50)
    assert country_values["DE"] == (1, 3, 10)
    assert [item.key for item in summary.blockers] == [
        "No response",
        "No budget",
        "Competitor",
        "Technical limitation",
        "Other",
    ]
    assert [item.share_percentage for item in summary.blockers] == [
        33, 17, 17, 17, 17,
    ]

    response = get_dashboard(application)
    countries = response.text.split(">Countries</h2>", 1)[1].split(
        "</article>", 1,
    )[0]
    blockers = response.text.split(">Blockers</h2>", 1)[1].split(
        "</article>", 1,
    )[0]
    assert countries.count("data-country=") == 8
    assert countries.count("data-expandable-row hidden") == 5
    country_rows = re.findall(
        r'<div\s+class="dashboard-ranked-item dashboard-breakdown-item"[\s\S]*?>',
        countries,
    )
    assert len(country_rows) == 8
    assert sum(" hidden" not in row for row in country_rows) == 3
    assert "data-expandable-row hidden" in country_rows[3]
    assert blockers.count("data-blocker=") == 5
    assert blockers.count("data-expandable-row hidden") == 2
    assert countries.count("data-expand-toggle") == 1
    assert blockers.count("data-expand-toggle") == 1
    assert 'aria-expanded="false"' in countries
    assert 'aria-expanded="false"' in blockers
    assert "No blocker" not in blockers
    assert 'data-blocker-count="0"' not in blockers


def test_mood_template_accessibility_and_empty_state(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    response = get_dashboard(application)
    mood_card = response.text.split('id="mood-summary-heading"', 1)[1].split(
        "</article>", 1,
    )[0]
    assert "Average mood" in mood_card
    assert "Mood distribution" in mood_card
    assert "Daily mood trend" in mood_card
    assert mood_card.count("data-mood-legend=") == 3
    assert "Missing mood is excluded, not treated as neutral." in mood_card
    assert "Current period" in mood_card
    assert "Previous period" not in mood_card
    assert 'aria-label="2026-07-13: average 3, 1 recorded entry"' in mood_card
    assert 'aria-label="2026-07-14: average 1, 1 recorded entry"' in mood_card
    assert 'data-mood-date="2026-07-15"' not in mood_card
    assert mood_card.count("dashboard-mood-current-line") == 1

    empty = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-05-01&to=2026-05-02",
    )
    assert empty.text.count("No recorded mood for this period.") == 1
    empty_mood_card = empty.text.split('id="mood-summary-heading"', 1)[1].split(
        "</article>", 1,
    )[0]
    assert "dashboard-mood-trend-chart" not in empty_mood_card
    assert "dashboard-mood-donut" not in empty_mood_card


def test_long_mood_trend_uses_compact_proportional_dates_and_retains_gaps(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Long periods keep daily records without requiring a wider chart."""
    _, engine, _, _ = dashboard_application
    with Session(engine) as session:
        selected, error = resolve_dashboard_filter(
            today=TEST_DATE,
            period=CURRENT_MONTH,
        )
        assert error is None and selected is not None
        mood = get_dashboard_summary(session, selected_period=selected).mood_summary

    assert len(mood.trend) == 31
    assert mood.chart_width == 640
    assert mood.trend[0].date == date(2026, 7, 1)
    assert mood.trend[-1].date == date(2026, 7, 31)
    assert mood.trend[0].show_date_label
    assert mood.trend[-1].show_date_label
    assert sum(point.show_date_label for point in mood.trend) <= 10
    assert mood.trend[0].x == 48
    assert mood.trend[-1].x == 628
    assert all(
        earlier.x < later.x
        for earlier, later in zip(mood.trend, mood.trend[1:])
    )
    assert mood.trend[14].average is None
    assert mood.trend[14].y is None
    assert mood.trend[14].recorded_count == 0
    recorded = [point for point in mood.trend if point.average is not None]
    assert [(point.date, point.display_average) for point in recorded] == [
        (date(2026, 7, 13), "3"),
        (date(2026, 7, 14), "1"),
    ]


def test_redesigned_analysis_layout_and_view_all_script_contract() -> None:
    template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")
    script = Path("app/static/js/dashboard_filter.js").read_text(encoding="utf-8")

    assert template.index("mood-summary-heading") < template.index(
        'class="dashboard-analysis-grid"',
    ) < template.index("comments-overview-heading")
    assert template.count("dashboard-mood-summary-card") == 1
    assert 'aria-label="Countries and blockers"' in template
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    mobile_css = css.split("@media (max-width: 47.999rem)", 1)[1].split(
        "@media (hover: hover)", 1,
    )[0]
    assert "grid-template-columns: minmax(0, 1fr)" in mobile_css
    mobile_card_css = mobile_css.split(
        ".dashboard-analysis-grid .dashboard-analysis-card {", 1,
    )[1].split("}", 1)[0]
    assert "min-height: 0" in mobile_card_css
    analysis_grid_css = css.split(
        ".dashboard-analysis-grid {\n  margin-top:", 1,
    )[1].split("}", 1)[0]
    assert "align-items: stretch" in analysis_grid_css
    analysis_card_css = css.split(
        ".dashboard-analysis-grid .dashboard-analysis-card {", 1,
    )[1].split("}", 1)[0]
    assert "display: flex" in analysis_card_css
    assert "flex-direction: column" in analysis_card_css
    assert "align-self: stretch" in analysis_card_css
    assert "height: auto" in analysis_card_css
    analysis_body_css = css.split(
        ".dashboard-analysis-body {", 1,
    )[1].split("}", 1)[0]
    assert "flex: 1 1 auto" in analysis_body_css
    expanded_grid_css = css.split(
        ".dashboard-analysis-grid.has-expanded-card {", 1,
    )[1].split("}", 1)[0]
    assert "align-items: start" in expanded_grid_css
    hidden_row_css = css.split(
        ".dashboard-ranked-item[hidden] {", 1,
    )[1].split("}", 1)[0]
    assert "display: none !important" in hidden_row_css
    assert "fixed" not in analysis_card_css
    desktop_css = css.split("@media (min-width: 64rem)", 1)[1]
    desktop_grid_css = desktop_css.split(
        ".dashboard-analysis-grid {", 1,
    )[1].split("}", 1)[0]
    assert "align-items: start" in desktop_grid_css
    desktop_card_css = desktop_css.split(
        ".dashboard-analysis-grid .dashboard-analysis-card {", 1,
    )[1].split("}", 1)[0]
    assert "min-height:" not in desktop_card_css
    assert "align-self: stretch" in desktop_card_css
    trend_viewport_css = css.split(
        ".dashboard-mood-trend-viewport {", 1,
    )[1].split("}", 1)[0]
    assert "overflow: hidden" in trend_viewport_css
    assert "overflow-x: auto" not in trend_viewport_css
    assert "max-width: 100%" in css.split(
        ".dashboard-mood-trend-viewport {", 1,
    )[1].split("}", 1)[0]
    assert 'width="100%"' in template
    assert "viewBox=\"0 0 {{ summary.mood_summary.chart_width }} 152\"" in template
    assert "loop.index > 3" in template
    assert "length > 3" in template
    assert 'document.querySelectorAll("[data-expand-toggle]")' in script
    assert 'toggle.setAttribute("aria-expanded", String(!expanded))' in script
    assert 'row.hidden = expanded' in script
    assert 'toggle.textContent = expanded ? "View all" : "Show less"' in script
    assert 'grid.classList.toggle("has-expanded-card", hasExpandedCard)' in script
    assert "captureCardBaseline" in script
    assert "clearCardBaseline" in script
    assert "window.location" not in script.split(
        'document.querySelectorAll("[data-expand-toggle]")', 1,
    )[1]
