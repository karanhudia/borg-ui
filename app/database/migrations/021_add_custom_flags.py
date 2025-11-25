from sqlalchemy import text

def upgrade(connection):
    """Add custom_flags column to repositories table

    This enables advanced users to specify custom command-line flags for the
    borg create command (e.g., "--stats", "--list", "--filter AME").
    """

    # Check if column already exists (idempotent)
    result = connection.execute(text("PRAGMA table_info(repositories)"))
    columns = [row[1] for row in result]

    if 'custom_flags' not in columns:
        # Add custom_flags column
        connection.execute(text("""
            ALTER TABLE repositories ADD COLUMN custom_flags TEXT
        """))

        print("✓ Migration 021: Added custom_flags column to repositories")
    else:
        print("⊘ Migration 021: custom_flags column already exists, skipping")

    connection.commit()

def downgrade(connection):
    """Remove custom_flags column from repositories table"""

    # Check if column exists before dropping
    result = connection.execute(text("PRAGMA table_info(repositories)"))
    columns = [row[1] for row in result]

    if 'custom_flags' in columns:
        # SQLite doesn't support DROP COLUMN directly, need to recreate table
        # Get current table schema to preserve all fields except custom_flags
        connection.execute(text("""
            CREATE TABLE repositories_new (
                id INTEGER PRIMARY KEY,
                name VARCHAR UNIQUE NOT NULL,
                path VARCHAR UNIQUE NOT NULL,
                encryption VARCHAR DEFAULT 'repokey',
                compression VARCHAR DEFAULT 'lz4',
                passphrase VARCHAR,
                source_directories TEXT,
                exclude_patterns TEXT,
                last_backup DATETIME,
                last_check DATETIME,
                last_compact DATETIME,
                total_size VARCHAR,
                archive_count INTEGER DEFAULT 0,
                created_at DATETIME,
                updated_at DATETIME,
                repository_type VARCHAR DEFAULT 'local',
                host VARCHAR,
                port INTEGER DEFAULT 22,
                username VARCHAR,
                ssh_key_id INTEGER,
                remote_path VARCHAR,
                auth_status VARCHAR DEFAULT 'unknown',
                last_auth_test DATETIME,
                auth_error_message TEXT,
                pre_backup_script TEXT,
                post_backup_script TEXT,
                hook_timeout INTEGER DEFAULT 300,
                continue_on_hook_failure BOOLEAN DEFAULT 0,
                mode VARCHAR DEFAULT 'full',
                FOREIGN KEY (ssh_key_id) REFERENCES ssh_keys (id)
            )
        """))

        connection.execute(text("""
            INSERT INTO repositories_new
            SELECT id, name, path, encryption, compression, passphrase,
                   source_directories, exclude_patterns, last_backup, last_check,
                   last_compact, total_size, archive_count, created_at, updated_at,
                   repository_type, host, port, username, ssh_key_id, remote_path,
                   auth_status, last_auth_test, auth_error_message,
                   pre_backup_script, post_backup_script, hook_timeout,
                   continue_on_hook_failure, mode
            FROM repositories
        """))

        connection.execute(text("DROP TABLE repositories"))
        connection.execute(text("ALTER TABLE repositories_new RENAME TO repositories"))

        print("✓ Migration 021 rolled back: Removed custom_flags column from repositories")
    else:
        print("⊘ Migration 021 rollback: custom_flags column doesn't exist, skipping")

    connection.commit()
