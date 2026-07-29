"""Add per-type scheduler concurrency limits to system settings."""

from sqlalchemy import text


def upgrade(db):
    result = db.execute(text("PRAGMA table_info(system_settings)"))
    existing_columns = {row[1] for row in result.fetchall()}

    if "max_concurrent_scheduled_backups" not in existing_columns:
        db.execute(
            text(
                """
                ALTER TABLE system_settings
                ADD COLUMN max_concurrent_scheduled_backups INTEGER DEFAULT 2
                """
            )
        )

    if "max_concurrent_scheduled_checks" not in existing_columns:
        db.execute(
            text(
                """
                ALTER TABLE system_settings
                ADD COLUMN max_concurrent_scheduled_checks INTEGER DEFAULT 4
                """
            )
        )

    db.commit()


def downgrade(db):
    # SQLite migrations in this project are additive; leave columns in place.
    db.commit()
