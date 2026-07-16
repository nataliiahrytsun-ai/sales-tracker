"""store targets separately for each calendar week

Revision ID: 20260716_0007
Revises: 20260715_0006
Create Date: 2026-07-16
"""

from collections.abc import Sequence
from datetime import date, timedelta

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0007"
down_revision: str | Sequence[str] | None = "20260715_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a canonical Monday and scope target uniqueness to one week."""
    op.add_column("targets", sa.Column("week_start", sa.Date(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, effective_from FROM targets"),
    ).mappings()
    for row in rows:
        effective_from = date.fromisoformat(str(row["effective_from"]))
        week_start = effective_from - timedelta(days=effective_from.weekday())
        connection.execute(
            sa.text(
                "UPDATE targets SET week_start = :week_start WHERE id = :target_id",
            ),
            {"week_start": week_start.isoformat(), "target_id": row["id"]},
        )

    with op.batch_alter_table("targets") as batch_op:
        batch_op.alter_column(
            "week_start",
            existing_type=sa.Date(),
            nullable=False,
        )
    op.drop_index("uq_targets_user_metric", table_name="targets")
    op.create_index(
        "uq_targets_user_week_metric",
        "targets",
        ["user_id", "week_start", "metric_name"],
        unique=True,
    )


def downgrade() -> None:
    """Return to one target per user and metric, retaining the latest week."""
    op.drop_index("uq_targets_user_week_metric", table_name="targets")
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM targets WHERE id NOT IN ("
            "SELECT MAX(id) FROM targets GROUP BY user_id, metric_name"
            ")",
        ),
    )
    op.create_index(
        "uq_targets_user_metric",
        "targets",
        ["user_id", "metric_name"],
        unique=True,
    )
    with op.batch_alter_table("targets") as batch_op:
        batch_op.drop_column("week_start")
