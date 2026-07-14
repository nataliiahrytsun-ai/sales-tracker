"""Tests for product database models and constraints."""

from collections.abc import Generator
from datetime import date
from pathlib import Path
from time import sleep

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, select

from app.database import create_db_engine
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


@pytest.fixture
def db_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    """Create an isolated database containing the model metadata."""
    database_url = f"sqlite:///{(tmp_path / 'models.db').as_posix()}"
    engine = create_db_engine(database_url)
    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def make_user(email: str = "user@example.com") -> User:
    """Build a valid user without implementing registration behavior."""
    return User(
        name="Test User",
        email=email,
        password_hash="not-a-plaintext-password",
    )


def make_outreach(user_id: int, activity_date: date) -> DailyOutreach:
    """Build a daily outreach record with only required fields."""
    return DailyOutreach(
        user_id=user_id,
        activity_date=activity_date,
        total_activities=10,
        unique_companies=5,
    )


def test_expected_product_tables_are_registered() -> None:
    """SQLModel metadata contains exactly the documented product tables."""
    assert set(SQLModel.metadata.tables) == {
        "daily_outreach",
        "outreach_countries",
        "pipeline_meetings",
        "targets",
        "users",
    }


def test_model_columns_match_implementation_plan() -> None:
    """Each product table contains exactly its documented fields."""
    expected_columns = {
        User: {"id", "name", "email", "password_hash", "active", "created_at"},
        PipelineMeeting: {
            "id",
            "user_id",
            "occurred_at",
            "company_name",
            "country_code",
            "customer_engagement",
            "need_identified",
            "outcome",
            "user_mood",
            "blocker_tag",
            "next_step_date",
            "note",
            "created_at",
            "updated_at",
        },
        DailyOutreach: {
            "id",
            "user_id",
            "activity_date",
            "total_activities",
            "unique_companies",
            "replies",
            "positive_replies",
            "meetings_booked",
            "user_mood",
            "blocker_tag",
            "note",
            "created_at",
            "updated_at",
        },
        OutreachCountry: {
            "id",
            "outreach_daily_id",
            "country_code",
            "companies_contacted",
        },
        Target: {
            "id",
            "user_id",
            "metric_name",
            "target_value",
            "effective_from",
            "effective_until",
        },
    }

    for model, column_names in expected_columns.items():
        assert set(model.__table__.c.keys()) == column_names


def test_model_relationships_round_trip(db_engine: Engine) -> None:
    """User, meeting, outreach, country, and target relationships persist."""
    with Session(db_engine) as session:
        user = make_user()
        session.add(user)
        session.flush()
        assert user.id is not None

        meeting = PipelineMeeting(
            user_id=user.id,
            customer_engagement=CustomerEngagement.HIGH,
            need_identified=NeedIdentified.YES,
            outcome=PipelineOutcome.FOLLOW_UP,
        )
        outreach = make_outreach(user.id, date(2026, 7, 14))
        country = OutreachCountry(
            country_code="AT",
            companies_contacted=5,
        )
        outreach.countries.append(country)
        target = Target(
            user_id=user.id,
            metric_name="total_activities",
            target_value=50,
            effective_from=date(2026, 7, 1),
        )
        session.add(meeting)
        session.add(outreach)
        session.add(target)
        session.commit()

        session.refresh(user)
        assert user.pipeline_meetings == [meeting]
        assert user.daily_outreach == [outreach]
        assert user.targets == [target]
        assert outreach.countries == [country]
        assert country.outreach_daily == outreach


def test_user_email_is_unique(db_engine: Engine) -> None:
    """The database rejects duplicate user email addresses."""
    with Session(db_engine) as session:
        session.add(make_user(email="duplicate@example.com"))
        session.add(make_user(email="duplicate@example.com"))

        with pytest.raises(IntegrityError):
            session.commit()


def test_user_is_active_by_default(db_engine: Engine) -> None:
    """New users default to active in the model and database."""
    user = make_user()
    assert user.active is True

    with Session(db_engine) as session:
        session.add(user)
        session.commit()
        session.refresh(user)

        assert user.active is True


def test_updated_at_changes_when_records_are_updated(
    db_engine: Engine,
) -> None:
    """Meeting and outreach update timestamps advance on persisted changes."""
    with Session(db_engine) as session:
        user = make_user()
        session.add(user)
        session.flush()
        assert user.id is not None

        meeting = PipelineMeeting(
            user_id=user.id,
            customer_engagement=CustomerEngagement.HIGH,
            need_identified=NeedIdentified.YES,
            outcome=PipelineOutcome.FOLLOW_UP,
        )
        outreach = make_outreach(user.id, date(2026, 7, 14))
        session.add(meeting)
        session.add(outreach)
        session.commit()
        session.refresh(meeting)
        session.refresh(outreach)

        original_meeting_updated_at = meeting.updated_at
        sleep(0.01)
        meeting.note = "Updated meeting"
        session.commit()
        session.refresh(meeting)
        assert meeting.updated_at > original_meeting_updated_at

        session.refresh(outreach)
        original_outreach_updated_at = outreach.updated_at
        sleep(0.01)
        outreach.note = "Updated outreach"
        session.commit()
        session.refresh(outreach)

        assert outreach.updated_at > original_outreach_updated_at


def test_daily_outreach_is_unique_per_user_and_date(
    db_engine: Engine,
) -> None:
    """The database rejects duplicate user/date outreach summaries."""
    activity_date = date(2026, 7, 14)
    with Session(db_engine) as session:
        user = make_user()
        session.add(user)
        session.flush()
        assert user.id is not None

        session.add(make_outreach(user.id, activity_date))
        session.commit()
        session.add(make_outreach(user.id, activity_date))

        with pytest.raises(IntegrityError):
            session.commit()


def test_foreign_keys_are_enforced(db_engine: Engine) -> None:
    """A meeting cannot reference a user that does not exist."""
    with Session(db_engine) as session:
        session.add(
            PipelineMeeting(
                user_id=999,
                customer_engagement=CustomerEngagement.LOW,
                need_identified=NeedIdentified.NO,
                outcome=PipelineOutcome.NO_FIT,
            ),
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_optional_mood_remains_null(db_engine: Engine) -> None:
    """Omitted meeting and outreach moods are persisted as NULL."""
    with Session(db_engine) as session:
        user = make_user()
        session.add(user)
        session.flush()
        assert user.id is not None

        meeting = PipelineMeeting(
            user_id=user.id,
            customer_engagement=CustomerEngagement.MEDIUM,
            need_identified=NeedIdentified.UNCLEAR,
            outcome=PipelineOutcome.UNCLEAR,
        )
        outreach = make_outreach(user.id, date(2026, 7, 14))
        session.add(meeting)
        session.add(outreach)
        session.commit()

        stored_meeting = session.exec(select(PipelineMeeting)).one()
        stored_outreach = session.exec(select(DailyOutreach)).one()
        assert stored_meeting.user_mood is None
        assert stored_outreach.user_mood is None


def test_documented_optional_columns_are_nullable() -> None:
    """Every optional workflow field is nullable in database metadata."""
    meeting_columns = PipelineMeeting.__table__.c
    outreach_columns = DailyOutreach.__table__.c

    for column_name in {
        "blocker_tag",
        "company_name",
        "country_code",
        "next_step_date",
        "note",
        "user_mood",
    }:
        assert meeting_columns[column_name].nullable

    for column_name in {
        "blocker_tag",
        "meetings_booked",
        "note",
        "positive_replies",
        "replies",
        "user_mood",
    }:
        assert outreach_columns[column_name].nullable


def test_documented_enum_values_are_exact() -> None:
    """Structured meeting and mood values match the implementation plan."""
    assert [item.value for item in CustomerEngagement] == [
        "Low",
        "Medium",
        "High",
    ]
    assert [item.value for item in NeedIdentified] == [
        "Yes",
        "No",
        "Unclear",
    ]
    assert [item.value for item in PipelineOutcome] == [
        "No fit",
        "Follow-up",
        "Introduction",
        "Proposal requested",
        "Meeting booked",
        "Opportunity identified",
        "Unclear",
    ]
    assert [item.value for item in UserMood] == [
        "Difficult",
        "Okay",
        "Good",
    ]
