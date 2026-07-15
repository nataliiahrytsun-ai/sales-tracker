"""SQLModel entities defined by the product implementation plan."""

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    Enum as SQLAlchemyEnum,
    UniqueConstraint,
    true,
)
from sqlmodel import Field, Relationship, SQLModel


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)


def enum_column(
    enum_class: type[StrEnum],
    name: str,
    *,
    nullable: bool = False,
) -> Column[Any]:
    """Create a constrained string enum column using enum values."""
    return Column(
        SQLAlchemyEnum(
            enum_class,
            name=name,
            native_enum=False,
            create_constraint=True,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=nullable,
    )


class CustomerEngagement(StrEnum):
    """Allowed customer engagement values."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class NeedIdentified(StrEnum):
    """Allowed need-identification values."""

    YES = "Yes"
    NO = "No"
    UNCLEAR = "Unclear"


class PipelineOutcome(StrEnum):
    """Allowed pipeline meeting outcomes."""

    NO_FIT = "No fit"
    FOLLOW_UP = "Follow-up"
    INTRODUCTION = "Introduction"
    PROPOSAL_REQUESTED = "Proposal requested"
    MEETING_BOOKED = "Meeting booked"
    OPPORTUNITY_IDENTIFIED = "Opportunity identified"
    UNCLEAR = "Unclear"


class UserMood(StrEnum):
    """Allowed optional employee sentiment values."""

    DIFFICULT = "Difficult"
    OKAY = "Okay"
    GOOD = "Good"


class User(SQLModel, table=True):
    """Authenticated application user data."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str
    email: str
    password_hash: str
    active: bool = Field(
        default=True,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default=true(),
        ),
    )
    created_at: datetime = Field(default_factory=utc_now)

    pipeline_meetings: list["PipelineMeeting"] = Relationship(
        back_populates="user",
    )
    daily_outreach: list["DailyOutreach"] = Relationship(
        back_populates="user",
    )
    targets: list["Target"] = Relationship(back_populates="user")


class PipelineMeeting(SQLModel, table=True):
    """Structured result of a short pipeline meeting."""

    __tablename__ = "pipeline_meetings"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    occurred_at: datetime = Field(default_factory=utc_now)
    company_name: str | None = None
    country_code: str | None = None
    customer_engagement: CustomerEngagement = Field(
        sa_column=enum_column(
            CustomerEngagement,
            "customer_engagement",
        ),
    )
    need_identified: NeedIdentified = Field(
        sa_column=enum_column(NeedIdentified, "need_identified"),
    )
    outcome: PipelineOutcome = Field(
        sa_column=enum_column(PipelineOutcome, "pipeline_outcome"),
    )
    user_mood: UserMood | None = Field(
        default=None,
        sa_column=enum_column(UserMood, "user_mood", nullable=True),
    )
    blocker_tag: str | None = None
    next_step_date: date | None = None
    note: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column_kwargs={"onupdate": utc_now},
    )

    user: User = Relationship(back_populates="pipeline_meetings")


class DailyOutreach(SQLModel, table=True):
    """One outbound outreach summary per user and activity date."""

    __tablename__ = "daily_outreach"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "activity_date",
            name="uq_daily_outreach_user_activity_date",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    activity_date: date = Field(default_factory=date.today)
    total_activities: int
    unique_companies: int
    replies: int | None = None
    positive_replies: int | None = None
    meetings_booked: int | None = None
    user_mood: UserMood | None = Field(
        default=None,
        sa_column=enum_column(UserMood, "outreach_user_mood", nullable=True),
    )
    blocker_tag: str | None = None
    note: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column_kwargs={"onupdate": utc_now},
    )

    user: User = Relationship(back_populates="daily_outreach")
    countries: list["OutreachCountry"] = Relationship(
        back_populates="outreach_daily",
    )


class OutreachCountry(SQLModel, table=True):
    """Per-country company count for a daily outreach record."""

    __tablename__ = "outreach_countries"
    __table_args__ = (
        UniqueConstraint(
            "outreach_daily_id",
            "country_code",
            name="uq_outreach_countries_daily_country",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    outreach_daily_id: int = Field(foreign_key="daily_outreach.id")
    country_code: str
    companies_contacted: int

    outreach_daily: DailyOutreach = Relationship(back_populates="countries")


class Target(SQLModel, table=True):
    """Time-bounded activity target for a user."""

    __tablename__ = "targets"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    metric_name: str
    target_value: float
    effective_from: date
    effective_until: date | None = None

    user: User = Relationship(back_populates="targets")
