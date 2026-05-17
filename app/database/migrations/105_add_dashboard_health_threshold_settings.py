"""Add configurable dashboard health threshold settings."""

from sqlalchemy import text


DEFAULT_THRESHOLDS = {
    "dashboard_backup_warning_days": 3,
    "dashboard_backup_critical_days": 7,
    "dashboard_check_warning_days": 7,
    "dashboard_check_critical_days": 30,
    "dashboard_compact_warning_days": 30,
    "dashboard_compact_critical_days": 60,
    "dashboard_restore_check_warning_days": 14,
    "dashboard_restore_check_critical_days": 30,
    "dashboard_observe_freshness_warning_days": 2,
    "dashboard_observe_freshness_critical_days": 7,
}


def upgrade(db):
    result = db.execute(text("PRAGMA table_info(system_settings)"))
    existing_columns = {row[1] for row in result.fetchall()}

    for column_name, default_value in DEFAULT_THRESHOLDS.items():
        if column_name not in existing_columns:
            db.execute(
                text(
                    f"""
                    ALTER TABLE system_settings
                    ADD COLUMN {column_name} INTEGER NOT NULL DEFAULT {default_value}
                    """
                )
            )

    db.commit()


def downgrade(db):
    # SQLite migrations in this project are additive; leave columns in place.
    db.commit()
