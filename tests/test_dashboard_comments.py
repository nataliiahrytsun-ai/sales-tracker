"""Focused regression tests for Dashboard comment grouping UI."""

import asyncio
from collections.abc import Generator
from datetime import UTC, date, datetime
from html import unescape
from pathlib import Path
import re
from urllib.parse import SplitResult, parse_qs, urlsplit

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
import httpx
import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel
from starlette.staticfiles import StaticFiles

from app.auth import get_current_user
from app.database import create_db_engine, get_session
from app.models import (
    CustomerEngagement,
    DailyOutreach,
    NeedIdentified,
    PipelineMeeting,
    PipelineOutcome,
    User,
)
from app.routes.auth import router as auth_router
from app.routes.outreach import current_local_date
from app.routes.dashboard import router as dashboard_router
from app.routes.home import router as home_router
from app.routes.meetings import router as meetings_router
from app.routes.my_week import router as my_week_router
from app.routes.outreach import router as outreach_router
from app.routes.targets import router as targets_router
from app.services.passwords import hash_password

TEST_DATE = date(2026, 7, 15)
TEST_PASSWORD = "dashboard-comments-password"


@pytest.fixture
def comments_application(
    tmp_path,
) -> Generator[tuple[FastAPI, Engine, int, int], None, None]:
    database_url = f"sqlite:///{(tmp_path / 'comments.db').as_posix()}"
    engine = create_db_engine(database_url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        first = User(
            name="Anna Employee",
            email="anna-comments@example.com",
            password_hash=hash_password(TEST_PASSWORD),
        )
        second = User(
            name="Ben Employee",
            email="ben-comments@example.com",
            password_hash=hash_password(TEST_PASSWORD),
        )
        session.add(first)
        session.add(second)
        session.flush()
        assert first.id is not None and second.id is not None
        session.add(
            DailyOutreach(
                user_id=first.id,
                activity_date=date(2026, 7, 13),
                total_activities=3,
                unique_companies=1,
                note="Anna outreach comment",
            ),
        )
        session.add(
            DailyOutreach(
                user_id=second.id,
                activity_date=date(2026, 7, 14),
                total_activities=4,
                unique_companies=2,
                note="Ben outreach comment",
            ),
        )
        session.add(
            DailyOutreach(
                user_id=second.id,
                activity_date=date(2026, 7, 7),
                total_activities=2,
                unique_companies=1,
                note="Previous period comment",
            ),
        )
        session.add(
            DailyOutreach(
                user_id=first.id,
                activity_date=date(2026, 7, 8),
                total_activities=1,
                unique_companies=1,
                note="   ",
            ),
        )
        session.add(
            PipelineMeeting(
                user_id=first.id,
                occurred_at=datetime(2026, 7, 15, 10, tzinfo=UTC),
                customer_engagement=CustomerEngagement.HIGH,
                need_identified=NeedIdentified.YES,
                outcome=PipelineOutcome.FOLLOW_UP,
                note="<script>alert('comment')</script>",
            ),
        )
        session.commit()
        first_id, second_id = first.id, second.id

    application = FastAPI()
    application.mount("/static", StaticFiles(directory="app/static"), name="static")

    @application.get("/exports/pipeline.csv", name="export_pipeline_csv")
    def pipeline_export() -> PlainTextResponse:
        return PlainTextResponse("")

    @application.get("/exports/outreach.csv", name="export_outreach_csv")
    def outreach_export() -> PlainTextResponse:
        return PlainTextResponse("")

    application.include_router(auth_router)
    application.include_router(dashboard_router)
    application.include_router(home_router)
    application.include_router(meetings_router)
    application.include_router(my_week_router)
    application.include_router(outreach_router)
    application.include_router(targets_router)

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_session] = override_session
    application.dependency_overrides[current_local_date] = lambda: TEST_DATE
    application.dependency_overrides[get_current_user] = lambda: first
    try:
        yield application, engine, first_id, second_id
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


def get_dashboard(application: FastAPI, url: str = "/dashboard") -> httpx.Response:
    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(url)

    return asyncio.run(scenario())


def grouping_url(response: httpx.Response, label: str) -> SplitResult:
    match = re.search(
        rf'<option value="([^"]+)"[^>]*>{re.escape(label)}</option>',
        response.text,
    )
    assert match is not None
    return urlsplit(unescape(match.group(1)))


def grouping_query(response: httpx.Response, label: str) -> dict[str, list[str]]:
    return parse_qs(grouping_url(response, label).query)


def comments_section(response: httpx.Response) -> str:
    marker = response.text.index('id="comments-overview"')
    start = response.text.rfind("<section", 0, marker)
    end = response.text.index("</section>", marker)
    return response.text[start:end]


def test_comments_default_invalid_fallback_sources_and_safe_rendering(
    comments_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = comments_application
    for response in (
        get_dashboard(application),
        get_dashboard(application, "/dashboard?comment_group=invalid"),
    ):
        assert response.status_code == 200
        section = comments_section(response)
        assert section.count("data-comment-group-select") == 1
        assert section.count("<select") == 1
        assert section.count("<option") == 3
        assert section.count(" selected") == 1
        assert section.count("<table") == 1
        assert section.count("<thead>") == 1
        assert section.count('scope="col"') == 5
        assert section.count('colspan="5" scope="rowgroup"') == 2
        assert ">Employee: Anna Employee</th>" in section
        assert ">Employee: Ben Employee</th>" in section
        assert "dashboard-comments-table-wrap" in section
        assert 'id="comments-overview"' in section
        for label in ("Employee", "Date", "Source"):
            assert grouping_url(response, label).fragment == "comments-overview"
        assert "Meeting" in response.text
        assert "Daily Outreach" in response.text
        assert "Follow-up" in response.text
        assert "&lt;script&gt;alert(&#39;comment&#39;)&lt;/script&gt;" in response.text
        assert "<script>alert('comment')</script>" not in response.text
        assert response.text.count("data-comment-source=") == 3
        assert "Target history" not in response.text
        assert "ISO KW" not in response.text
        assert 'data-metric="total_activities"' in response.text


def test_comments_group_by_date_and_source(
    comments_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = comments_application
    by_date = get_dashboard(application, "/dashboard?comment_group=date")
    by_date_section = comments_section(by_date)
    assert by_date_section.index(">Date: 2026-07-15</th>") < by_date_section.index(
        ">Date: 2026-07-14</th>",
    )
    assert by_date.text.count("data-comment-source=") == 3
    assert 'comment_group=date#comments-overview"' in by_date.text
    by_source = get_dashboard(application, "/dashboard?comment_group=source")
    assert ">Source: Meeting</th>" in by_source.text
    assert ">Source: Daily Outreach</th>" in by_source.text
    assert by_source.text.count("data-comment-source=") == 3
    assert 'comment_group=source#comments-overview"' in by_source.text


def test_comments_table_has_fixed_columns_and_stacked_mobile_layout() -> None:
    template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")

    assert "dashboard-comments-column-date" in template
    assert "dashboard-comments-column-employee" in template
    assert "dashboard-comments-column-source" in template
    assert "dashboard-comments-column-outcome" in template
    assert "dashboard-comments-column-comment" in template
    wrapper_css = css.split(
        ".dashboard-comments-table-wrap {",
        1,
    )[1].split("}", 1)[0]
    assert "min-width: 0" in wrapper_css
    assert "overscroll-behavior-inline: contain" in wrapper_css
    assert 'data-label="Date"' in template
    assert 'data-label="Employee"' in template
    assert 'data-label="Source"' in template
    assert 'data-label="Outcome"' in template
    assert 'data-label="Comment"' in template
    table_css = css.split(".dashboard-comments-table {", 1)[1].split("}", 1)[0]
    assert "min-width: 46rem" in table_css
    assert "table-layout: fixed" in table_css
    for selector, width in (
        (".dashboard-comments-column-date", "12%"),
        (".dashboard-comments-column-employee", "18%"),
        (".dashboard-comments-column-source", "14%"),
        (".dashboard-comments-column-outcome", "18%"),
        (".dashboard-comments-column-comment", "38%"),
    ):
        rule = css.split(f"{selector} {{", 1)[1].split("}", 1)[0]
        assert f"width: {width}" in rule
    assert ".dashboard-comment-group {" not in css
    assert "var(--accent)" not in css
    assert "var(--accent-soft)" not in css
    grouping_css = css.split(
        ".dashboard-comment-grouping {",
        1,
    )[1].split("}", 1)[0]
    label_css = css.split(
        ".dashboard-comment-grouping label {",
        1,
    )[1].split("}", 1)[0]
    select_css = css.split(
        ".dashboard-comment-grouping select {",
        1,
    )[1].split("}", 1)[0]
    assert "display: flex" in grouping_css
    assert "align-items: center" in grouping_css
    assert "white-space: nowrap" in label_css
    assert "width: 10rem" in select_css
    final_mobile_css = css.rsplit("@media (max-width: 47.999rem)", 1)[1]
    mobile_grouping_css = final_mobile_css.split(
        ".dashboard-comment-grouping {",
        1,
    )[1].split("}", 1)[0]
    mobile_select_css = final_mobile_css.split(
        ".dashboard-comment-grouping select {",
        1,
    )[1].split("}", 1)[0]
    assert "display: flex" in mobile_grouping_css
    assert "align-items: center" in mobile_grouping_css
    assert "flex: 1 1 auto" in mobile_select_css
    assert "min-width: 0" in mobile_select_css
    mobile_table_wrap_css = final_mobile_css.split(
        ".dashboard-comments-table-wrap {",
        1,
    )[1].split("}", 1)[0]
    mobile_table_css = final_mobile_css.split(
        ".dashboard-comments-table {",
        1,
    )[1].split("}", 1)[0]
    assert "overflow-x: visible" in mobile_table_wrap_css
    assert "min-width: 0" in mobile_table_css
    assert "display: block" in mobile_table_css
    mobile_width_reset_css = final_mobile_css.split(
        ".dashboard-comments,",
        1,
    )[1].split("}", 1)[0]
    for property_name in (
        "width: 100%",
        "max-width: 100%",
        "min-width: 0",
        "box-sizing: border-box",
    ):
        assert property_name in mobile_width_reset_css
    assert ".dashboard-comments-table tbody" in mobile_width_reset_css
    assert ".dashboard-comments-table tr" in mobile_width_reset_css
    assert ".dashboard-comments-table td" in mobile_width_reset_css
    assert ".dashboard-comments-table td::before" in final_mobile_css
    assert "content: attr(data-label)" in final_mobile_css
    assert ".dashboard-comments-table td:last-child" in final_mobile_css
    assert "grid-column: 1 / -1" in final_mobile_css


def test_grouping_links_preserve_period_dates_and_repeated_user_ids(
    comments_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, first_id, second_id = comments_application
    custom = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-13&to=2026-07-15"
        f"&user_scope=selected&user_id={first_id}&user_id={second_id}",
    )
    assert grouping_query(custom, "Source") == {
        "period": ["custom"],
        "from": ["2026-07-13"],
        "to": ["2026-07-15"],
        "user_scope": ["selected"],
        "user_id": [str(first_id), str(second_id)],
        "comment_group": ["source"],
    }
    assert grouping_url(custom, "Source").fragment == "comments-overview"


def test_comment_period_user_filters_empty_state_and_reset(
    comments_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, first_id, _ = comments_application
    first = get_dashboard(
        application,
        f"/dashboard?user_scope=selected&user_id={first_id}",
    )
    assert "Anna outreach comment" in first.text
    assert "Ben outreach comment" not in first.text
    previous = get_dashboard(application, "/dashboard?period=previous-week")
    assert "Previous period comment" in previous.text
    assert "Anna outreach comment" not in previous.text
    empty = get_dashboard(application, "/dashboard?user_scope=selected")
    assert "No comments for this period." in empty.text
    assert "data-comment-group-select" not in comments_section(empty)
    reset = get_dashboard(
        application,
        "/dashboard?period=previous-week&comment_group=source&reset=true",
    )
    assert grouping_query(reset, "Employee")["comment_group"] == ["employee"]
    assert grouping_url(reset, "Employee").fragment == "comments-overview"
    assert 'data-initial-period="current-week"' in reset.text
    assert 'data-initial-user-scope="all"' in reset.text
