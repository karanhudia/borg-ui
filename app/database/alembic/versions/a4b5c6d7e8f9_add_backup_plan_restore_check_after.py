"""add backup plan run_restore_check_after

Revision ID: a4b5c6d7e8f9
Revises: f2b3c4d5e6a7
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa

revision = "a4b5c6d7e8f9"
down_revision = "f2b3c4d5e6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Re-run on a database that already has the column (a boot killed before
    # the version bump, an install stuck on an older revision): skip it. A
    # re-add makes the batch rebuild reorder columns and, once a later
    # revision added another column, fail with a circular dependency.
    existing = {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("backup_plans")
    }
    if "run_restore_check_after" in existing:
        return
    with op.batch_alter_table("backup_plans") as batch:
        batch.add_column(
            sa.Column(
                "run_restore_check_after",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("backup_plans") as batch:
        batch.drop_column("run_restore_check_after")
