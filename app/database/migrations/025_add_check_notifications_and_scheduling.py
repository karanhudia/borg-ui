from sqlalchemy import text

def upgrade(connection):
    """Add check notifications and scheduled checks support

    This migration adds:
    1. Check notification settings to system_settings table
    2. Check notification settings to notification_settings table
    3. Scheduled check configuration to repositories table
    4. scheduled_check flag to check_jobs table
    """

    # Check if columns already exist in system_settings (idempotent)
    result = connection.execute(text("PRAGMA table_info(system_settings)"))
    settings_columns = [row[1] for row in result]

    columns_added = []

    # Add check notification settings to system_settings
    if 'notify_on_check_success' not in settings_columns:
        connection.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN notify_on_check_success BOOLEAN NOT NULL DEFAULT 0
        """))
        columns_added.append('system_settings.notify_on_check_success')

    if 'notify_on_check_failure' not in settings_columns:
        connection.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN notify_on_check_failure BOOLEAN NOT NULL DEFAULT 1
        """))
        columns_added.append('system_settings.notify_on_check_failure')

    # Check if columns already exist in notification_settings (idempotent)
    result = connection.execute(text("PRAGMA table_info(notification_settings)"))
    notif_columns = [row[1] for row in result]

    # Add check notification settings to notification_settings
    if 'notify_on_check_success' not in notif_columns:
        connection.execute(text("""
            ALTER TABLE notification_settings
            ADD COLUMN notify_on_check_success BOOLEAN NOT NULL DEFAULT 0
        """))
        columns_added.append('notification_settings.notify_on_check_success')

    if 'notify_on_check_failure' not in notif_columns:
        connection.execute(text("""
            ALTER TABLE notification_settings
            ADD COLUMN notify_on_check_failure BOOLEAN NOT NULL DEFAULT 1
        """))
        columns_added.append('notification_settings.notify_on_check_failure')

    # Check if columns already exist in repositories (idempotent)
    result = connection.execute(text("PRAGMA table_info(repositories)"))
    repo_columns = [row[1] for row in result]

    # Add scheduled check configuration to repositories
    if 'check_interval_days' not in repo_columns:
        connection.execute(text("""
            ALTER TABLE repositories
            ADD COLUMN check_interval_days INTEGER NULL
        """))
        columns_added.append('repositories.check_interval_days')

    if 'last_scheduled_check' not in repo_columns:
        connection.execute(text("""
            ALTER TABLE repositories
            ADD COLUMN last_scheduled_check DATETIME NULL
        """))
        columns_added.append('repositories.last_scheduled_check')

    if 'next_scheduled_check' not in repo_columns:
        connection.execute(text("""
            ALTER TABLE repositories
            ADD COLUMN next_scheduled_check DATETIME NULL
        """))
        columns_added.append('repositories.next_scheduled_check')

    if 'check_max_duration' not in repo_columns:
        connection.execute(text("""
            ALTER TABLE repositories
            ADD COLUMN check_max_duration INTEGER NOT NULL DEFAULT 3600
        """))
        columns_added.append('repositories.check_max_duration')

    if 'notify_on_check_success' not in repo_columns:
        connection.execute(text("""
            ALTER TABLE repositories
            ADD COLUMN notify_on_check_success BOOLEAN NOT NULL DEFAULT 0
        """))
        columns_added.append('repositories.notify_on_check_success')

    if 'notify_on_check_failure' not in repo_columns:
        connection.execute(text("""
            ALTER TABLE repositories
            ADD COLUMN notify_on_check_failure BOOLEAN NOT NULL DEFAULT 1
        """))
        columns_added.append('repositories.notify_on_check_failure')

    # Check if columns already exist in check_jobs (idempotent)
    result = connection.execute(text("PRAGMA table_info(check_jobs)"))
    check_job_columns = [row[1] for row in result]

    # Add scheduled_check flag to distinguish manual vs scheduled checks
    if 'scheduled_check' not in check_job_columns:
        connection.execute(text("""
            ALTER TABLE check_jobs
            ADD COLUMN scheduled_check BOOLEAN NOT NULL DEFAULT 0
        """))
        columns_added.append('check_jobs.scheduled_check')

    if columns_added:
        print(f"✓ Migration 025: Added {len(columns_added)} columns")
        for col in columns_added:
            print(f"  - {col}")
    else:
        print("⊘ Migration 025: All columns already exist, skipping")

    connection.commit()

def downgrade(connection):
    """Remove check notifications and scheduled checks columns"""
    # SQLite doesn't support DROP COLUMN directly
    print("⚠ Migration 025 downgrade: SQLite doesn't support DROP COLUMN")
    print("  The added columns will remain but can be ignored")
    connection.commit()
