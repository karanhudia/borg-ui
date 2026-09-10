"""The legacy job tables, frozen at the moment phase 9 deleted them.

Core definitions on their own MetaData, never on `Base`: the ORM must not know
these tables exist any more. Three readers need them: the collapse copy
(`legacy_job_collapse`), the collapse revision's downgrade (which recreates
them empty), and the tests that build a pre-collapse database. Column order,
types, and foreign keys are exactly what `models.py` declared at revision
b8c9d0e1f2a3. Do not add columns; do not reuse these for new code.
"""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

metadata = MetaData()

backup_jobs = Table(
    "backup_jobs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("repository", String),
    Column(
        "repository_id", Integer, ForeignKey("repositories.id", ondelete="SET NULL")
    ),
    Column(
        "backup_plan_id", Integer, ForeignKey("backup_plans.id", ondelete="SET NULL")
    ),
    Column(
        "backup_plan_run_id",
        Integer,
        ForeignKey("backup_plan_runs.id", ondelete="SET NULL"),
    ),
    Column("status", String, default="pending"),
    Column("started_at", DateTime),
    Column("completed_at", DateTime),
    Column("progress", Integer, default=0),
    Column("error_message", Text),
    Column("logs", Text),
    Column("log_file_path", String),
    Column("scheduled_job_id", Integer, ForeignKey("scheduled_jobs.id")),
    Column("original_size", BigInteger, default=0),
    Column("compressed_size", BigInteger, default=0),
    Column("deduplicated_size", BigInteger, default=0),
    Column("nfiles", Integer, default=0),
    Column("current_file", Text),
    Column("progress_percent", Float, default=0.0),
    Column("backup_speed", Float, default=0.0),
    Column("total_expected_size", BigInteger, default=0),
    Column("estimated_time_remaining", Integer, default=0),
    Column("archive_name", String),
    Column("archive_pruned_at", DateTime),
    Column("maintenance_status", String),
    Column("execution_mode", String, default="local"),
    Column("route_strategy", String),
    Column("source_ssh_connection_id", Integer, ForeignKey("ssh_connections.id")),
    Column("remote_process_pid", Integer),
    Column("remote_hostname", String),
    Column(
        "retry_original_job_id",
        Integer,
        ForeignKey("backup_jobs.id", ondelete="SET NULL"),
    ),
    Column(
        "retry_source_job_id",
        Integer,
        ForeignKey("backup_jobs.id", ondelete="SET NULL"),
    ),
    Column("retry_attempt", Integer, default=1, nullable=False),
    Column(
        "retry_requested_by_user_id",
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
    ),
    Column("retry_requested_at", DateTime),
    Column("created_at", DateTime),
)

backup_job_retry_lineage = Table(
    "backup_job_retry_lineage",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "original_job_id", Integer, ForeignKey("backup_jobs.id", ondelete="SET NULL")
    ),
    Column(
        "retry_source_job_id",
        Integer,
        ForeignKey("backup_jobs.id", ondelete="SET NULL"),
    ),
    Column("attempt_number", Integer, nullable=False),
    Column(
        "requested_by_user_id", Integer, ForeignKey("users.id", ondelete="SET NULL")
    ),
    Column("requested_at", DateTime, nullable=False),
    Column(
        "created_job_id", Integer, ForeignKey("backup_jobs.id", ondelete="SET NULL")
    ),
    Column("request_snapshot", JSON, nullable=False),
)

restore_jobs = Table(
    "restore_jobs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("repository", String),
    Column("archive", String),
    Column("destination", String),
    Column("status", String, default="pending"),
    Column("started_at", DateTime),
    Column("completed_at", DateTime),
    Column("progress", Integer, default=0),
    Column("error_message", Text),
    Column("logs", Text),
    Column("nfiles", Integer, default=0),
    Column("current_file", Text),
    Column("progress_percent", Float, default=0.0),
    Column("original_size", BigInteger, default=0),
    Column("restored_size", BigInteger, default=0),
    Column("restore_speed", Float, default=0.0),
    Column("estimated_time_remaining", Integer, default=0),
    Column("destination_type", String(50), default="local"),
    Column("destination_connection_id", Integer, ForeignKey("ssh_connections.id")),
    Column("execution_mode", String(50), default="local_to_local"),
    Column("temp_extraction_path", String(255)),
    Column("destination_hostname", String(255)),
    Column("repository_type", String(50), default="local"),
    Column("created_at", DateTime),
)

check_jobs = Table(
    "check_jobs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("repository_id", Integer, ForeignKey("repositories.id"), nullable=False),
    Column("repository_path", String),
    Column("status", String, default="pending"),
    Column("started_at", DateTime),
    Column("completed_at", DateTime),
    Column("progress", Integer, default=0),
    Column("progress_message", String),
    Column("error_message", Text),
    Column("logs", Text),
    Column("log_file_path", String),
    Column("has_logs", Boolean, default=False),
    Column("max_duration", Integer),
    Column("extra_flags", Text),
    Column("process_pid", Integer),
    Column("process_start_time", BigInteger),
    Column("scheduled_check", Boolean, default=False, nullable=False),
    Column("created_at", DateTime),
)

restore_check_jobs = Table(
    "restore_check_jobs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("repository_id", Integer, ForeignKey("repositories.id"), nullable=False),
    Column("repository_path", String),
    Column("archive_name", String),
    Column("status", String, default="pending"),
    Column("started_at", DateTime),
    Column("completed_at", DateTime),
    Column("progress", Integer, default=0),
    Column("progress_message", String),
    Column("error_message", Text),
    Column("logs", Text),
    Column("log_file_path", String),
    Column("has_logs", Boolean, default=False),
    Column("probe_paths", Text),
    Column("full_archive", Boolean, default=False, nullable=False),
    Column("process_pid", Integer),
    Column("process_start_time", BigInteger),
    Column("scheduled_restore_check", Boolean, default=False, nullable=False),
    Column("created_at", DateTime),
)

compact_jobs = Table(
    "compact_jobs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("repository_id", Integer, ForeignKey("repositories.id"), nullable=False),
    Column("repository_path", String),
    Column("status", String, default="pending"),
    Column("started_at", DateTime),
    Column("completed_at", DateTime),
    Column("progress", Integer, default=0),
    Column("progress_message", String),
    Column("error_message", Text),
    Column("logs", Text),
    Column("log_file_path", String),
    Column("has_logs", Boolean, default=False),
    Column("scheduled_compact", Boolean, default=False, nullable=False),
    Column("process_pid", Integer),
    Column("process_start_time", BigInteger),
    Column("created_at", DateTime),
)

prune_jobs = Table(
    "prune_jobs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("repository_id", Integer, ForeignKey("repositories.id"), nullable=False),
    Column("repository_path", String),
    Column("status", String, default="pending"),
    Column("started_at", DateTime),
    Column("completed_at", DateTime),
    Column("error_message", Text),
    Column("logs", Text),
    Column("log_file_path", String),
    Column("has_logs", Boolean, default=False),
    Column("scheduled_prune", Boolean, default=False, nullable=False),
    Column("created_at", DateTime),
)

delete_archive_jobs = Table(
    "delete_archive_jobs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "repository_id",
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("repository_path", String),
    Column("archive_name", String, nullable=False),
    Column("status", String, default="pending"),
    Column("started_at", DateTime),
    Column("completed_at", DateTime),
    Column("progress", Integer, default=0),
    Column("progress_message", String),
    Column("error_message", Text),
    Column("logs", Text),
    Column("log_file_path", String),
    Column("has_logs", Boolean, default=False),
    Column("process_pid", Integer),
    Column("process_start_time", BigInteger),
    Column("created_at", DateTime),
)

repository_wipe_jobs = Table(
    "repository_wipe_jobs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "repository_id", Integer, ForeignKey("repositories.id", ondelete="SET NULL")
    ),
    Column("repository_path", String),
    Column("repository_name", String),
    Column("borg_version", Integer),
    Column("status", String, default="previewed"),
    Column("phase", String),
    Column("archive_count", Integer, default=0),
    Column("archive_fingerprint", String),
    Column("archive_manifest_json", Text),
    Column("dry_run_output", Text),
    Column("blocking_reason", String),
    Column("protected_archives_json", Text),
    Column("run_compact", Boolean, default=True, nullable=False),
    Column("requested_by_user_id", Integer, ForeignKey("users.id")),
    Column("confirmed_by_user_id", Integer, ForeignKey("users.id")),
    Column("started_at", DateTime),
    Column("confirmed_at", DateTime),
    Column("completed_at", DateTime),
    Column("progress", Integer, default=0),
    Column("progress_message", String),
    Column("error_message", Text),
    Column("logs", Text),
    Column("log_file_path", String),
    Column("has_logs", Boolean, default=False),
    Column("created_at", DateTime),
)

rclone_sync_jobs = Table(
    "rclone_sync_jobs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "repository_id",
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("direction", String, nullable=False),
    Column("operation", String, default="sync", nullable=False),
    Column("status", String, default="pending", nullable=False),
    Column("triggered_by", String, default="manual", nullable=False),
    Column("scheduled_for", DateTime),
    Column("started_at", DateTime),
    Column("completed_at", DateTime),
    Column("bytes_transferred", BigInteger),
    Column("files_transferred", Integer),
    Column("log_path", String),
    Column("log_text", Text),
    Column("error_text", Text),
    Column("created_at", DateTime, nullable=False),
)

package_install_jobs = Table(
    "package_install_jobs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "package_id",
        Integer,
        ForeignKey("installed_packages.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("status", String, default="pending", nullable=False),
    Column("started_at", DateTime),
    Column("completed_at", DateTime),
    Column("exit_code", Integer),
    Column("stdout", Text),
    Column("stderr", Text),
    Column("error_message", Text),
    Column("process_pid", Integer),
    Column("process_start_time", BigInteger),
    Column("created_at", DateTime, nullable=False),
)

# Dropped by the collapse revision, children before parents so PostgreSQL
# never sees a dangling foreign key. `repository_wipe_jobs` is deliberately
# absent: it is the wipe preview store and survives the phase.
LEGACY_JOB_TABLE_NAMES = (
    "backup_job_retry_lineage",
    "backup_jobs",
    "restore_jobs",
    "check_jobs",
    "restore_check_jobs",
    "compact_jobs",
    "prune_jobs",
    "delete_archive_jobs",
    "rclone_sync_jobs",
    "package_install_jobs",
)


def create_legacy_job_tables(connection) -> None:
    """Recreate the dropped tables, empty, for the collapse revision's
    downgrade.

    Their foreign keys point at tables that survive the collapse, which this
    MetaData does not hold, so the surviving schema is reflected into a
    throwaway MetaData and the frozen definitions are copied onto it. Creation
    order is the reverse of the drop order, parents before children.
    """
    scratch = MetaData()
    scratch.reflect(bind=connection)
    for name in reversed(LEGACY_JOB_TABLE_NAMES):
        metadata.tables[name].to_metadata(scratch).create(connection)
