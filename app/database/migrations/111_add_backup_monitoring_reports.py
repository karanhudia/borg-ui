"""Add backup monitoring and report settings."""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


SYSTEM_COLUMNS = {
    "backup_monitoring_enabled": "BOOLEAN NOT NULL DEFAULT 0",
    "backup_monitoring_stale_after_days": "INTEGER NOT NULL DEFAULT 3",
    "backup_monitoring_interval_hours": "INTEGER NOT NULL DEFAULT 24",
    "backup_monitoring_alert_cooldown_hours": "INTEGER NOT NULL DEFAULT 24",
    "backup_monitoring_include_observe_repos": "BOOLEAN NOT NULL DEFAULT 1",
    "backup_monitoring_last_checked_at": "DATETIME",
    "backup_monitoring_last_alert_sent_at": "DATETIME",
    "backup_reports_enabled": "BOOLEAN NOT NULL DEFAULT 0",
    "backup_reports_frequency": "VARCHAR NOT NULL DEFAULT 'weekly'",
    "backup_reports_hour_utc": "INTEGER NOT NULL DEFAULT 8",
    "backup_reports_weekday": "INTEGER NOT NULL DEFAULT 0",
    "backup_reports_monthday": "INTEGER NOT NULL DEFAULT 1",
    "backup_reports_include_summary": "BOOLEAN NOT NULL DEFAULT 1",
    "backup_reports_include_stale_repositories": "BOOLEAN NOT NULL DEFAULT 1",
    "backup_reports_include_recent_activity": "BOOLEAN NOT NULL DEFAULT 1",
    "backup_reports_last_sent_at": "DATETIME",
}

NOTIFICATION_COLUMNS = {
    "notify_on_stale_backup": "BOOLEAN NOT NULL DEFAULT 1",
    "notify_on_backup_report": "BOOLEAN NOT NULL DEFAULT 1",
}


def _add_column_if_missing(db, table_name: str, column_name: str, ddl: str) -> None:
    columns = [row[1] for row in db.execute(text(f"PRAGMA table_info({table_name})"))]
    if column_name not in columns:
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))


def upgrade(db):
    for column_name, ddl in SYSTEM_COLUMNS.items():
        _add_column_if_missing(db, "system_settings", column_name, ddl)

    for column_name, ddl in NOTIFICATION_COLUMNS.items():
        _add_column_if_missing(db, "notification_settings", column_name, ddl)

    db.commit()
    logger.info("Migration 111_add_backup_monitoring_reports completed")


def downgrade(db):
    logger.warning(
        "Downgrade not supported for SQLite; backup monitoring/report columns remain"
    )
    db.commit()
