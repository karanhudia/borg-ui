"""Add built-in OIDC / SSO settings to system_settings."""

from sqlalchemy import text


OIDC_COLUMNS = {
    "oidc_enabled": "ALTER TABLE system_settings ADD COLUMN oidc_enabled BOOLEAN DEFAULT 0",
    "oidc_disable_local_auth": "ALTER TABLE system_settings ADD COLUMN oidc_disable_local_auth BOOLEAN DEFAULT 0",
    "oidc_provider_name": "ALTER TABLE system_settings ADD COLUMN oidc_provider_name VARCHAR",
    "oidc_discovery_url": "ALTER TABLE system_settings ADD COLUMN oidc_discovery_url VARCHAR",
    "oidc_client_id": "ALTER TABLE system_settings ADD COLUMN oidc_client_id VARCHAR",
    "oidc_client_secret_encrypted": "ALTER TABLE system_settings ADD COLUMN oidc_client_secret_encrypted VARCHAR",
    "oidc_scopes": "ALTER TABLE system_settings ADD COLUMN oidc_scopes VARCHAR DEFAULT 'openid profile email'",
    "oidc_redirect_uri_override": "ALTER TABLE system_settings ADD COLUMN oidc_redirect_uri_override VARCHAR",
    "oidc_end_session_endpoint_override": "ALTER TABLE system_settings ADD COLUMN oidc_end_session_endpoint_override VARCHAR",
    "oidc_claim_username": "ALTER TABLE system_settings ADD COLUMN oidc_claim_username VARCHAR DEFAULT 'preferred_username'",
    "oidc_claim_email": "ALTER TABLE system_settings ADD COLUMN oidc_claim_email VARCHAR DEFAULT 'email'",
    "oidc_claim_full_name": "ALTER TABLE system_settings ADD COLUMN oidc_claim_full_name VARCHAR DEFAULT 'name'",
    "oidc_role_claim": "ALTER TABLE system_settings ADD COLUMN oidc_role_claim VARCHAR",
    "oidc_all_repositories_role_claim": "ALTER TABLE system_settings ADD COLUMN oidc_all_repositories_role_claim VARCHAR",
    "oidc_new_user_mode": "ALTER TABLE system_settings ADD COLUMN oidc_new_user_mode VARCHAR DEFAULT 'viewer'",
    "oidc_new_user_template_username": "ALTER TABLE system_settings ADD COLUMN oidc_new_user_template_username VARCHAR",
    "oidc_default_role": "ALTER TABLE system_settings ADD COLUMN oidc_default_role VARCHAR DEFAULT 'viewer'",
    "oidc_default_all_repositories_role": "ALTER TABLE system_settings ADD COLUMN oidc_default_all_repositories_role VARCHAR DEFAULT 'viewer'",
}


def upgrade(db):
    result = db.execute(text("PRAGMA table_info(system_settings)"))
    existing_columns = {row[1] for row in result.fetchall()}

    for column_name, statement in OIDC_COLUMNS.items():
        if column_name not in existing_columns:
            db.execute(text(statement))

    db.commit()


def downgrade(db):
    # SQLite migrations in this project are additive; leave columns in place.
    db.commit()
