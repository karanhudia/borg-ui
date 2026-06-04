"""Add OIDC linking state and token endpoint auth method settings."""

from sqlalchemy import text


def _column_names(db, table_name: str) -> set[str]:
    result = db.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


def upgrade(db):
    settings_columns = _column_names(db, "system_settings")
    if "oidc_token_auth_method" not in settings_columns:
        db.execute(
            text(
                "ALTER TABLE system_settings ADD COLUMN oidc_token_auth_method VARCHAR DEFAULT 'client_secret_post' NOT NULL"
            )
        )

    state_columns = _column_names(db, "oidc_login_states")
    if "flow" not in state_columns:
        db.execute(
            text(
                "ALTER TABLE oidc_login_states ADD COLUMN flow VARCHAR DEFAULT 'login' NOT NULL"
            )
        )
    if "user_id" not in state_columns:
        db.execute(text("ALTER TABLE oidc_login_states ADD COLUMN user_id INTEGER"))

    db.execute(
        text(
            "UPDATE system_settings SET oidc_token_auth_method = 'client_secret_post' WHERE oidc_token_auth_method IS NULL OR oidc_token_auth_method = ''"
        )
    )
    db.execute(
        text(
            "UPDATE oidc_login_states SET flow = 'login' WHERE flow IS NULL OR flow = ''"
        )
    )
    db.commit()


def downgrade(db):
    db.commit()
