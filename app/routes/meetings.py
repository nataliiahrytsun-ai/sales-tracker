"""Private pipeline meeting entry routes."""

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models import (
    CustomerEngagement,
    NeedIdentified,
    PipelineMeeting,
    PipelineOutcome,
    User,
    UserMood,
)
from app.services.meetings import (
    BLOCKER_OPTIONS,
    COUNTRY_NAMES_BY_CODE,
    COUNTRY_OPTIONS,
    MeetingFormValues,
    apply_meeting_values,
    form_values_from_meeting,
    get_owned_recent_meeting,
    get_recent_meetings,
    validate_meeting_form,
)
from app.services.outreach import current_local_date

router = APIRouter(prefix="/meetings", tags=["meetings"])
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parents[1] / "templates",
)
LAST_CREATED_MEETING_SESSION_KEY = "last_created_meeting_id"


def meeting_template_context(
    current_user: User,
    values: MeetingFormValues,
    *,
    errors: dict[str, str] | None = None,
    saved_meeting_id: int | None = None,
    undone: bool = False,
    meeting_id: int | None = None,
    editing_meeting: PipelineMeeting | None = None,
) -> dict[str, object]:
    """Build the shared meeting form template context."""
    return {
        "current_user": current_user,
        "values": values,
        "errors": errors or {},
        "saved_meeting_id": saved_meeting_id,
        "undone": undone,
        "meeting_id": meeting_id,
        "editing": meeting_id is not None,
        "editing_meeting": editing_meeting,
        "customer_engagement_options": tuple(CustomerEngagement),
        "need_identified_options": tuple(NeedIdentified),
        "outcome_options": tuple(PipelineOutcome),
        "mood_options": tuple(UserMood),
        "country_options": COUNTRY_OPTIONS,
        "selected_country_name": COUNTRY_NAMES_BY_CODE.get(
            values.country_code,
            values.country_code,
        ),
        "blocker_options": BLOCKER_OPTIONS,
    }


@router.get("/new", response_class=HTMLResponse)
def new_meeting(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    saved: int | None = None,
    undone: bool = False,
) -> Response:
    """Render the private pipeline meeting entry form."""
    saved_meeting_id: int | None = None
    last_created_meeting_id = request.session.get(
        LAST_CREATED_MEETING_SESSION_KEY,
    )
    if saved is None:
        request.session.pop(LAST_CREATED_MEETING_SESSION_KEY, None)
    elif saved == last_created_meeting_id:
        saved_meeting_id = session.exec(
            select(PipelineMeeting.id).where(
                PipelineMeeting.id == saved,
                PipelineMeeting.user_id == current_user.id,
            ),
        ).one_or_none()
        if saved_meeting_id is None:
            request.session.pop(LAST_CREATED_MEETING_SESSION_KEY, None)

    return templates.TemplateResponse(
        request=request,
        name="meeting_form.html",
        context=meeting_template_context(
            current_user,
            MeetingFormValues(),
            saved_meeting_id=saved_meeting_id,
            undone=undone,
        ),
    )


@router.post("", response_class=HTMLResponse)
def create_meeting(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    customer_engagement: Annotated[str, Form()] = "",
    need_identified: Annotated[str, Form()] = "",
    outcome: Annotated[str, Form()] = "",
    user_mood: Annotated[str, Form()] = "",
    blocker_tag: Annotated[str, Form()] = "",
    country_code: Annotated[str, Form()] = "",
    company_name: Annotated[str, Form()] = "",
    next_step_date: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
) -> Response:
    """Validate and save a meeting owned by the authenticated user."""
    values = MeetingFormValues(
        customer_engagement=customer_engagement,
        need_identified=need_identified,
        outcome=outcome,
        user_mood=user_mood,
        blocker_tag=blocker_tag,
        country_code=country_code,
        company_name=company_name,
        next_step_date=next_step_date,
        note=note,
    )
    validated_values, errors = validate_meeting_form(values)
    if validated_values is None:
        return templates.TemplateResponse(
            request=request,
            name="meeting_form.html",
            context=meeting_template_context(
                current_user,
                values,
                errors=errors,
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    assert current_user.id is not None
    meeting = PipelineMeeting(
        user_id=current_user.id,
        customer_engagement=validated_values.customer_engagement,
        need_identified=validated_values.need_identified,
        outcome=validated_values.outcome,
    )
    apply_meeting_values(meeting, validated_values)
    session.add(meeting)
    try:
        session.commit()
        session.refresh(meeting)
    except SQLAlchemyError:
        session.rollback()
        return templates.TemplateResponse(
            request=request,
            name="meeting_form.html",
            context=meeting_template_context(
                current_user,
                values,
                errors={
                    "form": "Meeting could not be saved. Please try again.",
                },
            ),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    assert meeting.id is not None
    request.session[LAST_CREATED_MEETING_SESSION_KEY] = meeting.id
    return RedirectResponse(
        url=f"/meetings/new?saved={meeting.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/recent", response_class=HTMLResponse)
def recent_meetings(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(current_local_date)],
    updated: bool = False,
    deleted: bool = False,
) -> Response:
    """List the current user's meetings from the last 30 calendar days."""
    assert current_user.id is not None
    meetings = get_recent_meetings(
        session,
        user_id=current_user.id,
        today=today,
    )
    return templates.TemplateResponse(
        request=request,
        name="recent_meetings.html",
        context={
            "current_user": current_user,
            "meetings": meetings,
            "start_date": today - timedelta(days=29),
            "end_date": today,
            "updated": updated,
            "deleted": deleted,
        },
    )


def require_owned_recent_meeting(
    session: Session,
    *,
    meeting_id: int,
    user_id: int,
    today: date,
) -> PipelineMeeting:
    """Return an owned recent meeting or conceal it behind a 404."""
    meeting = get_owned_recent_meeting(
        session,
        meeting_id=meeting_id,
        user_id=user_id,
        today=today,
    )
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return meeting


@router.get("/{meeting_id}/edit", response_class=HTMLResponse)
def edit_meeting(
    meeting_id: int,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(current_local_date)],
) -> Response:
    """Render the shared meeting form for one owned recent meeting."""
    assert current_user.id is not None
    meeting = require_owned_recent_meeting(
        session,
        meeting_id=meeting_id,
        user_id=current_user.id,
        today=today,
    )
    return templates.TemplateResponse(
        request=request,
        name="meeting_form.html",
        context=meeting_template_context(
            current_user,
            form_values_from_meeting(meeting),
            meeting_id=meeting_id,
            editing_meeting=meeting,
        ),
    )


@router.post("/{meeting_id}", response_class=HTMLResponse)
def update_meeting(
    meeting_id: int,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(current_local_date)],
    customer_engagement: Annotated[str, Form()] = "",
    need_identified: Annotated[str, Form()] = "",
    outcome: Annotated[str, Form()] = "",
    user_mood: Annotated[str, Form()] = "",
    blocker_tag: Annotated[str, Form()] = "",
    country_code: Annotated[str, Form()] = "",
    company_name: Annotated[str, Form()] = "",
    next_step_date: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
) -> Response:
    """Validate and update one owned recent meeting."""
    assert current_user.id is not None
    meeting = require_owned_recent_meeting(
        session,
        meeting_id=meeting_id,
        user_id=current_user.id,
        today=today,
    )
    values = MeetingFormValues(
        customer_engagement=customer_engagement,
        need_identified=need_identified,
        outcome=outcome,
        user_mood=user_mood,
        blocker_tag=blocker_tag,
        country_code=country_code,
        company_name=company_name,
        next_step_date=next_step_date,
        note=note,
    )
    validated_values, errors = validate_meeting_form(values)
    if validated_values is None:
        return templates.TemplateResponse(
            request=request,
            name="meeting_form.html",
            context=meeting_template_context(
                current_user,
                values,
                errors=errors,
                meeting_id=meeting_id,
                editing_meeting=meeting,
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    apply_meeting_values(meeting, validated_values)
    session.add(meeting)
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        return templates.TemplateResponse(
            request=request,
            name="meeting_form.html",
            context=meeting_template_context(
                current_user,
                values,
                errors={"form": "Meeting could not be updated. Please try again."},
                meeting_id=meeting_id,
                editing_meeting=meeting,
            ),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return RedirectResponse(
        url="/meetings/recent?updated=true",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{meeting_id}/delete")
def delete_meeting(
    meeting_id: int,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(current_local_date)],
) -> Response:
    """Delete one owned recent meeting through a POST-only action."""
    assert current_user.id is not None
    meeting = require_owned_recent_meeting(
        session,
        meeting_id=meeting_id,
        user_id=current_user.id,
        today=today,
    )
    session.delete(meeting)
    try:
        session.commit()
    except SQLAlchemyError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Meeting could not be deleted.",
        ) from error

    if request.session.get(LAST_CREATED_MEETING_SESSION_KEY) == meeting_id:
        request.session.pop(LAST_CREATED_MEETING_SESSION_KEY, None)
    return RedirectResponse(
        url="/meetings/recent?deleted=true",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{meeting_id}/undo")
def undo_meeting(
    meeting_id: int,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Undo a save by deleting that meeting for its owning user."""
    if request.session.get(LAST_CREATED_MEETING_SESSION_KEY) != meeting_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    meeting = session.exec(
        select(PipelineMeeting).where(
            PipelineMeeting.id == meeting_id,
            PipelineMeeting.user_id == current_user.id,
        ),
    ).one_or_none()
    if meeting is None:
        request.session.pop(LAST_CREATED_MEETING_SESSION_KEY, None)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    session.delete(meeting)
    try:
        session.commit()
    except SQLAlchemyError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Meeting could not be undone.",
        ) from error

    request.session.pop(LAST_CREATED_MEETING_SESSION_KEY, None)
    return RedirectResponse(
        url="/meetings/new?undone=true",
        status_code=status.HTTP_303_SEE_OTHER,
    )
