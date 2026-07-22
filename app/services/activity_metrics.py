"""Shared activity totals used by personal and company reporting."""

from collections.abc import Iterable

from app.models import DailyOutreach, PipelineMeeting, PipelineOutcome


def aggregate_activity_actuals(
    outreach_records: Iterable[DailyOutreach],
    meetings: Iterable[PipelineMeeting],
) -> dict[str, int]:
    """Calculate canonical activity actuals from their single sources."""
    outreach = list(outreach_records)
    meeting_records = list(meetings)
    return {
        "total_activities": sum(record.total_activities for record in outreach),
        "companies_contacted": sum(record.unique_companies for record in outreach),
        "replies": sum(record.replies or 0 for record in outreach),
        "positive_replies": sum(record.positive_replies or 0 for record in outreach),
        "meetings_booked": sum(record.meetings_booked or 0 for record in outreach),
        "meetings_held": len(meeting_records),
        "requests_sent": sum(
            meeting.outcome.value == PipelineOutcome.REQUEST_SENT.value
            for meeting in meeting_records
        ),
    }


__all__ = ["aggregate_activity_actuals"]
