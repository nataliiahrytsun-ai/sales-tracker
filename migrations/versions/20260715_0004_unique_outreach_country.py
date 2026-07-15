"""enforce one country row per daily outreach

Revision ID: 20260715_0004
Revises: 20260714_0003
Create Date: 2026-07-15
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260715_0004"
down_revision: str | Sequence[str] | None = "20260714_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the required per-outreach country uniqueness constraint."""
    with op.batch_alter_table("outreach_countries", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_outreach_countries_daily_country",
            ["outreach_daily_id", "country_code"],
        )


def downgrade() -> None:
    """Remove the per-outreach country uniqueness constraint."""
    with op.batch_alter_table("outreach_countries", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_outreach_countries_daily_country",
            type_="unique",
        )
