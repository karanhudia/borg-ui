"""
Migration 075: Add skip_on_failure to repository_scripts and skip_on_hook_failure to repositories.

When enabled, a pre-backup script that exits non-zero causes the backup to be
marked "skipped" (not "failed") — used for intentional graceful skip signals
such as leader-election checks.
"""
from sqlalchemy import text


def upgrade(db):
    try:
        db.execute(text(
            "ALTER TABLE repository_scripts ADD COLUMN skip_on_failure BOOLEAN NOT NULL DEFAULT 0"
        ))
    except Exception:
        pass  # Column already exists

    try:
        db.execute(text(
            "ALTER TABLE repositories ADD COLUMN skip_on_hook_failure BOOLEAN NOT NULL DEFAULT 0"
        ))
    except Exception:
        pass  # Column already exists

    db.commit()
