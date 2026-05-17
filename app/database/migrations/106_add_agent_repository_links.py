"""Link repositories and backup jobs to managed agents."""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def _column_exists(db, table_name: str, column_name: str) -> bool:
    rows = db.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def upgrade(db):
    if not _column_exists(db, "repositories", "execution_target"):
        db.execute(
            text(
                "ALTER TABLE repositories "
                "ADD COLUMN execution_target VARCHAR NOT NULL DEFAULT 'local'"
            )
        )

    if not _column_exists(db, "repositories", "agent_machine_id"):
        db.execute(
            text(
                "ALTER TABLE repositories "
                "ADD COLUMN agent_machine_id INTEGER REFERENCES agent_machines(id)"
            )
        )

    if not _column_exists(db, "agent_jobs", "backup_job_id"):
        db.execute(
            text(
                "ALTER TABLE agent_jobs "
                "ADD COLUMN backup_job_id INTEGER REFERENCES backup_jobs(id) ON DELETE SET NULL"
            )
        )

    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_repositories_execution_target "
            "ON repositories(execution_target)"
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_repositories_agent_machine_id "
            "ON repositories(agent_machine_id)"
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_agent_jobs_backup_job_id "
            "ON agent_jobs(backup_job_id)"
        )
    )
    db.commit()
    logger.info("Migration 106_add_agent_repository_links completed")


def downgrade(db):
    logger.warning(
        "Downgrade not supported for SQLite - agent repository columns will remain"
    )
