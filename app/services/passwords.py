"""Secure password hashing and verification."""

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Create a modern password hash without retaining the plaintext value."""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext candidate against a stored password hash."""
    try:
        return password_hasher.verify(password, password_hash)
    except UnknownHashError:
        return False
