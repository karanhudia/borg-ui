"""
Migration 038: Add keyfile support for repositories

Adds has_keyfile field to track whether a repository uses keyfile encryption mode.
This enables support for uploading and managing keyfiles for keyfile/keyfile-blake2 encryption.
"""

from sqlalchemy import text

def upgrade(conn):
    """Add has_keyfile column to repositories table"""
    # Check if column already exists
    result = conn.execute(text("PRAGMA table_info(repositories)"))
    columns = [row[1] for row in result]

    if 'has_keyfile' not in columns:
        conn.execute(text("""
            ALTER TABLE repositories
            ADD COLUMN has_keyfile BOOLEAN DEFAULT FALSE
        """))
        conn.commit()

def downgrade(conn):
    """Remove has_keyfile column from repositories table"""
    conn.execute(text("""
        ALTER TABLE repositories
        DROP COLUMN has_keyfile
    """))
    conn.commit()
