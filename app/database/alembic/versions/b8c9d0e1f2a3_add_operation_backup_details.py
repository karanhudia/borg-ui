"""add operation backup extension tables and links

Revision ID: b8c9d0e1f2a3
Revises: f7a8b9c0d1e2
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa

revision = "b8c9d0e1f2a3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operation_backup_details",
        sa.Column(
            "operation_id",
            sa.Integer(),
            sa.ForeignKey("operations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("archive_name", sa.String(), nullable=True),
        sa.Column("archive_pruned_at", sa.DateTime(), nullable=True),
        sa.Column("original_size", sa.BigInteger(), nullable=True, server_default="0"),
        sa.Column(
            "compressed_size", sa.BigInteger(), nullable=True, server_default="0"
        ),
        sa.Column(
            "deduplicated_size", sa.BigInteger(), nullable=True, server_default="0"
        ),
        sa.Column("nfiles", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("current_file", sa.Text(), nullable=True),
        sa.Column("backup_speed", sa.Float(), nullable=True, server_default="0"),
        sa.Column(
            "total_expected_size", sa.BigInteger(), nullable=True, server_default="0"
        ),
        sa.Column(
            "estimated_time_remaining", sa.Integer(), nullable=True, server_default="0"
        ),
        sa.Column("route_strategy", sa.String(), nullable=True),
        sa.Column(
            "source_ssh_connection_id",
            sa.Integer(),
            sa.ForeignKey("ssh_connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("remote_process_pid", sa.Integer(), nullable=True),
        sa.Column("remote_hostname", sa.String(), nullable=True),
        sa.Column("retry_original_job_id", sa.Integer(), nullable=True),
        sa.Column("retry_source_job_id", sa.Integer(), nullable=True),
        sa.Column("retry_attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "retry_requested_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("retry_requested_at", sa.DateTime(), nullable=True),
        sa.Column("maintenance_status", sa.String(), nullable=True),
    )
    op.create_table(
        "operation_backup_retry_lineage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("original_job_id", sa.Integer(), nullable=True),
        sa.Column("retry_source_job_id", sa.Integer(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "requested_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("created_operation_id", sa.Integer(), nullable=True),
        sa.Column("request_snapshot", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "created_operation_id", name="uq_operation_backup_retry_created"
        ),
    )
    for name in (
        "id",
        "original_job_id",
        "retry_source_job_id",
        "requested_by_user_id",
        "created_operation_id",
    ):
        op.create_index(
            f"ix_operation_backup_retry_lineage_{name}",
            "operation_backup_retry_lineage",
            [name],
        )
    with op.batch_alter_table("agent_jobs") as batch_op:
        batch_op.add_column(sa.Column("operation_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("start_notified_at", sa.DateTime(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_agent_jobs_operation_id_operations",
            "operations",
            ["operation_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_agent_jobs_operation_id", ["operation_id"])
    with op.batch_alter_table("script_executions") as batch_op:
        batch_op.add_column(sa.Column("operation_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_script_executions_operation_id_operations",
            "operations",
            ["operation_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_script_executions_operation_id", ["operation_id"])
    with op.batch_alter_table("backup_plan_run_repositories") as batch_op:
        batch_op.add_column(
            sa.Column("backup_operation_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_backup_plan_run_repositories_backup_operation_id_operations",
            "operations",
            ["backup_operation_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("backup_plan_run_repositories") as batch_op:
        batch_op.drop_constraint(
            "fk_backup_plan_run_repositories_backup_operation_id_operations",
            type_="foreignkey",
        )
        batch_op.drop_column("backup_operation_id")
    with op.batch_alter_table("script_executions") as batch_op:
        batch_op.drop_index("ix_script_executions_operation_id")
        batch_op.drop_constraint(
            "fk_script_executions_operation_id_operations", type_="foreignkey"
        )
        batch_op.drop_column("operation_id")
    with op.batch_alter_table("agent_jobs") as batch_op:
        batch_op.drop_index("ix_agent_jobs_operation_id")
        batch_op.drop_constraint(
            "fk_agent_jobs_operation_id_operations", type_="foreignkey"
        )
        batch_op.drop_column("start_notified_at")
        batch_op.drop_column("operation_id")
    op.drop_table("operation_backup_retry_lineage")
    op.drop_table("operation_backup_details")
