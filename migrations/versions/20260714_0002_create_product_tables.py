"""create product tables

Revision ID: 20260714_0002
Revises: 20260714_0001
Create Date: 2026-07-14 11:16:40.547957
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260714_0002"
down_revision: str | Sequence[str] | None = "20260714_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "daily_outreach",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("total_activities", sa.Integer(), nullable=False),
        sa.Column("unique_companies", sa.Integer(), nullable=False),
        sa.Column("replies", sa.Integer(), nullable=True),
        sa.Column("positive_replies", sa.Integer(), nullable=True),
        sa.Column("meetings_booked", sa.Integer(), nullable=True),
        sa.Column(
            "user_mood",
            sa.Enum(
                "Difficult",
                "Okay",
                "Good",
                name="outreach_user_mood",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("blocker_tag", sa.String(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "activity_date",
            name="uq_daily_outreach_user_activity_date",
        ),
    )
    op.create_table(
        "pipeline_meetings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("company_name", sa.String(), nullable=True),
        sa.Column("country_code", sa.String(), nullable=True),
        sa.Column(
            "customer_engagement",
            sa.Enum(
                "Low",
                "Medium",
                "High",
                name="customer_engagement",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "need_identified",
            sa.Enum(
                "Yes",
                "No",
                "Unclear",
                name="need_identified",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "outcome",
            sa.Enum(
                "No fit",
                "Follow-up",
                "Introduction",
                "Proposal requested",
                "Meeting booked",
                "Opportunity identified",
                "Unclear",
                name="pipeline_outcome",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "user_mood",
            sa.Enum(
                "Difficult",
                "Okay",
                "Good",
                name="user_mood",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("blocker_tag", sa.String(), nullable=True),
        sa.Column("next_step_date", sa.Date(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("metric_name", sa.String(), nullable=False),
        sa.Column("target_value", sa.Float(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_until", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "outreach_countries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("outreach_daily_id", sa.Integer(), nullable=False),
        sa.Column("country_code", sa.String(), nullable=False),
        sa.Column("companies_contacted", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["outreach_daily_id"],
            ["daily_outreach.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_table("outreach_countries")
    op.drop_table("targets")
    op.drop_table("pipeline_meetings")
    op.drop_table("daily_outreach")
    op.drop_table("users")
