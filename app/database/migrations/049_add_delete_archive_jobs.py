"""Add delete_archive_jobs table for background archive deletion"""

from sqlalchemy import text


def upgrade(connection):
    """Create delete_archive_jobs table"""
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS delete_archive_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repository_id INTEGER NOT NULL,
            repository_path TEXT,
            archive_name TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            progress INTEGER DEFAULT 0,
            progress_message TEXT,
            error_message TEXT,
            logs TEXT,
            log_file_path TEXT,
            has_logs BOOLEAN DEFAULT 0,
            process_pid INTEGER,
            process_start_time BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (repository_id) REFERENCES repositories (id)
        )
    """))

    print("✓ Created delete_archive_jobs table")


def downgrade(connection):
    """Drop delete_archive_jobs table"""
    connection.execute(text("DROP TABLE IF EXISTS delete_archive_jobs"))
    print("✓ Dropped delete_archive_jobs table")
