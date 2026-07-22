"""Validation and persistence for personal weekly targets."""

from dataclasses import dataclass, fields
from datetime import date, timedelta

from sqlmodel import Session, select

from app.models import Target


TARGET_FIELDS = (
    ("companies_contacted", "Companies contacted"),
    ("replies", "Replies received"),
    ("positive_replies", "Positive replies"),
    ("meetings_booked", "Meetings booked"),
    ("meetings_held", "Meetings held"),
    ("requests_sent", "Requests sent"),
)
TARGET_METRICS = tuple(metric for metric, _label in TARGET_FIELDS)
EDITABLE_TARGET_FIELDS = TARGET_FIELDS
EDITABLE_TARGET_METRICS = TARGET_METRICS


@dataclass(frozen=True)
class TargetFormValues:
    """Raw weekly-target values retained for form redisplay."""

    companies_contacted: str = ""
    replies: str = ""
    positive_replies: str = ""
    meetings_booked: str = ""
    meetings_held: str = ""
    requests_sent: str = ""


@dataclass(frozen=True)
class TargetWeek:
    """One validated ISO calendar week."""

    value: str
    iso_year: int
    iso_week: int
    start_date: date
    end_date: date


@dataclass(frozen=True)
class TargetWeekPresentation:
    """English presentation parts for the selected ISO week."""

    relative_label: str | None
    week_label: str
    date_range: str

    @property
    def picker_label(self) -> str:
        return f"{self.week_label} · {self.date_range}"


def current_week_bounds(today: date) -> tuple[date, date]:
    """Return Monday and Sunday for the week containing today."""
    week_start = today - timedelta(days=today.weekday())
    return week_start, week_start + timedelta(days=6)


def iso_week_value(value: date) -> str:
    """Return the HTML week-control value for a date."""
    iso_year, iso_week, _ = value.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def _short_english_date(value: date, *, include_year: bool = False) -> str:
    months = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
    label = f"{value.day} {months[value.month - 1]}"
    return f"{label} {value.year}" if include_year else label


def target_week_presentation(
    week: TargetWeek,
    *,
    today: date,
) -> TargetWeekPresentation:
    """Return compact English display parts for one selected week."""
    current_start, _ = current_week_bounds(today)
    relative_label = None
    if week.start_date == current_start:
        relative_label = "Current week"
    elif week.start_date == current_start - timedelta(days=7):
        relative_label = "Previous week"
    elif week.start_date == current_start + timedelta(days=7):
        relative_label = "Next week"
    start = _short_english_date(
        week.start_date,
        include_year=week.start_date.year != week.end_date.year,
    )
    end = _short_english_date(week.end_date, include_year=True)
    return TargetWeekPresentation(
        relative_label=relative_label,
        week_label=f"Week {week.iso_week}",
        date_range=f"{start} – {end}",
    )


def resolve_target_week(
    raw_week: str | None,
    *,
    today: date,
) -> tuple[TargetWeek | None, str | None]:
    """Validate an ISO week and derive its authoritative Monday–Sunday dates."""
    week_value = (raw_week or iso_week_value(today)).strip()
    try:
        year_text, week_text = week_value.split("-W", maxsplit=1)
        if len(year_text) != 4 or len(week_text) != 2:
            raise ValueError
        iso_year = int(year_text)
        iso_week = int(week_text)
        week_start = date.fromisocalendar(iso_year, iso_week, 1)
    except (TypeError, ValueError):
        return None, "Select a valid ISO calendar week."
    return (
        TargetWeek(
            value=week_value,
            iso_year=iso_year,
            iso_week=iso_week,
            start_date=week_start,
            end_date=week_start + timedelta(days=6),
        ),
        None,
    )


def get_user_targets(
    session: Session,
    *,
    user_id: int,
    week_start: date,
) -> list[Target]:
    """Return one user's target rows for one canonical calendar week."""
    return list(
        session.exec(
            select(Target)
            .where(
                Target.user_id == user_id,
                Target.week_start == week_start,
                Target.metric_name.in_(EDITABLE_TARGET_METRICS),
            )
            .order_by(Target.id),
        ),
    )


def form_values_from_targets(targets: list[Target]) -> TargetFormValues:
    """Build form values from the user's stored target rows."""
    values = {
        target.metric_name: str(int(target.target_value))
        for target in targets
        if target.metric_name in EDITABLE_TARGET_METRICS
    }
    return TargetFormValues(
        **{field.name: values.get(field.name, "") for field in fields(TargetFormValues)},
    )


def validate_target_form(
    values: TargetFormValues,
) -> tuple[dict[str, int] | None, dict[str, str]]:
    """Require a non-negative whole number for every editable target metric."""
    validated: dict[str, int] = {}
    errors: dict[str, str] = {}
    for metric in EDITABLE_TARGET_METRICS:
        raw_value = getattr(values, metric).strip()
        try:
            parsed_value = int(raw_value)
        except ValueError:
            errors[metric] = "Enter a non-negative whole number."
            continue
        if parsed_value < 0:
            errors[metric] = "Enter a non-negative whole number."
            continue
        validated[metric] = parsed_value
    return (None, errors) if errors else (validated, {})


def upsert_user_targets(
    session: Session,
    *,
    user_id: int,
    values: dict[str, int],
    week_start: date,
) -> None:
    """Create or update only the user's selected weekly target set."""
    week_end = week_start + timedelta(days=6)
    existing = {
        target.metric_name: target
        for target in get_user_targets(
            session,
            user_id=user_id,
            week_start=week_start,
        )
    }
    for metric in EDITABLE_TARGET_METRICS:
        target = existing.get(metric)
        if target is None:
            target = Target(
                user_id=user_id,
                metric_name=metric,
                target_value=values[metric],
                week_start=week_start,
                effective_from=week_start,
                effective_until=week_end,
            )
        else:
            target.target_value = values[metric]
        session.add(target)


__all__ = [
    "TARGET_FIELDS",
    "TARGET_METRICS",
    "EDITABLE_TARGET_FIELDS",
    "EDITABLE_TARGET_METRICS",
    "TargetFormValues",
    "TargetWeek",
    "TargetWeekPresentation",
    "current_week_bounds",
    "form_values_from_targets",
    "get_user_targets",
    "iso_week_value",
    "resolve_target_week",
    "target_week_presentation",
    "upsert_user_targets",
    "validate_target_form",
]
