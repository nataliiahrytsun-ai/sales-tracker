"""Focused validation coverage for required meeting companies and outcomes."""

from app.models import PipelineOutcome
from app.services.meetings import MeetingFormValues, validate_meeting_form


def test_company_is_required_trimmed_and_new_outcomes_are_accepted() -> None:
    """New submissions require a real Company and retain its trimmed value."""
    for outcome in PipelineOutcome:
        values, errors = validate_meeting_form(
            MeetingFormValues(
                customer_engagement="High",
                need_identified="Yes",
                outcome=outcome.value,
                company_name="  Northstar GmbH  ",
            ),
        )
        assert errors == {}
        assert values is not None
        assert values.company_name == "Northstar GmbH"


def test_company_and_removed_outcomes_are_rejected() -> None:
    """Whitespace-only companies and removed taxonomy values cannot be saved."""
    values, errors = validate_meeting_form(
        MeetingFormValues(
            customer_engagement="High",
            need_identified="Yes",
            outcome="Follow-up",
            company_name=" \t ",
        ),
    )
    assert values is None
    assert errors["company_name"] == "Enter a company."
    assert errors["outcome"] == "Select a meeting outcome."
