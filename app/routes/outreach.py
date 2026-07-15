"""Private create/update routes for today's daily outreach summary."""

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.auth import get_current_user
from app.database import get_session
from app.models import User, UserMood
from app.services.outreach import (
    BLOCKER_OPTIONS,
    COUNTRY_NAMES_BY_CODE,
    COUNTRY_OPTIONS,
    OutreachFormValues,
    country_rows_from_submission,
    current_local_date,
    form_values_from_record,
    get_daily_outreach,
    get_recent_outreach,
    upsert_daily_outreach,
    validate_outreach_form,
)

router = APIRouter(prefix="/outreach", tags=["outreach"])
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parents[1] / "templates",
)


def country_total_from_values(values: OutreachFormValues) -> int:
    """Sum valid non-negative country counts for template display."""
    total = 0
    for row in values.country_rows:
        try:
            count = int(row.companies_contacted)
        except ValueError:
            continue
        if count >= 0:
            total += count
    return total


def outreach_template_context(
    current_user: User,
    activity_date: date,
    values: OutreachFormValues,
    *,
    errors: dict[str, str] | None = None,
    saved: bool = False,
    dated: bool = False,
) -> dict[str, object]:
    """Build the shared outreach form template context."""
    country_total = country_total_from_values(values)
    country_rows = [
        {
            "code": row.country_code,
            "name": COUNTRY_NAMES_BY_CODE.get(
                row.country_code,
                row.country_code or "Unknown country",
            ),
            "count": row.companies_contacted,
            "error": (errors or {}).get(f"country_count_{index}"),
        }
        for index, row in enumerate(values.country_rows)
    ]
    return {
        "current_user": current_user,
        "activity_date": activity_date,
        "values": values,
        "errors": errors or {},
        "saved": saved,
        "country_total": country_total,
        "dated": dated,
        "mood_options": tuple(UserMood),
        "blocker_options": BLOCKER_OPTIONS,
        "country_options": COUNTRY_OPTIONS,
        "country_rows": country_rows,
    }


@router.get("/today", response_class=HTMLResponse)
def today_outreach(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    activity_date: Annotated[date, Depends(current_local_date)],
    saved: bool = False,
) -> Response:
    """Render today's owned outreach record or an empty form."""
    assert current_user.id is not None
    record = get_daily_outreach(
        session,
        user_id=current_user.id,
        activity_date=activity_date,
    )
    values = (
        OutreachFormValues()
        if record is None
        else form_values_from_record(session, record)
    )
    return templates.TemplateResponse(
        request=request,
        name="outreach_form.html",
        context=outreach_template_context(
            current_user,
            activity_date,
            values,
            saved=saved and record is not None,
        ),
    )


@router.post("/today", response_class=HTMLResponse)
def save_today_outreach(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    activity_date: Annotated[date, Depends(current_local_date)],
    total_activities: Annotated[str, Form()] = "",
    country_codes: Annotated[list[str] | None, Form()] = None,
    country_counts: Annotated[list[str] | None, Form()] = None,
    replies: Annotated[str, Form()] = "",
    positive_replies: Annotated[str, Form()] = "",
    meetings_booked: Annotated[str, Form()] = "",
    user_mood: Annotated[str, Form()] = "",
    blocker_tag: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
) -> Response:
    """Validate and upsert today's record for the authenticated user."""
    values = OutreachFormValues(
        total_activities=total_activities,
        country_rows=country_rows_from_submission(
            country_codes or [],
            country_counts or [],
        ),
        replies=replies,
        positive_replies=positive_replies,
        meetings_booked=meetings_booked,
        user_mood=user_mood,
        blocker_tag=blocker_tag,
        note=note,
    )
    validated_values, errors = validate_outreach_form(values)
    if validated_values is None:
        return templates.TemplateResponse(
            request=request,
            name="outreach_form.html",
            context=outreach_template_context(
                current_user,
                activity_date,
                values,
                errors=errors,
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    assert current_user.id is not None
    try:
        upsert_daily_outreach(
            session,
            user_id=current_user.id,
            activity_date=activity_date,
            values=validated_values,
        )
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        return templates.TemplateResponse(
            request=request,
            name="outreach_form.html",
            context=outreach_template_context(
                current_user,
                activity_date,
                values,
                errors={
                    "form": "Today's outreach could not be saved. Please try again.",
                },
            ),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return RedirectResponse(
        url="/outreach/today?saved=true",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/recent", response_class=HTMLResponse)
def recent_outreach(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(current_local_date)],
    saved: bool = False,
) -> Response:
    """List the current user's outreach summaries from the last 30 days."""
    assert current_user.id is not None
    records = get_recent_outreach(
        session,
        user_id=current_user.id,
        today=today,
    )
    return templates.TemplateResponse(
        request=request,
        name="recent_outreach.html",
        context={
            "current_user": current_user,
            "records": records,
            "start_date": today - timedelta(days=29),
            "end_date": today,
            "saved": saved,
        },
    )


def require_recent_outreach_date(activity_date: date, today: date) -> None:
    """Reject future dates and dates outside the 30-day correction window."""
    if activity_date > today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Future outreach dates are not allowed.",
        )
    if activity_date < today - timedelta(days=29):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


@router.get("/{activity_date}", response_class=HTMLResponse)
def dated_outreach(
    activity_date: date,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(current_local_date)],
    saved: bool = False,
) -> Response:
    """Render an owned outreach record for an editable recent date."""
    require_recent_outreach_date(activity_date, today)
    assert current_user.id is not None
    record = get_daily_outreach(
        session,
        user_id=current_user.id,
        activity_date=activity_date,
    )
    values = (
        OutreachFormValues()
        if record is None
        else form_values_from_record(session, record)
    )
    return templates.TemplateResponse(
        request=request,
        name="outreach_form.html",
        context=outreach_template_context(
            current_user,
            activity_date,
            values,
            saved=saved and record is not None,
            dated=True,
        ),
    )


@router.post("/{activity_date}", response_class=HTMLResponse)
def save_dated_outreach(
    activity_date: date,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(current_local_date)],
    total_activities: Annotated[str, Form()] = "",
    country_codes: Annotated[list[str] | None, Form()] = None,
    country_counts: Annotated[list[str] | None, Form()] = None,
    replies: Annotated[str, Form()] = "",
    positive_replies: Annotated[str, Form()] = "",
    meetings_booked: Annotated[str, Form()] = "",
    user_mood: Annotated[str, Form()] = "",
    blocker_tag: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
) -> Response:
    """Validate and upsert an owned outreach summary for a recent date."""
    require_recent_outreach_date(activity_date, today)
    values = OutreachFormValues(
        total_activities=total_activities,
        country_rows=country_rows_from_submission(
            country_codes or [],
            country_counts or [],
        ),
        replies=replies,
        positive_replies=positive_replies,
        meetings_booked=meetings_booked,
        user_mood=user_mood,
        blocker_tag=blocker_tag,
        note=note,
    )
    validated_values, errors = validate_outreach_form(values)
    if validated_values is None:
        return templates.TemplateResponse(
            request=request,
            name="outreach_form.html",
            context=outreach_template_context(
                current_user,
                activity_date,
                values,
                errors=errors,
                dated=True,
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    assert current_user.id is not None
    try:
        upsert_daily_outreach(
            session,
            user_id=current_user.id,
            activity_date=activity_date,
            values=validated_values,
        )
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        return templates.TemplateResponse(
            request=request,
            name="outreach_form.html",
            context=outreach_template_context(
                current_user,
                activity_date,
                values,
                errors={
                    "form": "Daily outreach could not be saved. Please try again.",
                },
                dated=True,
            ),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return RedirectResponse(
        url=f"/outreach/{activity_date.isoformat()}?saved=true",
        status_code=status.HTTP_303_SEE_OTHER,
    )
