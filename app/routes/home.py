"""Authenticated home page."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.models import User

router = APIRouter(tags=["home"])
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parents[1] / "templates",
)


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> HTMLResponse:
    """Display the minimal private home page."""
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"current_user": current_user},
    )
