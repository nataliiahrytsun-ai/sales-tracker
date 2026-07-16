"""Privacy-safe CSV export queries and serialization."""

import csv
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from enum import Enum
from io import StringIO

from sqlmodel import Session, select

from app.models import DailyOutreach, OutreachCountry, PipelineMeeting, User
from app.services.dashboard import (
    DashboardFilter,
    DashboardUserFilter,
    DashboardUserOption,
)
from app.services.meetings import meeting_date_bounds

PIPELINE_COLUMNS = (
    "user_name",
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
)

OUTREACH_COLUMNS = (
    "user_name",
    "activity_date",
    "total_activities",
    "unique_companies",
    "replies",
    "positive_replies",
    "meetings_booked",
    "user_mood",
    "blocker_tag",
    "note",
    "country_breakdown",
    "created_at",
    "updated_at",
)


def safe_filename_slug(name: str) -> str:
    """Return a lowercase ASCII slug safe for a download filename."""
    ascii_name = (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    return slug or "user"


def user_scope_filename_part(
    user_filter: DashboardUserFilter,
    user_options: Sequence[DashboardUserOption],
) -> str:
    """Describe the normalized user scope without exposing IDs or email."""
    selected_ids = (
        {option.user_id for option in user_options}
        if user_filter.includes_all
        else set(user_filter.user_ids)
    )
    if not selected_ids:
        return "no-users"
    return "_".join(
        safe_filename_slug(option.label)
        for option in user_options
        if option.user_id in selected_ids
    )


def _safe_csv_value(value: object) -> str | int | float:
    """Serialize stable values and neutralize Excel formula prefixes."""
    if value is None:
        return ""
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def build_csv(
    columns: Sequence[str],
    rows: Iterable[Sequence[object]],
) -> str:
    """Return an Excel-friendly UTF-8 CSV string with a BOM."""
    output = StringIO(newline="")
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(columns)
    writer.writerows(
        tuple(_safe_csv_value(value) for value in row)
        for row in rows
    )
    return output.getvalue()


def _selected_user_ids(
    user_filter: DashboardUserFilter,
) -> tuple[int, ...] | None:
    return None if user_filter.includes_all else user_filter.user_ids


def pipeline_csv(
    session: Session,
    *,
    selected_period: DashboardFilter,
    user_filter: DashboardUserFilter,
) -> str:
    """Export one filtered Pipeline Meeting per CSV row."""
    start_time, end_time = meeting_date_bounds(
        selected_period.start_date,
        selected_period.end_date,
    )
    query = (
        select(PipelineMeeting, User.name)
        .join(User, PipelineMeeting.user_id == User.id)
        .where(
            PipelineMeeting.occurred_at >= start_time,
            PipelineMeeting.occurred_at < end_time,
        )
        .order_by(PipelineMeeting.occurred_at, PipelineMeeting.id)
    )
    user_ids = _selected_user_ids(user_filter)
    if user_ids is not None:
        query = query.where(PipelineMeeting.user_id.in_(user_ids))
    rows = (
        (
            user_name,
            meeting.occurred_at,
            meeting.company_name,
            meeting.country_code,
            meeting.customer_engagement,
            meeting.need_identified,
            meeting.outcome,
            meeting.user_mood,
            meeting.blocker_tag,
            meeting.next_step_date,
            meeting.note,
            meeting.created_at,
            meeting.updated_at,
        )
        for meeting, user_name in session.exec(query).all()
    )
    return build_csv(PIPELINE_COLUMNS, rows)


def outreach_csv(
    session: Session,
    *,
    selected_period: DashboardFilter,
    user_filter: DashboardUserFilter,
) -> str:
    """Export one filtered Daily Outreach record per CSV row."""
    query = (
        select(DailyOutreach, User.name)
        .join(User, DailyOutreach.user_id == User.id)
        .where(
            DailyOutreach.activity_date >= selected_period.start_date,
            DailyOutreach.activity_date <= selected_period.end_date,
        )
        .order_by(DailyOutreach.activity_date, DailyOutreach.id)
    )
    user_ids = _selected_user_ids(user_filter)
    if user_ids is not None:
        query = query.where(DailyOutreach.user_id.in_(user_ids))
    records = list(session.exec(query).all())
    record_ids = [record.id for record, _name in records if record.id is not None]
    countries_by_record: dict[int, list[str]] = defaultdict(list)
    if record_ids:
        country_query = (
            select(OutreachCountry)
            .where(OutreachCountry.outreach_daily_id.in_(record_ids))
            .order_by(
                OutreachCountry.outreach_daily_id,
                OutreachCountry.country_code,
            )
        )
        for country in session.exec(country_query).all():
            countries_by_record[country.outreach_daily_id].append(
                f"{country.country_code}:{country.companies_contacted}",
            )
    rows = (
        (
            user_name,
            record.activity_date,
            record.total_activities,
            record.unique_companies,
            record.replies,
            record.positive_replies,
            record.meetings_booked,
            record.user_mood,
            record.blocker_tag,
            record.note,
            "; ".join(countries_by_record.get(record.id or 0, ())),
            record.created_at,
            record.updated_at,
        )
        for record, user_name in records
    )
    return build_csv(OUTREACH_COLUMNS, rows)


__all__ = [
    "OUTREACH_COLUMNS",
    "PIPELINE_COLUMNS",
    "build_csv",
    "outreach_csv",
    "pipeline_csv",
    "safe_filename_slug",
    "user_scope_filename_part",
]
