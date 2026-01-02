"""
Migration 037: Add multi-repository schedule support

This migration adds:
1. scheduled_job_repositories junction table for many-to-many relationship
2. run_repository_scripts column to control per-repo script execution

This allows scheduling a single backup job that runs against multiple repositories
with shared pre/post scripts at the schedule level.
"""

from sqlalchemy import text

def upgrade(db):
    """Add multi-repository schedule support"""
    print("Running migration 037: Add multi-repository schedule support")

    try:
        # Check if scheduled_job_repositories table already exists
        result = db.execute(text("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='scheduled_job_repositories'
        """))
        table_exists = result.fetchone() is not None

        if not table_exists:
            # Create junction table for multi-repo schedules
            db.execute(text("""
                CREATE TABLE scheduled_job_repositories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scheduled_job_id INTEGER NOT NULL,
                    repository_id INTEGER NOT NULL,
                    execution_order INTEGER NOT NULL,
                    FOREIGN KEY (scheduled_job_id) REFERENCES scheduled_jobs(id) ON DELETE CASCADE,
                    FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE,
                    UNIQUE(scheduled_job_id, repository_id)
                )
            """))
            print("✓ Created scheduled_job_repositories junction table")
        else:
            print("⊘ Table scheduled_job_repositories already exists, skipping")

        # Check which columns already exist in scheduled_jobs
        result = db.execute(text("PRAGMA table_info(scheduled_jobs)"))
        existing_columns = {row[1] for row in result}

        # Add repository_id column
        if 'repository_id' not in existing_columns:
            db.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN repository_id INTEGER REFERENCES repositories(id)
            """))
            print("✓ Added repository_id column (nullable)")
        else:
            print("⊘ Column repository_id already exists, skipping")

        # Add pre_backup_script_id column
        if 'pre_backup_script_id' not in existing_columns:
            db.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN pre_backup_script_id INTEGER REFERENCES scripts(id)
            """))
            print("✓ Added pre_backup_script_id column (nullable)")
        else:
            print("⊘ Column pre_backup_script_id already exists, skipping")

        # Add post_backup_script_id column
        if 'post_backup_script_id' not in existing_columns:
            db.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN post_backup_script_id INTEGER REFERENCES scripts(id)
            """))
            print("✓ Added post_backup_script_id column (nullable)")
        else:
            print("⊘ Column post_backup_script_id already exists, skipping")

        # Add run_repository_scripts column
        if 'run_repository_scripts' not in existing_columns:
            db.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN run_repository_scripts INTEGER DEFAULT 0 NOT NULL
            """))
            print("✓ Added run_repository_scripts column with default 0 (disabled)")
        else:
            print("⊘ Column run_repository_scripts already exists, skipping")

        db.commit()
        print("✓ Migration 037 completed successfully")

    except Exception as e:
        print(f"✗ Migration 037 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Downgrade migration 037"""
    print("Running downgrade for migration 037")
    try:
        # Drop scheduled_job_repositories table
        db.execute(text("DROP TABLE IF EXISTS scheduled_job_repositories"))
        print("✓ Dropped scheduled_job_repositories table")

        # SQLite doesn't support DROP COLUMN directly
        print("! Note: SQLite doesn't support DROP COLUMN.")
        print("! The run_repository_scripts column will remain in the scheduled_jobs table.")

        db.commit()
        print("✓ Downgrade completed for migration 037")
    except Exception as e:
        print(f"! Error during downgrade: {e}")
        db.rollback()
        raise
