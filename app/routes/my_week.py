"""Private personal current-week summary route."""

from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.auth import get_current_user
from app.database import get_session
from app.models import User
from app.services.my_week import get_my_week_summary
from app.services.outreach import current_local_date

router = APIRouter(tags=["my-week"])
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parents[1] / "templates",
)


@router.get("/my-week", response_class=HTMLResponse)
def my_week_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(current_local_date)],
) -> Response:
    """Render the current user's current calendar-week summary."""
    assert current_user.id is not None
    summary = get_my_week_summary(
        session,
        user_id=current_user.id,
        today=today,
    )
    return templates.TemplateResponse(
        request=request,
        name="my_week.html",
        context={"current_user": current_user, "summary": summary},
    )


__all__ = ["router"]
