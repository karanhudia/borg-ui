from sqlalchemy import text

def upgrade(connection):
    """Add max_duration column to check_jobs table"""
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
