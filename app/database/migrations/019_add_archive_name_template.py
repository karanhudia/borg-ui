from sqlalchemy import text

def upgrade(connection):
    """Add archive_name_template column to scheduled_jobs table"""

    # Check if column already exists (idempotent)
    result = connection.execute(text("PRAGMA table_info(scheduled_jobs)"))
    columns = [row[1] for row in result]

    if 'archive_name_template' not in columns:
        connection.execute(text("""
            ALTER TABLE scheduled_jobs ADD COLUMN archive_name_template VARCHAR
        """))

    connection.commit()

def downgrade(connection):
    """Remove archive_name_template column from scheduled_jobs table"""

    # Check if column exists before dropping
    result = connection.execute(text("PRAGMA table_info(scheduled_jobs)"))
    columns = [row[1] for row in result]

    if 'archive_name_template' in columns:
        # SQLite doesn't support DROP COLUMN directly, need to recreate table
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
