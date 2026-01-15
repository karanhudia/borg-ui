"""Add connection_id to repositories table for proper SSH connection tracking"""

from sqlalchemy import text


def upgrade(connection):
    """Add connection_id column to repositories table"""
    # Check if column already exists (SQLite compatible)
    result = connection.execute(
        text("PRAGMA table_info(repositories)")
    ).fetchall()

    column_names = [row[1] for row in result]

    if 'connection_id' not in column_names:
        # Add connection_id column
        connection.execute(text(
            "ALTER TABLE repositories ADD COLUMN connection_id INTEGER"
        ))

        # Create index for performance
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_repositories_connection_id ON repositories(connection_id)"
        ))

        print("✓ Added connection_id column to repositories table")
    else:
        print("✓ connection_id column already exists in repositories table")


def downgrade(connection):
    """Remove connection_id column from repositories table"""
    # SQLite doesn't support DROP COLUMN, would need table recreation
    # For now, just drop the index
    connection.execute(text(
        "DROP INDEX IF EXISTS idx_repositories_connection_id"
    ))
    print("✓ Removed connection_id index from repositories table")
