"""Shared date-range handling for recent-record lists."""

from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import urlencode


DEFAULT_RECENT_DAYS = 7


def default_recent_date_values(today: date) -> tuple[str, str]:
    """Return the default inclusive seven-day range as form values."""
    start_date = today - timedelta(days=DEFAULT_RECENT_DAYS - 1)
    return start_date.isoformat(), today.isoformat()


def build_recent_range_query(
    from_value: str | None,
    to_value: str | None,
) -> str:
    """Preserve an explicitly supplied range in links and redirects."""
    if from_value is None and to_value is None:
        return ""
    return urlencode({"from": from_value or "", "to": to_value or ""})


@dataclass(frozen=True)
class RecentDateRange:
    """Submitted filter values and their validated calendar dates."""

    from_value: str
    to_value: str
    start_date: date | None
    end_date: date | None
    error: str | None = None

    @property
    def query_string(self) -> str:
        """Return an encoded query string that preserves both fields."""
        return urlencode({"from": self.from_value, "to": self.to_value})

    @property
    def is_valid(self) -> bool:
        """Report whether both values form an accepted range."""
        return self.error is None


def resolve_recent_date_range(
    *,
    today: date,
    from_value: str | None,
    to_value: str | None,
) -> RecentDateRange:
    """Validate a submitted range or return the inclusive seven-day default."""
    if from_value is None and to_value is None:
        default_from, default_to = default_recent_date_values(today)
        start_date = date.fromisoformat(default_from)
        return RecentDateRange(
            from_value=default_from,
            to_value=default_to,
            start_date=start_date,
            end_date=today,
        )

    cleaned_from = (from_value or "").strip()
    cleaned_to = (to_value or "").strip()
    if not cleaned_from or not cleaned_to:
        return RecentDateRange(
            from_value=cleaned_from,
            to_value=cleaned_to,
            start_date=None,
            end_date=None,
            error="Enter both From and To dates.",
        )

    try:
        start_date = date.fromisoformat(cleaned_from)
        end_date = date.fromisoformat(cleaned_to)
    except ValueError:
        return RecentDateRange(
            from_value=cleaned_from,
            to_value=cleaned_to,
            start_date=None,
            end_date=None,
            error="Enter valid From and To dates.",
        )

    error: str | None = None
    if end_date > today:
        error = "To date cannot be in the future."
    elif start_date > end_date:
        error = "From date cannot be later than To date."

    return RecentDateRange(
        from_value=cleaned_from,
        to_value=cleaned_to,
        start_date=start_date,
        end_date=end_date,
        error=error,
    )


__all__ = [
    "DEFAULT_RECENT_DAYS",
    "RecentDateRange",
    "build_recent_range_query",
    "default_recent_date_values",
    "resolve_recent_date_range",
]
