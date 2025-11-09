from sqlalchemy import text

def upgrade(connection):
    """Add PID tracking fields to check_jobs and compact_jobs tables"""

    # Add PID tracking to check_jobs
    connection.execute(text("""
        ALTER TABLE check_jobs ADD COLUMN process_pid INTEGER
    """))
    connection.execute(text("""
        ALTER TABLE check_jobs ADD COLUMN process_start_time BIGINT
    """))

    # Add PID tracking to compact_jobs
    connection.execute(text("""
        ALTER TABLE compact_jobs ADD COLUMN process_pid INTEGER
    """))
    connection.execute(text("""
        ALTER TABLE compact_jobs ADD COLUMN process_start_time BIGINT
    """))

    connection.commit()

def downgrade(connection):
    """Remove PID tracking fields from check_jobs and compact_jobs tables"""

    # Remove from check_jobs
    connection.execute(text("""
        ALTER TABLE check_jobs DROP COLUMN process_pid
    """))
    connection.execute(text("""
        ALTER TABLE check_jobs DROP COLUMN process_start_time
    """))

    # Remove from compact_jobs
    connection.execute(text("""
        ALTER TABLE compact_jobs DROP COLUMN process_pid
    """))
    connection.execute(text("""
        ALTER TABLE compact_jobs DROP COLUMN process_start_time
    """))

    connection.commit()
