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
from app.services.targets import TARGET_FIELDS, TARGET_METRICS

ACTIVE_EMAIL = "dashboard-user@example.com"
TEST_PASSWORD = "dashboard-test-password"
TEST_DATE = date(2026, 7, 15)
TARGET_DECISION_NOTICE = "Targets are currently shown only for Current week."


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
                        week_start=date(2026, 7, 13),
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


def metric_card(response: httpx.Response, metric: str) -> str:
    """Return one rendered metric card for focused assertions."""
    start = response.text.index(f'data-metric="{metric}"')
    end = response.text.index("</article>", start)
    return response.text[start:end]


def assert_empty_selected_dashboard(response: httpx.Response) -> None:
    """Assert a selected scope with no valid users cannot expose aggregates."""
    assert response.status_code == 200
    assert "Select at least one user to view data." in response.text
    assert TARGET_DECISION_NOTICE not in response.text
    assert 'data-users-summary>Select users</span>' in response.text
    assert response.text.count('class="week-metric-card dashboard-metric-card"') == 6
    for metric, _label in TARGET_FIELDS:
        card = metric_card(response, metric)
        assert 'data-actual="0"' in card
        assert 'data-target="0"' in card
        assert 'data-remaining="0"' in card
        assert 'data-percentage="none"' in card
        assert 'class="metric-remaining"' not in card
        assert 'class="week-metric-percentage"' not in card
    assert 'role="progressbar"' not in response.text
    assert "No activity to display." in response.text
    assert 'class="dashboard-chart-group"' not in response.text
    assert 'data-country=' not in response.text
    assert 'data-blocker=' not in response.text
    assert 'data-mood=' not in response.text
    assert "No country activity for this period." in response.text
    assert "No Daily outreach blockers for this period." in response.text
    assert "No Daily outreach mood for this period." in response.text
    assert "Outreach activities: 10" not in response.text
    assert "Outreach activities: 20" not in response.text


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
        rf'href="[^"]*comment_group={grouping}"[^>]*aria-current="true"',
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
    assert "No target set" in response.text
    assert TARGET_DECISION_NOTICE not in response.text


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


def test_period_and_selected_users_filter_together_without_historical_targets(
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
    assert 'data-actual="29"' in metric_card(month, "total_activities")
    assert 'data-actual="20"' in metric_card(custom, "total_activities")
    for response in (previous, month, custom):
        assert response.status_code == 200
        assert TARGET_DECISION_NOTICE in response.text
        assert "Select at least one user to view data." not in response.text
        assert 'role="progressbar"' not in response.text


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
    assert "new URL(window.location.href)" in url_helper
    assert "new URLSearchParams(url.search)" in url_helper

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
    reset_link = template.split("dashboard-reset-filters", 1)[1].split(
        "</a>",
        1,
    )[0]
    assert "period=current-week" in reset_link
    assert "user_scope=all" in reset_link
    assert "from=" not in reset_link
    assert "to=" not in reset_link


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
    assert TARGET_DECISION_NOTICE in previous.text
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
    assert custom.text.count("1 Jul – 1 Jul 2026") == 1
    assert 'data-actual="3"' in custom.text
    assert TARGET_DECISION_NOTICE in custom.text
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
    assert "margin-top: 1rem" in results_css
    target_helper_css = css.split(
        ".dashboard-metrics-helper {",
        1,
    )[1].split("}", 1)[0]
    assert "color: var(--muted)" in target_helper_css
    assert "background:" not in target_helper_css
    assert "border:" not in target_helper_css
    assert "padding:" not in target_helper_css
    assert template.count('class="dashboard-metrics-helper"') == 2
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
    assert "applyButton.disabled = !datesAreValid()" in script
    assert "if (!isCustom()) applyPresetPeriod()" in script
    assert "checkedUsers().length === 0" not in script
    assert 'return "Select both From and To dates."' in script
    assert 'return "From cannot be later than To."' in script
    assert 'return "To cannot be in the future."' in script
    assert "new URL(window.location.href)" in script
    assert "new URLSearchParams(url.search)" in script
    assert 'form.dataset.customApplied !== "true"' in script
    assert 'editDatesButton.addEventListener("click"' in script
    assert "customDatesEditing = true" in script
    assert "customAppliedSummary.hidden" in script
    assert "replaceUserParams(params)" in script
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
        ".dashboard-breakdown-grid .dashboard-analysis-card {",
        1,
    )[1].split("}", 1)[0]
    for declaration in (
        "display: flex",
        "height: 100%",
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
