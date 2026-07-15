"""Private personal weekly-target routes."""

from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.auth import get_current_user
from app.database import get_session
from app.models import User
from app.services.outreach import current_local_date
from app.services.targets import (
    TARGET_FIELDS,
    TargetFormValues,
    current_week_bounds,
    form_values_from_targets,
    get_user_targets,
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
    *,
    errors: dict[str, str] | None = None,
    saved: bool = False,
) -> dict[str, object]:
    """Build the weekly-target form context."""
    week_start, week_end = current_week_bounds(today)
    return {
        "current_user": current_user,
        "values": values,
        "errors": errors or {},
        "saved": saved,
        "target_fields": TARGET_FIELDS,
        "week_start": week_start,
        "week_end": week_end,
    }


@router.get("", response_class=HTMLResponse)
def targets_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(current_local_date)],
    saved: bool = False,
) -> Response:
    """Render the current user's personal weekly targets."""
    assert current_user.id is not None
    targets = get_user_targets(session, user_id=current_user.id)
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
            saved=saved and bool(targets),
        ),
    )


@router.post("", response_class=HTMLResponse)
def save_targets(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(current_local_date)],
    total_activities: Annotated[str, Form()] = "",
    companies_contacted: Annotated[str, Form()] = "",
    replies: Annotated[str, Form()] = "",
    positive_replies: Annotated[str, Form()] = "",
    meetings_booked: Annotated[str, Form()] = "",
    meetings_held: Annotated[str, Form()] = "",
) -> Response:
    """Validate and upsert the current user's weekly targets."""
    values = TargetFormValues(
        total_activities=total_activities,
        companies_contacted=companies_contacted,
        replies=replies,
        positive_replies=positive_replies,
        meetings_booked=meetings_booked,
        meetings_held=meetings_held,
    )
    validated, errors = validate_target_form(values)
    if validated is None:
        return templates.TemplateResponse(
            request=request,
            name="targets.html",
            context=target_template_context(
                current_user,
                values,
                today,
                errors=errors,
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    assert current_user.id is not None
    try:
        upsert_user_targets(
            session,
            user_id=current_user.id,
            values=validated,
            today=today,
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
                errors={"form": "Weekly targets could not be saved. Please try again."},
            ),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return RedirectResponse(
        url="/targets?saved=true",
        status_code=status.HTTP_303_SEE_OTHER,
    )


__all__ = ["router"]
