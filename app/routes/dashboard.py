"""Authenticated company-wide aggregate dashboard route."""

from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.auth import get_current_user
from app.database import get_session
from app.models import User
from app.services.dashboard import (
    CURRENT_WEEK,
    OUTCOME_FILTER_ALL,
    OUTCOME_FILTER_OPTIONS,
    PERIOD_OPTIONS,
    USER_SCOPE_ALL,
    get_dashboard_summary,
    group_dashboard_comments,
    resolve_dashboard_filters,
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
    user_scope: Annotated[str | None, Query()] = None,
    user_id: Annotated[list[str] | None, Query()] = None,
    outcome: Annotated[str, Query()] = OUTCOME_FILTER_ALL,
    reset: Annotated[bool, Query()] = False,
    comment_group: Annotated[str, Query()] = "employee",
) -> Response:
    """Render privacy-safe aggregates for the selected company period."""
    if reset:
        period, from_value, to_value = CURRENT_WEEK, "", ""
        user_scope, user_id = USER_SCOPE_ALL, []
        outcome = OUTCOME_FILTER_ALL
        comment_group = "employee"
    resolved = resolve_dashboard_filters(
        session,
        today=today,
        period=period,
        from_value=from_value,
        to_value=to_value,
        user_scope=user_scope,
        user_ids=user_id or [],
        outcome=outcome,
    )
    user_options = resolved.user_options
    selected_users = resolved.user_filter
    selected_period = resolved.selected_period
    error = resolved.error
    if selected_users is None or selected_users.includes_all:
        user_filter_summary = "All users"
    elif not selected_users.user_ids:
        user_filter_summary = "Select users"
    elif len(selected_users.user_ids) == 1:
        selected_user_id = selected_users.user_ids[0]
        user_filter_summary = next(
            option.label
            for option in user_options
            if option.user_id == selected_user_id
        )
    else:
        user_filter_summary = f"{len(selected_users.user_ids)} users selected"
    summary = (
        None
        if selected_period is None or selected_users is None
        else get_dashboard_summary(
            session,
            selected_period=selected_period,
            user_filter=selected_users,
            outcome_filter=resolved.outcome_filter,
        )
    )
    comment_grouping = (
        comment_group
        if comment_group in {"employee", "date", "source"}
        else "employee"
    )
    comment_groups = (
        group_dashboard_comments(summary.comments, comment_grouping)
        if summary is not None
        else ()
    )
    comment_group_urls: dict[str, str] = {}
    if selected_period is not None and selected_users is not None:
        comment_params: list[tuple[str, str | int]] = [
            ("period", selected_period.key),
            ("user_scope", selected_users.scope),
            ("outcome", outcome),
        ]
        if selected_period.key == "custom":
            comment_params.extend(
                (
                    ("from", selected_period.start_date.isoformat()),
                    ("to", selected_period.end_date.isoformat()),
                ),
            )
        comment_params.extend(
            ("user_id", selected_user_id)
            for selected_user_id in selected_users.user_ids
        )
        comment_group_urls = {
            grouping: (
                f"{request.url_for('dashboard_page')}?"
                f"{urlencode([*comment_params, ('comment_group', grouping)])}"
                "#comments-overview"
            )
            for grouping in ("employee", "date", "source")
        }
    export_urls: dict[str, str] = {}
    if selected_period is not None and selected_users is not None:
        export_params: list[tuple[str, str | int]] = [
            ("period", selected_period.key),
            ("user_scope", selected_users.scope),
        ]
        if selected_period.key == "custom":
            export_params.extend(
                (
                    ("from", selected_period.start_date.isoformat()),
                    ("to", selected_period.end_date.isoformat()),
                ),
            )
        export_params.extend(
            ("user_id", selected_user_id)
            for selected_user_id in selected_users.user_ids
        )
        query = urlencode(export_params)
        export_urls = {
            "pipeline": f"{request.url_for('export_pipeline_csv')}?{query}",
            "outreach": f"{request.url_for('export_outreach_csv')}?{query}",
        }
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
            "user_options": user_options,
            "selected_user_scope": (
                selected_users.scope if selected_users else (user_scope or USER_SCOPE_ALL)
            ),
            "selected_user_ids": (
                set(selected_users.user_ids) if selected_users else set()
            ),
            "outcome_options": OUTCOME_FILTER_OPTIONS,
            "selected_outcome": (
                resolved.outcome_filter.value
                if resolved.outcome_filter is not None
                else OUTCOME_FILTER_ALL
            ),
            "user_filter_summary": user_filter_summary,
            "filter_error": error,
            "export_urls": export_urls,
            "comment_grouping": comment_grouping,
            "comment_groups": comment_groups,
            "comment_group_urls": comment_group_urls,
        },
        status_code=400 if error else 200,
    )


__all__ = ["router"]
