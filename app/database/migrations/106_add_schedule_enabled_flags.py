"""Add explicit enabled flags for repository check + restore-check schedules.

Until now, a check or restore-check schedule was "enabled" iff its
`*_cron_expression` column was non-empty. That conflates two ideas (the
cadence, and whether it should run), so a user wanting to pause a schedule
had to clear the cron and re-enter it later.

This migration adds two boolean columns (default true, preserving the prior
behavior for existing rows) so the UI can offer a real on/off toggle.
"""

from sqlalchemy import text


def upgrade(db):
    result = db.execute(text("PRAGMA table_info(repositories)"))
    existing_columns = {row[1] for row in result.fetchall()}

    if "check_schedule_enabled" not in existing_columns:
        db.execute(
            text(
                """
                ALTER TABLE repositories
                ADD COLUMN check_schedule_enabled BOOLEAN NOT NULL DEFAULT 1
                """
            )
        )

    if "restore_check_schedule_enabled" not in existing_columns:
        db.execute(
            text(
                """
                ALTER TABLE repositories
                ADD COLUMN restore_check_schedule_enabled BOOLEAN NOT NULL DEFAULT 1
                """
            )
        )

    db.commit()


def downgrade(db):
    # SQLite migrations in this project are additive; leave columns in place.
    db.commit()
