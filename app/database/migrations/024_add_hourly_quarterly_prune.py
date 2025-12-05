from sqlalchemy import text

def upgrade(connection):
    """Add prune_keep_hourly and prune_keep_quarterly columns to repositories and scheduled_jobs tables

    This enables users to configure hourly and quarterly retention policies
    for their backups, providing finer-grained control over backup retention.

    - keep_hourly: Uses borg's --keep-hourly option
    - keep_quarterly: Uses borg's --keep-3monthly option (quarterly backups)
    """

    # Check if columns already exist in repositories (idempotent)
    result = connection.execute(text("PRAGMA table_info(repositories)"))
    columns = [row[1] for row in result]

    columns_added = []

    if 'prune_keep_hourly' not in columns:
        # Add prune_keep_hourly column to repositories
        connection.execute(text("""
            ALTER TABLE repositories ADD COLUMN prune_keep_hourly INTEGER NOT NULL DEFAULT 0
        """))
        columns_added.append('repositories.prune_keep_hourly')

    if 'prune_keep_quarterly' not in columns:
        # Add prune_keep_quarterly column to repositories
        connection.execute(text("""
            ALTER TABLE repositories ADD COLUMN prune_keep_quarterly INTEGER NOT NULL DEFAULT 0
        """))
        columns_added.append('repositories.prune_keep_quarterly')

    # Check if columns already exist in scheduled_jobs (idempotent)
    result = connection.execute(text("PRAGMA table_info(scheduled_jobs)"))
    scheduled_columns = [row[1] for row in result]

    if 'prune_keep_hourly' not in scheduled_columns:
        # Add prune_keep_hourly column to scheduled_jobs
        connection.execute(text("""
            ALTER TABLE scheduled_jobs ADD COLUMN prune_keep_hourly INTEGER NOT NULL DEFAULT 0
        """))
        columns_added.append('scheduled_jobs.prune_keep_hourly')

    if 'prune_keep_quarterly' not in scheduled_columns:
        # Add prune_keep_quarterly column to scheduled_jobs
        connection.execute(text("""
            ALTER TABLE scheduled_jobs ADD COLUMN prune_keep_quarterly INTEGER NOT NULL DEFAULT 0
        """))
        columns_added.append('scheduled_jobs.prune_keep_quarterly')

    if columns_added:
        print(f"✓ Migration 024: Added {', '.join(columns_added)} columns")
    else:
        print("⊘ Migration 024: prune_keep_hourly and prune_keep_quarterly columns already exist, skipping")

    connection.commit()

def downgrade(connection):
    """Remove prune_keep_hourly and prune_keep_quarterly columns from repositories and scheduled_jobs tables"""
    # SQLite doesn't support DROP COLUMN directly, would need to recreate table
    # For now, we'll just mark it as deprecated in a downgrade scenario
    print("⚠ Migration 024 downgrade: SQLite doesn't support DROP COLUMN")
    print("  The prune_keep_hourly and prune_keep_quarterly columns will remain but can be ignored")
    connection.commit()
