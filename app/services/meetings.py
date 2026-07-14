"""Validation and stable options for pipeline meeting entry."""

from dataclasses import dataclass
from datetime import date

from app.models import (
    CustomerEngagement,
    NeedIdentified,
    PipelineOutcome,
    UserMood,
)

COUNTRY_OPTIONS = (
    ("DE", "Germany"),
    ("AT", "Austria"),
    ("CH", "Switzerland"),
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

COUNTRY_CODES = {value for value, _label in COUNTRY_OPTIONS}
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
