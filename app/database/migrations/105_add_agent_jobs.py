"""Add managed agent job transport tables."""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    db.execute(
        text("""
        CREATE TABLE IF NOT EXISTS agent_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_machine_id INTEGER NOT NULL REFERENCES agent_machines(id) ON DELETE CASCADE,
            backup_job_id INTEGER REFERENCES backup_jobs(id) ON DELETE SET NULL,
            job_type VARCHAR NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'queued',
            payload JSON NOT NULL,
            result JSON,
            claimed_at DATETIME,
            started_at DATETIME,
            completed_at DATETIME,
            error_message TEXT,
            progress_percent FLOAT DEFAULT 0.0,
            current_file TEXT,
            original_size BIGINT DEFAULT 0,
            compressed_size BIGINT DEFAULT 0,
            deduplicated_size BIGINT DEFAULT 0,
            nfiles INTEGER DEFAULT 0,
            backup_speed FLOAT DEFAULT 0.0,
            total_expected_size BIGINT DEFAULT 0,
            estimated_time_remaining INTEGER DEFAULT 0,
            progress JSON,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)
    )
    db.execute(
        text("CREATE INDEX IF NOT EXISTS ix_agent_jobs_status ON agent_jobs(status)")
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_agent_jobs_agent_status "
            "ON agent_jobs(agent_machine_id, status)"
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_agent_jobs_backup_job_id "
            "ON agent_jobs(backup_job_id)"
        )
    )

    db.execute(
        text("""
        CREATE TABLE IF NOT EXISTS agent_job_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_job_id INTEGER NOT NULL REFERENCES agent_jobs(id) ON DELETE CASCADE,
            sequence INTEGER NOT NULL,
            stream VARCHAR NOT NULL DEFAULT 'stdout',
            message TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            received_at DATETIME NOT NULL,
            UNIQUE(agent_job_id, sequence)
        )
        """)
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_agent_job_logs_agent_job_id "
            "ON agent_job_logs(agent_job_id)"
        )
    )
    db.commit()
    logger.info("Migration 105_add_agent_jobs completed")


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite - agent job tables will remain")
