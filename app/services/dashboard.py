"""Company-wide aggregated dashboard calculations."""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import ceil

from sqlmodel import Session, select

from app.countries import COUNTRY_NAMES_BY_CODE
from app.models import (
    DailyOutreach,
    OutreachCountry,
    PipelineMeeting,
    Target,
    User,
    UserMood,
)
from app.services.activity_metrics import aggregate_activity_actuals
from app.services.meetings import meeting_date_bounds
from app.services.my_week import WeekMetric, build_week_metric
from app.services.targets import TARGET_FIELDS, TARGET_METRICS, current_week_bounds

CURRENT_WEEK = "current-week"
PREVIOUS_WEEK = "previous-week"
CURRENT_MONTH = "current-month"
CUSTOM_RANGE = "custom"
PERIOD_OPTIONS = (
    (CURRENT_WEEK, "Current week"),
    (PREVIOUS_WEEK, "Previous week"),
    (CURRENT_MONTH, "Current month"),
    (CUSTOM_RANGE, "Custom range"),
)
PERIOD_LABELS = dict(PERIOD_OPTIONS)
USER_SCOPE_ALL = "all"
USER_SCOPE_SELECTED = "selected"


@dataclass(frozen=True)
class DashboardFilter:
    """Resolved dashboard period and retained custom date values."""

    key: str
    label: str
    start_date: date
    end_date: date
    from_value: str = ""
    to_value: str = ""

    @property
    def is_current_week(self) -> bool:
        return self.key == CURRENT_WEEK

    @property
    def display_range(self) -> str:
        """Return a compact human-readable range for the dashboard heading."""
        start = f"{self.start_date.day} {self.start_date.strftime('%b')}"
        end = f"{self.end_date.day} {self.end_date.strftime('%b')}"
        if self.start_date.year == self.end_date.year:
            return f"{start} – {end} {self.end_date.year}"
        return f"{start} {self.start_date.year} – {end} {self.end_date.year}"


@dataclass(frozen=True)
class DashboardUserOption:
    """One safe user-filter option shown to authenticated users."""

    user_id: int
    label: str


@dataclass(frozen=True)
class DashboardUserFilter:
    """Normalized user scope used by routes and aggregate queries."""

    scope: str
    user_ids: tuple[int, ...]

    @property
    def includes_all(self) -> bool:
        return self.scope == USER_SCOPE_ALL


@dataclass(frozen=True)
class ActivityBucket:
    """Separate outreach and meeting values for one chart category."""

    label: str
    start_date: date
    end_date: date
    outreach_activities: int
    meetings_held: int
    outreach_bar: int
    meetings_bar: int

    @property
    def range_label(self) -> str:
        """Return the exact date or date range represented by this bucket."""
        if self.start_date == self.end_date:
            return self.start_date.isoformat()
        return f"{self.start_date.isoformat()} to {self.end_date.isoformat()}"


@dataclass(frozen=True)
class BreakdownItem:
    """One aggregate category with a relative bar width."""

    key: str
    label: str
    value: int
    bar_percentage: int


@dataclass(frozen=True)
class DashboardSummary:
    """All privacy-safe company aggregates for one selected period."""

    selected_period: DashboardFilter
    metrics: tuple[WeekMetric, ...]
    activity_buckets: tuple[ActivityBucket, ...]
    countries: tuple[BreakdownItem, ...]
    blockers: tuple[BreakdownItem, ...]
    moods: tuple[BreakdownItem, ...]
    has_activity: bool
    has_selected_users: bool

    @property
    def show_targets(self) -> bool:
        return self.selected_period.is_current_week

    @property
    def activity_label_stride(self) -> int:
        """Limit visible axis labels while retaining every accessible value."""
        return max(1, ceil(len(self.activity_buckets) / 7))


def resolve_dashboard_filter(
    *,
    today: date,
    period: str,
    from_value: str = "",
    to_value: str = "",
) -> tuple[DashboardFilter | None, str | None]:
    """Validate a preset or custom period without discarding submitted dates."""
    if period not in PERIOD_LABELS:
        return None, "Select a valid dashboard period."

    week_start, week_end = current_week_bounds(today)
    if period == CURRENT_WEEK:
        start_date, end_date = week_start, week_end
    elif period == PREVIOUS_WEEK:
        start_date = week_start - timedelta(days=7)
        end_date = week_start - timedelta(days=1)
    elif period == CURRENT_MONTH:
        start_date, end_date = today.replace(day=1), today
    else:
        try:
            start_date = date.fromisoformat(from_value)
            end_date = date.fromisoformat(to_value)
        except ValueError:
            return None, "Enter valid From and To dates."
        if start_date > end_date:
            return None, "From cannot be later than To."
        if end_date > today:
            return None, "To cannot be in the future."

    return (
        DashboardFilter(
            key=period,
            label=PERIOD_LABELS[period],
            start_date=start_date,
            end_date=end_date,
            from_value=from_value,
            to_value=to_value,
        ),
        None,
    )


def get_dashboard_user_options(session: Session) -> tuple[DashboardUserOption, ...]:
    """Return every user once, sorted and labelled without exposing email."""
    users = list(session.exec(select(User)).all())
    ordered = sorted(
        users,
        key=lambda user: (user.name.casefold(), user.name, user.id or 0),
    )
    return tuple(
        DashboardUserOption(
            user_id=user.id,
            label=user.name,
        )
        for user in ordered
        if user.id is not None
    )


def normalize_dashboard_user_filter(
    *,
    user_scope: str | None,
    user_ids: list[str] | tuple[str, ...],
    existing_user_ids: set[int],
) -> tuple[DashboardUserFilter | None, str | None]:
    """Normalize reusable GET user parameters against existing database IDs."""
    scope = user_scope or USER_SCOPE_ALL
    if scope not in {USER_SCOPE_ALL, USER_SCOPE_SELECTED}:
        return None, "Select a valid user scope."
    if scope == USER_SCOPE_ALL:
        return DashboardUserFilter(scope=scope, user_ids=()), None

    parsed_ids: set[int] = set()
    for raw_user_id in user_ids:
        try:
            parsed_id = int(raw_user_id)
        except (TypeError, ValueError):
            continue
        if parsed_id in existing_user_ids:
            parsed_ids.add(parsed_id)
    return (
        DashboardUserFilter(
            scope=scope,
            user_ids=tuple(sorted(parsed_ids)),
        ),
        None,
    )


def _company_records(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    user_ids: tuple[int, ...] | None,
) -> tuple[list[DailyOutreach], list[PipelineMeeting]]:
    outreach_query = select(DailyOutreach).where(
        DailyOutreach.activity_date >= start_date,
        DailyOutreach.activity_date <= end_date,
    )
    start_time, end_time = meeting_date_bounds(start_date, end_date)
    meeting_query = select(PipelineMeeting).where(
        PipelineMeeting.occurred_at >= start_time,
        PipelineMeeting.occurred_at < end_time,
    )
    if user_ids is not None:
        outreach_query = outreach_query.where(DailyOutreach.user_id.in_(user_ids))
        meeting_query = meeting_query.where(PipelineMeeting.user_id.in_(user_ids))
    outreach = list(
        session.exec(outreach_query).all(),
    )
    meetings = list(
        session.exec(meeting_query).all(),
    )
    return outreach, meetings


def _company_targets(
    session: Session,
    *,
    user_ids: tuple[int, ...] | None,
) -> dict[str, int]:
    totals = {metric: 0 for metric in TARGET_METRICS}
    query = select(Target).where(Target.metric_name.in_(TARGET_METRICS))
    if user_ids is not None:
        query = query.where(Target.user_id.in_(user_ids))
    for target in session.exec(query).all():
        totals[target.metric_name] += int(target.target_value)
    return totals


def _local_meeting_date(meeting: PipelineMeeting) -> date:
    occurred_at = meeting.occurred_at
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    return occurred_at.astimezone().date()


def _short_date(value: date) -> str:
    return f"{value.strftime('%b')} {value.day}"


def _week_label(start_date: date, end_date: date) -> str:
    if start_date.month == end_date.month:
        return f"{start_date.strftime('%b')} {start_date.day}-{end_date.day}"
    return f"{_short_date(start_date)}-{_short_date(end_date)}"


def _activity_buckets(
    selected_period: DashboardFilter,
    outreach: list[DailyOutreach],
    meetings: list[PipelineMeeting],
) -> tuple[ActivityBucket, ...]:
    outreach_by_day: Counter[date] = Counter()
    for record in outreach:
        outreach_by_day[record.activity_date] += record.total_activities
    meetings_by_day: Counter[date] = Counter(
        _local_meeting_date(meeting) for meeting in meetings
    )
    duration = (selected_period.end_date - selected_period.start_date).days + 1
    group_by_week = (
        selected_period.key not in {CURRENT_WEEK, PREVIOUS_WEEK} and duration > 14
    )

    raw_buckets: list[tuple[str, date, date, int, int]] = []
    current = selected_period.start_date
    while current <= selected_period.end_date:
        bucket_end = (
            min(
                current + timedelta(days=6 - current.weekday()),
                selected_period.end_date,
            )
            if group_by_week
            else current
        )
        bucket_dates = (
            current + timedelta(days=offset)
            for offset in range((bucket_end - current).days + 1)
        )
        dates = tuple(bucket_dates)
        outreach_value = sum(outreach_by_day[value] for value in dates)
        meeting_value = sum(meetings_by_day[value] for value in dates)
        label = (
            _week_label(current, bucket_end)
            if group_by_week
            else _short_date(current)
        )
        raw_buckets.append(
            (label, current, bucket_end, outreach_value, meeting_value),
        )
        current = bucket_end + timedelta(days=1)

    maximum = max(
        (
            max(outreach_value, meeting_value)
            for _, _, _, outreach_value, meeting_value in raw_buckets
        ),
        default=0,
    )
    return tuple(
        ActivityBucket(
            label=label,
            start_date=start_date,
            end_date=end_date,
            outreach_activities=outreach_value,
            meetings_held=meeting_value,
            outreach_bar=round(outreach_value / maximum * 100) if maximum else 0,
            meetings_bar=round(meeting_value / maximum * 100) if maximum else 0,
        )
        for label, start_date, end_date, outreach_value, meeting_value in raw_buckets
    )


def _relative_breakdown(
    counts: Counter[str],
    *,
    labels: dict[str, str] | None = None,
) -> tuple[BreakdownItem, ...]:
    positive_counts = Counter(
        {key: value for key, value in counts.items() if value > 0},
    )
    maximum = max(positive_counts.values(), default=0)
    return tuple(
        BreakdownItem(
            key=key,
            label=(labels or {}).get(key, key),
            value=value,
            bar_percentage=round(value / maximum * 100) if maximum else 0,
        )
        for key, value in sorted(
            positive_counts.items(),
            key=lambda item: (-item[1], (labels or {}).get(item[0], item[0])),
        )
    )


def _country_breakdown(
    session: Session,
    outreach: list[DailyOutreach],
) -> tuple[BreakdownItem, ...]:
    outreach_ids = [record.id for record in outreach if record.id is not None]
    if not outreach_ids:
        return ()
    counts: Counter[str] = Counter()
    for country in session.exec(
        select(OutreachCountry).where(
            OutreachCountry.outreach_daily_id.in_(outreach_ids),
        ),
    ).all():
        counts[country.country_code] += country.companies_contacted
    return _relative_breakdown(counts, labels=COUNTRY_NAMES_BY_CODE)


def _mood_breakdown(outreach: list[DailyOutreach]) -> tuple[BreakdownItem, ...]:
    counts = Counter(
        record.user_mood.value
        for record in outreach
        if record.user_mood is not None
    )
    total = sum(counts.values())
    return tuple(
        BreakdownItem(
            key=mood.value.lower(),
            label=mood.value,
            value=counts[mood.value],
            bar_percentage=(round(counts[mood.value] / total * 100) if total else 0),
        )
        for mood in UserMood
        if counts[mood.value] > 0
    )


def get_dashboard_summary(
    session: Session,
    *,
    selected_period: DashboardFilter,
    user_filter: DashboardUserFilter | None = None,
) -> DashboardSummary:
    """Build company aggregates without exposing employee or record details."""
    selected_user_ids = (
        None
        if user_filter is None or user_filter.includes_all
        else user_filter.user_ids
    )
    outreach, meetings = _company_records(
        session,
        start_date=selected_period.start_date,
        end_date=selected_period.end_date,
        user_ids=selected_user_ids,
    )
    actuals = aggregate_activity_actuals(outreach, meetings)
    targets = (
        _company_targets(session, user_ids=selected_user_ids)
        if selected_period.is_current_week
        else {}
    )
    metrics = tuple(
        build_week_metric(
            key=metric,
            label=label,
            actual=actuals[metric],
            target=targets.get(metric, 0),
        )
        for metric, label in TARGET_FIELDS
    )
    blockers = Counter(
        record.blocker_tag for record in outreach if record.blocker_tag is not None
    )
    return DashboardSummary(
        selected_period=selected_period,
        metrics=metrics,
        activity_buckets=_activity_buckets(selected_period, outreach, meetings),
        countries=_country_breakdown(session, outreach),
        blockers=_relative_breakdown(blockers),
        moods=_mood_breakdown(outreach),
        has_activity=bool(outreach or meetings),
        has_selected_users=(
            user_filter is None
            or user_filter.includes_all
            or bool(user_filter.user_ids)
        ),
    )


__all__ = [
    "CURRENT_MONTH",
    "CURRENT_WEEK",
    "CUSTOM_RANGE",
    "DashboardFilter",
    "DashboardSummary",
    "DashboardUserFilter",
    "DashboardUserOption",
    "PERIOD_OPTIONS",
    "PREVIOUS_WEEK",
    "USER_SCOPE_ALL",
    "USER_SCOPE_SELECTED",
    "get_dashboard_user_options",
    "get_dashboard_summary",
    "normalize_dashboard_user_filter",
    "resolve_dashboard_filter",
]
