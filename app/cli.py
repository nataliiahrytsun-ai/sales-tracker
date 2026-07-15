"""Local administrative commands for Sales Tracker."""

import argparse
from collections.abc import Callable, Sequence
from getpass import getpass
import sys

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, select

from app.database import create_session
from app.models import User
from app.services.passwords import hash_password

Prompt = Callable[[str], str]
Output = Callable[[str], None]


def create_user(
    session: Session,
    *,
    prompt: Prompt = input,
    secret_prompt: Prompt = getpass,
    output: Output = print,
) -> int:
    """Interactively create one active user without exposing credentials."""
    email = prompt("Email: ").strip()
    if not email:
        print("User was not created: email is required.", file=sys.stderr)
        return 1

    existing_user = session.exec(
        select(User).where(User.email == email),
    ).first()
    if existing_user is not None:
        print("User was not created: email already exists.", file=sys.stderr)
        return 1

    name = prompt("Name: ").strip()
    if not name:
        print("User was not created: name is required.", file=sys.stderr)
        return 1

    password = secret_prompt("Password: ")
    password_confirmation = secret_prompt("Confirm password: ")
    if not password:
        print("User was not created: password is required.", file=sys.stderr)
        return 1
    if password != password_confirmation:
        print("User was not created: passwords do not match.", file=sys.stderr)
        return 1

    session.add(
        User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            must_change_password=True,
        ),
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        print("User was not created: email already exists.", file=sys.stderr)
        return 1

    output("User created successfully.")
    return 0


def reset_password(
    session: Session,
    *,
    prompt: Prompt = input,
    secret_prompt: Prompt = getpass,
    output: Output = print,
) -> int:
    """Set a temporary password and revoke a user's existing sessions."""
    email = prompt("Email: ").strip()
    if not email:
        print("Password was not reset: email is required.", file=sys.stderr)
        return 1

    user = session.exec(select(User).where(User.email == email)).one_or_none()
    if user is None:
        print("Password was not reset: user was not found.", file=sys.stderr)
        return 1

    password = secret_prompt("Temporary password: ")
    password_confirmation = secret_prompt("Confirm temporary password: ")
    if not password:
        print("Password was not reset: password is required.", file=sys.stderr)
        return 1
    if password != password_confirmation:
        print("Password was not reset: passwords do not match.", file=sys.stderr)
        return 1

    user.password_hash = hash_password(password)
    user.must_change_password = True
    user.auth_version += 1
    session.add(user)
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        print("Password could not be reset.", file=sys.stderr)
        return 1

    output("Password reset successfully.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(
        "create-user",
        help="Interactively create a local application user.",
    )
    subcommands.add_parser(
        "reset-password",
        help="Set a temporary password for an existing user.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the selected local administrative command."""
    parsed_arguments = build_parser().parse_args(arguments)
    if parsed_arguments.command == "create-user":
        with create_session() as session:
            return create_user(session)
    if parsed_arguments.command == "reset-password":
        with create_session() as session:
            return reset_password(session)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
