"""Add backup plan upload rate limit schedule policies."""

from sqlalchemy import inspect, text


def _bind(db):
    return db.get_bind() if hasattr(db, "get_bind") else db


def _columns(db, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(_bind(db)).get_columns(table_name)}


def upgrade(db):
    if "upload_ratelimit_schedule_policies" not in _columns(db, "backup_plans"):
        db.execute(
            text(
                "ALTER TABLE backup_plans "
                "ADD COLUMN upload_ratelimit_schedule_policies TEXT"
            )
        )
    db.commit()


def downgrade(db):
    if "upload_ratelimit_schedule_policies" not in _columns(db, "backup_plans"):
        return
    if _bind(db).dialect.name == "sqlite":
        version = db.execute(text("SELECT sqlite_version()")).scalar() or "0.0.0"
        supports_drop = tuple(int(part) for part in version.split(".")[:3]) >= (
            3,
            35,
            0,
        )
        if not supports_drop:
            raise RuntimeError(
                "SQLite does not support DROP COLUMN; "
                "backup_plans.upload_ratelimit_schedule_policies was not removed"
            )
    db.execute(
        text("ALTER TABLE backup_plans DROP COLUMN upload_ratelimit_schedule_policies")
    )
    db.commit()
