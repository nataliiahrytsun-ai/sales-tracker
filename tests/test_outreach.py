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
from app.countries import COUNTRY_CODES, COUNTRY_NAMES_BY_CODE, COUNTRY_OPTIONS
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


def valid_outreach_data(
    **overrides: str | list[str],
) -> dict[str, str | list[str]]:
    """Return one valid outreach form submission with arbitrary countries."""
    values: dict[str, str | list[str]] = {
        "total_activities": "40",
        "unique_companies": "999",
        "country_codes": ["DE", "BR", "PL"],
        "country_counts": ["6", "4", "2"],
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


def test_local_country_list_contains_worldwide_iso_codes() -> None:
    """The local list is complete, unique, and includes required examples."""
    assert len(COUNTRY_OPTIONS) == 249
    assert len(COUNTRY_CODES) == len(COUNTRY_OPTIONS)
    assert COUNTRY_NAMES_BY_CODE["DE"] == "Germany"
    assert COUNTRY_NAMES_BY_CODE["FR"] == "France"
    assert COUNTRY_NAMES_BY_CODE["PL"] == "Poland"
    assert COUNTRY_NAMES_BY_CODE["BR"] == "Brazil"


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
            "replies",
            "positive_replies",
            "meetings_booked",
            "user_mood",
            "blocker_tag",
            "note",
        ):
            assert f'name="{field}"' in response.text
        assert 'name="total_activities"' not in response.text
        assert 'name="unique_companies"' not in response.text
        assert (
            '<output class="country-summary-value" '
            'data-total-outreach-activities>0'
            in response.text
        )
        assert "Countries selected" not in response.text
        assert "Total Companies" not in response.text
        assert "Add countries and enter all result counts for this date." not in (
            response.text
        )
        assert "The total is calculated automatically." not in response.text
        assert "Sentiment and context may be left empty." not in response.text
        assert "Calculated from countries" in response.text
        assert "Country breakdown" in response.text
        assert "Count each company only once per day." not in response.text
        assert 'aria-describedby="positive_replies_error"' not in response.text
        assert 'data-country-row data-country-code=' not in response.text
        for code, country in (
            ("DE", "Germany"),
            ("BR", "Brazil"),
            ("FR", "France"),
            ("PL", "Poland"),
        ):
            assert f'data-country-code="{code}"' in response.text
            assert country in response.text
        assert 'data-country-search' in response.text
        assert 'data-country-select' in response.text
        assert '<option value="">Select country</option>' in response.text
        assert 'data-country-add' in response.text
        assert "Add country" in response.text
        assert 'data-country-rows' in response.text
        assert 'data-country-summary' in response.text
        assert response.text.index('data-country-rows') < response.text.index(
            'data-country-add-row',
        )
        for field in ("replies", "positive_replies", "meetings_booked"):
            assert re.search(
                rf'name="{field}"[^>]*\brequired\b',
                response.text,
            )
        required_start = response.text.index(
            'class="field-section required-fields"',
        )
        optional_start = response.text.index(
            'class="field-section optional-fields"',
        )
        required_section = response.text[required_start:optional_start]
        optional_section = response.text[optional_start:]
        for label in (
            "Companies contacted today",
            "Country",
            "Companies count",
            "Replies received",
            "Positive replies",
            "Meetings booked",
        ):
            assert label in required_section
        assert "Total outreach activities" not in required_section
        for label in ("User mood", "Main blocker", "Note"):
            assert label not in required_section
            assert label in optional_section
        assert "Replies received" not in optional_section
        assert required_section.index("Companies contacted today") < (
            required_section.index("Replies received")
        )
        assert required_section.index("Meetings booked") < (
            required_section.index('data-country-rows')
        )
        assert required_section.index("Country breakdown") < (
            required_section.index('data-country-rows')
        )
        assert required_section.index('data-country-rows') < (
            required_section.index('data-country-add-row')
        )
        for label in (
            "Replies received",
            "Positive replies",
            "Meetings booked",
        ):
            assert (
                f'{label}<span class="required-marker" '
                'aria-hidden="true">*</span>'
            ) in required_section
        assert '<label for="country_search">Country</label>' in required_section
        assert (
            '<label for="country_add_count">Companies count</label>'
            in required_section
        )
        assert "Country <span" not in required_section
        assert "Companies count <span" not in required_section
        assert "Companies contacted today <span" not in required_section
        assert required_section.count("Optional") == 1
        assert optional_section.count("Optional") == 1
        assert '/static/js/outreach_countries.js' in response.text
        assert 'name="user_id"' not in response.text
        assert 'name="activity_date"' not in response.text
        normal_actions = re.search(
            r'<nav class="page-context-nav" aria-label="Outreach page actions">'
            r'(?P<actions>.*?)</nav>',
            response.text,
            re.DOTALL,
        )
        assert normal_actions is not None
        actions = normal_actions.group("actions")
        assert 'href="http://testserver/outreach/recent"' in actions
        assert "View / edit outreach" in actions
        assert 'href="http://testserver/my-week"' in actions
        assert "Go to My Week" in actions
        assert 'href="http://testserver/"' in actions
        assert "Back to Home" in actions
        assert 'class="button' not in actions
        assert response.text.count(
            '<nav class="page-context-nav" aria-label="Outreach page actions">',
        ) == 1
        assert "Today's outreach was saved successfully." not in response.text

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
    """Brazil and multiple arbitrary countries persist on the owned record."""
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
                },
            )
            response = await client.post("/outreach/today", data=submitted)
            confirmation = await client.get(response.headers["location"])
            refreshed_confirmation = await client.get(
                response.headers["location"],
            )

        assert response.status_code == 303
        assert response.headers["location"] == "/outreach/today?saved=true"
        assert confirmation.status_code == 200
        assert refreshed_confirmation.status_code == 200
        assert "Today's outreach was saved successfully." in confirmation.text
        assert "Your saved values are shown below and can be updated." in (
            confirmation.text
        )
        panel_start = confirmation.text.index(
            '<div class="success confirmation-panel" role="status">',
        )
        navigation_start = confirmation.text.index(
            '<nav class="page-context-nav" aria-label="Outreach page actions">',
            panel_start,
        )
        panel = confirmation.text[panel_start:navigation_start]
        navigation = re.search(
            r'<nav class="page-context-nav" aria-label="Outreach page actions">'
            r'(?P<links>.*?)</nav>',
            confirmation.text[navigation_start:],
            re.DOTALL,
        )
        assert navigation is not None
        links = navigation.group("links")
        assert 'href="http://testserver/outreach/recent"' in links
        assert "View / edit outreach" in links
        assert 'href="http://testserver/my-week"' in links
        assert "Go to My Week" in links
        assert 'href="http://testserver/"' in links
        assert "Back to Home" in links
        assert 'class="button' not in links
        assert "page-context-nav" not in panel
        assert "Edit today's outreach" not in panel
        assert 'data-total-outreach-activities>12' in confirmation.text
        assert 'aria-describedby="outreach-saved-entry"' in confirmation.text
        assert confirmation.text.count(
            '<nav class="page-context-nav" aria-label="Outreach page actions">',
        ) == 1

    asyncio.run(scenario())

    with Session(engine) as session:
        records = session.exec(select(DailyOutreach)).all()
        assert len(records) == 1
        record = records[0]
        assert record.user_id == first_user_id
        assert record.user_id != second_user_id
        assert record.activity_date == TEST_DATE
        assert record.total_activities == 12
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
        } == {"DE": 6, "BR": 4, "PL": 2}


def test_repeat_post_updates_same_daily_record_and_country_rows(
    outreach_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """A second save updates, adds, and removes countries without duplicates."""
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
                    total_activities="9999",
                    country_codes=["BR", "FR"],
                    country_counts=["7", "3"],
                    replies="0",
                    positive_replies="0",
                    meetings_booked="0",
                    user_mood="",
                    blocker_tag="",
                    note="Updated safely",
                ),
            )
            reopened = await client.get("/outreach/today")

        assert second.status_code == 303
        assert reopened.status_code == 200
        assert 'name="total_activities"' not in reopened.text
        assert 'data-total-outreach-activities>10' in reopened.text
        assert "Updated safely" in reopened.text
        assert 'name="country_codes" value="BR"' in reopened.text
        assert 'name="country_codes" value="FR"' in reopened.text
        for removed_code in ("DE", "AT", "CH", "PL"):
            assert f'name="country_codes" value="{removed_code}"' not in (
                reopened.text
            )

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
        assert record.total_activities == 10
        assert record.unique_companies == 10
        assert record.replies == 0
        assert record.positive_replies == 0
        assert record.meetings_booked == 0
        assert record.user_mood is None
        assert record.blocker_tag is None
        assert record.note == "Updated safely"
        assert record.id is not None
        countries = session.exec(
            select(OutreachCountry).where(
                OutreachCountry.outreach_daily_id == record.id,
            ),
        ).all()
        assert len(countries) == 2
        assert {
            country.country_code: country.companies_contacted
            for country in countries
        } == {"BR": 7, "FR": 3}


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
                    "total_activities": "not-trusted",
                    "unique_companies": "-1",
                    "country_codes": ["BR", "FR"],
                    "country_counts": ["-3", "1.5"],
                    "replies": "-2",
                    "positive_replies": "1.5",
                    "meetings_booked": "3",
                    "user_mood": "Neutral",
                    "blocker_tag": "free-text-blocker",
                    "note": '<script>alert("safe")</script>',
                },
            )

        assert response.status_code == 400
        assert "Enter total outreach activities." not in response.text
        assert "Companies contacted in Brazil cannot be negative." in response.text
        assert "Enter a whole number for companies contacted in France." in (
            response.text
        )
        assert "Replies received cannot be negative." in response.text
        assert "Enter a whole number for positive replies." in response.text
        assert "Select a valid mood" in response.text
        assert "Select a valid blocker" in response.text
        assert "&lt;script&gt;" in response.text
        assert '<script>alert("safe")</script>' not in response.text
        assert re.search(r'name="meetings_booked"[^>]*value="3"', response.text)
        assert 'name="country_codes" value="BR"' in response.text
        assert 'name="country_codes" value="FR"' in response.text
        assert 'name="country_counts"' in response.text
        assert 'value="-3"' in response.text
        assert 'value="1.5"' in response.text

    asyncio.run(scenario())

    with Session(engine) as session:
        assert session.exec(select(DailyOutreach)).all() == []


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("replies", "Enter replies received."),
        ("positive_replies", "Enter positive replies."),
        ("meetings_booked", "Enter meetings booked."),
    ],
)
def test_required_result_counters_reject_missing_values(
    outreach_application: tuple[FastAPI, Engine, int, int],
    field: str,
    message: str,
) -> None:
    """Each required outreach result is enforced on the server."""
    application, engine, _, _ = outreach_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.post(
                "/outreach/today",
                data=valid_outreach_data(**{field: ""}),
            )

    response = asyncio.run(scenario())
    assert response.status_code == 400
    assert message in response.text
    with Session(engine) as session:
        assert session.exec(select(DailyOutreach)).all() == []


def test_server_calculates_totals_and_ignores_forged_values(
    outreach_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """The server derives the total instead of trusting the browser."""
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
                    total_activities="700",
                    unique_companies="500",
                    country_codes=["BR", "FR"],
                    country_counts=["2", "1"],
                ),
            )
            confirmation = await client.get(response.headers["location"])

        assert response.status_code == 303
        assert "Today's outreach was saved successfully." in confirmation.text
        assert "Country total does not match unique companies." not in confirmation.text
        assert 'data-total-outreach-activities>3' in confirmation.text

    asyncio.run(scenario())

    with Session(engine) as session:
        records = session.exec(select(DailyOutreach)).all()
        assert len(records) == 1
    assert records[0].total_activities == 3
    assert records[0].unique_companies == 3
    assert records[0].replies == 8
    assert records[0].total_activities != records[0].replies


@pytest.mark.parametrize(
    ("replies", "positive_replies"),
    [("5", "2"), ("5", "5")],
)
def test_positive_replies_at_or_below_replies_received_are_saved(
    outreach_application: tuple[FastAPI, Engine, int, int],
    replies: str,
    positive_replies: str,
) -> None:
    """Valid and equal reply counts pass server validation."""
    application, engine, _, _ = outreach_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.post(
                "/outreach/today",
                data=valid_outreach_data(
                    replies=replies,
                    positive_replies=positive_replies,
                ),
            )

    response = asyncio.run(scenario())
    assert response.status_code == 303
    with Session(engine) as session:
        record = session.exec(select(DailyOutreach)).one()
        assert record.replies == int(replies)
        assert record.positive_replies == int(positive_replies)


@pytest.mark.parametrize(
    ("replies", "positive_replies"),
    [("", "1"), ("2", "3")],
)
def test_positive_replies_require_sufficient_replies_received(
    outreach_application: tuple[FastAPI, Engine, int, int],
    replies: str,
    positive_replies: str,
) -> None:
    """Missing or lower replies block saving and preserve both values."""
    application, engine, _, _ = outreach_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.post(
                "/outreach/today",
                data=valid_outreach_data(
                    replies=replies,
                    positive_replies=positive_replies,
                ),
            )

    response = asyncio.run(scenario())
    assert response.status_code == 400
    assert "Positive replies cannot exceed replies received." in response.text
    assert 'aria-describedby="positive_replies_error"' in response.text
    assert 'id="positive_replies_error">Positive replies cannot exceed' in (
        response.text
    )
    assert re.search(
        rf'name="replies"[^>]*value="{re.escape(replies)}"',
        response.text,
    )
    assert re.search(
        rf'name="positive_replies"[^>]*value="{positive_replies}"',
        response.text,
    )
    with Session(engine) as session:
        assert session.exec(select(DailyOutreach)).all() == []


@pytest.mark.parametrize(
    ("country_codes", "country_counts", "expected_error"),
    [
        (["BR", "BR"], ["2", "3"], "Each country can be added only once."),
        (["XX"], ["2"], "Select only countries from the available list."),
    ],
)
def test_server_rejects_duplicate_and_unknown_countries(
    outreach_application: tuple[FastAPI, Engine, int, int],
    country_codes: list[str],
    country_counts: list[str],
    expected_error: str,
) -> None:
    """Server validation does not rely on the dynamic-country JavaScript."""
    application, engine, _, _ = outreach_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.post(
                "/outreach/today",
                data=valid_outreach_data(
                    country_codes=country_codes,
                    country_counts=country_counts,
                ),
            )

    response = asyncio.run(scenario())
    assert response.status_code == 400
    assert expected_error in response.text
    for code, count in zip(country_codes, country_counts, strict=True):
        assert f'name="country_codes" value="{code}"' in response.text
        assert f'value="{count}"' in response.text

    with Session(engine) as session:
        assert session.exec(select(DailyOutreach)).all() == []


@pytest.mark.parametrize(
    ("country_codes", "country_counts", "expected_error"),
    [
        (["BR"], [], "Enter companies contacted in Brazil."),
        ([], ["2"], "Select only countries from the available list."),
    ],
)
def test_server_rejects_incomplete_country_rows(
    outreach_application: tuple[FastAPI, Engine, int, int],
    country_codes: list[str],
    country_counts: list[str],
    expected_error: str,
) -> None:
    """A submitted country row must include both country and count."""
    application, engine, _, _ = outreach_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.post(
                "/outreach/today",
                data=valid_outreach_data(
                    country_codes=country_codes,
                    country_counts=country_counts,
                ),
            )

    response = asyncio.run(scenario())
    assert response.status_code == 400
    assert expected_error in response.text
    with Session(engine) as session:
        assert session.exec(select(DailyOutreach)).all() == []


def test_zero_country_count_is_valid(
    outreach_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Zero is retained as a valid country count and contributes zero."""
    application, engine, _, _ = outreach_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.post(
                "/outreach/today",
                data=valid_outreach_data(
                    country_codes=["BR"],
                    country_counts=["0"],
                    replies="4",
                    positive_replies="2",
                ),
            )

    response = asyncio.run(scenario())
    assert response.status_code == 303
    with Session(engine) as session:
        record = session.exec(select(DailyOutreach)).one()
        country = session.exec(select(OutreachCountry)).one()
        assert record.total_activities == 0
        assert record.unique_companies == 0
        assert record.replies == 4
        assert record.positive_replies == 2
        assert country.companies_contacted == 0


def test_empty_country_breakdown_is_allowed(
    outreach_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """A daily summary may be saved without any country rows."""
    application, engine, _, _ = outreach_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.post(
                "/outreach/today",
                data=valid_outreach_data(
                    unique_companies="100",
                    country_codes=[],
                    country_counts=[],
                ),
            )

    response = asyncio.run(scenario())
    assert response.status_code == 303
    with Session(engine) as session:
        records = session.exec(select(DailyOutreach)).all()
        assert len(records) == 1
        assert records[0].total_activities == 0
        assert records[0].unique_companies == 0
        assert session.exec(select(OutreachCountry)).all() == []


def test_database_rejects_duplicate_country_for_daily_outreach(
    outreach_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """The database enforces one row per outreach and country code."""
    _, engine, first_user_id, _ = outreach_application
    with Session(engine) as session:
        record = DailyOutreach(
            user_id=first_user_id,
            activity_date=TEST_DATE,
            total_activities=2,
            unique_companies=2,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        assert record.id is not None
        session.add(
            OutreachCountry(
                outreach_daily_id=record.id,
                country_code="BR",
                companies_contacted=1,
            ),
        )
        session.add(
            OutreachCountry(
                outreach_daily_id=record.id,
                country_code="BR",
                companies_contacted=1,
            ),
        )
        with pytest.raises(IntegrityError):
            session.commit()


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


def test_outreach_form_has_responsive_dynamic_country_controls() -> None:
    """Country rows and controls remain compact and overflow-safe."""
    css = STYLESHEET_PATH.read_text(encoding="utf-8")
    template = Path("app/templates/outreach_form.html").read_text(
        encoding="utf-8",
    )
    javascript = Path("app/static/js/outreach_countries.js").read_text(
        encoding="utf-8",
    )
    mobile_css, desktop_css = css.split("@media (min-width: 48rem)", 1)

    for selector in (
        ".country-add-row",
        ".country-rows",
        ".country-row",
        ".country-count-controls",
        ".country-row-name",
    ):
        assert selector in mobile_css
    assert "flex-wrap: wrap" in mobile_css
    assert "overflow-wrap: anywhere" in mobile_css
    assert re.search(
        r"\.outreach-form \.country-row\s*\{[^}]*"
        r"grid-template-columns:\s*minmax\(0,\s*1fr\) auto;"
        r"[^}]*align-items:\s*center;",
        mobile_css,
    )
    assert re.search(
        r"\.outreach-form \.country-row-name\s*\{[^}]*"
        r"overflow:\s*hidden;[^}]*text-overflow:\s*ellipsis;"
        r"[^}]*white-space:\s*nowrap;",
        mobile_css,
    )
    assert re.search(
        r"\.outreach-form \.country-count-controls\s*\{[^}]*"
        r"flex-wrap:\s*nowrap;",
        mobile_css,
    )
    assert re.search(
        r"\.outreach-total-display\s*\{[^}]*display:\s*flex;"
        r"[^}]*min-height:\s*2\.75rem;[^}]*align-items:\s*center;"
        r"[^}]*justify-content:\s*space-between;",
        mobile_css,
    )
    assert re.search(
        r"\.country-add-row\s*\{[^}]*grid-template-columns:\s*"
        r"minmax\(0,\s*1fr\)",
        desktop_css,
    )
    assert re.search(
        r"\.outreach-form \.outreach-result-fields\s*\{[^}]*"
        r"grid-template-columns:\s*minmax\(0,\s*1\.15fr\)\s*"
        r"repeat\(3,\s*minmax\(0,\s*1fr\)\)",
        desktop_css,
    )
    assert re.search(
        r"\.outreach-form \.outreach-result-fields > \.field-group\s*"
        r"\{[^}]*grid-template-rows:\s*2\.5rem auto auto;",
        desktop_css,
    )
    assert re.search(
        r"\.outreach-form \.outreach-result-fields > \.field-group > input,\s*"
        r"\.outreach-form \.outreach-total-display\s*\{[^}]*"
        r"height:\s*2\.75rem;[^}]*min-height:\s*2\.75rem;",
        desktop_css,
    )
    assert re.search(
        r"\.outreach-form \.required-fields,\s*"
        r"\.outreach-form \.optional-fields\s*\{[^}]*gap:\s*0\.65rem;"
        r"[^}]*padding:\s*0\.75rem;",
        mobile_css,
    )
    assert 'list="country_options"' in template
    assert 'id="country_select" data-country-select' in template
    assert 'name="country_codes"' in template
    assert 'name="country_counts"' in template
    assert 'class="outreach-result-fields"' in template
    for attribute in (
        "data-country-add",
        "data-country-remove",
        "data-country-select",
        "data-total-outreach-activities",
    ):
        assert attribute in template
        assert attribute in javascript
    assert "This country is already added" in javascript
    assert "window.setTimeout" in javascript
    assert 'rows.addEventListener("input", updateTotal)' in javascript
    assert javascript.count("updateTotal();") >= 3
    assert 'window.matchMedia("(max-width: 47.999rem)")' in javascript
    assert "mobileOption.disabled = disabled" in javascript
    assert re.search(
        r"\.outreach-form \.country-search-field-desktop\s*\{[^}]*"
        r"display:\s*none;",
        mobile_css,
    )
    assert re.search(
        r"\.outreach-form \.country-search-field-mobile\s*\{[^}]*"
        r"display:\s*none;",
        desktop_css,
    )
    assert re.search(
        r"\.outreach-form \.country-search-field-desktop\s*\{[^}]*"
        r"display:\s*grid;",
        desktop_css,
    )
    assert "data-country-increase" not in template
    assert "data-country-decrease" not in template
    assert "data-countries-selected" not in template
    assert "data-companies-contacted" not in template
    assert 'name="unique_companies"' not in template
    assert 'name="total_activities"' not in template
    assert template.count('class="field-section required-fields"') == 1
    assert template.count('class="field-section optional-fields"') == 1
    assert "Companies contacted today" in template
    assert "Calculated from countries" in template
    assert "Country breakdown" in template
    assert "Total outreach activities" not in template
    assert template.index('class="outreach-result-fields"') < template.index(
        "Companies contacted today",
    )
    assert template.index("Companies contacted today") < template.index(
        "Replies received",
    )
    assert template.index("Country breakdown") < template.index(
        'data-country-rows',
    )
    assert template.index('data-country-rows') < template.index(
        'data-country-add-row',
    )
    assert re.search(
        r'class="field-group outreach-total-field"[^>]*>.*?'
        r'Companies contacted today.*?Calculated from countries.*?</div>',
        template,
        re.DOTALL,
    )
    assert '<label for="country_search">Country</label>' in template
    assert '<label for="country_add_count">Companies count</label>' in template
    assert "Country <span" not in template
    assert "Companies count <span" not in template
    assert re.search(
        r"\.outreach-form \.country-breakdown-heading\s*\{[^}]*"
        r"display:\s*flex;",
        mobile_css,
    )
    assert re.search(
        r"\.outreach-form \.country-rows \+ "
        r"\.country-add-row\s*\{[^}]*margin-top:\s*-0\.35rem;",
        mobile_css,
    )
    assert re.search(
        r"\.outreach-form-card\s*\{[^}]*max-width:\s*58rem;",
        mobile_css,
    )
    assert re.search(
        r"\.outreach-form \.required-marker\s*\{[^}]*"
        r"margin-left:\s*0\.25rem;",
        mobile_css,
    )
    assert "Add countries and enter all result counts for this date." not in template
    assert "The total is calculated automatically." not in template
    assert "Sentiment and context may be left empty." not in template
    assert template.count('class="optional"') == 1
    assert 'rows="3"' in template
    assert "Countries selected" not in template
    assert "Total Companies" not in template
    assert "Count each company only once per day." not in template
    assert "Country total" not in template
    assert "Country total does not match unique companies." not in template
