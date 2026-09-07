"""encrypt repository passphrase

Encrypts every existing plaintext ``repositories.passphrase`` value in place
so it matches the new ``EncryptedString`` column type in
app.database.models.Repository. Purely a data transform: the column stays a
plain String, so no schema change is needed, and the ORM's encrypt-on-write /
decrypt-on-read now applies to every row going forward.

Idempotent: a value that already decrypts successfully is assumed to already
be encrypted and is left untouched, so re-running this migration (or running
it against a database seeded after the model change already shipped) is
safe.

Revision ID: 7de0064b0d99
Revises: e4f5a6b7c8d9
Create Date: 2026-09-05 11:54:02.514854

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.security import decrypt_secret, encrypt_secret


# revision identifiers, used by Alembic.
revision: str = "7de0064b0d99"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_already_encrypted(value: str) -> bool:
    try:
        decrypt_secret(value)
        return True
    except Exception:
        return False


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, passphrase FROM repositories WHERE passphrase IS NOT NULL")
    ).fetchall()

    migrated = 0
    for row_id, passphrase in rows:
        if not passphrase or _is_already_encrypted(passphrase):
            continue
        connection.execute(
            sa.text("UPDATE repositories SET passphrase = :value WHERE id = :id"),
            {"value": encrypt_secret(passphrase), "id": row_id},
        )
        migrated += 1

    print(f"✓ Encrypted {migrated} repository passphrase(s)")


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, passphrase FROM repositories WHERE passphrase IS NOT NULL")
    ).fetchall()

    reverted = 0
    for row_id, passphrase in rows:
        if not passphrase or not _is_already_encrypted(passphrase):
            continue
        connection.execute(
            sa.text("UPDATE repositories SET passphrase = :value WHERE id = :id"),
            {"value": decrypt_secret(passphrase), "id": row_id},
        )
        reverted += 1

    print(f"✓ Decrypted {reverted} repository passphrase(s)")
