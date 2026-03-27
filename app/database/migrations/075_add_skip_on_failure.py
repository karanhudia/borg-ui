"""
Migration 075: Add skip_on_failure to repository_scripts and skip_on_hook_failure to repositories.

When enabled, a pre-backup script that exits non-zero causes the backup to be
marked "skipped" (not "failed") — used for intentional graceful skip signals
such as leader-election checks.
"""
from sqlalchemy import text


def upgrade(db):
    rs_cols = [row[1] for row in db.execute(text("PRAGMA table_info(repository_scripts)")).fetchall()]
    if "skip_on_failure" not in rs_cols:
        db.execute(text(
            "ALTER TABLE repository_scripts ADD COLUMN skip_on_failure BOOLEAN NOT NULL DEFAULT 0"
        ))
        print("✓ Added skip_on_failure column to repository_scripts")
    else:
        print("✓ skip_on_failure column already exists in repository_scripts — skipping")

    repo_cols = [row[1] for row in db.execute(text("PRAGMA table_info(repositories)")).fetchall()]
    if "skip_on_hook_failure" not in repo_cols:
        db.execute(text(
            "ALTER TABLE repositories ADD COLUMN skip_on_hook_failure BOOLEAN NOT NULL DEFAULT 0"
        ))
        print("✓ Added skip_on_hook_failure column to repositories")
    else:
        print("✓ skip_on_hook_failure column already exists in repositories — skipping")

    db.commit()
