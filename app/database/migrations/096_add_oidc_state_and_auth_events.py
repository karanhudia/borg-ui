"""Add OIDC state tracking and auth audit/event tables."""

from sqlalchemy import text


def _table_exists(db, table_name: str) -> bool:
    result = db.execute(
        text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = :table_name"
        ),
        {"table_name": table_name},
    )
    return result.first() is not None


def _column_names(db, table_name: str) -> set[str]:
    result = db.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


def upgrade(db):
    user_columns = _column_names(db, "users")
    if "auth_source" not in user_columns:
        db.execute(
            text(
                "ALTER TABLE users ADD COLUMN auth_source VARCHAR DEFAULT 'local' NOT NULL"
            )
        )
    if "oidc_subject" not in user_columns:
        db.execute(text("ALTER TABLE users ADD COLUMN oidc_subject VARCHAR"))
    if "oidc_last_id_token_encrypted" not in user_columns:
        db.execute(
            text("ALTER TABLE users ADD COLUMN oidc_last_id_token_encrypted TEXT")
        )

    if not _table_exists(db, "oidc_login_states"):
        db.execute(
            text(
                """
                CREATE TABLE oidc_login_states (
                    id INTEGER PRIMARY KEY,
                    state_id VARCHAR NOT NULL UNIQUE,
                    nonce VARCHAR NOT NULL,
                    code_verifier TEXT NOT NULL,
                    return_to TEXT NOT NULL,
                    used_at DATETIME,
                    expires_at DATETIME NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        db.execute(
            text(
                "CREATE INDEX ix_oidc_login_states_state_id ON oidc_login_states (state_id)"
            )
        )
        db.execute(
            text(
                "CREATE INDEX ix_oidc_login_states_expires_at ON oidc_login_states (expires_at)"
            )
        )

    if not _table_exists(db, "auth_events"):
        db.execute(
            text(
                """
                CREATE TABLE auth_events (
                    id INTEGER PRIMARY KEY,
                    event_type VARCHAR NOT NULL,
                    auth_source VARCHAR NOT NULL,
                    username VARCHAR,
                    email VARCHAR,
                    success BOOLEAN NOT NULL DEFAULT 1,
                    detail TEXT,
                    actor_user_id INTEGER,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY(actor_user_id) REFERENCES users (id)
                )
                """
            )
        )
        db.execute(
            text("CREATE INDEX ix_auth_events_event_type ON auth_events (event_type)")
        )
        db.execute(
            text("CREATE INDEX ix_auth_events_auth_source ON auth_events (auth_source)")
        )
        db.execute(
            text("CREATE INDEX ix_auth_events_username ON auth_events (username)")
        )
        db.execute(text("CREATE INDEX ix_auth_events_success ON auth_events (success)"))
        db.execute(
            text("CREATE INDEX ix_auth_events_created_at ON auth_events (created_at)")
        )

    db.commit()


def downgrade(db):
    db.commit()
