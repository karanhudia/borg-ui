from sqlalchemy import text

def upgrade(connection):
    """Add default_path column to ssh_keys table

    This enables users to specify a default starting path for SSH file browsing,
    which is particularly useful for restricted shells like Hetzner Storage Box
    that only allow access within /home directory.
    """

    # Check if column already exists (idempotent)
    result = connection.execute(text("PRAGMA table_info(ssh_keys)"))
    columns = [row[1] for row in result]

    if 'default_path' not in columns:
        # Add default_path column
        connection.execute(text("""
            ALTER TABLE ssh_keys ADD COLUMN default_path TEXT
        """))

        print("✓ Migration 022: Added default_path column to ssh_keys")
    else:
        print("⊘ Migration 022: default_path column already exists, skipping")

    connection.commit()

def downgrade(connection):
    """Remove default_path column from ssh_keys table"""
    # SQLite doesn't support DROP COLUMN directly, would need to recreate table
    # For now, we'll just mark it as deprecated in a downgrade scenario
    print("⚠ Migration 022 downgrade: SQLite doesn't support DROP COLUMN")
    print("  The default_path column will remain but can be ignored")
    connection.commit()
