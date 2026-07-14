"""Local administrative commands for Sales Tracker."""

import argparse
from collections.abc import Callable, Sequence
from getpass import getpass
import sys

from sqlalchemy.exc import IntegrityError
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


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(
        "create-user",
        help="Interactively create a local application user.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the selected local administrative command."""
    parsed_arguments = build_parser().parse_args(arguments)
    if parsed_arguments.command == "create-user":
        with create_session() as session:
            return create_user(session)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
