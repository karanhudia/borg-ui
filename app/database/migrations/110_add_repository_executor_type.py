"""Add first-class repository executor type."""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def _column_exists(db, table_name: str, column_name: str) -> bool:
    rows = db.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def upgrade(db):
    if not _column_exists(db, "repositories", "executor_type"):
        db.execute(
            text(
                "ALTER TABLE repositories "
                "ADD COLUMN executor_type VARCHAR NOT NULL DEFAULT 'server'"
            )
        )

    db.execute(
        text(
            "UPDATE repositories "
            "SET executor_type = CASE "
            "WHEN execution_target = 'agent' THEN 'agent' "
            "ELSE 'server' END "
            "WHERE executor_type IS NULL OR executor_type NOT IN ('server', 'agent')"
        )
    )
    db.execute(
        text(
            "UPDATE repositories "
            "SET execution_target = 'agent' "
            "WHERE executor_type = 'agent' AND execution_target != 'agent'"
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_repositories_executor_type "
            "ON repositories(executor_type)"
        )
    )
    db.commit()
    logger.info("Migration 110_add_repository_executor_type completed")


def downgrade(db):
    logger.warning(
        "Downgrade not supported for SQLite - repository executor column will remain"
    )
