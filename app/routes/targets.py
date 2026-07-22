"""Private personal weekly-target routes."""

from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.auth import get_current_user
from app.database import get_session
from app.models import User
from app.services.outreach import current_local_date
from app.services.targets import (
    EDITABLE_TARGET_FIELDS,
    TargetFormValues,
    TargetWeek,
    current_week_bounds,
    form_values_from_targets,
    get_user_targets,
    resolve_target_week,
    target_week_presentation,
    upsert_user_targets,
    validate_target_form,
)

router = APIRouter(prefix="/targets", tags=["targets"])
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parents[1] / "templates",
)


def target_template_context(
    current_user: User,
    values: TargetFormValues,
    today: date,
    selected_week: TargetWeek,
    *,
    errors: dict[str, str] | None = None,
    saved: bool = False,
) -> dict[str, object]:
    """Build the weekly-target form context."""
    current_week_start, _ = current_week_bounds(today)
    week_presentation = target_week_presentation(selected_week, today=today)
    return {
        "current_user": current_user,
        "values": values,
        "errors": errors or {},
        "saved": saved,
        "target_fields": EDITABLE_TARGET_FIELDS,
        "selected_week": selected_week,
        "week_presentation": week_presentation,
        "is_past_week": selected_week.start_date < current_week_start,
    }


@router.get("", response_class=HTMLResponse)
def targets_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(current_local_date)],
    week: Annotated[str | None, Query()] = None,
    saved: bool = False,
) -> Response:
    """Render the current user's targets for a validated ISO week."""
    selected_week, week_error = resolve_target_week(week, today=today)
    if selected_week is None:
        fallback_week, _ = resolve_target_week(None, today=today)
        assert fallback_week is not None
        return templates.TemplateResponse(
            request=request,
            name="targets.html",
            context=target_template_context(
                current_user,
                TargetFormValues(),
                today,
                fallback_week,
                errors={"week": week_error or "Select a valid ISO calendar week."},
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    assert current_user.id is not None
    targets = get_user_targets(
        session,
        user_id=current_user.id,
        week_start=selected_week.start_date,
    )
    values = (
        TargetFormValues()
        if not targets
        else form_values_from_targets(targets)
    )
    return templates.TemplateResponse(
        request=request,
        name="targets.html",
        context=target_template_context(
            current_user,
            values,
            today,
            selected_week,
            saved=saved and bool(targets),
        ),
    )


@router.post("", response_class=HTMLResponse)
def save_targets(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(current_local_date)],
    week: Annotated[str, Form()] = "",
    total_activities: Annotated[str, Form()] = "",
    companies_contacted: Annotated[str, Form()] = "",
    replies: Annotated[str, Form()] = "",
    positive_replies: Annotated[str, Form()] = "",
    meetings_booked: Annotated[str, Form()] = "",
    meetings_held: Annotated[str, Form()] = "",
    requests_sent: Annotated[str, Form()] = "",
) -> Response:
    """Validate and upsert the current user's weekly targets."""
    values = TargetFormValues(
        total_activities=total_activities,
        companies_contacted=companies_contacted,
        replies=replies,
        positive_replies=positive_replies,
        meetings_booked=meetings_booked,
        meetings_held=meetings_held,
        requests_sent=requests_sent,
    )
    selected_week, week_error = resolve_target_week(week, today=today)
    validated, errors = validate_target_form(values)
    if week_error:
        errors["week"] = week_error
    current_week_start, _ = current_week_bounds(today)
    if selected_week is not None and selected_week.start_date < current_week_start:
        errors["form"] = "Past weekly targets are read-only."
    if validated is None or errors:
        fallback_week, _ = resolve_target_week(None, today=today)
        assert fallback_week is not None
        return templates.TemplateResponse(
            request=request,
            name="targets.html",
            context=target_template_context(
                current_user,
                values,
                today,
                selected_week or fallback_week,
                errors=errors,
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    assert current_user.id is not None
    assert selected_week is not None
    assert validated is not None
    try:
        upsert_user_targets(
            session,
            user_id=current_user.id,
            values=validated,
            week_start=selected_week.start_date,
        )
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        return templates.TemplateResponse(
            request=request,
            name="targets.html",
            context=target_template_context(
                current_user,
                values,
                today,
                selected_week,
                errors={"form": "Weekly targets could not be saved. Please try again."},
            ),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return RedirectResponse(
        url=f"/targets?week={selected_week.value}&saved=true",
        status_code=status.HTTP_303_SEE_OTHER,
    )


__all__ = ["router"]
