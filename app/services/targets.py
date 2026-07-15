"""Validation and persistence for personal weekly targets."""

from dataclasses import dataclass, fields
from datetime import date, timedelta

from sqlmodel import Session, select

from app.models import Target


TARGET_FIELDS = (
    ("total_activities", "Total outreach activities"),
    ("companies_contacted", "Companies contacted"),
    ("replies", "Replies received"),
    ("positive_replies", "Positive replies"),
    ("meetings_booked", "Meetings booked"),
    ("meetings_held", "Meetings held"),
)
TARGET_METRICS = tuple(metric for metric, _label in TARGET_FIELDS)


@dataclass(frozen=True)
class TargetFormValues:
    """Raw weekly-target values retained for form redisplay."""

    total_activities: str = ""
    companies_contacted: str = ""
    replies: str = ""
    positive_replies: str = ""
    meetings_booked: str = ""
    meetings_held: str = ""


def current_week_bounds(today: date) -> tuple[date, date]:
    """Return Monday and Sunday for the week containing today."""
    week_start = today - timedelta(days=today.weekday())
    return week_start, week_start + timedelta(days=6)


def get_user_targets(session: Session, *, user_id: int) -> list[Target]:
    """Return only the current target rows owned by one user."""
    return list(
        session.exec(
            select(Target)
            .where(
                Target.user_id == user_id,
                Target.metric_name.in_(TARGET_METRICS),
            )
            .order_by(Target.id),
        ),
    )


def form_values_from_targets(targets: list[Target]) -> TargetFormValues:
    """Build form values from the user's stored target rows."""
    values = {
        target.metric_name: str(int(target.target_value))
        for target in targets
        if target.metric_name in TARGET_METRICS
    }
    return TargetFormValues(
        **{field.name: values.get(field.name, "") for field in fields(TargetFormValues)},
    )


def validate_target_form(
    values: TargetFormValues,
) -> tuple[dict[str, int] | None, dict[str, str]]:
    """Require a non-negative whole number for all six target metrics."""
    validated: dict[str, int] = {}
    errors: dict[str, str] = {}
    for metric in TARGET_METRICS:
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
    today: date,
) -> None:
    """Create or update the user's single current weekly target set."""
    week_start, week_end = current_week_bounds(today)
    existing = {
        target.metric_name: target
        for target in get_user_targets(session, user_id=user_id)
    }
    for metric in TARGET_METRICS:
        target = existing.get(metric)
        if target is None:
            target = Target(
                user_id=user_id,
                metric_name=metric,
                target_value=values[metric],
                effective_from=week_start,
                effective_until=week_end,
            )
        else:
            target.target_value = values[metric]
            target.effective_from = week_start
            target.effective_until = week_end
        session.add(target)


__all__ = [
    "TARGET_FIELDS",
    "TARGET_METRICS",
    "TargetFormValues",
    "current_week_bounds",
    "form_values_from_targets",
    "get_user_targets",
    "upsert_user_targets",
    "validate_target_form",
]
