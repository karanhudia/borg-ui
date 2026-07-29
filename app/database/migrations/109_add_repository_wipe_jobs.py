"""Add repository_wipe_jobs table for repository contents wipe audit trail."""

from sqlalchemy import text


def upgrade(db):
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS repository_wipe_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_id INTEGER,
                repository_path VARCHAR,
                repository_name VARCHAR,
                borg_version INTEGER,
                status VARCHAR DEFAULT 'previewed',
                phase VARCHAR,
                archive_count INTEGER DEFAULT 0,
                archive_fingerprint VARCHAR,
                archive_manifest_json TEXT,
                dry_run_output TEXT,
                blocking_reason VARCHAR,
                protected_archives_json TEXT,
                run_compact BOOLEAN NOT NULL DEFAULT 1,
                requested_by_user_id INTEGER,
                confirmed_by_user_id INTEGER,
                started_at DATETIME,
                confirmed_at DATETIME,
                completed_at DATETIME,
                progress INTEGER DEFAULT 0,
                progress_message VARCHAR,
                error_message TEXT,
                logs TEXT,
                log_file_path VARCHAR,
                has_logs BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(repository_id) REFERENCES repositories(id) ON DELETE SET NULL,
                FOREIGN KEY(requested_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY(confirmed_by_user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_repository_wipe_jobs_repository_id "
            "ON repository_wipe_jobs(repository_id)"
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_repository_wipe_jobs_status "
            "ON repository_wipe_jobs(status)"
        )
    )


def downgrade(db):
    db.execute(text("DROP TABLE IF EXISTS repository_wipe_jobs"))
