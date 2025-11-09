from sqlalchemy import text

def upgrade(connection):
    """Add max_duration column to check_jobs table"""
    # Check if column already exists (idempotent)
    result = connection.execute(text("PRAGMA table_info(check_jobs)"))
    columns = [row[1] for row in result]

    if 'max_duration' not in columns:
        connection.execute(text("""
            ALTER TABLE check_jobs ADD COLUMN max_duration INTEGER
        """))
        connection.commit()

def downgrade(connection):
    """Remove max_duration column from check_jobs table"""
    connection.execute(text("""
        ALTER TABLE check_jobs DROP COLUMN max_duration
    """))
    connection.commit()
