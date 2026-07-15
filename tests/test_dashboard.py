"""Integration and calculation tests for the company Dashboard."""

import asyncio
from collections.abc import Generator
from datetime import UTC, date, datetime
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
    PREVIOUS_WEEK,
    get_dashboard_summary,
    resolve_dashboard_filter,
)
from app.services.passwords import hash_password
from app.services.targets import TARGET_METRICS

ACTIVE_EMAIL = "dashboard-user@example.com"
TEST_PASSWORD = "dashboard-test-password"
TEST_DATE = date(2026, 7, 15)


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
) -> None:
    session.add(
        PipelineMeeting(
            user_id=user_id,
            occurred_at=occurred_at,
            customer_engagement=CustomerEngagement.HIGH,
            need_identified=NeedIdentified.YES,
            outcome=PipelineOutcome.FOLLOW_UP,
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
                        effective_from=date(2026, 7, 13),
                        effective_until=date(2026, 7, 19),
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
        "Foreign Employee Name",
        "Private outreach note",
        "Foreign private note",
        "Do not expose company",
        "Do not expose meeting note",
    ):
        assert private_value not in response.text


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
    assert "No target set" in response.text
    assert "Historical Targets are unavailable" not in response.text


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
    assert "Meeting-only blocker" not in response.text
    assert 'data-mood="difficult"' in response.text
    assert 'data-mood="okay"' not in response.text
    assert 'data-mood="good"' in response.text
    assert "Daily outreach mood" in response.text
    assert "Daily outreach blockers" in response.text


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
            (date(2026, 7, 13), date(2026, 7, 15), 30, 3),
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


@pytest.mark.parametrize(
    ("period", "expected_start", "expected_end"),
    (
        (CURRENT_WEEK, date(2026, 7, 13), date(2026, 7, 19)),
        (PREVIOUS_WEEK, date(2026, 7, 6), date(2026, 7, 12)),
        (CURRENT_MONTH, date(2026, 7, 1), date(2026, 7, 15)),
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


def test_previous_week_and_month_filter_actuals_without_target_comparison(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    previous = get_dashboard(application, "/dashboard?period=previous-week")
    assert 'data-metric="total_activities"' in previous.text
    assert 'data-actual="16"' in previous.text
    assert 'data-actual="19"' not in previous.text
    assert "Historical Targets are unavailable" in previous.text
    assert 'role="progressbar"' not in previous.text

    month = get_dashboard(application, "/dashboard?period=current-month")
    assert 'data-metric="total_activities"' in month.text
    assert 'data-actual="49"' in month.text
    assert 'data-actual="148"' not in month.text


def test_custom_range_and_validation_preserve_dates(
    dashboard_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = dashboard_application
    custom = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-01&to=2026-07-01",
    )
    assert custom.status_code == 200
    assert "1 Jul – 1 Jul 2026" in custom.text
    assert 'data-actual="3"' in custom.text
    assert "Historical Targets are unavailable" in custom.text

    invalid = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-10&to=2026-07-01",
    )
    assert invalid.status_code == 400
    assert "From cannot be later than To." in invalid.text
    assert 'value="2026-07-10"' in invalid.text
    assert 'value="2026-07-01"' in invalid.text

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
    assert "data-reset" in reset.text
    assert reset.text.count(" disabled") == 2


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
    assert 'name="reset"' in template
    assert 'type="date"' in template
    assert ".dashboard-filter" in css
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
        ".dashboard-filter-actions > *",
        ".dashboard-metric-grid > *",
        ".dashboard-breakdown-grid > *",
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
    assert ".dashboard-period-field select" in mobile_dashboard_css
    assert ".dashboard-filter-actions" in mobile_dashboard_css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in mobile_dashboard_css
    assert ".dashboard-metric-grid" in mobile_dashboard_css
    assert "grid-template-columns: minmax(0, 1fr)" in mobile_dashboard_css
    assert ".dashboard-metric-card" in mobile_dashboard_css
    assert ".dashboard-grouped-chart" in mobile_dashboard_css
    assert ".dashboard-breakdown-grid" in mobile_dashboard_css
    assert ".dashboard-metric-grid > *" in mobile_dashboard_css
    assert ".dashboard-breakdown-grid > *" in mobile_dashboard_css
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
    assert "dashboard-filter" in navigation_markup
    assert template.index("dashboard-period-summary") < template.index(
        "dashboard-filter",
    )
    assert "grid-template-columns: repeat(2, 5rem)" in tablet_css
    assert "margin-inline-start: auto" in tablet_css
    assert "min-height: 2.75rem" in css
    assert ".dashboard-metric-grid" in css
    assert ".dashboard-breakdown-grid" in css
    assert 'class="metric-primary-row"' in template
    assert 'class="metric-remaining"' in template
    primary_row = template.split('class="metric-primary-row"', 1)[1].split(
        "</div>",
        1,
    )[0]
    assert "week-metric-primary" in primary_row
    assert "week-metric-percentage" in primary_row
    assert "remaining" not in primary_row
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
    assert "applyButton.disabled = !(isChanged() && isValid())" in script
    assert 'period.value === "current-week"' in script
    assert 'chart.style.setProperty("--chart-columns"' in script
    assert "barGroup.style.setProperty(" in script
    assert '"--bar-height"' in script
    assert "ResizeObserver" not in script
    assert "scheduleChartLayout" not in script
    assert "debug_layout" not in script
    assert "dashboard-layout-debug" not in script
    assert "console.log" not in script
    assert ".dashboard-layout-debug-panel" not in css
    assert ".dashboard-layout-debug-outline" not in css
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
