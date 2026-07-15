"""Integration tests for private recent-record correction workflows."""

import asyncio
from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, select

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
    User,
)
from app.routes.outreach import current_local_date
from app.services.passwords import hash_password

ACTIVE_EMAIL = "recent-user@example.com"
SECOND_EMAIL = "other-recent-user@example.com"
TEST_PASSWORD = "recent-test-password"
TEST_DATE = date(2026, 7, 14)


def meeting_data(**overrides: str) -> dict[str, str]:
    """Return a valid meeting form submission."""
    values = {
        "customer_engagement": "High",
        "need_identified": "Yes",
        "outcome": "Follow-up",
        "user_mood": "",
        "blocker_tag": "",
        "country_code": "AT",
        "company_name": "Example company",
        "next_step_date": "",
        "note": "Recent note",
    }
    values.update(overrides)
    return values


def outreach_data(
    **overrides: str | list[str],
) -> dict[str, str | list[str]]:
    """Return a valid outreach form submission."""
    values: dict[str, str | list[str]] = {
        "total_activities": "20",
        "unique_companies": "10",
        "country_codes": ["BR", "FR"],
        "country_counts": ["6", "4"],
        "replies": "5",
        "positive_replies": "2",
        "meetings_booked": "1",
        "user_mood": "",
        "blocker_tag": "",
        "note": "Recent outreach",
    }
    values.update(overrides)
    return values


@pytest.fixture
def recent_application(
    tmp_path: Path,
) -> Generator[tuple[FastAPI, Engine, int, int], None, None]:
    """Create an isolated application with a deterministic local date."""
    database_url = f"sqlite:///{(tmp_path / 'recent.db').as_posix()}"
    engine = create_db_engine(database_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        first_user = User(
            name="Recent User",
            email=ACTIVE_EMAIL,
            password_hash=hash_password(TEST_PASSWORD),
        )
        second_user = User(
            name="Other User",
            email=SECOND_EMAIL,
            password_hash=hash_password(TEST_PASSWORD),
        )
        session.add(first_user)
        session.add(second_user)
        session.commit()
        session.refresh(first_user)
        session.refresh(second_user)
        assert first_user.id is not None
        assert second_user.id is not None
        first_user_id = first_user.id
        second_user_id = second_user.id

    application = create_app(
        Settings(
            database_url=database_url,
            environment="test",
            session_secret="recent-session-secret-with-at-least-32-characters",
            session_cookie_secure=False,
        ),
    )

    def override_get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_session] = override_get_session
    application.dependency_overrides[current_local_date] = lambda: TEST_DATE
    try:
        yield application, engine, first_user_id, second_user_id
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


async def login(client: httpx.AsyncClient, email: str = ACTIVE_EMAIL) -> None:
    """Authenticate one fixture user."""
    response = await client.post(
        "/login",
        data={"email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 303


def add_meeting(
    session: Session,
    *,
    user_id: int,
    occurred_at: datetime,
    company_name: str,
) -> PipelineMeeting:
    """Persist one meeting for list and ownership tests."""
    meeting = PipelineMeeting(
        user_id=user_id,
        occurred_at=occurred_at,
        company_name=company_name,
        customer_engagement=CustomerEngagement.HIGH,
        need_identified=NeedIdentified.YES,
        outcome=PipelineOutcome.FOLLOW_UP,
    )
    session.add(meeting)
    session.commit()
    session.refresh(meeting)
    return meeting


def add_outreach(
    session: Session,
    *,
    user_id: int,
    activity_date: date,
    total: int,
) -> DailyOutreach:
    """Persist one daily outreach summary for list tests."""
    record = DailyOutreach(
        user_id=user_id,
        activity_date=activity_date,
        total_activities=total,
        unique_companies=total,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def test_recent_routes_require_authentication(
    recent_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Every recent list and correction route is private."""
    application, _, _, _ = recent_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            for method, path in (
                ("GET", "/meetings/recent"),
                ("GET", "/meetings/999/edit"),
                ("POST", "/meetings/999"),
                ("POST", "/meetings/999/delete"),
                ("GET", "/outreach/recent"),
                ("GET", f"/outreach/{TEST_DATE.isoformat()}"),
                ("POST", f"/outreach/{TEST_DATE.isoformat()}"),
            ):
                response = await client.request(method, path)
                assert response.status_code == 303
                assert response.headers["location"] == "/login"

    asyncio.run(scenario())


def test_recent_lists_filter_30_days_sort_and_hide_other_users(
    recent_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Both lists use inclusive 30-day windows and newest-first ordering."""
    application, engine, first_user_id, second_user_id = recent_application
    with Session(engine) as session:
        add_meeting(
            session,
            user_id=first_user_id,
            occurred_at=datetime(2026, 7, 14, 12, tzinfo=UTC),
            company_name="Newest meeting",
        )
        add_meeting(
            session,
            user_id=first_user_id,
            occurred_at=datetime(2026, 6, 15, 12, tzinfo=UTC),
            company_name="Boundary meeting",
        )
        add_meeting(
            session,
            user_id=first_user_id,
            occurred_at=datetime(2026, 6, 14, 12, tzinfo=UTC),
            company_name="Old meeting",
        )
        add_meeting(
            session,
            user_id=second_user_id,
            occurred_at=datetime(2026, 7, 13, 12, tzinfo=UTC),
            company_name="Foreign meeting",
        )
        add_outreach(
            session,
            user_id=first_user_id,
            activity_date=TEST_DATE,
            total=30,
        )
        add_outreach(
            session,
            user_id=first_user_id,
            activity_date=TEST_DATE - timedelta(days=29),
            total=29,
        )
        add_outreach(
            session,
            user_id=first_user_id,
            activity_date=TEST_DATE - timedelta(days=30),
            total=28,
        )
        add_outreach(
            session,
            user_id=second_user_id,
            activity_date=TEST_DATE - timedelta(days=1),
            total=99,
        )

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return (
                await client.get("/meetings/recent"),
                await client.get("/outreach/recent"),
            )

    meetings_response, outreach_response = asyncio.run(scenario())
    assert meetings_response.status_code == 200
    assert "Newest meeting" in meetings_response.text
    assert "Boundary meeting" in meetings_response.text
    assert "Old meeting" not in meetings_response.text
    assert "Foreign meeting" not in meetings_response.text
    assert meetings_response.text.index("Newest meeting") < meetings_response.text.index(
        "Boundary meeting",
    )

    assert outreach_response.status_code == 200
    assert TEST_DATE.isoformat() in outreach_response.text
    assert (TEST_DATE - timedelta(days=29)).isoformat() in outreach_response.text
    assert (TEST_DATE - timedelta(days=30)).isoformat() not in outreach_response.text
    assert ">99<" not in outreach_response.text
    newest_link = f'href="http://testserver/outreach/{TEST_DATE.isoformat()}"'
    boundary_link = (
        'href="http://testserver/outreach/'
        f'{(TEST_DATE - timedelta(days=29)).isoformat()}"'
    )
    assert outreach_response.text.index(newest_link) < outreach_response.text.index(
        boundary_link,
    )


def test_meeting_edit_reuses_validation_and_preserves_values(
    recent_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """An owned recent meeting can be edited and invalid input is retained."""
    application, engine, first_user_id, _ = recent_application
    with Session(engine) as session:
        meeting = add_meeting(
            session,
            user_id=first_user_id,
            occurred_at=datetime(2026, 7, 12, 12, tzinfo=UTC),
            company_name="Before edit",
        )
        assert meeting.id is not None
        meeting_id = meeting.id

    async def scenario() -> tuple[
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
            form = await client.get(f"/meetings/{meeting_id}/edit")
            invalid = await client.post(
                f"/meetings/{meeting_id}",
                data=meeting_data(
                    customer_engagement="invalid",
                    company_name="Keep this value",
                ),
            )
            updated = await client.post(
                f"/meetings/{meeting_id}",
                data=meeting_data(
                    customer_engagement="Medium",
                    outcome="Proposal requested",
                    company_name="After edit",
                ),
            )
            confirmation = await client.get(updated.headers["location"])
            return form, invalid, updated, confirmation

    form, invalid, updated, confirmation = asyncio.run(scenario())
    assert form.status_code == 200
    assert "<strong>Editing:</strong>" in form.text
    assert "2026-07-12 12:00" in form.text
    assert "Before edit" in form.text
    assert invalid.status_code == 400
    assert "Select customer engagement." in invalid.text
    assert 'value="Keep this value"' in invalid.text
    assert "Before edit" in invalid.text
    assert updated.status_code == 303
    assert updated.headers["location"] == "/meetings/recent?updated=true"
    assert "Meeting updated successfully." in confirmation.text

    with Session(engine) as session:
        stored = session.get(PipelineMeeting, meeting_id)
        assert stored is not None
        assert stored.company_name == "After edit"
        assert stored.customer_engagement == CustomerEngagement.MEDIUM
        assert stored.outcome == PipelineOutcome.PROPOSAL_REQUESTED


def test_meeting_delete_is_post_only_and_confirms(
    recent_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """An owned recent meeting is deleted only through POST."""
    application, engine, first_user_id, _ = recent_application
    with Session(engine) as session:
        meeting = add_meeting(
            session,
            user_id=first_user_id,
            occurred_at=datetime(2026, 7, 13, 12, tzinfo=UTC),
            company_name="Delete me",
        )
        assert meeting.id is not None
        meeting_id = meeting.id

    async def scenario() -> tuple[
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
            recent = await client.get("/meetings/recent")
            rejected = await client.get(f"/meetings/{meeting_id}/delete")
            deleted = await client.post(f"/meetings/{meeting_id}/delete")
            confirmation = await client.get(deleted.headers["location"])
            return recent, rejected, deleted, confirmation

    recent, rejected, deleted, confirmation = asyncio.run(scenario())
    assert recent.status_code == 200
    assert (
        "onsubmit=\"return window.confirm('Are you sure you want to delete "
        "this meeting?')\""
    ) in recent.text
    assert rejected.status_code == 405
    assert deleted.status_code == 303
    assert confirmation.status_code == 200
    assert "Meeting deleted successfully." in confirmation.text
    with Session(engine) as session:
        assert session.get(PipelineMeeting, meeting_id) is None


def test_meeting_edit_identifies_record_without_company(
    recent_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """The edit heading identifies an optional-company meeting by timestamp."""
    application, engine, first_user_id, _ = recent_application
    with Session(engine) as session:
        meeting = add_meeting(
            session,
            user_id=first_user_id,
            occurred_at=datetime(2026, 7, 11, 9, 30, tzinfo=UTC),
            company_name="",
        )
        assert meeting.id is not None
        meeting_id = meeting.id

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.get(f"/meetings/{meeting_id}/edit")

    response = asyncio.run(scenario())
    assert response.status_code == 200
    assert "2026-07-11 09:30" in response.text
    assert "Company not provided" in response.text


def test_foreign_and_missing_meetings_return_404(
    recent_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Read, update, and delete conceal foreign and missing meeting IDs."""
    application, engine, _, second_user_id = recent_application
    with Session(engine) as session:
        foreign = add_meeting(
            session,
            user_id=second_user_id,
            occurred_at=datetime(2026, 7, 13, 12, tzinfo=UTC),
            company_name="Secret meeting",
        )
        assert foreign.id is not None
        foreign_id = foreign.id

    async def scenario() -> list[int]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            statuses = []
            for meeting_id in (foreign_id, 999999):
                statuses.append(
                    (await client.get(f"/meetings/{meeting_id}/edit")).status_code,
                )
                statuses.append(
                    (
                        await client.post(
                            f"/meetings/{meeting_id}",
                            data=meeting_data(),
                        )
                    ).status_code,
                )
                statuses.append(
                    (await client.post(f"/meetings/{meeting_id}/delete")).status_code,
                )
            return statuses

    assert asyncio.run(scenario()) == [404] * 6
    with Session(engine) as session:
        assert session.get(PipelineMeeting, foreign_id) is not None


def test_meeting_outside_recent_window_cannot_be_changed(
    recent_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """An owned but stale meeting is not available to edit or delete."""
    application, engine, first_user_id, _ = recent_application
    with Session(engine) as session:
        meeting = add_meeting(
            session,
            user_id=first_user_id,
            occurred_at=datetime(2026, 6, 14, 12, tzinfo=UTC),
            company_name="Outside correction window",
        )
        assert meeting.id is not None
        meeting_id = meeting.id

    async def scenario() -> list[int]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return [
                (await client.get(f"/meetings/{meeting_id}/edit")).status_code,
                (
                    await client.post(
                        f"/meetings/{meeting_id}",
                        data=meeting_data(),
                    )
                ).status_code,
                (
                    await client.post(f"/meetings/{meeting_id}/delete")
                ).status_code,
            ]

    assert asyncio.run(scenario()) == [404, 404, 404]
    with Session(engine) as session:
        assert session.get(PipelineMeeting, meeting_id) is not None


def test_outreach_edit_by_date_updates_without_duplicate(
    recent_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """A dated outreach form safely creates then updates the same owned row."""
    application, engine, first_user_id, _ = recent_application
    activity_date = TEST_DATE - timedelta(days=2)

    async def scenario() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            form = await client.get(f"/outreach/{activity_date.isoformat()}")
            created = await client.post(
                f"/outreach/{activity_date.isoformat()}",
                data=outreach_data(
                    total_activities="20",
                    user_id="999",
                    activity_date="1999-01-01",
                ),
            )
            updated = await client.post(
                f"/outreach/{activity_date.isoformat()}",
                data=outreach_data(total_activities="27"),
            )
            return form, created, updated

    form, created, updated = asyncio.run(scenario())
    assert form.status_code == 200
    assert 'name="activity_date"' not in form.text
    assert created.status_code == 303
    assert updated.status_code == 303

    with Session(engine) as session:
        records = session.exec(
            select(DailyOutreach).where(
                DailyOutreach.user_id == first_user_id,
                DailyOutreach.activity_date == activity_date,
            ),
        ).all()
        assert len(records) == 1
        assert records[0].total_activities == 27
        assert records[0].id is not None
        countries = session.exec(
            select(OutreachCountry).where(
                OutreachCountry.outreach_daily_id == records[0].id,
            ),
        ).all()
        assert {
            country.country_code: country.companies_contacted
            for country in countries
        } == {"BR": 6, "FR": 4}


def test_outreach_validation_future_dates_and_ownership(
    recent_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Dated outreach retains invalid values, rejects future dates, and is owned."""
    application, engine, first_user_id, second_user_id = recent_application
    activity_date = TEST_DATE - timedelta(days=1)
    with Session(engine) as session:
        foreign = add_outreach(
            session,
            user_id=second_user_id,
            activity_date=activity_date,
            total=88,
        )
        foreign_id = foreign.id

    old_date = TEST_DATE - timedelta(days=30)

    async def scenario() -> tuple[
        httpx.Response,
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
            private_form = await client.get(f"/outreach/{activity_date.isoformat()}")
            invalid = await client.post(
                f"/outreach/{activity_date.isoformat()}",
                data=outreach_data(total_activities="invalid", note="Keep safely"),
            )
            future_get = await client.get(
                f"/outreach/{(TEST_DATE + timedelta(days=1)).isoformat()}",
            )
            future_post = await client.post(
                f"/outreach/{(TEST_DATE + timedelta(days=1)).isoformat()}",
                data=outreach_data(),
            )
            old_get = await client.get(f"/outreach/{old_date.isoformat()}")
            old_post = await client.post(
                f"/outreach/{old_date.isoformat()}",
                data=outreach_data(),
            )
            return (
                private_form,
                invalid,
                future_get,
                future_post,
                old_get,
                old_post,
            )

    private_form, invalid, future_get, future_post, old_get, old_post = (
        asyncio.run(scenario())
    )
    assert private_form.status_code == 200
    assert 'value="88"' not in private_form.text
    assert invalid.status_code == 400
    assert "Enter a whole number for total outreach activities." in invalid.text
    assert "Keep safely" in invalid.text
    assert future_get.status_code == 400
    assert future_post.status_code == 400
    assert old_get.status_code == 404
    assert old_post.status_code == 404

    with Session(engine) as session:
        assert session.get(DailyOutreach, foreign_id) is not None
        assert session.exec(
            select(DailyOutreach).where(DailyOutreach.user_id == first_user_id),
        ).all() == []


def test_recent_records_layout_is_structurally_responsive() -> None:
    """Recent record cards use overflow-safe mobile-first responsive CSS."""
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")
    meeting_template = Path("app/templates/meeting_form.html").read_text(
        encoding="utf-8",
    )
    outreach_template = Path("app/templates/outreach_form.html").read_text(
        encoding="utf-8",
    )
    recent_meetings_template = Path(
        "app/templates/recent_meetings.html",
    ).read_text(encoding="utf-8")
    mobile_css, desktop_css = css.split("@media (min-width: 48rem)", 1)
    assert 'class="back-link"' in meeting_template
    assert 'class="back-link"' in outreach_template
    assert ".back-link" in mobile_css
    assert "margin-bottom: 1.25rem" in mobile_css
    assert ".records-page" in mobile_css
    assert ".record-list" in mobile_css
    assert ".record-card" in mobile_css
    assert ".record-actions" in mobile_css
    assert 'class="record-details meeting-record-details"' in (
        recent_meetings_template
    )
    assert ".meeting-record-details" in mobile_css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in mobile_css
    assert "min-width: 0" in mobile_css
    assert "flex-wrap: wrap" in mobile_css
    assert "grid-template-columns: minmax(0, 1fr)" in mobile_css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in desktop_css
    assert "grid-template-columns: minmax(0, 1fr) auto" in desktop_css
