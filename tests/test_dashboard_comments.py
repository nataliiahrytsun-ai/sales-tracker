"""Focused regression tests for Dashboard comment grouping UI."""

import asyncio
from collections.abc import Generator
from datetime import UTC, date, datetime
from html import unescape
import re
from urllib.parse import parse_qs, urlsplit

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
from app.routes.outreach import current_local_date
from app.routes.dashboard import router as dashboard_router
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

    @application.get("/", name="home")
    def home() -> PlainTextResponse:
        return PlainTextResponse("Home")

    @application.post("/logout", name="logout")
    def logout() -> PlainTextResponse:
        return PlainTextResponse("")

    @application.get("/change-password", name="change_password_page")
    def change_password() -> PlainTextResponse:
        return PlainTextResponse("")

    @application.get("/exports/pipeline.csv", name="export_pipeline_csv")
    def pipeline_export() -> PlainTextResponse:
        return PlainTextResponse("")

    @application.get("/exports/outreach.csv", name="export_outreach_csv")
    def outreach_export() -> PlainTextResponse:
        return PlainTextResponse("")

    application.include_router(dashboard_router)

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


def grouping_query(response: httpx.Response, label: str) -> dict[str, list[str]]:
    match = re.search(
        rf'<a[^>]+href="([^"]+)"[^>]*>{re.escape(label)}</a>',
        response.text,
    )
    assert match is not None
    return parse_qs(urlsplit(unescape(match.group(1))).query)


def test_comments_default_invalid_fallback_sources_and_safe_rendering(
    comments_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = comments_application
    for response in (
        get_dashboard(application),
        get_dashboard(application, "/dashboard?comment_group=invalid"),
    ):
        assert response.status_code == 200
        assert response.text.count('aria-current="true"') == 1
        assert ">Anna Employee</h3>" in response.text
        assert ">Ben Employee</h3>" in response.text
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
    assert by_date.text.index(">2026-07-15</h3>") < by_date.text.index(
        ">2026-07-14</h3>",
    )
    assert 'comment_group=date"' in by_date.text
    by_source = get_dashboard(application, "/dashboard?comment_group=source")
    assert ">Meeting</h3>" in by_source.text
    assert ">Daily Outreach</h3>" in by_source.text
    assert 'comment_group=source"' in by_source.text


def test_grouping_links_preserve_period_dates_and_repeated_user_ids(
    comments_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, first_id, second_id = comments_application
    custom = get_dashboard(
        application,
        "/dashboard?period=custom&from=2026-07-13&to=2026-07-15"
        f"&user_scope=selected&user_id={first_id}&user_id={second_id}",
    )
    assert grouping_query(custom, "By source") == {
        "period": ["custom"],
        "from": ["2026-07-13"],
        "to": ["2026-07-15"],
        "user_scope": ["selected"],
        "user_id": [str(first_id), str(second_id)],
        "comment_group": ["source"],
    }


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
    reset = get_dashboard(
        application,
        "/dashboard?period=previous-week&comment_group=source&reset=true",
    )
    assert grouping_query(reset, "By employee")["comment_group"] == ["employee"]
    assert 'data-initial-period="current-week"' in reset.text
    assert 'data-initial-user-scope="all"' in reset.text
