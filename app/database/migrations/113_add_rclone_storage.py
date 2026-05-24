"""Add rclone-backed repository storage tables."""

from sqlalchemy import text


def _table_exists(db, table_name: str) -> bool:
    result = db.execute(
        text(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = :table_name"
        ),
        {"table_name": table_name},
    )
    return result.first() is not None


def upgrade(db):
    if not _table_exists(db, "rclone_remotes"):
        db.execute(
            text(
                """
                CREATE TABLE rclone_remotes (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR NOT NULL UNIQUE,
                    provider VARCHAR NOT NULL,
                    config_source VARCHAR NOT NULL DEFAULT 'managed',
                    config_path VARCHAR,
                    redacted_config JSON,
                    last_tested_at DATETIME,
                    last_test_status VARCHAR NOT NULL DEFAULT 'unknown',
                    last_error TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        db.execute(text("CREATE INDEX ix_rclone_remotes_id ON rclone_remotes (id)"))
        db.execute(text("CREATE INDEX ix_rclone_remotes_name ON rclone_remotes (name)"))

    if not _table_exists(db, "repository_storage"):
        db.execute(
            text(
                """
                CREATE TABLE repository_storage (
                    id INTEGER PRIMARY KEY,
                    repository_id INTEGER NOT NULL UNIQUE,
                    backend VARCHAR NOT NULL DEFAULT 'local',
                    rclone_remote_id INTEGER,
                    rclone_remote_path VARCHAR,
                    cache_path VARCHAR,
                    sync_policy VARCHAR NOT NULL DEFAULT 'after_success',
                    sync_direction VARCHAR NOT NULL DEFAULT 'cache_to_remote',
                    sync_status VARCHAR NOT NULL DEFAULT 'pending',
                    last_synced_at DATETIME,
                    last_hydrated_at DATETIME,
                    last_remote_check_at DATETIME,
                    last_sync_error TEXT,
                    extra_flags JSON,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY(repository_id) REFERENCES repositories(id) ON DELETE CASCADE,
                    FOREIGN KEY(rclone_remote_id) REFERENCES rclone_remotes(id) ON DELETE SET NULL
                )
                """
            )
        )
        db.execute(
            text("CREATE INDEX ix_repository_storage_id ON repository_storage (id)")
        )
        db.execute(
            text(
                "CREATE INDEX ix_repository_storage_repository_id "
                "ON repository_storage (repository_id)"
            )
        )

    if not _table_exists(db, "rclone_sync_jobs"):
        db.execute(
            text(
                """
                CREATE TABLE rclone_sync_jobs (
                    id INTEGER PRIMARY KEY,
                    repository_id INTEGER NOT NULL,
                    direction VARCHAR NOT NULL,
                    status VARCHAR NOT NULL DEFAULT 'pending',
                    started_at DATETIME,
                    completed_at DATETIME,
                    bytes_transferred BIGINT,
                    files_transferred INTEGER,
                    log_path VARCHAR,
                    error_text TEXT,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY(repository_id) REFERENCES repositories(id) ON DELETE CASCADE
                )
                """
            )
        )
        db.execute(text("CREATE INDEX ix_rclone_sync_jobs_id ON rclone_sync_jobs (id)"))
        db.execute(
            text(
                "CREATE INDEX ix_rclone_sync_jobs_repository_id "
                "ON rclone_sync_jobs (repository_id)"
            )
        )

    db.commit()


def downgrade(db):
    db.commit()
