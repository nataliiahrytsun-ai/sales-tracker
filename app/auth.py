"""Authentication services and FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session, select

from app.database import get_session
from app.models import User
from app.services.passwords import hash_password, verify_password

DUMMY_PASSWORD_HASH = hash_password("unused-authentication-timing-value")


def authenticate_user(
    session: Session,
    email: str,
    password: str,
) -> User | None:
    """Authenticate an active user by email without exposing failure details."""
    user = session.exec(
        select(User).where(User.email == email.strip()),
    ).one_or_none()

    stored_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_is_valid = verify_password(password, stored_hash)
    if user is None or not password_is_valid or not user.active:
        return None
    return user


def get_optional_current_user(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> User | None:
    """Return the active session user, if one exists."""
    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        return None

    user = session.get(User, user_id)
    if user is None or not user.active:
        request.session.clear()
        return None
    return user


def get_current_user(
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
) -> User:
    """Require an authenticated user for a private server-side route."""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return current_user
