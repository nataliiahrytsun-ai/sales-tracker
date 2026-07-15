"""Validation and stable options for pipeline meeting entry."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlmodel import Session, select

from app.countries import COUNTRY_CODES, COUNTRY_NAMES_BY_CODE, COUNTRY_OPTIONS
from app.models import (
    CustomerEngagement,
    NeedIdentified,
    PipelineMeeting,
    PipelineOutcome,
    UserMood,
)

BLOCKER_OPTIONS = (
    ("No budget", "No budget"),
    ("No decision-maker", "No decision-maker"),
    ("No urgency", "No urgency"),
    ("Competitor", "Competitor"),
    ("Technical limitation", "Technical limitation"),
    ("Procurement/legal delay", "Procurement/legal delay"),
    ("No response", "No response"),
    ("Other", "Other"),
)

BLOCKER_VALUES = {value for value, _label in BLOCKER_OPTIONS}


@dataclass(frozen=True)
class MeetingFormValues:
    """Submitted strings retained for safe form re-rendering."""

    customer_engagement: str = ""
    need_identified: str = ""
    outcome: str = ""
    user_mood: str = ""
    blocker_tag: str = ""
    country_code: str = ""
    company_name: str = ""
    next_step_date: str = ""
    note: str = ""


@dataclass(frozen=True)
class ValidatedMeetingValues:
    """Typed values ready for the existing PipelineMeeting model."""

    customer_engagement: CustomerEngagement
    need_identified: NeedIdentified
    outcome: PipelineOutcome
    user_mood: UserMood | None
    blocker_tag: str | None
    country_code: str | None
    company_name: str | None
    next_step_date: date | None
    note: str | None


def meeting_date_bounds(
    start_date: date,
    end_date: date,
) -> tuple[datetime, datetime]:
    """Return UTC bounds for an inclusive local calendar-date range."""
    start_local = datetime.combine(start_date, time.min)
    end_local = datetime.combine(end_date + timedelta(days=1), time.min)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def form_values_from_meeting(meeting: PipelineMeeting) -> MeetingFormValues:
    """Convert a stored meeting into editable form strings."""
    return MeetingFormValues(
        customer_engagement=meeting.customer_engagement.value,
        need_identified=meeting.need_identified.value,
        outcome=meeting.outcome.value,
        user_mood="" if meeting.user_mood is None else meeting.user_mood.value,
        blocker_tag=meeting.blocker_tag or "",
        country_code=meeting.country_code or "",
        company_name=meeting.company_name or "",
        next_step_date=(
            "" if meeting.next_step_date is None else meeting.next_step_date.isoformat()
        ),
        note=meeting.note or "",
    )


def apply_meeting_values(
    meeting: PipelineMeeting,
    values: ValidatedMeetingValues,
) -> None:
    """Apply validated form values to a new or existing meeting."""
    meeting.customer_engagement = values.customer_engagement
    meeting.need_identified = values.need_identified
    meeting.outcome = values.outcome
    meeting.user_mood = values.user_mood
    meeting.blocker_tag = values.blocker_tag
    meeting.country_code = values.country_code
    meeting.company_name = values.company_name
    meeting.next_step_date = values.next_step_date
    meeting.note = values.note


def get_recent_meetings(
    session: Session,
    *,
    user_id: int,
    start_date: date,
    end_date: date,
) -> list[PipelineMeeting]:
    """Return the user's meetings in one inclusive calendar-date range."""
    start, end = meeting_date_bounds(start_date, end_date)
    return list(
        session.exec(
            select(PipelineMeeting)
            .where(
                PipelineMeeting.user_id == user_id,
                PipelineMeeting.occurred_at >= start,
                PipelineMeeting.occurred_at < end,
            )
            .order_by(PipelineMeeting.occurred_at.desc()),
        ).all(),
    )


def get_owned_meeting(
    session: Session,
    *,
    meeting_id: int,
    user_id: int,
) -> PipelineMeeting | None:
    """Return one meeting only when it belongs to the requested user."""
    return session.exec(
        select(PipelineMeeting).where(
            PipelineMeeting.id == meeting_id,
            PipelineMeeting.user_id == user_id,
        ),
    ).one_or_none()


def _optional_text(value: str) -> str | None:
    cleaned_value = value.strip()
    return cleaned_value or None


def validate_meeting_form(
    values: MeetingFormValues,
) -> tuple[ValidatedMeetingValues | None, dict[str, str]]:
    """Validate required enums and constrained optional meeting values."""
    errors: dict[str, str] = {}

    try:
        customer_engagement = CustomerEngagement(values.customer_engagement)
    except ValueError:
        customer_engagement = None
        errors["customer_engagement"] = "Select customer engagement."

    try:
        need_identified = NeedIdentified(values.need_identified)
    except ValueError:
        need_identified = None
        errors["need_identified"] = "Select whether a need was identified."

    try:
        outcome = PipelineOutcome(values.outcome)
    except ValueError:
        outcome = None
        errors["outcome"] = "Select a meeting outcome."

    user_mood: UserMood | None = None
    if values.user_mood:
        try:
            user_mood = UserMood(values.user_mood)
        except ValueError:
            errors["user_mood"] = "Select a valid mood or leave it empty."

    blocker_tag = _optional_text(values.blocker_tag)
    if blocker_tag is not None and blocker_tag not in BLOCKER_VALUES:
        errors["blocker_tag"] = "Select a valid blocker or leave it empty."

    country_code = _optional_text(values.country_code)
    if country_code is not None and country_code not in COUNTRY_CODES:
        errors["country_code"] = "Select a valid country or leave it empty."

    parsed_next_step_date: date | None = None
    if values.next_step_date:
        try:
            parsed_next_step_date = date.fromisoformat(values.next_step_date)
        except ValueError:
            errors["next_step_date"] = "Enter a valid next-step date."

    if errors:
        return None, errors

    assert customer_engagement is not None
    assert need_identified is not None
    assert outcome is not None
    return (
        ValidatedMeetingValues(
            customer_engagement=customer_engagement,
            need_identified=need_identified,
            outcome=outcome,
            user_mood=user_mood,
            blocker_tag=blocker_tag,
            country_code=country_code,
            company_name=_optional_text(values.company_name),
            next_step_date=parsed_next_step_date,
            note=_optional_text(values.note),
        ),
        {},
    )
