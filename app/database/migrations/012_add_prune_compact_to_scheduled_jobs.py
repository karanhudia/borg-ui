"""
Migration 012: Add prune and compact options to scheduled_jobs

This migration adds fields to enable automatic prune and compact operations
after scheduled backups complete.
"""

from sqlalchemy import text

def upgrade(connection):
    """Add prune and compact fields to scheduled_jobs table"""

    # Check if columns already exist
    result = connection.execute(text("""
        SELECT sql FROM sqlite_master
        WHERE type='table' AND name='scheduled_jobs'
    """))

    table_sql = result.fetchone()
    if table_sql:
        table_def = table_sql[0]

        # Add run_prune_after column if it doesn't exist
        if 'run_prune_after' not in table_def:
            connection.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN run_prune_after BOOLEAN DEFAULT 0
            """))
            print("  Added column: run_prune_after")
        else:
            print("  Skipped (exists): run_prune_after column")

        # Add run_compact_after column if it doesn't exist
        if 'run_compact_after' not in table_def:
            connection.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN run_compact_after BOOLEAN DEFAULT 0
            """))
            print("  Added column: run_compact_after")
        else:
            print("  Skipped (exists): run_compact_after column")

        # Add prune retention settings columns
        if 'prune_keep_daily' not in table_def:
            connection.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN prune_keep_daily INTEGER DEFAULT 7
            """))
            print("  Added column: prune_keep_daily")
        else:
            print("  Skipped (exists): prune_keep_daily column")

        if 'prune_keep_weekly' not in table_def:
            connection.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN prune_keep_weekly INTEGER DEFAULT 4
            """))
            print("  Added column: prune_keep_weekly")
        else:
            print("  Skipped (exists): prune_keep_weekly column")

        if 'prune_keep_monthly' not in table_def:
            connection.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN prune_keep_monthly INTEGER DEFAULT 6
            """))
            print("  Added column: prune_keep_monthly")
        else:
            print("  Skipped (exists): prune_keep_monthly column")

        if 'prune_keep_yearly' not in table_def:
            connection.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN prune_keep_yearly INTEGER DEFAULT 1
            """))
            print("  Added column: prune_keep_yearly")
        else:
            print("  Skipped (exists): prune_keep_yearly column")

        # Add last maintenance operation tracking
        if 'last_prune' not in table_def:
            connection.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN last_prune DATETIME
            """))
            print("  Added column: last_prune")
        else:
            print("  Skipped (exists): last_prune column")

        if 'last_compact' not in table_def:
            connection.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN last_compact DATETIME
            """))
            print("  Added column: last_compact")
        else:
            print("  Skipped (exists): last_compact column")

    print("✓ Migration 012: Added prune and compact options to scheduled_jobs")

def downgrade(connection):
    """Remove prune and compact fields from scheduled_jobs table"""

    # SQLite doesn't support DROP COLUMN directly
    # Would need to recreate table without these columns
    # For now, we'll leave them (they default to disabled)

    print("✓ Migration 012 rollback: Prune/compact columns remain (set to disabled)")
