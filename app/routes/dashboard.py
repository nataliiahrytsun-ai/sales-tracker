"""Authenticated company-wide aggregate dashboard route."""

from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.auth import get_current_user
from app.database import get_session
from app.models import User
from app.services.dashboard import (
    CURRENT_WEEK,
    PERIOD_OPTIONS,
    get_dashboard_summary,
    resolve_dashboard_filter,
)
from app.services.outreach import current_local_date

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parents[1] / "templates",
)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(current_local_date)],
    period: Annotated[str, Query()] = CURRENT_WEEK,
    from_value: Annotated[str, Query(alias="from")] = "",
    to_value: Annotated[str, Query(alias="to")] = "",
    reset: Annotated[bool, Query()] = False,
) -> Response:
    """Render privacy-safe aggregates for the selected company period."""
    if reset:
        period, from_value, to_value = CURRENT_WEEK, "", ""
    selected_period, error = resolve_dashboard_filter(
        today=today,
        period=period,
        from_value=from_value,
        to_value=to_value,
    )
    summary = (
        None
        if selected_period is None
        else get_dashboard_summary(session, selected_period=selected_period)
    )
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "current_user": current_user,
            "summary": summary,
            "period_options": PERIOD_OPTIONS,
            "selected_period_key": period,
            "from_value": from_value,
            "to_value": to_value,
            "today_value": today.isoformat(),
            "filter_error": error,
        },
        status_code=400 if error else 200,
    )


__all__ = ["router"]
