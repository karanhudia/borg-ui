"""collapse the legacy job tables into operations

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-10

Spec section 13 phase 9 and section 14: the legacy job rows are copied into
`operations` once (the "explicit one-off copy"), then the nine legacy tables
and the three legacy link columns are dropped. `repository_wipe_jobs` stays
as the wipe preview store; only its executed rows move.

The downgrade recreates the tables empty and restores the link columns. The
copied rows stay in `operations`; a downgrade is a schema rollback, not a
data restore.
"""

import logging
from pathlib import Path

import sqlalchemy as sa
from alembic import op

from app.config import settings
from app.database import legacy_job_tables as legacy
from app.database.legacy_job_collapse import collapse_legacy_job_tables

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    connection = op.get_bind()
    report = collapse_legacy_job_tables(
        connection, log_dir=Path(settings.data_dir) / "logs"
    )
    for table, count in sorted(report.copied.items()):
        log.info(
            "collapsed %s: %s rows copied, %s skipped",
            table,
            count,
            report.skipped.get(table, 0),
        )

    with op.batch_alter_table("agent_jobs") as batch_op:
        batch_op.drop_index("ix_agent_jobs_backup_job_id")
        batch_op.drop_column("backup_job_id")
    with op.batch_alter_table("script_executions") as batch_op:
        batch_op.drop_index("ix_script_executions_backup_job_id")
        batch_op.drop_column("backup_job_id")
    with op.batch_alter_table("backup_plan_run_repositories") as batch_op:
        batch_op.drop_column("backup_job_id")
    for name in legacy.LEGACY_JOB_TABLE_NAMES:
        op.drop_table(name)


def downgrade() -> None:
    connection = op.get_bind()
    legacy.create_legacy_job_tables(connection)
    with op.batch_alter_table("backup_plan_run_repositories") as batch_op:
        batch_op.add_column(
            sa.Column(
                "backup_job_id",
                sa.Integer(),
                sa.ForeignKey("backup_jobs.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
    with op.batch_alter_table("script_executions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "backup_job_id",
                sa.Integer(),
                sa.ForeignKey("backup_jobs.id", ondelete="CASCADE"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_script_executions_backup_job_id", ["backup_job_id"])
    with op.batch_alter_table("agent_jobs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "backup_job_id",
                sa.Integer(),
                sa.ForeignKey("backup_jobs.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_agent_jobs_backup_job_id", ["backup_job_id"])
