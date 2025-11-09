from sqlalchemy import text

def upgrade(connection):
    """Add PID tracking fields to check_jobs and compact_jobs tables"""

    # Check if columns already exist in check_jobs (idempotent)
    result = connection.execute(text("PRAGMA table_info(check_jobs)"))
    check_columns = [row[1] for row in result]

    if 'process_pid' not in check_columns:
        connection.execute(text("""
            ALTER TABLE check_jobs ADD COLUMN process_pid INTEGER
        """))

    if 'process_start_time' not in check_columns:
        connection.execute(text("""
            ALTER TABLE check_jobs ADD COLUMN process_start_time BIGINT
        """))

    # Check if columns already exist in compact_jobs (idempotent)
    result = connection.execute(text("PRAGMA table_info(compact_jobs)"))
    compact_columns = [row[1] for row in result]

    if 'process_pid' not in compact_columns:
        connection.execute(text("""
            ALTER TABLE compact_jobs ADD COLUMN process_pid INTEGER
        """))

    if 'process_start_time' not in compact_columns:
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
