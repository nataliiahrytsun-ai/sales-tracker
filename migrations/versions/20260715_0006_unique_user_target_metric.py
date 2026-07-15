"""enforce one current target per user and metric

Revision ID: 20260715_0006
Revises: 20260715_0005
Create Date: 2026-07-15
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260715_0006"
down_revision: str | Sequence[str] | None = "20260715_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enforce one target row for each user and metric."""
    op.create_index(
        "uq_targets_user_metric",
        "targets",
        ["user_id", "metric_name"],
        unique=True,
    )


def downgrade() -> None:
    """Remove the current-target uniqueness rule."""
    op.drop_index("uq_targets_user_metric", table_name="targets")
