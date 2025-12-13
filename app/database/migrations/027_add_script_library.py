"""
Migration 027: Add Script Library System

This migration creates the script library system for Phase 2.
Creates tables for scripts, repository_scripts junction, and script_executions.
Enables reusable scripts, chaining, and better script management.

Fixes issues #85 and #88.
"""

from sqlalchemy import text

def upgrade(db):
    """Create script library tables"""
    print("Running migration 027: Add Script Library System")

    try:
        # Check if tables already exist
        cursor = db.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('scripts', 'repository_scripts', 'script_executions')"))
        existing_tables = [row[0] for row in cursor.fetchall()]

        if 'scripts' not in existing_tables:
            print("Creating scripts table...")
            db.execute(text("""
                CREATE TABLE scripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(255) NOT NULL UNIQUE,
                    description TEXT,
                    file_path VARCHAR(500) NOT NULL,
                    category VARCHAR(50) NOT NULL DEFAULT 'custom',

                    timeout INTEGER NOT NULL DEFAULT 300,
                    shell VARCHAR(50) NOT NULL DEFAULT '/bin/bash',
                    run_on VARCHAR(50) NOT NULL DEFAULT 'success',

                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    created_by_user_id INTEGER REFERENCES users(id),

                    is_template BOOLEAN NOT NULL DEFAULT 0,
                    template_version VARCHAR(20),

                    usage_count INTEGER NOT NULL DEFAULT 0,
                    last_used_at TIMESTAMP
                )
            """))
            db.execute(text("CREATE INDEX ix_scripts_name ON scripts(name)"))
            db.execute(text("CREATE INDEX ix_scripts_category ON scripts(category)"))
            print("✓ Created scripts table")
        else:
            print("✓ Table scripts already exists, skipping")

        if 'repository_scripts' not in existing_tables:
            print("Creating repository_scripts junction table...")
            db.execute(text("""
                CREATE TABLE repository_scripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                    script_id INTEGER NOT NULL REFERENCES scripts(id) ON DELETE CASCADE,

                    hook_type VARCHAR(50) NOT NULL,
                    execution_order INTEGER NOT NULL DEFAULT 1,
                    enabled BOOLEAN NOT NULL DEFAULT 1,

                    custom_timeout INTEGER,
                    custom_run_on VARCHAR(50),

                    created_at TIMESTAMP NOT NULL,

                    UNIQUE(repository_id, script_id, hook_type)
                )
            """))
            db.execute(text("CREATE INDEX ix_repository_scripts_repository_id ON repository_scripts(repository_id)"))
            db.execute(text("CREATE INDEX ix_repository_scripts_script_id ON repository_scripts(script_id)"))
            db.execute(text("CREATE INDEX ix_repository_scripts_hook_type ON repository_scripts(hook_type)"))
            print("✓ Created repository_scripts table")
        else:
            print("✓ Table repository_scripts already exists, skipping")

        if 'script_executions' not in existing_tables:
            print("Creating script_executions table...")
            db.execute(text("""
                CREATE TABLE script_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    script_id INTEGER NOT NULL REFERENCES scripts(id),
                    repository_id INTEGER REFERENCES repositories(id),
                    backup_job_id INTEGER REFERENCES backup_jobs(id),

                    hook_type VARCHAR(50),
                    status VARCHAR(50) NOT NULL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    execution_time REAL,

                    exit_code INTEGER,
                    stdout TEXT,
                    stderr TEXT,
                    error_message TEXT,

                    triggered_by VARCHAR(50),
                    triggered_by_user_id INTEGER REFERENCES users(id),

                    UNIQUE(script_id, backup_job_id, hook_type)
                )
            """))
            db.execute(text("CREATE INDEX ix_script_executions_script_id ON script_executions(script_id)"))
            db.execute(text("CREATE INDEX ix_script_executions_repository_id ON script_executions(repository_id)"))
            db.execute(text("CREATE INDEX ix_script_executions_backup_job_id ON script_executions(backup_job_id)"))
            db.execute(text("CREATE INDEX ix_script_executions_status ON script_executions(status)"))
            print("✓ Created script_executions table")
        else:
            print("✓ Table script_executions already exists, skipping")

        db.commit()
        print("✓ Migration 027 completed successfully")

    except Exception as e:
        print(f"✗ Migration 027 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Remove script library tables"""
    print("Running downgrade for migration 027")

    try:
        # Drop tables in reverse order (respecting foreign keys)
        db.execute(text("DROP TABLE IF EXISTS script_executions"))
        print("✓ Dropped script_executions table")

        db.execute(text("DROP TABLE IF EXISTS repository_scripts"))
        print("✓ Dropped repository_scripts table")

        db.execute(text("DROP TABLE IF EXISTS scripts"))
        print("✓ Dropped scripts table")

        db.commit()
        print("✓ Downgrade completed successfully")

    except Exception as e:
        print(f"✗ Downgrade failed: {e}")
        db.rollback()
        raise
