from sqlalchemy import text

def upgrade(connection):
    """Add mode column to repositories table

    This enables observability-only repositories that can browse and restore
    existing archives without requiring source directories for backups.

    Modes:
    - 'full': Normal mode with backups + observability (default)
    - 'observe': Observability-only mode - browse/restore but no backups
    """

    # Check if column already exists (idempotent)
    result = connection.execute(text("PRAGMA table_info(repositories)"))
    columns = [row[1] for row in result]

    if 'mode' not in columns:
        # Add mode column with default value 'full'
        connection.execute(text("""
            ALTER TABLE repositories ADD COLUMN mode VARCHAR DEFAULT 'full'
        """))

        # Set existing repositories with source_directories to 'full'
        connection.execute(text("""
            UPDATE repositories
            SET mode = 'full'
            WHERE source_directories IS NOT NULL
        """))

        print("✓ Migration 020: Added mode column to repositories")
    else:
        print("⊘ Migration 020: mode column already exists, skipping")

    connection.commit()

def downgrade(connection):
    """Remove mode column from repositories table"""

    # Check if column exists before dropping
    result = connection.execute(text("PRAGMA table_info(repositories)"))
    columns = [row[1] for row in result]

    if 'mode' in columns:
        # SQLite doesn't support DROP COLUMN directly, need to recreate table
        # Get current table schema to preserve all fields except mode
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
                   continue_on_hook_failure
            FROM repositories
        """))

        connection.execute(text("DROP TABLE repositories"))
        connection.execute(text("ALTER TABLE repositories_new RENAME TO repositories"))

        print("✓ Migration 020 rolled back: Removed mode column from repositories")
    else:
        print("⊘ Migration 020 rollback: mode column doesn't exist, skipping")

    connection.commit()
