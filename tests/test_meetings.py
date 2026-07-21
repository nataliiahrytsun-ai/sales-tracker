"""Integration tests for the private Record meeting workflow."""

import asyncio
from collections.abc import Generator
from datetime import date
from pathlib import Path
import re

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
    NeedIdentified,
    PipelineMeeting,
    PipelineOutcome,
    User,
    UserMood,
)
from app.services.meetings import BLOCKER_OPTIONS, COUNTRY_OPTIONS
from app.services.passwords import hash_password

ACTIVE_EMAIL = "meeting-user@example.com"
SECOND_EMAIL = "second-user@example.com"
TEST_PASSWORD = "meeting-test-password"
STYLESHEET_PATH = Path("app/static/css/app.css")


def css_rule(css: str, selector: str) -> str:
    """Return declarations for one selector from a CSS source section."""
    match = re.search(
        rf"(?m)^\s*{re.escape(selector)}\s*\{{(?P<body>[^}}]+)\}}",
        css,
    )
    assert match is not None
    return match.group("body")


@pytest.fixture
def meeting_application(
    tmp_path: Path,
) -> Generator[tuple[FastAPI, Engine, int, int], None, None]:
    """Create an isolated application with two active users."""
    database_url = f"sqlite:///{(tmp_path / 'meetings.db').as_posix()}"
    engine = create_db_engine(database_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        first_user = User(
            name="Meeting User",
            email=ACTIVE_EMAIL,
            password_hash=hash_password(TEST_PASSWORD),
        )
        second_user = User(
            name="Second User",
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
            session_secret="meeting-session-secret-with-at-least-32-characters",
            session_cookie_secure=False,
        ),
    )

    def override_get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_session] = override_get_session
    try:
        yield application, engine, first_user_id, second_user_id
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


async def login(client: httpx.AsyncClient) -> None:
    """Authenticate the primary meeting test user."""
    response = await client.post(
        "/login",
        data={"email": ACTIVE_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 303


def test_authenticated_user_can_open_meeting_form(
    meeting_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """The form uses the shared layout and exact documented options."""
    application, _, _, _ = meeting_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            response = await client.get("/meetings/new")

        assert response.status_code == 200
        assert 'action="http://testserver/meetings"' in response.text
        assert 'href="http://testserver/static/css/app.css"' in response.text
        assert (
            'class="field-section required-fields" '
            'aria-labelledby="required-fields-heading"'
        ) in response.text
        assert (
            'class="field-section optional-fields" '
            'aria-labelledby="optional-fields-heading"'
        ) in response.text
        assert response.text.count('<fieldset class="choice-section">') == 3
        assert response.text.count('type="radio"') == 13
        for value in (
            "Low",
            "Medium",
            "High",
            "Yes",
            "No",
            "Unclear",
            "No fit",
            "Follow-up",
            "Introduction",
            "Proposal requested",
            "Meeting booked",
            "Opportunity identified",
            "Difficult",
            "Okay",
            "Good",
            "Brazil",
            "Poland",
            "No budget",
            "Procurement/legal delay",
            "Other",
        ):
            assert value in response.text
        assert len(COUNTRY_OPTIONS) == 249
        assert response.text.count('data-country-code="') == 249
        assert 'type="search"' in response.text
        assert 'list="meeting_country_options"' in response.text
        assert 'name="country_code" value=""' in response.text
        assert '/static/js/meeting_country.js' in response.text
        normal_actions = re.search(
            r'<nav class="page-context-nav" aria-label="Meeting page actions">'
            r'(?P<actions>.*?)</nav>',
            response.text,
            re.DOTALL,
        )
        assert normal_actions is not None
        actions = normal_actions.group("actions")
        assert 'href="http://testserver/meetings/recent"' in actions
        assert "View / edit meetings" in actions
        assert 'href="http://testserver/my-week"' in actions
        assert "Go to My Week" in actions
        assert 'href="http://testserver/"' in actions
        assert "Back to Home" in actions
        assert "Add another meeting" not in actions
        assert 'action="http://testserver/meetings/' not in actions
        assert 'class="button' not in actions
        assert response.text.count(
            '<nav class="page-context-nav" aria-label="Meeting page actions">',
        ) == 1
        assert "Meeting saved successfully." not in response.text
        for code, country_name in (("BR", "Brazil"), ("PL", "Poland")):
            assert (
                f'<option value="{country_name}" data-country-code="{code}">'
                in response.text
            )

    asyncio.run(scenario())


def test_meeting_form_uses_exact_approved_blocker_values() -> None:
    """Blockers remain stable strings suitable for storage and reporting."""
    assert tuple(value for value, _label in BLOCKER_OPTIONS) == (
        "No budget",
        "No decision-maker",
        "No urgency",
        "Competitor",
        "Technical limitation",
        "Procurement/legal delay",
        "No response",
        "Other",
    )


def test_meeting_option_grids_are_structurally_responsive() -> None:
    """Mobile stacks options while desktop restores compact columns."""
    css = STYLESHEET_PATH.read_text(encoding="utf-8")
    mobile_css, desktop_css = css.split("@media (min-width: 48rem)", 1)

    universal_box = css_rule(mobile_css, "*")
    body = css_rule(mobile_css, "body")
    shell = css_rule(mobile_css, ".shell")
    page_content = css_rule(mobile_css, ".page-content")
    mobile_grid = css_rule(mobile_css, ".choice-grid")
    form_card = css_rule(mobile_css, ".form-card")
    meeting_form = css_rule(mobile_css, ".meeting-form")
    meeting_form_children = css_rule(mobile_css, ".meeting-form > *")
    field_section = css_rule(mobile_css, ".field-section")
    section_heading = css_rule(mobile_css, ".field-section-heading")
    section_heading_children = css_rule(
        mobile_css,
        ".field-section-heading > *",
    )
    section_heading_text = css_rule(
        mobile_css,
        ".field-section-heading p",
    )
    optional_fields = css_rule(mobile_css, ".optional-fields")
    page_actions = css_rule(mobile_css, ".page-context-nav")
    page_action_children = css_rule(mobile_css, ".page-context-nav > *")
    page_action_links = css_rule(mobile_css, ".page-context-nav a")
    page_action_focus = css_rule(
        mobile_css,
        ".page-context-nav a:focus-visible",
    )
    narrow_css = css.split("@media (max-width: 47.999rem)", 1)[1]
    narrow_page_actions = css_rule(narrow_css, ".page-context-nav")
    confirmation_actions = css_rule(mobile_css, ".confirmation-actions")
    confirmation_undo = css_rule(mobile_css, ".confirmation-undo")
    option_wrapper = css_rule(mobile_css, ".choice-button")
    option_target = css_rule(mobile_css, ".choice-button span")
    action_button = css_rule(mobile_css, ".button")

    assert "box-sizing: border-box" in universal_box
    assert "min-width: 0" in body
    assert "width: 100%" in shell
    assert "max-width: none" in shell
    assert "min-width: 0" in shell
    assert "margin-inline: 0" in shell
    assert "padding-inline: max(1rem, calc((100% - 68rem) / 2))" in shell
    assert "width: 100%" not in page_content
    assert "min-width: 0" in page_content

    assert "grid-template-columns: minmax(0, 1fr)" in mobile_grid
    assert "width: 100%" in mobile_grid
    assert "max-width: 100%" in mobile_grid
    assert "min-width: 0" in mobile_grid

    assert "width: 100%" in form_card
    assert "max-width: 52rem" in form_card
    assert "min-width: 0" in form_card
    assert "margin-inline: auto" in form_card
    assert "width: 100%" in meeting_form
    assert "min-width: 0" in meeting_form
    assert "max-width: 100%" in meeting_form_children
    assert "min-width: 0" in meeting_form_children
    assert "width: 100%" in field_section
    assert "max-width: 100%" in field_section
    assert "min-width: 0" in field_section
    assert "max-width: 100%" in section_heading
    assert "min-width: 0" in section_heading
    assert "max-width: 100%" in section_heading_children
    assert "min-width: 0" in section_heading_children
    assert "overflow-wrap: anywhere" in section_heading_text
    assert "min-width: 0" in optional_fields
    assert "display: flex" in page_actions
    assert "flex-wrap: wrap" in page_actions
    assert "column-gap: 1.25rem" in page_actions
    assert "row-gap: 0.75rem" in page_actions
    assert "margin-block: 1.5rem" in page_actions
    assert "min-width: 0" in page_actions
    assert "max-width: 100%" in page_action_children
    assert "min-width: 0" in page_action_children
    assert "text-decoration: underline" in page_action_links
    assert "outline: 0.2rem solid var(--focus)" in page_action_focus
    assert "outline-offset: 0.15rem" in page_action_focus
    assert "flex-direction: column" in narrow_page_actions
    assert "align-items: flex-start" in narrow_page_actions
    assert "column-gap: 1.25rem" in confirmation_actions
    assert "row-gap: 0.75rem" in confirmation_actions
    assert "flex: 0 0 auto" in confirmation_undo
    assert "margin: 0" in confirmation_undo

    assert "min-width: 0" in option_wrapper
    assert "width: 100%" in option_target
    assert "min-height: 2.75rem" in option_target
    assert "padding: 0.45rem 0.55rem" in option_target
    assert "font-size: 0.92rem" in option_target
    assert "line-height: 1.25" in option_target
    assert "overflow-wrap: anywhere" in option_target
    assert "white-space: normal" in option_target

    assert re.search(
        r"\.choice-grid,\s*\.choice-grid-wide\s*\{[^}]*"
        r"grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)",
        desktop_css,
    )

    # Save, Record another meeting, and Undo retain the shared 44 px target.
    assert "min-height: 2.75rem" in action_button
    assert "padding: 0.65rem 1rem" in action_button


def test_meeting_visual_states_use_accessible_existing_palette() -> None:
    """Visual emphasis preserves focus, contrast, and restrained sections."""
    css = STYLESHEET_PATH.read_text(encoding="utf-8")
    mobile_css, _desktop_css = css.split("@media (min-width: 48rem)", 1)

    selected = css_rule(
        mobile_css,
        ".choice-button input:checked + span",
    )
    keyboard_focus = css_rule(
        mobile_css,
        ".choice-button input:focus-visible + span",
    )
    hover = css_rule(mobile_css, ".choice-button:hover span")
    field_section = css_rule(mobile_css, ".field-section")
    required_fields = css_rule(mobile_css, ".required-fields")
    optional_fields = css_rule(mobile_css, ".optional-fields")
    confirmation = css_rule(mobile_css, ".confirmation-panel")

    assert "border: 2px solid var(--primary)" in selected
    assert "background: #edf2ff" in selected
    assert "color: #183d9b" in selected
    assert "box-shadow:" in selected
    assert "font-weight: 750" in selected

    assert "outline: 0.2rem solid var(--focus)" in keyboard_focus
    assert "outline-offset: 0.15rem" in keyboard_focus
    assert "@media (hover: hover)" in mobile_css
    assert "border-color: var(--primary)" in hover
    assert "background: var(--background)" in hover

    assert "border: 1px solid var(--border)" in field_section
    assert "background: var(--background)" in required_fields
    assert "background: var(--surface)" in optional_fields

    assert "border-color: var(--primary)" in confirmation
    assert "border-left-width: 0.35rem" in confirmation
    assert "background: #edf2ff" in confirmation
    assert "color: var(--text)" in confirmation
    assert "box-shadow:" in confirmation


def test_native_selects_use_the_shared_custom_arrow() -> None:
    """Every native select uses one padded, accessible arrow treatment."""
    css = STYLESHEET_PATH.read_text(encoding="utf-8")
    mobile_css, _desktop_css = css.split("@media (min-width: 48rem)", 1)
    select_rule = css_rule(mobile_css, "select")
    disabled_rule = css_rule(mobile_css, "select:disabled")

    assert "-webkit-appearance: none" in select_rule
    assert "appearance: none" in select_rule
    assert "padding-right: 2.75rem" in select_rule
    assert "background-image: url(" in select_rule
    assert "stroke-width='2.25'" in select_rule
    assert "background-repeat: no-repeat" in select_rule
    assert "background-position: right 0.85rem center" in select_rule
    assert "background-size: 1rem 0.625rem" in select_rule
    assert "opacity: 0.65" in disabled_rule
    assert "cursor: not-allowed" in disabled_rule


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/meetings/new"),
        ("POST", "/meetings"),
        ("POST", "/meetings/1/undo"),
    ],
)
def test_anonymous_meeting_routes_redirect_to_login(
    meeting_application: tuple[FastAPI, Engine, int, int],
    method: str,
    path: str,
) -> None:
    """Both meeting routes enforce authentication on the server."""
    application, _, _, _ = meeting_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.request(method, path)

        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    asyncio.run(scenario())


def test_successful_meeting_is_saved_for_current_user_only(
    meeting_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """A forged form user_id is ignored and all documented values persist."""
    application, engine, first_user_id, second_user_id = meeting_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            response = await client.post(
                "/meetings",
                data={
                    "user_id": str(second_user_id),
                    "customer_engagement": "High",
                    "need_identified": "Yes",
                    "outcome": "Proposal requested",
                    "user_mood": "Good",
                    "blocker_tag": "Procurement/legal delay",
                    "country_code": "BR",
                    "company_name": "Example GmbH",
                    "next_step_date": "2026-07-20",
                    "note": "Send the requested overview.",
                },
            )
            confirmation = await client.get(response.headers["location"])
            refreshed_confirmation = await client.get(
                response.headers["location"],
            )

        assert response.status_code == 303
        assert response.headers["location"] == "/meetings/new?saved=1"
        assert confirmation.status_code == 200
        assert refreshed_confirmation.status_code == 200
        assert 'class="success confirmation-panel" role="status"' in (
            confirmation.text
        )
        assert "Meeting saved successfully" in confirmation.text
        assert "Meeting saved successfully." in confirmation.text
        assert "The form below is ready for a new meeting." in confirmation.text
        panel_start = confirmation.text.index(
            '<div class="success confirmation-panel" role="status">',
        )
        navigation_start = confirmation.text.index(
            '<nav class="page-context-nav" aria-label="Meeting page actions">',
            panel_start,
        )
        panel = confirmation.text[panel_start:navigation_start]
        navigation = re.search(
            r'<nav class="page-context-nav" aria-label="Meeting page actions">'
            r'(?P<links>.*?)</nav>',
            confirmation.text[navigation_start:],
            re.DOTALL,
        )
        assert navigation is not None
        links = navigation.group("links")
        assert 'href="http://testserver/meetings/recent"' in links
        assert "View / edit meetings" in links
        assert 'href="http://testserver/my-week"' in links
        assert "Go to My Week" in links
        assert 'href="http://testserver/"' in links
        assert "Back to Home" in links
        assert 'class="button' not in links
        assert "Add another meeting" not in confirmation.text
        assert "page-context-nav" not in panel
        assert ">Undo</button>" in panel
        assert re.search(
            r'<form class="confirmation-undo" method="post" '
            r'action="http://testserver/meetings/\d+/undo">',
            panel,
        )
        assert "<a" not in re.search(
            r'<form class="confirmation-undo".*?</form>',
            panel,
            re.DOTALL,
        ).group(0)
        assert confirmation.text.count(
            '<nav class="page-context-nav" aria-label="Meeting page actions">',
        ) == 1
        assert 'id="meeting-next-entry">Record another meeting</p>' in (
            confirmation.text
        )
        assert 'aria-describedby="meeting-next-entry"' in confirmation.text

    asyncio.run(scenario())

    with Session(engine) as session:
        meetings = session.exec(select(PipelineMeeting)).all()
        assert len(meetings) == 1
        meeting = meetings[0]
        assert meeting.user_id == first_user_id
        assert meeting.user_id != second_user_id
        assert meeting.customer_engagement is CustomerEngagement.HIGH
        assert meeting.need_identified is NeedIdentified.YES
        assert meeting.outcome is PipelineOutcome.PROPOSAL_REQUESTED
        assert meeting.user_mood is UserMood.GOOD
        assert meeting.blocker_tag == "Procurement/legal delay"
        assert meeting.country_code == "BR"
        assert meeting.company_name == "Example GmbH"
        assert meeting.next_step_date == date(2026, 7, 20)
        assert meeting.note == "Send the requested overview."


def test_meeting_can_be_saved_with_only_required_fields(
    meeting_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """All optional product fields remain NULL when omitted."""
    application, engine, first_user_id, _ = meeting_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            response = await client.post(
                "/meetings",
                data={
                    "customer_engagement": "Low",
                    "need_identified": "Unclear",
                    "outcome": "Follow-up",
                },
            )

        assert response.status_code == 303

    asyncio.run(scenario())

    with Session(engine) as session:
        meeting = session.exec(select(PipelineMeeting)).one()
        assert meeting.user_id == first_user_id
        assert meeting.user_mood is None
        assert meeting.blocker_tag is None
        assert meeting.country_code is None
        assert meeting.company_name is None
        assert meeting.next_step_date is None
        assert meeting.note is None


def test_meeting_accepts_european_country_outside_dach(
    meeting_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """A valid worldwide ISO code is accepted outside the former DACH list."""
    application, engine, _, _ = meeting_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.post(
                "/meetings",
                data={
                    "customer_engagement": "Medium",
                    "need_identified": "Yes",
                    "outcome": "Follow-up",
                    "country_code": "PL",
                },
            )

    response = asyncio.run(scenario())
    assert response.status_code == 303
    with Session(engine) as session:
        assert session.exec(select(PipelineMeeting)).one().country_code == "PL"


def test_selected_country_is_preserved_after_other_validation_error(
    meeting_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """A valid country name and code survive a failed meeting submission."""
    application, engine, _, _ = meeting_application

    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            return await client.post(
                "/meetings",
                data={
                    "customer_engagement": "invalid",
                    "need_identified": "Yes",
                    "outcome": "Follow-up",
                    "country_code": "PL",
                },
            )

    response = asyncio.run(scenario())
    assert response.status_code == 400
    assert 'value="Poland"' in response.text
    assert 'name="country_code" value="PL"' in response.text
    with Session(engine) as session:
        assert session.exec(select(PipelineMeeting)).all() == []


def test_missing_required_fields_return_form_errors(
    meeting_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Missing required selections return HTML validation without a write."""
    application, engine, _, _ = meeting_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            response = await client.post("/meetings", data={})

        assert response.status_code == 400
        assert "Select customer engagement." in response.text
        assert "Select whether a need was identified." in response.text
        assert "Select a meeting outcome." in response.text

    asyncio.run(scenario())

    with Session(engine) as session:
        assert session.exec(select(PipelineMeeting)).all() == []


def test_invalid_values_are_rejected_and_safe_values_are_preserved(
    meeting_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Server validation rejects forged selectors and re-renders safe input."""
    application, engine, _, _ = meeting_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            response = await client.post(
                "/meetings",
                data={
                    "customer_engagement": "Extreme",
                    "need_identified": "Yes",
                    "outcome": "Follow-up",
                    "user_mood": "Neutral",
                    "blocker_tag": "free-text-blocker",
                    "country_code": "XX",
                    "company_name": '<script>alert("x")</script>',
                    "next_step_date": "not-a-date",
                    "note": "Safe retained note",
                },
            )

        assert response.status_code == 400
        assert "Select customer engagement." in response.text
        assert "Select a valid mood" in response.text
        assert "Select a valid blocker" in response.text
        assert "Select a valid country" in response.text
        assert "Enter a valid next-step date." in response.text
        assert "Safe retained note" in response.text
        assert "&lt;script&gt;" in response.text
        assert '<script>alert("x")</script>' not in response.text
        assert re.search(r'value="Yes"\s+checked', response.text)
        assert re.search(r'value="Follow-up"\s+checked', response.text)

    asyncio.run(scenario())

    with Session(engine) as session:
        assert session.exec(select(PipelineMeeting)).all() == []


def test_saved_meeting_can_be_undone_by_its_owner(
    meeting_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """The post-save Undo action removes the saved meeting."""
    application, engine, _, _ = meeting_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            created = await client.post(
                "/meetings",
                data={
                    "customer_engagement": "Medium",
                    "need_identified": "No",
                    "outcome": "Unclear",
                },
            )
            undo_url = created.headers["location"].replace(
                "/new?saved=",
                "/",
            ) + "/undo"
            undone = await client.post(undo_url)
            confirmation = await client.get(undone.headers["location"])

        assert undone.status_code == 303
        assert undone.headers["location"] == "/meetings/new?undone=true"
        assert "The meeting was removed." in confirmation.text

    asyncio.run(scenario())

    with Session(engine) as session:
        assert session.exec(select(PipelineMeeting)).all() == []


def test_undo_rejects_get_requests(
    meeting_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Undo is a state-changing action available only through POST."""
    application, engine, _, _ = meeting_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            created = await client.post(
                "/meetings",
                data={
                    "customer_engagement": "Medium",
                    "need_identified": "No",
                    "outcome": "Unclear",
                },
            )
            meeting_id = int(created.headers["location"].rsplit("=", 1)[1])
            response = await client.get(f"/meetings/{meeting_id}/undo")

        assert response.status_code == 405

    asyncio.run(scenario())

    with Session(engine) as session:
        assert len(session.exec(select(PipelineMeeting)).all()) == 1


def test_only_most_recently_created_meeting_can_be_undone(
    meeting_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Creating another meeting expires Undo for the previous meeting."""
    application, engine, _, _ = meeting_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            first = await client.post(
                "/meetings",
                data={
                    "customer_engagement": "Low",
                    "need_identified": "No",
                    "outcome": "No fit",
                },
            )
            first_id = int(first.headers["location"].rsplit("=", 1)[1])
            second = await client.post(
                "/meetings",
                data={
                    "customer_engagement": "High",
                    "need_identified": "Yes",
                    "outcome": "Follow-up",
                },
            )
            second_id = int(second.headers["location"].rsplit("=", 1)[1])

            stale_undo = await client.post(f"/meetings/{first_id}/undo")
            current_undo = await client.post(f"/meetings/{second_id}/undo")

        assert stale_undo.status_code == 404
        assert current_undo.status_code == 303

    asyncio.run(scenario())

    with Session(engine) as session:
        meetings = session.exec(select(PipelineMeeting)).all()
        assert len(meetings) == 1
        assert meetings[0].customer_engagement is CustomerEngagement.LOW


def test_record_another_meeting_opens_clean_form_and_expires_undo(
    meeting_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """The post-save action starts a clean entry and closes the Undo window."""
    application, engine, _, _ = meeting_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            created = await client.post(
                "/meetings",
                data={
                    "customer_engagement": "High",
                    "need_identified": "Yes",
                    "outcome": "Proposal requested",
                    "company_name": "Must not carry over",
                    "note": "Must also be cleared",
                },
            )
            meeting_id = int(created.headers["location"].rsplit("=", 1)[1])
            confirmation = await client.get(created.headers["location"])
            fresh_form = await client.get("/meetings/new")
            expired_undo = await client.post(f"/meetings/{meeting_id}/undo")

        assert "Meeting saved successfully" in confirmation.text
        assert 'href="http://testserver/meetings/recent"' in confirmation.text
        assert "Meeting saved successfully" not in fresh_form.text
        assert "Must not carry over" not in fresh_form.text
        assert "Must also be cleared" not in fresh_form.text
        assert " checked" not in fresh_form.text
        assert expired_undo.status_code == 404

    asyncio.run(scenario())

    with Session(engine) as session:
        assert len(session.exec(select(PipelineMeeting)).all()) == 1


def test_user_cannot_undo_another_users_meeting(
    meeting_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """Undo enforces record ownership on the server."""
    application, engine, _, second_user_id = meeting_application
    with Session(engine) as session:
        meeting = PipelineMeeting(
            user_id=second_user_id,
            customer_engagement=CustomerEngagement.HIGH,
            need_identified=NeedIdentified.YES,
            outcome=PipelineOutcome.FOLLOW_UP,
        )
        session.add(meeting)
        session.commit()
        session.refresh(meeting)
        assert meeting.id is not None
        meeting_id = meeting.id

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            response = await client.post(f"/meetings/{meeting_id}/undo")

        assert response.status_code == 404

    asyncio.run(scenario())

    with Session(engine) as session:
        assert session.get(PipelineMeeting, meeting_id) is not None


def test_save_confirmation_cannot_be_forged_or_viewed_by_another_user(
    meeting_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """A confirmation is shown only for an owned, existing meeting."""
    application, engine, _, second_user_id = meeting_application
    with Session(engine) as session:
        meeting = PipelineMeeting(
            user_id=second_user_id,
            customer_engagement=CustomerEngagement.LOW,
            need_identified=NeedIdentified.NO,
            outcome=PipelineOutcome.NO_FIT,
        )
        session.add(meeting)
        session.commit()
        session.refresh(meeting)
        assert meeting.id is not None
        meeting_id = meeting.id

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            other_users = await client.get(f"/meetings/new?saved={meeting_id}")
            missing = await client.get("/meetings/new?saved=999999")

        assert "Meeting saved successfully" not in other_users.text
        assert "Meeting saved successfully" not in missing.text

    asyncio.run(scenario())


def test_save_confirmation_is_limited_to_the_just_created_meeting(
    meeting_application: tuple[FastAPI, Engine, int, int],
) -> None:
    """An older owned record cannot be presented as the current save."""
    application, _, _, _ = meeting_application

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await login(client)
            first = await client.post(
                "/meetings",
                data={
                    "customer_engagement": "Low",
                    "need_identified": "No",
                    "outcome": "No fit",
                },
            )
            first_id = int(first.headers["location"].rsplit("=", 1)[1])
            second = await client.post(
                "/meetings",
                data={
                    "customer_engagement": "High",
                    "need_identified": "Yes",
                    "outcome": "Follow-up",
                },
            )
            second_id = int(second.headers["location"].rsplit("=", 1)[1])

            stale = await client.get(f"/meetings/new?saved={first_id}")
            current = await client.get(f"/meetings/new?saved={second_id}")

        assert "Meeting saved successfully" not in stale.text
        assert "Meeting saved successfully" in current.text

    asyncio.run(scenario())
