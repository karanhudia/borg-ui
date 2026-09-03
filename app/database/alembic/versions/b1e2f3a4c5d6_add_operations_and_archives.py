"""add operations, archives, archive_changes tables and runner settings

Revision ID: b1e2f3a4c5d6
Revises: c7e4f8a1d2b3
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa

revision = "b1e2f3a4c5d6"
down_revision = "c7e4f8a1d2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("trigger", sa.String(), nullable=False, server_default="manual"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column(
            "depends_on_id",
            sa.Integer(),
            sa.ForeignKey("operations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "triggered_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "scheduled_job_id",
            sa.Integer(),
            sa.ForeignKey("scheduled_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "backup_plan_run_id",
            sa.Integer(),
            sa.ForeignKey("backup_plan_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("execution_mode", sa.String(), nullable=True),
        sa.Column("process_pid", sa.Integer(), nullable=True),
        sa.Column("process_start_time", sa.Float(), nullable=True),
        sa.Column("progress_percent", sa.Float(), nullable=True),
        sa.Column("progress_current", sa.Integer(), nullable=True),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        sa.Column("progress_message", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("skip_reason", sa.String(), nullable=True),
        sa.Column("log_file_path", sa.String(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_operations_repository_id", "operations", ["repository_id"])
    op.create_index("ix_operations_kind", "operations", ["kind"])
    op.create_index("ix_operations_category", "operations", ["category"])
    op.create_index("ix_operations_status", "operations", ["status"])
    op.create_index("ix_operations_run_id", "operations", ["run_id"])
    op.create_index("ix_operations_created_at", "operations", ["created_at"])
    op.create_index(
        "ix_operations_repository_status", "operations", ["repository_id", "status"]
    )
    op.create_index(
        "ix_operations_status_priority_created",
        "operations",
        ["status", "priority", "created_at"],
    )
    op.create_index(
        "ix_operations_category_created", "operations", ["category", "created_at"]
    )

    op.create_table(
        "archives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("borg_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("series", sa.String(), nullable=False),
        sa.Column("start", sa.DateTime(), nullable=False),
        sa.Column("end", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("nfiles", sa.Integer(), nullable=True),
        sa.Column("original_size", sa.BigInteger(), nullable=True),
        sa.Column("compressed_size", sa.BigInteger(), nullable=True),
        sa.Column("deduplicated_size", sa.BigInteger(), nullable=True),
        sa.Column("hostname", sa.String(), nullable=True),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "backup_operation_id",
            sa.Integer(),
            sa.ForeignKey("operations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "history_state", sa.String(), nullable=False, server_default="pending"
        ),
        sa.Column("history_indexed_at", sa.DateTime(), nullable=True),
        sa.Column("history_rows", sa.Integer(), nullable=True),
        sa.Column(
            "history_truncated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "repository_id", "borg_id", name="uq_archives_repository_id_borg_id"
        ),
    )
    op.create_index("ix_archives_repository_id", "archives", ["repository_id"])
    op.create_index("ix_archives_series", "archives", ["series"])
    op.create_index("ix_archives_start", "archives", ["start"])

    op.create_table(
        "archive_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "archive_id",
            sa.Integer(),
            sa.ForeignKey("archives.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("change", sa.String(8), nullable=False),
        sa.Column("size_before", sa.BigInteger(), nullable=True),
        sa.Column("size_after", sa.BigInteger(), nullable=True),
        sa.Column(
            "mode_changed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "owner_changed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("summary_count", sa.Integer(), nullable=True),
    )
    op.create_index("ix_archive_changes_archive_id", "archive_changes", ["archive_id"])
    op.create_index(
        "ix_archive_changes_archive_path", "archive_changes", ["archive_id", "path"]
    )
    op.create_index("ix_archive_changes_path", "archive_changes", ["path"])

    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.add_column(
            sa.Column("index_workers", sa.Integer(), nullable=False, server_default="2")
        )
        batch_op.add_column(
            sa.Column(
                "background_paused",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.drop_column("background_paused")
        batch_op.drop_column("index_workers")
    op.drop_index("ix_archive_changes_path", table_name="archive_changes")
    op.drop_index("ix_archive_changes_archive_path", table_name="archive_changes")
    op.drop_index("ix_archive_changes_archive_id", table_name="archive_changes")
    op.drop_table("archive_changes")
    op.drop_index("ix_archives_start", table_name="archives")
    op.drop_index("ix_archives_series", table_name="archives")
    op.drop_index("ix_archives_repository_id", table_name="archives")
    op.drop_table("archives")
    for name in (
        "ix_operations_category_created",
        "ix_operations_status_priority_created",
        "ix_operations_repository_status",
        "ix_operations_created_at",
        "ix_operations_run_id",
        "ix_operations_status",
        "ix_operations_category",
        "ix_operations_kind",
        "ix_operations_repository_id",
    ):
        op.drop_index(name, table_name="operations")
    op.drop_table("operations")
