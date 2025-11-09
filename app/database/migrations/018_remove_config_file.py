from sqlalchemy import text

def upgrade(connection):
    """Remove config_file columns from backup_jobs and scheduled_jobs tables"""

    # Check if columns exist before dropping (idempotent)
    result = connection.execute(text("PRAGMA table_info(backup_jobs)"))
    backup_columns = [row[1] for row in result]

    if 'config_file' in backup_columns:
        # SQLite doesn't support DROP COLUMN directly, need to recreate table
        connection.execute(text("""
            CREATE TABLE backup_jobs_new (
                id INTEGER PRIMARY KEY,
                repository VARCHAR,
                status VARCHAR DEFAULT 'pending',
                started_at DATETIME,
                completed_at DATETIME,
                progress INTEGER DEFAULT 0,
                error_message TEXT,
                logs TEXT,
                log_file_path VARCHAR,
                scheduled_job_id INTEGER,
                original_size BIGINT DEFAULT 0,
                compressed_size BIGINT DEFAULT 0,
                deduplicated_size BIGINT DEFAULT 0,
                nfiles INTEGER DEFAULT 0,
                current_file TEXT,
                progress_percent FLOAT DEFAULT 0.0,
                backup_speed FLOAT DEFAULT 0.0,
                total_expected_size BIGINT DEFAULT 0,
                estimated_time_remaining INTEGER DEFAULT 0,
                maintenance_status VARCHAR,
                created_at DATETIME,
                FOREIGN KEY(scheduled_job_id) REFERENCES scheduled_jobs(id)
            )
        """))

        connection.execute(text("""
            INSERT INTO backup_jobs_new
            SELECT id, repository, status, started_at, completed_at, progress,
                   error_message, logs, log_file_path, scheduled_job_id, original_size,
                   compressed_size, deduplicated_size, nfiles, current_file, progress_percent,
                   backup_speed, total_expected_size, estimated_time_remaining,
                   maintenance_status, created_at
            FROM backup_jobs
        """))

        connection.execute(text("DROP TABLE backup_jobs"))
        connection.execute(text("ALTER TABLE backup_jobs_new RENAME TO backup_jobs"))

    # Check if columns exist in scheduled_jobs before dropping
    result = connection.execute(text("PRAGMA table_info(scheduled_jobs)"))
    scheduled_columns = [row[1] for row in result]

    if 'config_file' in scheduled_columns:
        connection.execute(text("""
            CREATE TABLE scheduled_jobs_new (
                id INTEGER PRIMARY KEY,
                name VARCHAR UNIQUE NOT NULL,
                cron_expression VARCHAR NOT NULL,
                repository VARCHAR,
                enabled BOOLEAN DEFAULT 1,
                last_run DATETIME,
                next_run DATETIME,
                description TEXT,
                run_prune_after BOOLEAN DEFAULT 0,
                run_compact_after BOOLEAN DEFAULT 0,
                prune_keep_daily INTEGER DEFAULT 7,
                prune_keep_weekly INTEGER DEFAULT 4,
                prune_keep_monthly INTEGER DEFAULT 6,
                prune_keep_yearly INTEGER DEFAULT 1,
                last_prune DATETIME,
                last_compact DATETIME,
                created_at DATETIME,
                updated_at DATETIME
            )
        """))

        connection.execute(text("""
            INSERT INTO scheduled_jobs_new
            SELECT id, name, cron_expression, repository, enabled, last_run, next_run,
                   description, run_prune_after, run_compact_after, prune_keep_daily,
                   prune_keep_weekly, prune_keep_monthly, prune_keep_yearly, last_prune,
                   last_compact, created_at, updated_at
            FROM scheduled_jobs
        """))

        connection.execute(text("DROP TABLE scheduled_jobs"))
        connection.execute(text("ALTER TABLE scheduled_jobs_new RENAME TO scheduled_jobs"))

    connection.commit()

def downgrade(connection):
    """Add config_file columns back to backup_jobs and scheduled_jobs tables"""

    # Check if columns already exist (idempotent)
    result = connection.execute(text("PRAGMA table_info(backup_jobs)"))
    backup_columns = [row[1] for row in result]

    if 'config_file' not in backup_columns:
        connection.execute(text("""
            ALTER TABLE backup_jobs ADD COLUMN config_file VARCHAR
        """))

    result = connection.execute(text("PRAGMA table_info(scheduled_jobs)"))
    scheduled_columns = [row[1] for row in result]

    if 'config_file' not in scheduled_columns:
        connection.execute(text("""
            ALTER TABLE scheduled_jobs ADD COLUMN config_file VARCHAR
        """))

    connection.commit()
