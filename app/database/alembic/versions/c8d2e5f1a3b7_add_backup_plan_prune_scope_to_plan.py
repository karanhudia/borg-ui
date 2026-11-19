"""add backup plan prune_scope_to_plan

Revision ID: c8d2e5f1a3b7
Revises: e4b7c2a9d1f3
Create Date: 2026-11-18
"""

from alembic import op
import sqlalchemy as sa

revision = "c8d2e5f1a3b7"
down_revision = "e4b7c2a9d1f3"
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
    if "prune_scope_to_plan" in existing:
        return
    with op.batch_alter_table("backup_plans") as batch:
        batch.add_column(
            sa.Column(
                "prune_scope_to_plan",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("backup_plans") as batch:
        batch.drop_column("prune_scope_to_plan")
