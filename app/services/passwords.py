"""Secure password hashing and verification."""

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

password_hasher = PasswordHash.recommended()
MINIMUM_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    """Create a modern password hash without retaining the plaintext value."""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext candidate against a stored password hash."""
    try:
        return password_hasher.verify(password, password_hash)
    except UnknownHashError:
        return False


def validate_password_change(
    *,
    current_password: str,
    new_password: str,
    confirm_new_password: str,
    password_hash: str,
) -> dict[str, str]:
    """Validate a password change without retaining submitted secrets."""
    errors: dict[str, str] = {}
    if not verify_password(current_password, password_hash):
        errors["current_password"] = "Current password is incorrect."
    if new_password != confirm_new_password:
        errors["confirm_new_password"] = "New passwords do not match."
    if len(new_password) < MINIMUM_PASSWORD_LENGTH:
        errors["new_password"] = (
            f"New password must be at least {MINIMUM_PASSWORD_LENGTH} characters."
        )
    elif verify_password(new_password, password_hash):
        errors["new_password"] = (
            "New password must be different from current password."
        )
    return errors
