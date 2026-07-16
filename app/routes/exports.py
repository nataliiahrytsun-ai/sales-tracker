"""Authenticated Company Dashboard CSV export routes."""

from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse, Response
from sqlmodel import Session

from app.auth import get_current_user
from app.database import get_session
from app.models import User
from app.services.dashboard import CURRENT_WEEK, resolve_dashboard_filters
from app.services.exports import (
    outreach_csv,
    pipeline_csv,
    user_scope_filename_part,
)
from app.services.outreach import current_local_date

router = APIRouter(prefix="/exports", tags=["exports"])


def _csv_response(
    *,
    session: Session,
    today: date,
    period: str,
    from_value: str,
    to_value: str,
    user_scope: str | None,
    user_ids: list[str],
    export_name: str,
    exporter: Callable[..., str],
) -> Response:
    resolved = resolve_dashboard_filters(
        session,
        today=today,
        period=period,
        from_value=from_value,
        to_value=to_value,
        user_scope=user_scope,
        user_ids=user_ids,
    )
    if (
        resolved.error
        or resolved.selected_period is None
        or resolved.user_filter is None
    ):
        return PlainTextResponse(
            resolved.error or "Invalid Dashboard filters.",
            status_code=400,
        )
    selected_period = resolved.selected_period
    user_scope_part = user_scope_filename_part(
        resolved.user_filter,
        resolved.user_options,
    )
    content = exporter(
        session,
        selected_period=selected_period,
        user_filter=resolved.user_filter,
    )
    filename = (
        f"{export_name}_{user_scope_part}_"
        f"{selected_period.start_date.isoformat()}_"
        f"{selected_period.end_date.isoformat()}.csv"
    )
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pipeline.csv", name="export_pipeline_csv")
def export_pipeline_csv(
    _current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(current_local_date)],
    period: Annotated[str, Query()] = CURRENT_WEEK,
    from_value: Annotated[str, Query(alias="from")] = "",
    to_value: Annotated[str, Query(alias="to")] = "",
    user_scope: Annotated[str | None, Query()] = None,
    user_id: Annotated[list[str] | None, Query()] = None,
) -> Response:
    """Download filtered Pipeline Meeting rows."""
    return _csv_response(
        session=session,
        today=today,
        period=period,
        from_value=from_value,
        to_value=to_value,
        user_scope=user_scope,
        user_ids=user_id or [],
        export_name="pipeline",
        exporter=pipeline_csv,
    )


@router.get("/outreach.csv", name="export_outreach_csv")
def export_outreach_csv(
    _current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(current_local_date)],
    period: Annotated[str, Query()] = CURRENT_WEEK,
    from_value: Annotated[str, Query(alias="from")] = "",
    to_value: Annotated[str, Query(alias="to")] = "",
    user_scope: Annotated[str | None, Query()] = None,
    user_id: Annotated[list[str] | None, Query()] = None,
) -> Response:
    """Download filtered Daily Outreach rows."""
    return _csv_response(
        session=session,
        today=today,
        period=period,
        from_value=from_value,
        to_value=to_value,
        user_scope=user_scope,
        user_ids=user_id or [],
        export_name="outreach",
        exporter=outreach_csv,
    )


__all__ = ["router"]
