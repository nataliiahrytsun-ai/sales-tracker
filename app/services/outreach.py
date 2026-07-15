"""Validation and persistence for today's daily outreach workflow."""

from dataclasses import dataclass
from datetime import date, timedelta
from itertools import zip_longest

from sqlmodel import Session, select

from app.countries import COUNTRY_CODES, COUNTRY_NAMES_BY_CODE, COUNTRY_OPTIONS
from app.models import DailyOutreach, OutreachCountry, UserMood
from app.services.meetings import (
    BLOCKER_OPTIONS,
    BLOCKER_VALUES,
)


@dataclass(frozen=True)
class CountryFormValue:
    """One submitted country row retained for validation re-rendering."""

    country_code: str
    companies_contacted: str


@dataclass(frozen=True)
class OutreachFormValues:
    """Submitted strings retained for safe form re-rendering."""

    total_activities: str = ""
    country_rows: tuple[CountryFormValue, ...] = ()
    replies: str = ""
    positive_replies: str = ""
    meetings_booked: str = ""
    user_mood: str = ""
    blocker_tag: str = ""
    note: str = ""


@dataclass(frozen=True)
class ValidatedOutreachValues:
    """Typed values ready for the existing outreach models."""

    total_activities: int
    country_counts: tuple[tuple[str, int], ...]
    replies: int | None
    positive_replies: int | None
    meetings_booked: int | None
    user_mood: UserMood | None
    blocker_tag: str | None
    note: str | None

    @property
    def country_total(self) -> int:
        """Return the number of companies represented by country rows."""
        return sum(count for _code, count in self.country_counts)


def current_local_date() -> date:
    """Return today's date in the application process's local timezone."""
    return date.today()


def _optional_text(value: str) -> str | None:
    cleaned_value = value.strip()
    return cleaned_value or None


def country_rows_from_submission(
    country_codes: list[str],
    country_counts: list[str],
) -> tuple[CountryFormValue, ...]:
    """Pair repeated form fields without silently dropping malformed rows."""
    return tuple(
        CountryFormValue(
            country_code=(code or "").strip().upper(),
            companies_contacted=count or "",
        )
        for code, count in zip_longest(
            country_codes,
            country_counts,
            fillvalue="",
        )
    )


def _parse_counter(
    value: str,
    *,
    field: str,
    label: str,
    required: bool,
    errors: dict[str, str],
) -> int | None:
    """Parse one required or optional non-negative integer counter."""
    cleaned_value = value.strip()
    if not cleaned_value:
        if required:
            errors[field] = f"Enter {label}."
        return None

    try:
        parsed_value = int(cleaned_value)
    except ValueError:
        errors[field] = f"Enter a whole number for {label}."
        return None

    if parsed_value < 0:
        errors[field] = f"{label[0].upper()}{label[1:]} cannot be negative."
        return None
    return parsed_value


def validate_outreach_form(
    values: OutreachFormValues,
) -> tuple[ValidatedOutreachValues | None, dict[str, str]]:
    """Validate the exact required and optional outreach plan fields."""
    errors: dict[str, str] = {}
    total_activities = _parse_counter(
        values.total_activities,
        field="total_activities",
        label="total outreach activities",
        required=True,
        errors=errors,
    )
    country_counts: list[tuple[str, int]] = []
    seen_country_codes: set[str] = set()
    for index, row in enumerate(values.country_rows):
        code = row.country_code.strip().upper()
        if code not in COUNTRY_CODES:
            errors["countries"] = "Select only countries from the available list."
            continue
        if code in seen_country_codes:
            errors["countries"] = "Each country can be added only once."
            continue
        seen_country_codes.add(code)

        label = COUNTRY_NAMES_BY_CODE[code]
        count = _parse_counter(
            row.companies_contacted,
            field=f"country_count_{index}",
            label=f"companies contacted in {label}",
            required=True,
            errors=errors,
        )
        if count is not None:
            country_counts.append((code, count))

    replies = _parse_counter(
        values.replies,
        field="replies",
        label="replies received",
        required=False,
        errors=errors,
    )
    positive_replies = _parse_counter(
        values.positive_replies,
        field="positive_replies",
        label="positive replies",
        required=False,
        errors=errors,
    )
    if positive_replies is not None:
        if replies is None and not values.replies.strip():
            errors["positive_replies"] = (
                "Positive replies cannot exceed replies received."
            )
        elif replies is not None and positive_replies > replies:
            errors["positive_replies"] = (
                "Positive replies cannot exceed replies received."
            )
    meetings_booked = _parse_counter(
        values.meetings_booked,
        field="meetings_booked",
        label="meetings booked",
        required=False,
        errors=errors,
    )

    user_mood: UserMood | None = None
    if values.user_mood:
        try:
            user_mood = UserMood(values.user_mood)
        except ValueError:
            errors["user_mood"] = "Select a valid mood or leave it empty."

    blocker_tag = _optional_text(values.blocker_tag)
    if blocker_tag is not None and blocker_tag not in BLOCKER_VALUES:
        errors["blocker_tag"] = "Select a valid blocker or leave it empty."

    if errors:
        return None, errors

    assert total_activities is not None
    return (
        ValidatedOutreachValues(
            total_activities=total_activities,
            country_counts=tuple(country_counts),
            replies=replies,
            positive_replies=positive_replies,
            meetings_booked=meetings_booked,
            user_mood=user_mood,
            blocker_tag=blocker_tag,
            note=_optional_text(values.note),
        ),
        {},
    )


def get_daily_outreach(
    session: Session,
    *,
    user_id: int,
    activity_date: date,
) -> DailyOutreach | None:
    """Return only the owning user's outreach record for one date."""
    return session.exec(
        select(DailyOutreach).where(
            DailyOutreach.user_id == user_id,
            DailyOutreach.activity_date == activity_date,
        ),
    ).one_or_none()


def get_recent_outreach(
    session: Session,
    *,
    user_id: int,
    today: date,
) -> list[DailyOutreach]:
    """Return the user's outreach summaries from the last 30 calendar days."""
    start_date = today - timedelta(days=29)
    return list(
        session.exec(
            select(DailyOutreach)
            .where(
                DailyOutreach.user_id == user_id,
                DailyOutreach.activity_date >= start_date,
                DailyOutreach.activity_date <= today,
            )
            .order_by(DailyOutreach.activity_date.desc()),
        ).all(),
    )


def form_values_from_record(
    session: Session,
    record: DailyOutreach,
) -> OutreachFormValues:
    """Convert one owned database record back into editable form strings."""
    assert record.id is not None
    stored_countries = session.exec(
        select(OutreachCountry).where(
            OutreachCountry.outreach_daily_id == record.id,
        ),
    ).all()
    country_rows = tuple(
        CountryFormValue(
            country_code=country.country_code,
            companies_contacted=str(country.companies_contacted),
        )
        for country in sorted(
            stored_countries,
            key=lambda item: COUNTRY_NAMES_BY_CODE.get(
                item.country_code,
                item.country_code,
            ),
        )
    )

    return OutreachFormValues(
        total_activities=str(record.total_activities),
        country_rows=country_rows,
        replies="" if record.replies is None else str(record.replies),
        positive_replies=(
            "" if record.positive_replies is None else str(record.positive_replies)
        ),
        meetings_booked=(
            "" if record.meetings_booked is None else str(record.meetings_booked)
        ),
        user_mood="" if record.user_mood is None else record.user_mood.value,
        blocker_tag=record.blocker_tag or "",
        note=record.note or "",
    )


def upsert_daily_outreach(
    session: Session,
    *,
    user_id: int,
    activity_date: date,
    values: ValidatedOutreachValues,
) -> DailyOutreach:
    """Create or update the single outreach row for a user and date."""
    record = get_daily_outreach(
        session,
        user_id=user_id,
        activity_date=activity_date,
    )
    if record is None:
        record = DailyOutreach(
            user_id=user_id,
            activity_date=activity_date,
            total_activities=values.total_activities,
            unique_companies=values.country_total,
        )

    record.total_activities = values.total_activities
    record.unique_companies = values.country_total
    record.replies = values.replies
    record.positive_replies = values.positive_replies
    record.meetings_booked = values.meetings_booked
    record.user_mood = values.user_mood
    record.blocker_tag = values.blocker_tag
    record.note = values.note
    session.add(record)
    session.flush()
    assert record.id is not None

    stored_countries = session.exec(
        select(OutreachCountry).where(
            OutreachCountry.outreach_daily_id == record.id,
        ),
    ).all()
    stored_by_code = {
        country.country_code: country for country in stored_countries
    }

    for code, count in values.country_counts:
        country = stored_by_code.pop(code, None)
        if country is None:
            country = OutreachCountry(
                outreach_daily_id=record.id,
                country_code=code,
                companies_contacted=count,
            )
        else:
            country.companies_contacted = count
        session.add(country)

    for removed_country in stored_by_code.values():
        session.delete(removed_country)
    return record


__all__ = [
    "BLOCKER_OPTIONS",
    "COUNTRY_CODES",
    "COUNTRY_NAMES_BY_CODE",
    "COUNTRY_OPTIONS",
    "CountryFormValue",
    "OutreachFormValues",
    "ValidatedOutreachValues",
    "current_local_date",
    "country_rows_from_submission",
    "form_values_from_record",
    "get_daily_outreach",
    "get_recent_outreach",
    "upsert_daily_outreach",
    "validate_outreach_form",
]
