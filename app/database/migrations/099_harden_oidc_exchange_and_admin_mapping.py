"""Harden OIDC exchange flow and admin-role mapping support."""

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


def _index_exists(db, index_name: str) -> bool:
    result = db.execute(
        text(
            "SELECT name FROM sqlite_master WHERE type='index' AND name = :index_name"
        ),
        {"index_name": index_name},
    )
    return result.first() is not None


def upgrade(db):
    settings_columns = _column_names(db, "system_settings")
    if "oidc_group_claim" not in settings_columns:
        db.execute(
            text("ALTER TABLE system_settings ADD COLUMN oidc_group_claim VARCHAR")
        )
    if "oidc_admin_groups" not in settings_columns:
        db.execute(
            text("ALTER TABLE system_settings ADD COLUMN oidc_admin_groups TEXT")
        )

    db.execute(
        text(
            "UPDATE system_settings SET oidc_scopes = 'openid profile email' WHERE oidc_scopes IS NULL"
        )
    )
    db.execute(
        text(
            "UPDATE system_settings SET oidc_claim_username = 'preferred_username' WHERE oidc_claim_username IS NULL"
        )
    )
    db.execute(
        text(
            "UPDATE system_settings SET oidc_claim_email = 'email' WHERE oidc_claim_email IS NULL"
        )
    )
    db.execute(
        text(
            "UPDATE system_settings SET oidc_claim_full_name = 'name' WHERE oidc_claim_full_name IS NULL"
        )
    )
    db.execute(
        text(
            "UPDATE system_settings SET oidc_new_user_mode = 'viewer' WHERE oidc_new_user_mode IS NULL"
        )
    )
    db.execute(
        text(
            "UPDATE system_settings SET oidc_default_role = 'viewer' WHERE oidc_default_role IS NULL"
        )
    )
    db.execute(
        text(
            "UPDATE system_settings SET oidc_default_all_repositories_role = 'viewer' WHERE oidc_default_all_repositories_role IS NULL"
        )
    )

    if not _table_exists(db, "oidc_exchange_grants"):
        db.execute(
            text(
                """
                CREATE TABLE oidc_exchange_grants (
                    id INTEGER PRIMARY KEY,
                    grant_id VARCHAR NOT NULL UNIQUE,
                    username VARCHAR NOT NULL,
                    oidc_subject VARCHAR,
                    email VARCHAR,
                    full_name VARCHAR,
                    groups_json TEXT,
                    role VARCHAR,
                    all_repositories_role VARCHAR,
                    id_token_hint_encrypted TEXT,
                    used_at DATETIME,
                    expires_at DATETIME NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        db.execute(
            text(
                "CREATE INDEX ix_oidc_exchange_grants_grant_id ON oidc_exchange_grants (grant_id)"
            )
        )
        db.execute(
            text(
                "CREATE INDEX ix_oidc_exchange_grants_oidc_subject ON oidc_exchange_grants (oidc_subject)"
            )
        )
        db.execute(
            text(
                "CREATE INDEX ix_oidc_exchange_grants_expires_at ON oidc_exchange_grants (expires_at)"
            )
        )

    exchange_columns = _column_names(db, "oidc_exchange_grants")
    if "groups_json" not in exchange_columns:
        db.execute(text("ALTER TABLE oidc_exchange_grants ADD COLUMN groups_json TEXT"))

    if not _index_exists(db, "ix_users_oidc_subject"):
        db.execute(text("CREATE INDEX ix_users_oidc_subject ON users (oidc_subject)"))

    db.commit()


def downgrade(db):
    db.commit()
