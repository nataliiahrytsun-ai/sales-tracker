"""Login and logout routes."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.auth import (
    authenticate_user,
    get_current_user,
    get_optional_current_user,
    set_authenticated_session,
)
from app.database import get_session
from app.models import User
from app.security import LoginRateLimiter, reset_session
from app.services.passwords import hash_password, validate_password_change

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parents[1] / "templates",
)
LOGIN_RATE_LIMIT_MESSAGE = "Too many login attempts. Please try again later."


def rate_limited_login_response(
    request: Request,
    *,
    email: str,
    retry_after: int,
) -> Response:
    """Render a neutral throttling response without account disclosure."""
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": LOGIN_RATE_LIMIT_MESSAGE, "email": email},
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": str(retry_after)},
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
        destination = (
            "/change-password" if current_user.must_change_password else "/"
        )
        return RedirectResponse(
            url=destination,
            status_code=status.HTTP_303_SEE_OTHER,
        )
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
    limiter: LoginRateLimiter = request.app.state.login_rate_limiter
    limiter_key = limiter.key(request, email)
    retry_after = limiter.retry_after(limiter_key)
    if retry_after is not None:
        return rate_limited_login_response(
            request,
            email=email,
            retry_after=retry_after,
        )

    user = authenticate_user(session, email, password)
    if user is None:
        retry_after = limiter.record_failure(limiter_key)
        if retry_after is not None:
            return rate_limited_login_response(
                request,
                email=email,
                retry_after=retry_after,
            )
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Invalid email or password.",
                "email": email,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    limiter.clear(limiter_key)
    set_authenticated_session(request, user)
    destination = "/change-password" if user.must_change_password else "/"
    return RedirectResponse(
        url=destination,
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/change-password", response_class=HTMLResponse)
def change_password_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    """Display the password-change form to an authenticated user."""
    return templates.TemplateResponse(
        request=request,
        name="change_password.html",
        context={"current_user": current_user, "errors": {}},
    )


@router.post("/change-password", response_class=HTMLResponse)
def change_password(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    current_password: Annotated[str, Form()] = "",
    new_password: Annotated[str, Form()] = "",
    confirm_new_password: Annotated[str, Form()] = "",
) -> Response:
    """Validate a new password, revoke old sessions, and refresh this one."""
    errors = validate_password_change(
        current_password=current_password,
        new_password=new_password,
        confirm_new_password=confirm_new_password,
        password_hash=current_user.password_hash,
    )
    if errors:
        return templates.TemplateResponse(
            request=request,
            name="change_password.html",
            context={"current_user": current_user, "errors": errors},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    current_user.password_hash = hash_password(new_password)
    current_user.must_change_password = False
    current_user.auth_version += 1
    session.add(current_user)
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        return templates.TemplateResponse(
            request=request,
            name="change_password.html",
            context={
                "current_user": current_user,
                "errors": {
                    "form": "Password could not be changed. Please try again.",
                },
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    set_authenticated_session(request, current_user)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(
    request: Request,
    _current_user: Annotated[User, Depends(get_current_user)],
) -> RedirectResponse:
    """End the authenticated session."""
    reset_session(request)
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
