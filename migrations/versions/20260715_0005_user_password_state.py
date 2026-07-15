"""add user password state

Revision ID: 20260715_0005
Revises: 20260715_0004
Create Date: 2026-07-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260715_0005"
down_revision: str | Sequence[str] | None = "20260715_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add forced-password-change and session-version state."""
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_users")
    existing_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("users")
    }
    if "must_change_password" not in existing_columns:
        op.add_column(
            "users",
            sa.Column(
                "must_change_password",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if "auth_version" not in existing_columns:
        op.add_column(
            "users",
            sa.Column(
                "auth_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
        )


def downgrade() -> None:
    """Remove password state from users."""
    op.drop_column("users", "auth_version")
    op.drop_column("users", "must_change_password")
