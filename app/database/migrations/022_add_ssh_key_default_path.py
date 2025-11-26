from sqlalchemy import text

def upgrade(connection):
    """Add default_path column to ssh_connections table

    This enables users to specify a default starting path per SSH connection,
    which is particularly useful for restricted shells like Hetzner Storage Box
    that only allow access within /home directory.
    """

    # Check if column already exists in ssh_connections (idempotent)
    result = connection.execute(text("PRAGMA table_info(ssh_connections)"))
    columns = [row[1] for row in result]

    if 'default_path' not in columns:
        # Add default_path column to ssh_connections
        connection.execute(text("""
            ALTER TABLE ssh_connections ADD COLUMN default_path TEXT
        """))

        print("✓ Migration 022: Added default_path column to ssh_connections")
    else:
        print("⊘ Migration 022: default_path column already exists in ssh_connections, skipping")

    connection.commit()

def downgrade(connection):
    """Remove default_path column from ssh_connections table"""
    # SQLite doesn't support DROP COLUMN directly, would need to recreate table
    # For now, we'll just mark it as deprecated in a downgrade scenario
    print("⚠ Migration 022 downgrade: SQLite doesn't support DROP COLUMN")
    print("  The default_path column will remain but can be ignored")
    connection.commit()
