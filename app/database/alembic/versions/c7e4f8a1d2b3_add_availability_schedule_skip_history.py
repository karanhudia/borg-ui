"""add durable availability schedule skip history

Revision ID: c7e4f8a1d2b3
Revises: a3d1e7b4c9f2
Create Date: 2026-08-13
"""

from alembic import op
import sqlalchemy as sa


revision = "c7e4f8a1d2b3"
down_revision = "a3d1e7b4c9f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("backup_plan_runs") as batch_op:
        batch_op.add_column(sa.Column("skip_reason", sa.String(), nullable=True))

    op.create_table(
        "availability_schedule_skips",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "scheduled_job_id",
            sa.Integer(),
            sa.ForeignKey("scheduled_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("next_check_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_availability_schedule_skips_scheduled_job_id",
        "availability_schedule_skips",
        ["scheduled_job_id"],
    )
    op.create_index(
        "ix_availability_schedule_skips_occurred_at",
        "availability_schedule_skips",
        ["occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_availability_schedule_skips_occurred_at",
        table_name="availability_schedule_skips",
    )
    op.drop_index(
        "ix_availability_schedule_skips_scheduled_job_id",
        table_name="availability_schedule_skips",
    )
    op.drop_table("availability_schedule_skips")
    with op.batch_alter_table("backup_plan_runs") as batch_op:
        batch_op.drop_column("skip_reason")
