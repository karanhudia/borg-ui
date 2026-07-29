"""Add explicit timezone intent to recurring schedules."""

from sqlalchemy import text


def upgrade(db):
    result = db.execute(text("PRAGMA table_info(scheduled_jobs)"))
    scheduled_job_columns = {row[1] for row in result.fetchall()}

    if "timezone" not in scheduled_job_columns:
        db.execute(
            text(
                """
                ALTER TABLE scheduled_jobs
                ADD COLUMN timezone VARCHAR NOT NULL DEFAULT 'UTC'
                """
            )
        )

    result = db.execute(text("PRAGMA table_info(repositories)"))
    repository_columns = {row[1] for row in result.fetchall()}

    if "check_timezone" not in repository_columns:
        db.execute(
            text(
                """
                ALTER TABLE repositories
                ADD COLUMN check_timezone VARCHAR NOT NULL DEFAULT 'UTC'
                """
            )
        )

    db.commit()


def downgrade(db):
    # SQLite migrations in this project are additive; leave columns in place.
    db.commit()
