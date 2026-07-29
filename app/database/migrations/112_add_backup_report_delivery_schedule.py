"""Add explicit cron and timezone settings for backup report delivery."""

from sqlalchemy import text

from app.utils.schedule_time import get_container_timezone


def _add_column_if_missing(db, table_name: str, column_name: str, ddl: str) -> None:
    columns = [row[1] for row in db.execute(text(f"PRAGMA table_info({table_name})"))]
    if column_name not in columns:
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))


def upgrade(db):
    report_timezone = get_container_timezone()
    _add_column_if_missing(
        db,
        "system_settings",
        "backup_reports_cron_expression",
        "VARCHAR NOT NULL DEFAULT '0 8 * * 1'",
    )
    _add_column_if_missing(
        db,
        "system_settings",
        "backup_reports_timezone",
        f"VARCHAR NOT NULL DEFAULT '{report_timezone}'",
    )

    db.execute(
        text(
            """
            UPDATE system_settings
            SET backup_reports_cron_expression = CASE backup_reports_frequency
                WHEN 'daily' THEN
                    '0 ' || COALESCE(backup_reports_hour_utc, 8) || ' * * *'
                WHEN 'monthly' THEN
                    '0 ' || COALESCE(backup_reports_hour_utc, 8) || ' ' ||
                    COALESCE(backup_reports_monthday, 1) || ' * *'
                ELSE
                    '0 ' || COALESCE(backup_reports_hour_utc, 8) || ' * * ' ||
                    ((COALESCE(backup_reports_weekday, 0) + 1) % 7)
            END
            WHERE backup_reports_cron_expression = '0 8 * * 1'
            """
        )
    )

    db.commit()


def downgrade(db):
    db.commit()
