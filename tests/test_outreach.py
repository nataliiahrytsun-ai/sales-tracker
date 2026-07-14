"""Integration tests for today's private daily outreach workflow."""

import asyncio
from collections.abc import Generator
from datetime import date
from pathlib import Path
import re

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select

from app.config import Settings
from app.database import create_db_engine, get_session
from app.main import create_app
from app.models import DailyOutreach, OutreachCountry, User, UserMood
from app.routes.outreach import current_local_date
from app.services.passwords import hash_password

ACTIVE_EMAIL = "outreach-user@example.com"
SECOND_EMAIL = "second-outreach-user@example.com"
TEST_PASSWORD = "outreach-test-password"
TEST_DATE = date(2026, 7, 14)
STYLESHEET_PATH = Path("app/static/css/app.css")


def valid_outreach_data(**overrides: str) -> dict[str, str]:
    """Return one exact-plan valid outreach form submission."""
    values = {
        "total_activities": "40",
        "unique_companies": "12",
        "country_de": "6",
        "country_at": "4",
        "country_ch": "2",
        "replies": "8",
        "positive_replies": "5",
        "meetings_booked": "2",
        "user_mood": "Good",
        "blocker_tag": "No response",
        "note": "Continue the strongest conversations.",
    }
    values.update(overrides)
    return values


@pytest.fixture
def outreach_application(
    tmp_path: Path,
) -> Generator[tuple[FastAPI, Engine, int, int], None, None]:
    """Create an isolated app with a deterministic local date and two users."""
    database_url = f"sqlite:///{(tmp_path / 'outreach.db').as_posix()}"
    engine = create_db_engine(database_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        first_user = User(
            name="Outreach User",
            email=ACTIVE_EMAIL,
            password_hash=hash_password(TEST_PASSWORD),
        )
        second_user = User(
            name="Second Outreach User",
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
            session_secret="outreach-session-secret-with-at-least-32-characters",
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


async def login(
    client: httpx.AsyncClient,
    email: str = ACTIVE_EMAIL,
) -> None:
    """Authenticate one outreach test user."""
    response = await client.post(
        "/login",
        data={"email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 303


def test_authenticated_user_can_open_today_outreach_form(
    outreach_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """The private form uses the shared layout and exact plan fields."""
    application, _, _, _ = outreach_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            response = await client.get("/outreach/today")

        assert response.status_code == 200
        assert 'action="http://testserver/outreach/today"' in response.text
        assert TEST_DATE.isoformat() in response.text
        for field in (
            "total_activities",
            "unique_companies",
            "country_de",
            "country_at",
            "country_ch",
            "replies",
            "positive_replies",
            "meetings_booked",
            "user_mood",
            "blocker_tag",
            "note",
        ):
            assert f'name="{field}"' in response.text
        for code, country in (
            ("DE", "Germany"),
            ("AT", "Austria"),
            ("CH", "Switzerland"),
        ):
            assert f'name="country_{code.lower()}"' in response.text
            assert country in response.text
        assert 'name="user_id"' not in response.text
        assert 'name="activity_date"' not in response.text

    asyncio.run(scenario())


@pytest.mark.parametrize("method", ("GET", "POST"))
def test_anonymous_today_outreach_redirects_to_login(
    outreach_application: tuple[FastAPI, Engine, int, int],
    method: str,
) -> None:
    """Both form routes enforce authentication on the server."""
    application, _, _, _ = outreach_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.request(method, "/outreach/today")

        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    asyncio.run(scenario())


def test_successful_create_persists_today_for_authenticated_user(
    outreach_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """All exact-plan fields and DACH codes persist on the owned record."""
    application, engine, first_user_id, second_user_id = outreach_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            submitted = valid_outreach_data()
            submitted.update(
                {
                    "user_id": str(second_user_id),
                    "activity_date": "1999-01-01",
                    "country_us": "999",
                },
            )
            response = await client.post("/outreach/today", data=submitted)
            confirmation = await client.get(response.headers["location"])

        assert response.status_code == 303
        assert response.headers["location"] == "/outreach/today?saved=true"
        assert confirmation.status_code == 200
        assert "Today's outreach was saved." in confirmation.text

    asyncio.run(scenario())

    with Session(engine) as session:
        records = session.exec(select(DailyOutreach)).all()
        assert len(records) == 1
        record = records[0]
        assert record.user_id == first_user_id
        assert record.user_id != second_user_id
        assert record.activity_date == TEST_DATE
        assert record.total_activities == 40
        assert record.unique_companies == 12
        assert record.replies == 8
        assert record.positive_replies == 5
        assert record.meetings_booked == 2
        assert record.user_mood is UserMood.GOOD
        assert record.blocker_tag == "No response"
        assert record.note == "Continue the strongest conversations."
        assert record.id is not None
        countries = session.exec(
            select(OutreachCountry).where(
                OutreachCountry.outreach_daily_id == record.id,
            ),
        ).all()
        assert {
            country.country_code: country.companies_contacted
            for country in countries
        } == {"DE": 6, "AT": 4, "CH": 2}


def test_repeat_post_updates_same_daily_record_and_country_rows(
    outreach_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """A second save updates rather than duplicating today's owned record."""
    application, engine, first_user_id, _ = outreach_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            first = await client.post(
                "/outreach/today",
                data=valid_outreach_data(),
            )
            assert first.status_code == 303
            second = await client.post(
                "/outreach/today",
                data=valid_outreach_data(
                    total_activities="55",
                    unique_companies="10",
                    country_de="3",
                    country_at="2",
                    country_ch="5",
                    replies="",
                    positive_replies="",
                    meetings_booked="",
                    user_mood="",
                    blocker_tag="",
                    note="Updated safely",
                ),
            )
            reopened = await client.get("/outreach/today")

        assert second.status_code == 303
        assert reopened.status_code == 200
        assert re.search(r'name="total_activities"[^>]*value="55"', reopened.text)
        assert "Updated safely" in reopened.text

    asyncio.run(scenario())

    with Session(engine) as session:
        records = session.exec(
            select(DailyOutreach).where(
                DailyOutreach.user_id == first_user_id,
                DailyOutreach.activity_date == TEST_DATE,
            ),
        ).all()
        assert len(records) == 1
        record = records[0]
        assert record.total_activities == 55
        assert record.replies is None
        assert record.positive_replies is None
        assert record.meetings_booked is None
        assert record.user_mood is None
        assert record.blocker_tag is None
        assert record.note == "Updated safely"
        assert record.id is not None
        countries = session.exec(
            select(OutreachCountry).where(
                OutreachCountry.outreach_daily_id == record.id,
            ),
        ).all()
        assert len(countries) == 3
        assert {
            country.country_code: country.companies_contacted
            for country in countries
        } == {"DE": 3, "AT": 2, "CH": 5}


def test_second_user_has_separate_record_for_same_date(
    outreach_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Ownership permits one independent same-date row per user."""
    application, engine, first_user_id, second_user_id = outreach_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as first_client:
            await login(first_client)
            response = await first_client.post(
                "/outreach/today",
                data=valid_outreach_data(note="First user"),
            )
            assert response.status_code == 303

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as second_client:
            await login(second_client, SECOND_EMAIL)
            empty_form = await second_client.get("/outreach/today")
            assert "First user" not in empty_form.text
            response = await second_client.post(
                "/outreach/today",
                data=valid_outreach_data(note="Second user"),
            )
            assert response.status_code == 303

    asyncio.run(scenario())

    with Session(engine) as session:
        records = session.exec(
            select(DailyOutreach).where(
                DailyOutreach.activity_date == TEST_DATE,
            ),
        ).all()
        assert len(records) == 2
        assert {record.user_id for record in records} == {
            first_user_id,
            second_user_id,
        }


def test_invalid_counters_and_selectors_preserve_safe_values(
    outreach_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Invalid input returns clear errors without writing or losing safe text."""
    application, engine, _, _ = outreach_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            response = await client.post(
                "/outreach/today",
                data={
                    "total_activities": "",
                    "unique_companies": "-1",
                    "country_de": "not-a-number",
                    "country_at": "",
                    "country_ch": "2",
                    "replies": "-2",
                    "positive_replies": "1.5",
                    "meetings_booked": "3",
                    "user_mood": "Neutral",
                    "blocker_tag": "free-text-blocker",
                    "note": '<script>alert("safe")</script>',
                },
            )

        assert response.status_code == 400
        assert "Enter total outreach activities." in response.text
        assert "Unique companies contacted cannot be negative." in response.text
        assert (
            "Enter a whole number for companies contacted in Germany."
            in response.text
        )
        assert "Enter companies contacted in Austria." in response.text
        assert "Replies received cannot be negative." in response.text
        assert "Enter a whole number for positive replies." in response.text
        assert "Select a valid mood" in response.text
        assert "Select a valid blocker" in response.text
        assert "&lt;script&gt;" in response.text
        assert '<script>alert("safe")</script>' not in response.text
        assert re.search(r'name="meetings_booked"[^>]*value="3"', response.text)

    asyncio.run(scenario())

    with Session(engine) as session:
        assert session.exec(select(DailyOutreach)).all() == []


def test_country_mismatch_warns_but_allows_save(
    outreach_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Country sum mismatch is non-blocking exactly as documented."""
    application, engine, _, _ = outreach_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            response = await client.post(
                "/outreach/today",
                data=valid_outreach_data(
                    unique_companies="12",
                    country_de="2",
                    country_at="1",
                    country_ch="0",
                ),
            )
            confirmation = await client.get(response.headers["location"])

        assert response.status_code == 303
        assert "Today's outreach was saved." in confirmation.text
        assert "Country total does not match unique companies." in confirmation.text
        assert "breakdown totals 3" in confirmation.text

    asyncio.run(scenario())

    with Session(engine) as session:
        assert len(session.exec(select(DailyOutreach)).all()) == 1


def test_database_constraint_rejects_duplicate_user_and_date(
    outreach_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """The database remains the final one-row-per-user/date enforcement."""
    _, engine, first_user_id, _ = outreach_application
    with Session(engine) as session:
        session.add(
            DailyOutreach(
                user_id=first_user_id,
                activity_date=TEST_DATE,
                total_activities=1,
                unique_companies=1,
            ),
        )
        session.commit()
        session.add(
            DailyOutreach(
                user_id=first_user_id,
                activity_date=TEST_DATE,
                total_activities=2,
                unique_companies=2,
            ),
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_outreach_form_has_mobile_first_and_desktop_grids() -> None:
    """Outreach counters remain overflow-safe across existing breakpoints."""
    css = STYLESHEET_PATH.read_text(encoding="utf-8")
    mobile_css, desktop_css = css.split("@media (min-width: 48rem)", 1)

    assert re.search(
        r"\.counter-grid,\s*\.country-grid\s*\{[^}]*display:\s*grid;"
        r"[^}]*min-width:\s*0",
        mobile_css,
    )
    assert "grid-template-columns" not in re.search(
        r"\.counter-grid,\s*\.country-grid\s*\{(?P<body>[^}]+)\}",
        mobile_css,
    ).group("body")
    assert re.search(
        r"\.counter-grid\s*\{[^}]*grid-template-columns:\s*"
        r"repeat\(2,\s*minmax\(0,\s*1fr\)\)",
        desktop_css,
    )
    assert re.search(
        r"\.country-grid\s*\{[^}]*grid-template-columns:\s*"
        r"repeat\(3,\s*minmax\(0,\s*1fr\)\)",
        desktop_css,
    )
