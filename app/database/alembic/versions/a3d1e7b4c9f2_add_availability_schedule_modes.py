"""add availability schedule modes

Revision ID: a3d1e7b4c9f2
Revises: f6c46c665fd3
Create Date: 2026-08-07
"""

from alembic import op
import sqlalchemy as sa


revision = "a3d1e7b4c9f2"
down_revision = "f6c46c665fd3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("backup_plans", "scheduled_jobs"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "schedule_mode", sa.String(), nullable=False, server_default="cron"
                )
            )
            batch_op.add_column(
                sa.Column(
                    "availability_check_interval_minutes",
                    sa.Integer(),
                    nullable=False,
                    server_default="30",
                )
            )
            batch_op.add_column(
                sa.Column(
                    "min_success_interval_minutes",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )
    with op.batch_alter_table("scheduled_jobs") as batch_op:
        batch_op.alter_column(
            "cron_expression", existing_type=sa.String(), nullable=True
        )


def downgrade() -> None:
    # Availability schedules may not have a cron expression, so restoring the
    # old NOT NULL constraint is unsafe. Keep this downgrade intentionally
    # additive/non-destructive, matching the project's migration policy.
    pass
