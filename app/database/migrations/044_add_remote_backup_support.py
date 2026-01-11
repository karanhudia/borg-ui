"""
Migration 044: Add remote backup support

This migration adds fields to support remote backup orchestration:
- SSHConnection: is_backup_source, borg_binary_path, borg_version, last_borg_check
- BackupJob: execution_mode, source_ssh_connection_id, remote_process_pid, remote_hostname
- ScheduledJob: execution_mode, source_ssh_connection_id
"""

from sqlalchemy import text

def upgrade(db):
    """Add remote backup support fields"""
    print("Running migration 044: Add remote backup support")

    try:
        # Extend SSH connections
        result = db.execute(text("PRAGMA table_info(ssh_connections)"))
        ssh_columns = {row[1] for row in result}

        if 'is_backup_source' not in ssh_columns:
            db.execute(text("""
                ALTER TABLE ssh_connections
                ADD COLUMN is_backup_source INTEGER DEFAULT 0 NOT NULL
            """))
            print("✓ Added is_backup_source column to ssh_connections")
        else:
            print("⊘ Column is_backup_source already exists in ssh_connections")

        if 'borg_binary_path' not in ssh_columns:
            db.execute(text("""
                ALTER TABLE ssh_connections
                ADD COLUMN borg_binary_path TEXT DEFAULT '/usr/bin/borg' NOT NULL
            """))
            print("✓ Added borg_binary_path column to ssh_connections")
        else:
            print("⊘ Column borg_binary_path already exists in ssh_connections")

        if 'borg_version' not in ssh_columns:
            db.execute(text("""
                ALTER TABLE ssh_connections
                ADD COLUMN borg_version TEXT
            """))
            print("✓ Added borg_version column to ssh_connections")
        else:
            print("⊘ Column borg_version already exists in ssh_connections")

        if 'last_borg_check' not in ssh_columns:
            db.execute(text("""
                ALTER TABLE ssh_connections
                ADD COLUMN last_borg_check TIMESTAMP
            """))
            print("✓ Added last_borg_check column to ssh_connections")
        else:
            print("⊘ Column last_borg_check already exists in ssh_connections")

        # Extend backup jobs
        result = db.execute(text("PRAGMA table_info(backup_jobs)"))
        backup_columns = {row[1] for row in result}

        if 'execution_mode' not in backup_columns:
            db.execute(text("""
                ALTER TABLE backup_jobs
                ADD COLUMN execution_mode TEXT DEFAULT 'local' NOT NULL
            """))
            print("✓ Added execution_mode column to backup_jobs")
        else:
            print("⊘ Column execution_mode already exists in backup_jobs")

        if 'source_ssh_connection_id' not in backup_columns:
            db.execute(text("""
                ALTER TABLE backup_jobs
                ADD COLUMN source_ssh_connection_id INTEGER
            """))
            print("✓ Added source_ssh_connection_id column to backup_jobs")
        else:
            print("⊘ Column source_ssh_connection_id already exists in backup_jobs")

        if 'remote_process_pid' not in backup_columns:
            db.execute(text("""
                ALTER TABLE backup_jobs
                ADD COLUMN remote_process_pid INTEGER
            """))
            print("✓ Added remote_process_pid column to backup_jobs")
        else:
            print("⊘ Column remote_process_pid already exists in backup_jobs")

        if 'remote_hostname' not in backup_columns:
            db.execute(text("""
                ALTER TABLE backup_jobs
                ADD COLUMN remote_hostname TEXT
            """))
            print("✓ Added remote_hostname column to backup_jobs")
        else:
            print("⊘ Column remote_hostname already exists in backup_jobs")

        # Extend scheduled jobs
        result = db.execute(text("PRAGMA table_info(scheduled_jobs)"))
        scheduled_columns = {row[1] for row in result}

        if 'execution_mode' not in scheduled_columns:
            db.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN execution_mode TEXT DEFAULT 'local' NOT NULL
            """))
            print("✓ Added execution_mode column to scheduled_jobs")
        else:
            print("⊘ Column execution_mode already exists in scheduled_jobs")

        if 'source_ssh_connection_id' not in scheduled_columns:
            db.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN source_ssh_connection_id INTEGER
            """))
            print("✓ Added source_ssh_connection_id column to scheduled_jobs")
        else:
            print("⊘ Column source_ssh_connection_id already exists in scheduled_jobs")

        # Create indices for faster lookups
        try:
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_backup_jobs_source_ssh
                ON backup_jobs(source_ssh_connection_id)
            """))
            print("✓ Created index idx_backup_jobs_source_ssh")
        except Exception as e:
            print(f"⊘ Index idx_backup_jobs_source_ssh may already exist: {e}")

        try:
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_source_ssh
                ON scheduled_jobs(source_ssh_connection_id)
            """))
            print("✓ Created index idx_scheduled_jobs_source_ssh")
        except Exception as e:
            print(f"⊘ Index idx_scheduled_jobs_source_ssh may already exist: {e}")

        db.commit()
        print("✓ Migration 044 completed successfully")

    except Exception as e:
        print(f"✗ Migration 044 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Downgrade migration 044"""
    print("Running downgrade for migration 044")
    try:
        # SQLite doesn't support DROP COLUMN directly
        print("! Note: SQLite doesn't support DROP COLUMN. Manual intervention required if needed.")
        print("! The remote backup support columns will remain in the tables.")
        db.commit()
        print("✓ Downgrade noted for migration 044")
    except Exception as e:
        print(f"! Error during downgrade: {e}")
        db.rollback()
        raise
