"""Allow never-expiring enrollment tokens and soft-deleted agents."""

from sqlalchemy import text


def _columns(db, table_name: str) -> dict[str, object]:
    result = db.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1]: row for row in result.fetchall()}


def _copy_enrollment_tokens_with_nullable_expiry(db) -> None:
    columns = _columns(db, "agent_enrollment_tokens")
    expires_at = columns.get("expires_at")
    if not expires_at or not expires_at[3]:
        return

    db.execute(text("PRAGMA foreign_keys=OFF"))
    db.execute(
        text("""
        CREATE TABLE IF NOT EXISTS agent_enrollment_tokens_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR NOT NULL,
            token_hash VARCHAR NOT NULL,
            token_prefix VARCHAR(20) NOT NULL,
            created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            expires_at DATETIME,
            used_at DATETIME,
            used_by_agent_id INTEGER REFERENCES agent_machines(id) ON DELETE SET NULL,
            revoked_at DATETIME,
            created_at DATETIME NOT NULL
        )
        """)
    )
    db.execute(
        text("""
        INSERT INTO agent_enrollment_tokens_new (
            id, name, token_hash, token_prefix, created_by_user_id, expires_at,
            used_at, used_by_agent_id, revoked_at, created_at
        )
        SELECT
            id, name, token_hash, token_prefix, created_by_user_id, expires_at,
            used_at, used_by_agent_id, revoked_at, created_at
        FROM agent_enrollment_tokens
        """)
    )
    db.execute(text("DROP TABLE agent_enrollment_tokens"))
    db.execute(
        text(
            "ALTER TABLE agent_enrollment_tokens_new RENAME TO agent_enrollment_tokens"
        )
    )
    db.execute(text("PRAGMA foreign_keys=ON"))


def upgrade(db):
    if "deleted_at" not in _columns(db, "agent_machines"):
        db.execute(text("ALTER TABLE agent_machines ADD COLUMN deleted_at DATETIME"))

    _copy_enrollment_tokens_with_nullable_expiry(db)
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_agent_enrollment_tokens_token_prefix "
            "ON agent_enrollment_tokens(token_prefix)"
        )
    )
    db.commit()


def downgrade(db):
    db.commit()
