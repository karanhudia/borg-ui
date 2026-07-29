"""Add route strategy tracking to backup jobs."""

from sqlalchemy import text


def _columns(db, table_name: str) -> set[str]:
    result = db.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


def upgrade(db):
    if "route_strategy" not in _columns(db, "backup_jobs"):
        db.execute(text("ALTER TABLE backup_jobs ADD COLUMN route_strategy VARCHAR"))
    db.commit()


def downgrade(db):
    db.commit()
