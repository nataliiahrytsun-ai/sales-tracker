"""Company-wide aggregated dashboard calculations."""

from calendar import monthrange
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import ceil

from sqlmodel import Session, select

from app.countries import COUNTRY_NAMES_BY_CODE
from app.models import (
    CustomerEngagement,
    DailyOutreach,
    NeedIdentified,
    OutreachCountry,
    PipelineMeeting,
    StoredPipelineOutcome,
    Target,
    User,
    UserMood,
)
from app.services.activity_metrics import aggregate_activity_actuals
from app.services.discussion_prompts import (
    DiscussionPrompt,
    build_discussion_prompts,
)
from app.services.meetings import BLOCKER_OPTIONS, meeting_date_bounds
from app.services.targets import TARGET_FIELDS, TARGET_METRICS, current_week_bounds

CURRENT_WEEK = "current-week"
PREVIOUS_WEEK = "previous-week"
CURRENT_MONTH = "current-month"
CUSTOM_RANGE = "custom"
DASHBOARD_METRIC_LABEL_OVERRIDES = {
    "meetings_booked": "Meetings booked from outreach",
    "meetings_held": "Pipeline meetings held",
}
PERIOD_OPTIONS = (
    (CURRENT_WEEK, "Current week"),
    (PREVIOUS_WEEK, "Previous week"),
    (CURRENT_MONTH, "Current month"),
    (CUSTOM_RANGE, "Custom range"),
)
PERIOD_LABELS = dict(PERIOD_OPTIONS)
USER_SCOPE_ALL = "all"
USER_SCOPE_SELECTED = "selected"
ACTIVITY_GRANULARITY_DAY = "day"
ACTIVITY_GRANULARITY_WEEK = "week"
ACTIVITY_GRANULARITY_MONTH = "month"
ACTIVITY_GRANULARITY_PERIOD = "period"
ACTIVITY_HEADINGS = {
    ACTIVITY_GRANULARITY_DAY: "Activity by day",
    ACTIVITY_GRANULARITY_WEEK: "Activity by week",
    ACTIVITY_GRANULARITY_MONTH: "Activity by month",
    ACTIVITY_GRANULARITY_PERIOD: "Activity for selected period",
}


@dataclass(frozen=True)
class DashboardFilter:
    """Resolved dashboard period and retained custom date values."""

    key: str
    label: str
    start_date: date
    end_date: date
    from_value: str = ""
    to_value: str = ""
    as_of_date: date | None = None

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
class ComparisonPeriod:
    """One exact inclusive range used by previous-period comparisons."""

    start_date: date
    end_date: date

    @property
    def duration_days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    @property
    def display_range(self) -> str:
        if self.start_date == self.end_date:
            return (
                f"{self.start_date.strftime('%b')} {self.start_date.day}, "
                f"{self.start_date.year}"
            )
        if self.start_date.year == self.end_date.year:
            if self.start_date.month == self.end_date.month:
                return (
                    f"{self.start_date.strftime('%b')} {self.start_date.day}"
                    f"–{self.end_date.day}, {self.end_date.year}"
                )
            return (
                f"{self.start_date.strftime('%b')} {self.start_date.day}"
                f"–{self.end_date.strftime('%b')} {self.end_date.day}, "
                f"{self.end_date.year}"
            )
        return (
            f"{self.start_date.strftime('%b')} {self.start_date.day}, "
            f"{self.start_date.year}–{self.end_date.strftime('%b')} "
            f"{self.end_date.day}, {self.end_date.year}"
        )


@dataclass(frozen=True)
class DashboardComparisonPeriods:
    """Positionally comparable current and previous inclusive ranges."""

    current: ComparisonPeriod
    previous: ComparisonPeriod


@dataclass(frozen=True)
class ComparisonDisplay:
    """Compact, accessible display model for one metric difference."""

    state: str
    text: str
    accessible_label: str


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
class ResolvedDashboardFilters:
    """Shared validated Dashboard filters for HTML and export routes."""

    selected_period: DashboardFilter | None
    user_filter: DashboardUserFilter | None
    user_options: tuple[DashboardUserOption, ...]
    error: str | None


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
    share_percentage: int


@dataclass(frozen=True)
class MoodTrendPoint:
    """One calendar day in the outreach-only mood trend."""

    date: date
    average: Decimal | None
    recorded_count: int
    display_average: str | None
    x: int
    y: int | None
    show_date_label: bool
    connects_to_previous: bool

    @property
    def accessible_label(self) -> str:
        """Describe a plotted point without hiding its exact source count."""
        if self.average is None or self.display_average is None:
            return f"{self.date.isoformat()}: no recorded mood"
        noun = "entry" if self.recorded_count == 1 else "entries"
        return (
            f"{self.date.isoformat()}: average {self.display_average}, "
            f"{self.recorded_count} recorded {noun}"
        )


@dataclass(frozen=True)
class MoodSummary:
    """Outreach-only average, distribution, and exact daily mood series."""

    average: Decimal | None
    average_text: str | None
    recorded_count: int
    distribution: tuple[BreakdownItem, ...]
    trend: tuple[MoodTrendPoint, ...]
    chart_width: int
    comparison: ComparisonDisplay | None = None
    previous_trend: tuple[MoodTrendPoint, ...] = ()
    previous_recorded_count: int = 0

    @property
    def has_recorded_mood(self) -> bool:
        return self.recorded_count > 0

    @property
    def has_previous_mood(self) -> bool:
        return self.previous_recorded_count > 0

    @property
    def trend_pairs(
        self,
    ) -> tuple[tuple[MoodTrendPoint, MoodTrendPoint | None], ...]:
        """Pair series by ordinal day rather than unrelated calendar dates."""
        return tuple(
            (
                selected,
                self.previous_trend[index]
                if index < len(self.previous_trend)
                else None,
            )
            for index, selected in enumerate(self.trend)
        )


@dataclass(frozen=True)
class DashboardComment:
    """One non-empty comment from an existing activity note field."""

    date: date
    employee: str
    source_type: str
    outcome: str | None
    comment: str


@dataclass(frozen=True)
class CommentGroup:
    """One presentation-only grouping of dashboard comments."""

    label: str
    comments: tuple[DashboardComment, ...]


@dataclass(frozen=True)
class PipelineConversionMetric:
    """One pipeline conversion numerator against all filtered meetings."""

    key: str
    label: str
    numerator: int
    denominator: int
    percentage: int | None
    comparison: ComparisonDisplay | None = None

    @property
    def percentage_text(self) -> str:
        return "No data" if self.percentage is None else f"{self.percentage}%"


@dataclass(frozen=True)
class PipelineConversionSummary:
    """Pipeline meeting count and conversion rates for the exact filters."""

    total_meetings: int
    metrics: tuple[PipelineConversionMetric, ...]


@dataclass(frozen=True)
class OutreachConversionMetric:
    """One Outreach conversion numerator and its documented denominator."""

    key: str
    label: str
    numerator: int
    denominator: int
    percentage: int | None
    comparison: ComparisonDisplay | None = None

    @property
    def percentage_text(self) -> str:
        return "No data" if self.percentage is None else f"{self.percentage}%"


@dataclass(frozen=True)
class OutreachConversionSummary:
    """Aggregated Outreach rates for the exact filtered record set."""

    record_count: int
    metrics: tuple[OutreachConversionMetric, ...]


def _display_decimal(value: Decimal) -> str:
    """Format an aggregate target compactly without changing its precision."""
    if value == value.to_integral_value():
        return str(int(value))
    rounded = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return format(rounded, "f").rstrip("0").rstrip(".")


@dataclass(frozen=True)
class DashboardMetric:
    """One exact-period actual compared with prorated weekly targets."""

    key: str
    label: str
    actual: int
    target: Decimal
    remaining: Decimal
    exceeded_by: Decimal
    percentage: int | None
    bar_percentage: int
    progress_state: str
    comparison: ComparisonDisplay | None = None

    @property
    def target_text(self) -> str:
        return _display_decimal(self.target)

    @property
    def remaining_text(self) -> str:
        return _display_decimal(self.remaining)

    @property
    def exceeded_by_text(self) -> str:
        return _display_decimal(self.exceeded_by)

    @property
    def percentage_text(self) -> str:
        return "No target" if self.percentage is None else f"{self.percentage}%"

    @property
    def status_text(self) -> str:
        if self.target == 0:
            return "No target"
        if self.actual < self.target:
            return f"{self.remaining_text} remaining"
        if self.actual == self.target:
            return "Goal reached"
        return f"{self.exceeded_by_text} above target"

    @property
    def status_state(self) -> str:
        return "success" if self.target > 0 and self.actual >= self.target else "muted"

    @property
    def needs_attention(self) -> bool:
        return (
            self.target > 0
            and Decimal(self.actual) / self.target < DASHBOARD_TARGET_ATTENTION_RATIO
        )


# Metrics below half of their prorated target receive a quiet, non-warning hint.
DASHBOARD_TARGET_ATTENTION_RATIO = Decimal("0.5")


def _build_dashboard_metric(
    *,
    key: str,
    label: str,
    actual: int,
    target: Decimal,
) -> DashboardMetric:
    """Build safe display values while retaining the exact prorated target."""
    actual_decimal = Decimal(actual)
    remaining = max(target - actual_decimal, Decimal(0))
    exceeded_by = max(actual_decimal - target, Decimal(0))
    if target == 0:
        return DashboardMetric(
            key=key,
            label=label,
            actual=actual,
            target=target,
            remaining=remaining,
            exceeded_by=exceeded_by,
            percentage=None,
            bar_percentage=0,
            progress_state="neutral",
        )

    ratio = actual_decimal / target
    percentage = int(
        (ratio * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP),
    )
    progress_state = "success" if ratio >= 1 else "standard"
    return DashboardMetric(
        key=key,
        label=label,
        actual=actual,
        target=target,
        remaining=remaining,
        exceeded_by=exceeded_by,
        percentage=percentage,
        bar_percentage=min(percentage, 100),
        progress_state=progress_state,
    )


@dataclass(frozen=True)
class DashboardSummary:
    """All privacy-safe company aggregates for one selected period."""

    selected_period: DashboardFilter
    comparison_periods: DashboardComparisonPeriods
    metrics: tuple[DashboardMetric, ...]
    pipeline_conversions: PipelineConversionSummary
    outreach_conversions: OutreachConversionSummary
    activity_buckets: tuple[ActivityBucket, ...]
    activity_granularity: str
    countries: tuple[BreakdownItem, ...]
    blockers: tuple[BreakdownItem, ...]
    discussion_prompts: tuple[DiscussionPrompt, ...]
    mood_summary: MoodSummary
    comments: tuple[DashboardComment, ...]
    has_activity: bool
    has_selected_users: bool

    @property
    def moods(self) -> tuple[BreakdownItem, ...]:
        """Retain the existing distribution access name for callers."""
        return self.mood_summary.distribution

    @property
    def activity_label_stride(self) -> int:
        """Limit visible axis labels while retaining every accessible value."""
        return max(1, ceil(len(self.activity_buckets) / 7))

    @property
    def activity_heading(self) -> str:
        """Describe the actual aggregation used by the activity series."""
        return ACTIVITY_HEADINGS[self.activity_granularity]

    @property
    def target_adjustment_text(self) -> str:
        """Explain target proration in compact product language."""
        if self.selected_period.key != CUSTOM_RANGE:
            return "Targets adjusted to the selected period"
        days = (
            self.selected_period.end_date - self.selected_period.start_date
        ).days + 1
        noun = "day" if days == 1 else "days"
        return f"Targets adjusted to {days} selected {noun}"


def resolve_comparison_periods(
    selected_period: DashboardFilter,
) -> DashboardComparisonPeriods:
    """Resolve the documented non-overlapping previous comparison range."""
    current_end = selected_period.end_date
    if selected_period.key in {CURRENT_WEEK, CURRENT_MONTH}:
        current_end = min(
            selected_period.as_of_date or selected_period.end_date,
            selected_period.end_date,
        )
    current = ComparisonPeriod(
        start_date=selected_period.start_date,
        end_date=current_end,
    )

    if selected_period.key in {CURRENT_WEEK, PREVIOUS_WEEK}:
        previous = ComparisonPeriod(
            start_date=current.start_date - timedelta(days=7),
            end_date=current.end_date - timedelta(days=7),
        )
    elif selected_period.key == CURRENT_MONTH:
        previous_month_end = current.start_date - timedelta(days=1)
        previous = ComparisonPeriod(
            start_date=previous_month_end.replace(day=1),
            end_date=previous_month_end.replace(
                day=min(current.end_date.day, previous_month_end.day),
            ),
        )
    else:
        previous_end = current.start_date - timedelta(days=1)
        previous = ComparisonPeriod(
            start_date=previous_end
            - timedelta(days=current.duration_days - 1),
            end_date=previous_end,
        )
    return DashboardComparisonPeriods(current=current, previous=previous)


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
        start_date = today.replace(day=1)
        end_date = today.replace(day=monthrange(today.year, today.month)[1])
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
            as_of_date=today,
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


def resolve_dashboard_filters(
    session: Session,
    *,
    today: date,
    period: str,
    from_value: str = "",
    to_value: str = "",
    user_scope: str | None = None,
    user_ids: list[str] | tuple[str, ...] = (),
) -> ResolvedDashboardFilters:
    """Resolve the complete shared Dashboard/export GET filter contract."""
    user_options = get_dashboard_user_options(session)
    user_filter, user_error = normalize_dashboard_user_filter(
        user_scope=user_scope,
        user_ids=user_ids,
        existing_user_ids={option.user_id for option in user_options},
    )
    selected_period, period_error = resolve_dashboard_filter(
        today=today,
        period=period,
        from_value=from_value,
        to_value=to_value,
    )
    return ResolvedDashboardFilters(
        selected_period=selected_period,
        user_filter=user_filter,
        user_options=user_options,
        error=period_error or user_error,
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
    start_date: date,
    end_date: date,
    user_ids: tuple[int, ...] | None,
) -> dict[str, Decimal]:
    """Prorate every weekly target by its inclusive period overlap."""
    totals = {metric: Decimal(0) for metric in TARGET_METRICS}
    first_week_start = start_date - timedelta(days=start_date.weekday())
    last_week_start = end_date - timedelta(days=end_date.weekday())
    query = select(Target).where(
        Target.week_start >= first_week_start,
        Target.week_start <= last_week_start,
        Target.metric_name.in_(TARGET_METRICS),
    )
    if user_ids is not None:
        query = query.where(Target.user_id.in_(user_ids))
    for target in session.exec(query).all():
        week_end = target.week_start + timedelta(days=6)
        overlap_start = max(start_date, target.week_start)
        overlap_end = min(end_date, week_end)
        overlap_days = (overlap_end - overlap_start).days + 1
        totals[target.metric_name] += (
            Decimal(str(target.target_value)) * Decimal(overlap_days) / Decimal(7)
        )
    return totals


def _user_names(session: Session, user_ids: set[int]) -> dict[int, str]:
    """Load public employee names in one query."""
    if not user_ids:
        return {}
    return {
        user.id: user.name
        for user in session.exec(select(User).where(User.id.in_(user_ids))).all()
        if user.id is not None
    }


def _dashboard_comments(
    session: Session,
    outreach: list[DailyOutreach],
    meetings: list[PipelineMeeting],
) -> tuple[DashboardComment, ...]:
    """Build comments only from the two real optional note fields."""
    user_names = _user_names(
        session,
        {record.user_id for record in outreach}
        | {record.user_id for record in meetings},
    )
    comments: list[DashboardComment] = []
    for meeting in meetings:
        note = (meeting.note or "").strip()
        if note:
            comments.append(
                DashboardComment(
                    date=_local_meeting_date(meeting),
                    employee=user_names.get(meeting.user_id, "Unknown user"),
                    source_type="Meeting",
                    outcome=meeting.outcome.value,
                    comment=note,
                ),
            )
    for record in outreach:
        note = (record.note or "").strip()
        if note:
            comments.append(
                DashboardComment(
                    date=record.activity_date,
                    employee=user_names.get(record.user_id, "Unknown user"),
                    source_type="Daily Outreach",
                    outcome=None,
                    comment=note,
                ),
            )
    return tuple(
        sorted(
            comments,
            key=lambda item: (
                -item.date.toordinal(),
                item.employee.casefold(),
                item.source_type,
                item.comment,
            ),
        ),
    )


def group_dashboard_comments(
    comments: tuple[DashboardComment, ...],
    grouping: str,
) -> tuple[CommentGroup, ...]:
    """Group a fixed comment set without changing its membership."""
    key_functions = {
        "employee": lambda item: item.employee,
        "date": lambda item: item.date.isoformat(),
        "source": lambda item: item.source_type,
    }
    key_function = key_functions[grouping]
    grouped: dict[str, list[DashboardComment]] = {}
    for comment in comments:
        grouped.setdefault(key_function(comment), []).append(comment)
    labels = sorted(
        grouped,
        key=(lambda label: label if grouping == "date" else label.casefold()),
        reverse=grouping == "date",
    )
    return tuple(
        CommentGroup(label=label, comments=tuple(grouped[label]))
        for label in labels
    )


def _local_meeting_date(meeting: PipelineMeeting) -> date:
    occurred_at = meeting.occurred_at
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    return occurred_at.astimezone().date()


def _short_date(value: date) -> str:
    return f"{value.strftime('%b')} {value.day}"


def _week_label(start_date: date, end_date: date) -> str:
    if start_date.month == end_date.month:
        return f"{start_date.strftime('%b')} {start_date.day}–{end_date.day}"
    return f"{_short_date(start_date)}–{_short_date(end_date)}"


def _activity_bucket_granularity(selected_period: DashboardFilter) -> str:
    """Return the aggregation metadata used to build the activity series."""
    duration = (selected_period.end_date - selected_period.start_date).days + 1
    if (
        selected_period.key not in {CURRENT_WEEK, PREVIOUS_WEEK}
        and duration > 14
    ):
        return ACTIVITY_GRANULARITY_WEEK
    return ACTIVITY_GRANULARITY_DAY


def _activity_buckets(
    selected_period: DashboardFilter,
    outreach: list[DailyOutreach],
    meetings: list[PipelineMeeting],
    *,
    granularity: str | None = None,
) -> tuple[ActivityBucket, ...]:
    outreach_by_day: Counter[date] = Counter()
    for record in outreach:
        outreach_by_day[record.activity_date] += record.total_activities
    meetings_by_day: Counter[date] = Counter(
        _local_meeting_date(meeting) for meeting in meetings
    )
    bucket_granularity = granularity or _activity_bucket_granularity(selected_period)
    group_by_week = bucket_granularity == ACTIVITY_GRANULARITY_WEEK

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
    total = sum(positive_counts.values())
    return tuple(
        BreakdownItem(
            key=key,
            label=(labels or {}).get(key, key),
            value=value,
            bar_percentage=_rounded_percentage(value, maximum),
            share_percentage=_rounded_percentage(value, total),
        )
        for key, value in sorted(
            positive_counts.items(),
            key=lambda item: -item[1],
        )
    )


def _rounded_percentage(numerator: int, denominator: int) -> int:
    """Round a whole-number share consistently with product rate displays."""
    if denominator == 0:
        return 0
    return int(
        (
            Decimal(numerator) / Decimal(denominator) * Decimal(100)
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP),
    )


def _difference_display(
    difference: Decimal,
    *,
    unit: str = "",
    decimal_places: int = 0,
) -> ComparisonDisplay:
    """Format a rounded difference with redundant non-color direction cues."""
    quantum = Decimal(1).scaleb(-decimal_places)
    rounded = difference.quantize(quantum, rounding=ROUND_HALF_UP)
    if rounded == 0:
        return ComparisonDisplay(
            state="neutral",
            text="— No change",
            accessible_label="No change compared with the previous period",
        )
    magnitude = format(abs(rounded), f".{decimal_places}f")
    suffix = f" {unit}" if unit else ""
    accessible_unit = " percentage points" if unit == "pp" else ""
    if rounded > 0:
        return ComparisonDisplay(
            state="positive",
            text=f"↑ {magnitude}{suffix}",
            accessible_label=(
                f"Increased by {magnitude}{accessible_unit} "
                "compared with the previous period"
            ),
        )
    return ComparisonDisplay(
        state="negative",
        text=f"↓ {magnitude}{suffix}",
        accessible_label=(
            f"Decreased by {magnitude}{accessible_unit} "
            "compared with the previous period"
        ),
    )


def _rate_comparison(
    *,
    current_numerator: int,
    current_denominator: int,
    previous_numerator: int,
    previous_denominator: int,
) -> ComparisonDisplay:
    """Compare source rates before rounding to the whole-pp UI precision."""
    if current_denominator == 0 or previous_denominator == 0:
        return ComparisonDisplay(
            state="unavailable",
            text="— No comparable rate",
            accessible_label=(
                "No comparable rate for the previous period"
            ),
        )
    current_rate = (
        Decimal(current_numerator) / Decimal(current_denominator) * Decimal(100)
    )
    previous_rate = (
        Decimal(previous_numerator)
        / Decimal(previous_denominator)
        * Decimal(100)
    )
    return _difference_display(current_rate - previous_rate, unit="pp")


def _attach_rate_comparisons(
    display: tuple[PipelineConversionMetric, ...]
    | tuple[OutreachConversionMetric, ...],
    current: tuple[PipelineConversionMetric, ...]
    | tuple[OutreachConversionMetric, ...],
    previous: tuple[PipelineConversionMetric, ...]
    | tuple[OutreachConversionMetric, ...],
) -> tuple[PipelineConversionMetric, ...] | tuple[OutreachConversionMetric, ...]:
    current_by_key = {metric.key: metric for metric in current}
    previous_by_key = {metric.key: metric for metric in previous}
    return tuple(
        replace(
            metric,
            comparison=_rate_comparison(
                current_numerator=current_by_key[metric.key].numerator,
                current_denominator=current_by_key[metric.key].denominator,
                previous_numerator=previous_by_key[metric.key].numerator,
                previous_denominator=previous_by_key[metric.key].denominator,
            ),
        )
        for metric in display
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
        ).order_by(OutreachCountry.id),
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
            bar_percentage=_rounded_percentage(counts[mood.value], total),
            share_percentage=_rounded_percentage(counts[mood.value], total),
        )
        for mood in UserMood
        if counts[mood.value] > 0
    )


MOOD_SCORES = {
    UserMood.DIFFICULT: Decimal(1),
    UserMood.OKAY: Decimal(2),
    UserMood.GOOD: Decimal(3),
}


def _mood_display(value: Decimal) -> str:
    """Apply ROUND_HALF_UP once for a compact one-decimal mood value."""
    rounded = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return format(rounded, "f").rstrip("0").rstrip(".")


def _mood_summary(
    selected_period: DashboardFilter | ComparisonPeriod,
    outreach: list[DailyOutreach],
    *,
    position_count: int | None = None,
) -> MoodSummary:
    """Build all mood analytics from the same filled outreach user-days."""
    recorded = [record for record in outreach if record.user_mood is not None]
    scores = [MOOD_SCORES[record.user_mood] for record in recorded]
    average = sum(scores, Decimal(0)) / len(scores) if scores else None
    daily_scores: dict[date, list[Decimal]] = {}
    for record in recorded:
        daily_scores.setdefault(record.activity_date, []).append(
            MOOD_SCORES[record.user_mood],
        )

    duration = (selected_period.end_date - selected_period.start_date).days + 1
    chart_positions = position_count or duration
    chart_width = 640
    label_stride = max(1, ceil(duration / 9))
    trend: list[MoodTrendPoint] = []
    has_previous_point = False
    for index in range(duration):
        point_date = selected_period.start_date + timedelta(days=index)
        day_scores = daily_scores.get(point_date, [])
        daily_average = (
            sum(day_scores, Decimal(0)) / len(day_scores)
            if day_scores
            else None
        )
        trend.append(
            MoodTrendPoint(
                date=point_date,
                average=daily_average,
                recorded_count=len(day_scores),
                display_average=(
                    _mood_display(daily_average)
                    if daily_average is not None
                    else None
                ),
                x=(
                    48
                    if chart_positions == 1
                    else round(
                        48
                        + (chart_width - 60)
                        * index
                        / (chart_positions - 1),
                    )
                ),
                y=(
                    int(18 + (Decimal(3) - daily_average) * Decimal(49))
                    if daily_average is not None
                    else None
                ),
                show_date_label=(
                    index % label_stride == 0 or index == duration - 1
                ),
                connects_to_previous=bool(day_scores) and has_previous_point,
            ),
        )
        has_previous_point = bool(day_scores)

    return MoodSummary(
        average=average,
        average_text=_mood_display(average) if average is not None else None,
        recorded_count=len(recorded),
        distribution=_mood_breakdown(outreach),
        trend=tuple(trend),
        chart_width=chart_width,
    )


def _attach_mood_comparison(
    current: MoodSummary,
    previous: MoodSummary,
) -> MoodSummary:
    if current.average is None:
        comparison = None
    elif previous.average is None:
        comparison = ComparisonDisplay(
            state="unavailable",
            text="— No previous mood data",
            accessible_label="No previous mood data",
        )
    else:
        comparison = _difference_display(
            current.average - previous.average,
            decimal_places=1,
        )
    return replace(
        current,
        comparison=comparison,
        previous_trend=previous.trend,
        previous_recorded_count=previous.recorded_count,
    )


def _blocker_breakdown(outreach: list[DailyOutreach]) -> tuple[BreakdownItem, ...]:
    """Return only real positive blockers in stable approved category order."""
    counts = Counter(
        record.blocker_tag
        for record in outreach
        if record.blocker_tag not in {None, "", "No blocker"}
    )
    option_order = {
        value: index
        for index, (value, _label) in enumerate(BLOCKER_OPTIONS)
    }
    ordered_counts = Counter()
    for key, value in sorted(
        counts.items(),
        key=lambda item: (option_order.get(item[0], len(option_order)),),
    ):
        ordered_counts[key] = value
    return _relative_breakdown(ordered_counts)


def _pipeline_conversion_summary(
    meetings: list[PipelineMeeting],
) -> PipelineConversionSummary:
    """Calculate documented pipeline rates with one shared denominator."""
    total_meetings = len(meetings)
    concrete_next_step_outcomes = {
        StoredPipelineOutcome.FOLLOW_UP,
        StoredPipelineOutcome.INTRODUCTION,
        StoredPipelineOutcome.PROPOSAL_REQUESTED,
        StoredPipelineOutcome.MEETING_BOOKED,
        StoredPipelineOutcome.OPPORTUNITY_IDENTIFIED,
    }
    definitions = (
        (
            "high_engagement",
            "High-engagement rate",
            sum(
                meeting.customer_engagement == CustomerEngagement.HIGH
                for meeting in meetings
            ),
        ),
        (
            "need_identification",
            "Need-identification rate",
            sum(
                meeting.need_identified == NeedIdentified.YES
                for meeting in meetings
            ),
        ),
        (
            "concrete_next_step",
            "Concrete-next-step rate",
            sum(
                meeting.outcome in concrete_next_step_outcomes
                for meeting in meetings
            ),
        ),
        (
            "proposal",
            "Proposal rate",
            sum(
                meeting.outcome == StoredPipelineOutcome.PROPOSAL_REQUESTED
                for meeting in meetings
            ),
        ),
        (
            "opportunity_identification",
            "Opportunity identification rate",
            sum(
                meeting.outcome == StoredPipelineOutcome.OPPORTUNITY_IDENTIFIED
                for meeting in meetings
            ),
        ),
    )
    metrics = tuple(
        PipelineConversionMetric(
            key=key,
            label=label,
            numerator=numerator,
            denominator=total_meetings,
            percentage=(
                int(
                    (
                        Decimal(numerator)
                        / Decimal(total_meetings)
                        * Decimal(100)
                    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP),
                )
                if total_meetings
                else None
            ),
        )
        for key, label, numerator in definitions
    )
    return PipelineConversionSummary(
        total_meetings=total_meetings,
        metrics=metrics,
    )


def _outreach_conversion_summary(
    outreach: list[DailyOutreach],
) -> OutreachConversionSummary:
    """Calculate rates after summing every selected record's components."""
    total_activities = sum(record.total_activities for record in outreach)
    companies_contacted = sum(record.unique_companies for record in outreach)
    definitions = (
        (
            "reply",
            "Reply rate",
            sum(record.replies or 0 for record in outreach),
            total_activities,
        ),
        (
            "positive_reply",
            "Positive reply rate",
            sum(record.positive_replies or 0 for record in outreach),
            total_activities,
        ),
        (
            "meeting_booking",
            "Outreach meeting booking rate",
            sum(record.meetings_booked or 0 for record in outreach),
            companies_contacted,
        ),
    )
    metrics = tuple(
        OutreachConversionMetric(
            key=key,
            label=label,
            numerator=numerator,
            denominator=denominator,
            percentage=(
                int(
                    (
                        Decimal(numerator)
                        / Decimal(denominator)
                        * Decimal(100)
                    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP),
                )
                if denominator
                else None
            ),
        )
        for key, label, numerator, denominator in definitions
    )
    return OutreachConversionSummary(
        record_count=len(outreach),
        metrics=metrics,
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
    comparison_periods = resolve_comparison_periods(selected_period)
    outreach, meetings = _company_records(
        session,
        start_date=selected_period.start_date,
        end_date=selected_period.end_date,
        user_ids=selected_user_ids,
    )
    current_outreach = [
        record
        for record in outreach
        if comparison_periods.current.start_date
        <= record.activity_date
        <= comparison_periods.current.end_date
    ]
    current_meetings = [
        meeting
        for meeting in meetings
        if comparison_periods.current.start_date
        <= meeting.occurred_at.date()
        <= comparison_periods.current.end_date
    ]
    previous_outreach, previous_meetings = _company_records(
        session,
        start_date=comparison_periods.previous.start_date,
        end_date=comparison_periods.previous.end_date,
        user_ids=selected_user_ids,
    )
    actuals = aggregate_activity_actuals(outreach, meetings)
    comparison_actuals = aggregate_activity_actuals(
        current_outreach,
        current_meetings,
    )
    previous_actuals = aggregate_activity_actuals(
        previous_outreach,
        previous_meetings,
    )
    targets = _company_targets(
        session,
        start_date=selected_period.start_date,
        end_date=selected_period.end_date,
        user_ids=selected_user_ids,
    )
    metrics = tuple(
        replace(
            _build_dashboard_metric(
                key=metric,
                label=DASHBOARD_METRIC_LABEL_OVERRIDES.get(metric, label),
                actual=actuals[metric],
                target=targets[metric],
            ),
            comparison=_difference_display(
                Decimal(comparison_actuals[metric] - previous_actuals[metric]),
            ),
        )
        for metric, label in TARGET_FIELDS
    )
    pipeline_conversions = _pipeline_conversion_summary(meetings)
    outreach_conversions = _outreach_conversion_summary(outreach)
    current_pipeline_conversions = _pipeline_conversion_summary(
        current_meetings,
    )
    previous_pipeline_conversions = _pipeline_conversion_summary(
        previous_meetings,
    )
    pipeline_conversions = replace(
        pipeline_conversions,
        metrics=_attach_rate_comparisons(
            pipeline_conversions.metrics,
            current_pipeline_conversions.metrics,
            previous_pipeline_conversions.metrics,
        ),
    )
    current_outreach_conversions = _outreach_conversion_summary(
        current_outreach,
    )
    previous_outreach_conversions = _outreach_conversion_summary(
        previous_outreach,
    )
    outreach_conversions = replace(
        outreach_conversions,
        metrics=_attach_rate_comparisons(
            outreach_conversions.metrics,
            current_outreach_conversions.metrics,
            previous_outreach_conversions.metrics,
        ),
    )
    blockers = _blocker_breakdown(outreach)
    mood_summary = _attach_mood_comparison(
        _mood_summary(comparison_periods.current, current_outreach),
        _mood_summary(
            comparison_periods.previous,
            previous_outreach,
            position_count=comparison_periods.current.duration_days,
        ),
    )
    outreach_metrics = {
        metric.key: metric for metric in outreach_conversions.metrics
    }
    positive_replies = outreach_metrics["positive_reply"].numerator
    meetings_booked = outreach_metrics["meeting_booking"].numerator
    discussion_prompts = build_discussion_prompts(
        difficult_mood_dates=(
            record.activity_date
            for record in outreach
            if record.user_mood == UserMood.DIFFICULT
        ),
        total_meetings=pipeline_conversions.total_meetings,
        positive_replies=positive_replies,
        meetings_booked=meetings_booked,
        blocker_counts=(
            (item.label, item.value)
            for item in blockers
        ),
    )
    activity_granularity = _activity_bucket_granularity(selected_period)
    return DashboardSummary(
        selected_period=selected_period,
        comparison_periods=comparison_periods,
        metrics=metrics,
        pipeline_conversions=pipeline_conversions,
        outreach_conversions=outreach_conversions,
        activity_buckets=_activity_buckets(
            selected_period,
            outreach,
            meetings,
            granularity=activity_granularity,
        ),
        activity_granularity=activity_granularity,
        countries=_country_breakdown(session, outreach),
        blockers=blockers,
        discussion_prompts=discussion_prompts,
        mood_summary=mood_summary,
        comments=_dashboard_comments(session, outreach, meetings),
        has_activity=bool(outreach or meetings),
        has_selected_users=(
            user_filter is None
            or user_filter.includes_all
            or bool(user_filter.user_ids)
        ),
    )


__all__ = [
    "ACTIVITY_GRANULARITY_DAY",
    "ACTIVITY_GRANULARITY_MONTH",
    "ACTIVITY_GRANULARITY_PERIOD",
    "ACTIVITY_GRANULARITY_WEEK",
    "ACTIVITY_HEADINGS",
    "CURRENT_MONTH",
    "CURRENT_WEEK",
    "CUSTOM_RANGE",
    "ComparisonDisplay",
    "ComparisonPeriod",
    "DashboardComparisonPeriods",
    "DashboardFilter",
    "DashboardComment",
    "DashboardMetric",
    "DashboardSummary",
    "MoodSummary",
    "MoodTrendPoint",
    "DashboardUserFilter",
    "DashboardUserOption",
    "OutreachConversionMetric",
    "OutreachConversionSummary",
    "PERIOD_OPTIONS",
    "PREVIOUS_WEEK",
    "PipelineConversionMetric",
    "PipelineConversionSummary",
    "ResolvedDashboardFilters",
    "USER_SCOPE_ALL",
    "USER_SCOPE_SELECTED",
    "get_dashboard_user_options",
    "get_dashboard_summary",
    "group_dashboard_comments",
    "normalize_dashboard_user_filter",
    "resolve_dashboard_filter",
    "resolve_dashboard_filters",
    "resolve_comparison_periods",
]
