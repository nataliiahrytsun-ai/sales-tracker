"""Login and logout routes."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.auth import (
    authenticate_user,
    get_current_user,
    get_optional_current_user,
)
from app.database import get_session
from app.models import User

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parents[1] / "templates",
)


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    current_user: Annotated[
        User | None,
        Depends(get_optional_current_user),
    ],
) -> Response:
    """Display the login page to anonymous users."""
    if current_user is not None:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None, "email": ""},
    )


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Authenticate a user and start a signed cookie session."""
    user = authenticate_user(session, email, password)
    if user is None:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Invalid email or password.",
                "email": email,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(
    request: Request,
    _current_user: Annotated[User, Depends(get_current_user)],
) -> RedirectResponse:
    """End the authenticated session."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
