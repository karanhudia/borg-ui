"""add backup_jobs.archive_pruned_at

A backup job whose archive was pruned used to be deleted with the archive
(job_history_retention.purge_jobs_for_pruned_archives). The row is the only
record that the backup ran, and everything that shows run history (the
dashboard activity timeline, the plan history) went blank for pruned runs.
The row now stays and records when its archive went; it falls with
cleanup_retention_days like every other job row.

Nullable, no backfill: rows deleted before this revision are gone, and a
NULL means "archive not known to be pruned".

Revision ID: a5b7c9d1e3f2
Revises: c3d5e7f9a1b2
Create Date: 2026-09-07 12:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a5b7c9d1e3f2"
down_revision: Union[str, Sequence[str], None] = "c3d5e7f9a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "backup_jobs", sa.Column("archive_pruned_at", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("backup_jobs", "archive_pruned_at")
