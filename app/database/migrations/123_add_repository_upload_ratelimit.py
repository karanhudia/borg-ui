"""Add repository default upload rate limits."""

from sqlalchemy import inspect, text


def _bind(db):
    return db.get_bind() if hasattr(db, "get_bind") else db


def _columns(db, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(_bind(db)).get_columns(table_name)}


def upgrade(db):
    if "upload_ratelimit_kib" not in _columns(db, "repositories"):
        db.execute(
            text("ALTER TABLE repositories ADD COLUMN upload_ratelimit_kib INTEGER")
        )
    db.commit()


def downgrade(db):
    if "upload_ratelimit_kib" not in _columns(db, "repositories"):
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
                "repositories.upload_ratelimit_kib was not removed"
            )
    db.execute(text("ALTER TABLE repositories DROP COLUMN upload_ratelimit_kib"))
    db.commit()
