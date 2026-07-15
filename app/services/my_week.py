"""Personal current-week activity and target progress."""

from dataclasses import dataclass
from datetime import date

from sqlmodel import Session

from app.services.activity_metrics import aggregate_activity_actuals
from app.services.meetings import get_recent_meetings
from app.services.outreach import get_recent_outreach
from app.services.targets import TARGET_FIELDS, current_week_bounds, get_user_targets


@dataclass(frozen=True)
class WeekMetric:
    """One actual-versus-target comparison for the weekly view."""

    key: str
    label: str
    actual: int
    target: int
    remaining: int
    percentage: int | None
    bar_percentage: int
    progress_state: str
    aria_value: int
    aria_max: int

    @property
    def percentage_text(self) -> str:
        """Return a safe textual percentage or the zero-target state."""
        if self.percentage is None:
            return "No target set"
        return f"{self.percentage}%"


@dataclass(frozen=True)
class MyWeekSummary:
    """Current user's activity and comparisons for one calendar week."""

    week_start: date
    week_end: date
    metrics: tuple[WeekMetric, ...]
    has_activity: bool

def build_week_metric(
    *,
    key: str,
    label: str,
    actual: int,
    target: int,
) -> WeekMetric:
    """Calculate remaining work, percentage, and accessible bar state."""
    remaining = max(target - actual, 0)
    if target == 0:
        return WeekMetric(
            key=key,
            label=label,
            actual=actual,
            target=target,
            remaining=remaining,
            percentage=None,
            bar_percentage=0,
            progress_state="neutral",
            aria_value=0,
            aria_max=100,
        )

    ratio = actual / target
    percentage = round(ratio * 100)
    if ratio < 0.5:
        progress_state = "orange"
    elif ratio < 0.8:
        progress_state = "amber"
    elif ratio < 1:
        progress_state = "light-green"
    else:
        progress_state = "green"
    return WeekMetric(
        key=key,
        label=label,
        actual=actual,
        target=target,
        remaining=remaining,
        percentage=percentage,
        bar_percentage=min(percentage, 100),
        progress_state=progress_state,
        aria_value=min(actual, target),
        aria_max=target,
    )


def get_my_week_summary(
    session: Session,
    *,
    user_id: int,
    today: date,
) -> MyWeekSummary:
    """Aggregate current-week records and current targets for one user."""
    week_start, week_end = current_week_bounds(today)
    outreach_records = get_recent_outreach(
        session,
        user_id=user_id,
        start_date=week_start,
        end_date=week_end,
    )
    meetings = get_recent_meetings(
        session,
        user_id=user_id,
        start_date=week_start,
        end_date=week_end,
    )
    actuals = aggregate_activity_actuals(outreach_records, meetings)
    targets = {
        target.metric_name: int(target.target_value)
        for target in get_user_targets(session, user_id=user_id)
    }
    metrics = tuple(
        build_week_metric(
            key=metric,
            label=label,
            actual=actuals[metric],
            target=targets.get(metric, 0),
        )
        for metric, label in TARGET_FIELDS
    )
    return MyWeekSummary(
        week_start=week_start,
        week_end=week_end,
        metrics=metrics,
        has_activity=bool(outreach_records or meetings),
    )


__all__ = [
    "MyWeekSummary",
    "WeekMetric",
    "build_week_metric",
    "get_my_week_summary",
]
