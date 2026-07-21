"""Integration tests for authenticated Company Dashboard CSV exports."""

import asyncio
import codecs
import csv
from collections.abc import Generator
from datetime import UTC, date, datetime
from io import StringIO
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
    OutreachCountry,
    PipelineMeeting,
    PipelineOutcome,
    User,
    UserMood,
)
from app.routes.outreach import current_local_date
from app.services.exports import (
    OUTREACH_COLUMNS,
    PIPELINE_COLUMNS,
    build_csv,
    safe_filename_slug,
)
from app.services.passwords import hash_password

EXPORT_EMAIL = "export-user@example.com"
EXPORT_PASSWORD = "export-test-password"
EXPORT_TODAY = date(2026, 7, 15)


@pytest.fixture
def export_application(
    tmp_path: Path,
) -> Generator[tuple[FastAPI, Engine, int, int], None, None]:
    """Create export records spanning every supported period filter."""
    database_url = f"sqlite:///{(tmp_path / 'exports.db').as_posix()}"
    engine = create_db_engine(database_url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        first = User(
            name="  Export / User!!  ",
            email=EXPORT_EMAIL,
            password_hash=hash_password(EXPORT_PASSWORD),
        )
        second = User(
            name="Second Export User",
            email="second-export@example.com",
            password_hash=hash_password(EXPORT_PASSWORD),
        )
        session.add(first)
        session.add(second)
        session.flush()
        assert first.id is not None and second.id is not None

        meetings = (
            PipelineMeeting(
                user_id=first.id,
                occurred_at=datetime(2026, 7, 13, 9, tzinfo=UTC),
                company_name="=FORMULA(1)",
                country_code="AT",
                customer_engagement=CustomerEngagement.HIGH,
                need_identified=NeedIdentified.YES,
                outcome=PipelineOutcome.REQUEST_SENT,
                user_mood=None,
                blocker_tag=None,
                next_step_date=None,
                note='Line 1, "quoted"\nLine 2',
            ),
            PipelineMeeting(
                user_id=second.id,
                occurred_at=datetime(2026, 7, 14, 10, tzinfo=UTC),
                company_name="Second company",
                country_code=None,
                customer_engagement=CustomerEngagement.MEDIUM,
                need_identified=NeedIdentified.UNCLEAR,
                outcome=PipelineOutcome.MANUAL_ALIGNMENT,
                user_mood=UserMood.GOOD,
                blocker_tag="Budget",
                note="@unsafe note",
            ),
            PipelineMeeting(
                user_id=first.id,
                occurred_at=datetime(2026, 7, 6, 11, tzinfo=UTC),
                company_name="Previous company",
                customer_engagement=CustomerEngagement.LOW,
                need_identified=NeedIdentified.NO,
                outcome=PipelineOutcome.NO_OUTCOME,
            ),
            PipelineMeeting(
                user_id=second.id,
                occurred_at=datetime(2026, 7, 1, 12, tzinfo=UTC),
                company_name="Month company",
                customer_engagement=CustomerEngagement.HIGH,
                need_identified=NeedIdentified.YES,
                outcome=PipelineOutcome.REQUEST_SENT,
            ),
            PipelineMeeting(
                user_id=first.id,
                occurred_at=datetime(2026, 7, 31, 12, tzinfo=UTC),
                company_name="Month-end company",
                customer_engagement=CustomerEngagement.MEDIUM,
                need_identified=NeedIdentified.YES,
                outcome=PipelineOutcome.REQUEST_SENT,
            ),
            PipelineMeeting(
                user_id=first.id,
                occurred_at=datetime(2026, 6, 30, 12, tzinfo=UTC),
                company_name="Outside company",
                customer_engagement=CustomerEngagement.LOW,
                need_identified=NeedIdentified.NO,
                outcome=PipelineOutcome.NO_OUTCOME,
            ),
            PipelineMeeting(
                user_id=first.id,
                occurred_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
                company_name="After month company",
                customer_engagement=CustomerEngagement.LOW,
                need_identified=NeedIdentified.NO,
                outcome=PipelineOutcome.NO_OUTCOME,
            ),
        )
        session.add_all(meetings)

        outreach_records = (
            DailyOutreach(
                user_id=first.id,
                activity_date=date(2026, 7, 13),
                total_activities=10,
                unique_companies=3,
                replies=None,
                positive_replies=None,
                meetings_booked=None,
                user_mood=None,
                blocker_tag=None,
                note="+unsafe outreach",
            ),
            DailyOutreach(
                user_id=second.id,
                activity_date=date(2026, 7, 14),
                total_activities=20,
                unique_companies=5,
                replies=4,
                positive_replies=2,
                meetings_booked=1,
                user_mood=UserMood.DIFFICULT,
                blocker_tag="No response",
                note='Comma, quote " and\nnewline',
            ),
            DailyOutreach(
                user_id=first.id,
                activity_date=date(2026, 7, 6),
                total_activities=7,
                unique_companies=2,
            ),
            DailyOutreach(
                user_id=second.id,
                activity_date=date(2026, 7, 1),
                total_activities=3,
                unique_companies=1,
            ),
            DailyOutreach(
                user_id=first.id,
                activity_date=date(2026, 7, 31),
                total_activities=31,
                unique_companies=8,
            ),
            DailyOutreach(
                user_id=first.id,
                activity_date=date(2026, 6, 30),
                total_activities=99,
                unique_companies=99,
            ),
            DailyOutreach(
                user_id=first.id,
                activity_date=date(2026, 8, 1),
                total_activities=101,
                unique_companies=20,
            ),
        )
        session.add_all(outreach_records)
        session.flush()
        first_current, second_current = outreach_records[:2]
        assert first_current.id is not None and second_current.id is not None
        session.add_all(
            (
                OutreachCountry(
                    outreach_daily_id=first_current.id,
                    country_code="DE",
                    companies_contacted=2,
                ),
                OutreachCountry(
                    outreach_daily_id=first_current.id,
                    country_code="AT",
                    companies_contacted=1,
                ),
                OutreachCountry(
                    outreach_daily_id=second_current.id,
                    country_code="CH",
                    companies_contacted=5,
                ),
            ),
        )
        session.commit()
        first_id, second_id = first.id, second.id

    application = create_app(
        Settings(
            database_url=database_url,
            environment="test",
            session_secret="export-session-secret-with-at-least-32-characters",
            session_cookie_secure=False,
        ),
    )

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_session] = override_session
    application.dependency_overrides[current_local_date] = lambda: EXPORT_TODAY
    try:
        yield application, engine, first_id, second_id
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


async def login(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/login",
        data={"email": EXPORT_EMAIL, "password": EXPORT_PASSWORD},
    )
    assert response.status_code == 303


def request_export(
    application: FastAPI,
    url: str,
    *,
    authenticated: bool = True,
) -> httpx.Response:
    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            if authenticated:
                await login(client)
            return await client.get(url)

    return asyncio.run(scenario())


def csv_rows(response: httpx.Response) -> list[dict[str, str]]:
    assert response.content.startswith(codecs.BOM_UTF8)
    return list(
        csv.DictReader(
            StringIO(response.content.decode("utf-8-sig")),
            delimiter=";",
        ),
    )


def test_export_routes_require_authentication(
    export_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = export_application
    for url in ("/exports/pipeline.csv", "/exports/outreach.csv"):
        response = request_export(application, url, authenticated=False)
        assert response.status_code == 303
        assert response.headers["location"].endswith("/login")


def test_pipeline_csv_headers_records_escaping_and_response_metadata(
    export_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = export_application
    response = request_export(application, "/exports/pipeline.csv")
    rows = csv_rows(response)

    assert response.status_code == 200
    header = response.content.decode("utf-8-sig").splitlines()[0]
    assert ";" in header
    assert "," not in header
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        'attachment; filename="pipeline_export-user_second-export-user_'
        '2026-07-13_2026-07-19.csv"'
    )
    assert tuple(rows[0]) == PIPELINE_COLUMNS
    assert [row["user_name"] for row in rows] == [
        "  Export / User!!  ",
        "Second Export User",
    ]
    assert rows[0]["company_name"] == "'=FORMULA(1)"
    assert rows[0]["note"] == 'Line 1, "quoted"\nLine 2'
    assert rows[0]["user_mood"] == ""
    assert rows[0]["next_step_date"] == ""
    assert rows[1]["note"] == "'@unsafe note"
    assert "export-user@example.com" not in response.text
    assert "password_hash" not in response.text


def test_outreach_csv_headers_country_breakdown_optional_and_formula_values(
    export_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = export_application
    response = request_export(application, "/exports/outreach.csv")
    rows = csv_rows(response)

    raw_csv = response.content.decode("utf-8-sig")
    header = raw_csv.splitlines()[0]
    assert ";" in header
    assert "," not in header
    assert '"AT:1; DE:2"' in raw_csv
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        'attachment; filename="outreach_export-user_second-export-user_'
        '2026-07-13_2026-07-19.csv"'
    )
    assert tuple(rows[0]) == OUTREACH_COLUMNS
    assert rows[0]["country_breakdown"] == "AT:1; DE:2"
    assert rows[1]["country_breakdown"] == "CH:5"
    assert rows[0]["replies"] == ""
    assert rows[0]["positive_replies"] == ""
    assert rows[0]["meetings_booked"] == ""
    assert rows[0]["note"] == "'+unsafe outreach"
    assert rows[1]["note"] == 'Comma, quote " and\nnewline'

    previous = request_export(
        application,
        "/exports/outreach.csv?period=previous-week",
    )
    assert csv_rows(previous)[0]["country_breakdown"] == ""


def test_formula_prefixes_are_neutralized() -> None:
    content = build_csv(
        ("value",),
        (("=one",), ("+two",), ("-three",), ("@four",), ("plain",)),
    )
    rows = list(
        csv.DictReader(
            StringIO(content.lstrip("\ufeff")),
            delimiter=";",
        ),
    )
    assert [row["value"] for row in rows] == [
        "'=one",
        "'+two",
        "'-three",
        "'@four",
        "plain",
    ]


def test_filename_slug_removes_unsafe_characters_and_has_fallback() -> None:
    assert safe_filename_slug("  Max / Mustermann !!! ") == "max-mustermann"
    assert safe_filename_slug("/// @@@") == "user"


@pytest.mark.parametrize("endpoint", ("pipeline", "outreach"))
def test_export_filenames_use_normalized_user_scope(
    export_application: tuple[FastAPI, Engine, int, int],
    endpoint: str,
) -> None:
    application, _, first_id, second_id = export_application
    cases = (
        ("", "export-user_second-export-user"),
        (f"?user_scope=selected&user_id={first_id}", "export-user"),
        (
            "?user_scope=selected"
            f"&user_id={first_id}&user_id={second_id}"
            f"&user_id={first_id}&user_id=invalid&user_id=999999",
            "export-user_second-export-user",
        ),
        ("?user_scope=selected", "no-users"),
    )
    for query, expected_scope in cases:
        response = request_export(
            application,
            f"/exports/{endpoint}.csv{query}",
        )
        assert response.headers["content-disposition"] == (
            f'attachment; filename="{endpoint}_{expected_scope}_'
            '2026-07-13_2026-07-19.csv"'
        )


@pytest.mark.parametrize(
    ("query", "expected_companies"),
    (
        ("period=previous-week", ["Previous company"]),
        (
            "period=current-month",
            [
                "Month company",
                "Previous company",
                "'=FORMULA(1)",
                "Second company",
                "Month-end company",
            ],
        ),
        (
            "period=custom&from=2026-07-01&to=2026-07-01",
            ["Month company"],
        ),
    ),
)
def test_pipeline_export_period_filters_are_inclusive(
    export_application: tuple[FastAPI, Engine, int, int],
    query: str,
    expected_companies: list[str],
) -> None:
    application, _, _, _ = export_application
    response = request_export(application, f"/exports/pipeline.csv?{query}")
    assert [row["company_name"] for row in csv_rows(response)] == expected_companies


@pytest.mark.parametrize(
    ("query", "expected_totals"),
    (
        ("period=previous-week", ["7"]),
        ("period=current-month", ["3", "7", "10", "20", "31"]),
        (
            "period=custom&from=2026-07-13&to=2026-07-14",
            ["10", "20"],
        ),
    ),
)
def test_outreach_export_period_filters_are_inclusive(
    export_application: tuple[FastAPI, Engine, int, int],
    query: str,
    expected_totals: list[str],
) -> None:
    application, _, _, _ = export_application
    response = request_export(application, f"/exports/outreach.csv?{query}")
    assert [row["total_activities"] for row in csv_rows(response)] == expected_totals


def test_current_month_pipeline_export_matches_dashboard_full_month_range(
    export_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, first_id, second_id = export_application
    query = (
        "period=current-month&user_scope=selected"
        f"&user_id={first_id}&user_id={second_id}"
    )
    dashboard = request_export(application, f"/dashboard?{query}")
    response = request_export(application, f"/exports/pipeline.csv?{query}")

    assert "31 Jul 2026" in dashboard.text
    assert (
        "period=current-month&amp;user_scope=selected"
        f"&amp;user_id={first_id}&amp;user_id={second_id}"
    ) in dashboard.text
    assert response.headers["content-disposition"] == (
        'attachment; filename="pipeline_export-user_second-export-user_'
        '2026-07-01_2026-07-31.csv"'
    )
    companies = [row["company_name"] for row in csv_rows(response)]
    assert "Month-end company" in companies
    assert "Outside company" not in companies
    assert "After month company" not in companies


def test_current_month_outreach_export_matches_dashboard_full_month_range(
    export_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, first_id, second_id = export_application
    query = (
        "period=current-month&user_scope=selected"
        f"&user_id={first_id}&user_id={second_id}"
    )
    dashboard = request_export(application, f"/dashboard?{query}")
    response = request_export(application, f"/exports/outreach.csv?{query}")

    assert "31 Jul 2026" in dashboard.text
    assert (
        "period=current-month&amp;user_scope=selected"
        f"&amp;user_id={first_id}&amp;user_id={second_id}"
    ) in dashboard.text
    assert response.headers["content-disposition"] == (
        'attachment; filename="outreach_export-user_second-export-user_'
        '2026-07-01_2026-07-31.csv"'
    )
    totals = [row["total_activities"] for row in csv_rows(response)]
    assert "31" in totals
    assert "99" not in totals
    assert "101" not in totals


def test_user_filters_multiple_duplicates_empty_and_unknown_are_safe(
    export_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, first_id, second_id = export_application
    for endpoint in ("pipeline", "outreach"):
        selected = request_export(
            application,
            f"/exports/{endpoint}.csv?user_scope=selected&user_id={first_id}",
        )
        assert {row["user_name"] for row in csv_rows(selected)} == {
            "  Export / User!!  ",
        }

        mixed = request_export(
            application,
            f"/exports/{endpoint}.csv?user_scope=selected"
            f"&user_id=invalid&user_id=999999&user_id={first_id}",
        )
        assert {row["user_name"] for row in csv_rows(mixed)} == {
            "  Export / User!!  ",
        }

        multiple = request_export(
            application,
            f"/exports/{endpoint}.csv?user_scope=selected"
            f"&user_id={first_id}&user_id={second_id}&user_id={first_id}",
        )
        assert {row["user_name"] for row in csv_rows(multiple)} == {
            "  Export / User!!  ",
            "Second Export User",
        }

        for suffix in ("", "&user_id=invalid&user_id=999999"):
            empty = request_export(
                application,
                f"/exports/{endpoint}.csv?user_scope=selected{suffix}",
            )
            assert csv_rows(empty) == []
            header = empty.content.decode("utf-8-sig").splitlines()[0]
            assert ";" in header
            assert "," not in header


def test_invalid_custom_range_returns_http_400(
    export_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, _, _ = export_application
    for endpoint in ("pipeline", "outreach"):
        response = request_export(
            application,
            f"/exports/{endpoint}.csv?period=custom"
            "&from=2026-07-15&to=2026-07-01",
        )
        assert response.status_code == 400
        assert response.text == "From cannot be later than To."


def test_dashboard_export_links_preserve_applied_filters(
    export_application: tuple[FastAPI, Engine, int, int],
) -> None:
    application, _, first_id, second_id = export_application
    response = request_export(
        application,
        "/dashboard?period=custom&from=2026-07-13&to=2026-07-14"
        f"&user_scope=selected&user_id={first_id}&user_id={second_id}",
    )

    expected_query = (
        "period=custom&amp;user_scope=selected&amp;from=2026-07-13"
        f"&amp;to=2026-07-14&amp;user_id={first_id}&amp;user_id={second_id}"
    )
    assert f'href="http://testserver/exports/pipeline.csv?{expected_query}"' in (
        response.text
    )
    assert f'href="http://testserver/exports/outreach.csv?{expected_query}"' in (
        response.text
    )
    assert (
        f'class="dashboard-csv-download" '
        f'href="http://testserver/exports/pipeline.csv?{expected_query}"'
        in response.text
    )
    assert (
        f'class="dashboard-csv-download" '
        f'href="http://testserver/exports/outreach.csv?{expected_query}"'
        in response.text
    )
    assert "Pipeline CSV" in response.text
    assert "Outreach CSV" in response.text
