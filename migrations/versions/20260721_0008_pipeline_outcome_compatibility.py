"""Allow current and historical pipeline outcome values.

Revision ID: 20260721_0008
Revises: 20260716_0007
Create Date: 2026-07-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260721_0008"
down_revision: str | Sequence[str] | None = "20260716_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_OUTCOMES = (
    "No fit", "Follow-up", "Introduction", "Proposal requested",
    "Meeting booked", "Opportunity identified", "Unclear",
)
CURRENT_OUTCOMES = (
    "Waiting for further information", "No outcome", "Request sent",
    "Manual alignment (discussion)", "Unclear",
)


def _enum(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(
        *values,
        name="pipeline_outcome",
        native_enum=False,
        create_constraint=True,
    )


def upgrade() -> None:
    """Rebuild SQLite's check constraint without modifying stored rows."""
    with op.batch_alter_table("pipeline_meetings") as batch_op:
        batch_op.alter_column(
            "outcome",
            existing_type=_enum(OLD_OUTCOMES),
            type_=_enum((*OLD_OUTCOMES, *CURRENT_OUTCOMES[:-1])),
            existing_nullable=False,
            nullable=False,
        )


def downgrade() -> None:
    """Refuse a lossy downgrade while current outcome rows may exist."""
    raise RuntimeError(
        "Downgrade is unsafe because it would reject current pipeline outcomes."
    )
