"""Initial Alembic setup without product tables.

Revision ID: 20260714_0001
Revises:
Create Date: 2026-07-14
"""

from collections.abc import Sequence

revision: str = "20260714_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the initial empty schema revision."""
    pass


def downgrade() -> None:
    """Revert the initial empty schema revision."""
    pass
