"""re-encrypt repository passphrases left plaintext by the Alembic transfer

A pre-Alembic database is transferred onto a baseline built up to
PRE_COLLAPSE_REVISION, which already includes 7de0064b0d99. That revision ran
on an empty table, so every transferred passphrase stayed plaintext and the
EncryptedString column failed to read it (issue #1211). Re-running the same
idempotent upgrade after the transfer repairs those rows; already encrypted
values are left untouched.

Revision ID: f2b3c4d5e6a7
Revises: e1a2b3c4d5f6
Create Date: 2026-09-26
"""

import importlib

revision = "f2b3c4d5e6a7"
down_revision = "e1a2b3c4d5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    importlib.import_module(
        "app.database.alembic.versions.7de0064b0d99_encrypt_repository_passphrase"
    ).upgrade()


def downgrade() -> None:
    # Encrypted is the state e1a2b3c4d5f6 expects; nothing to undo.
    pass
