"""Add persistent auth rate limiting buckets."""

from sqlalchemy import text


def _table_exists(db, table_name: str) -> bool:
    result = db.execute(
        text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = :table_name"
        ),
        {"table_name": table_name},
    )
    return result.first() is not None


def upgrade(db):
    if _table_exists(db, "auth_rate_limit_buckets"):
        db.commit()
        return

    db.execute(
        text(
            """
            CREATE TABLE auth_rate_limit_buckets (
                id INTEGER PRIMARY KEY,
                bucket_key VARCHAR NOT NULL UNIQUE,
                scope VARCHAR NOT NULL,
                subject VARCHAR NOT NULL,
                client_ip VARCHAR NOT NULL,
                failure_count INTEGER NOT NULL DEFAULT 0,
                window_started_at DATETIME NOT NULL,
                last_attempt_at DATETIME NOT NULL,
                locked_until DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
    )
    db.execute(
        text(
            "CREATE INDEX ix_auth_rate_limit_buckets_bucket_key ON auth_rate_limit_buckets (bucket_key)"
        )
    )
    db.execute(
        text(
            "CREATE INDEX ix_auth_rate_limit_buckets_scope ON auth_rate_limit_buckets (scope)"
        )
    )
    db.execute(
        text(
            "CREATE INDEX ix_auth_rate_limit_buckets_client_ip ON auth_rate_limit_buckets (client_ip)"
        )
    )
    db.commit()


def downgrade(db):
    db.commit()
