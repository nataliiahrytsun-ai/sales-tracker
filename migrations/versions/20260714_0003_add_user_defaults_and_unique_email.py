"""add user defaults and unique email

Revision ID: 20260714_0003
Revises: 20260714_0002
Create Date: 2026-07-14 11:29:31.838332
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260714_0003"
down_revision: str | Sequence[str] | None = "20260714_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "active",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            server_default=sa.true(),
        )
        batch_op.create_unique_constraint("uq_users_email", ["email"])


def downgrade() -> None:
    """Revert the migration."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("uq_users_email", type_="unique")
        batch_op.alter_column(
            "active",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            server_default=None,
        )
