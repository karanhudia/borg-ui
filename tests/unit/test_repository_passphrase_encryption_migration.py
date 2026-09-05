"""Tests for revision 7de0064b0d99 (encrypt repository passphrase at rest)."""

import importlib

from alembic import command
import sqlalchemy as sa
from sqlalchemy import text
import pytest

from app.core.security import encrypt_secret
from app.database.db_upgrade import _alembic_config, _engine
from app.database.models import Repository

_migration_module = importlib.import_module(
    "app.database.alembic.versions.7de0064b0d99_encrypt_repository_passphrase"
)
_is_already_encrypted = _migration_module._is_already_encrypted

REVISION = "7de0064b0d99"
PREVIOUS = "e4f5a6b7c8d9"
PLAINTEXT = "supersecret"


def _migrate(url, target, *, down=False):
    engine = _engine(url)
    config = _alembic_config(url)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if down else command.upgrade)(config, target)
        connection.commit()
    engine.dispose()


def _insert_plaintext_repository(url):
    """Insert a repository row with a plain-String bind for passphrase,
    bypassing the ORM's EncryptedString column type so the row lands exactly
    as a pre-migration database would have stored it: plaintext. Column
    defaults for the other NOT NULL fields still come from Repository's own
    Core table (via insert().values()), so this only overrides passphrase."""
    engine = _engine(url)
    with engine.begin() as connection:
        result = connection.execute(
            Repository.__table__.insert().values(
                name="r",
                path="/srv/r",
                passphrase=sa.bindparam(
                    "passphrase", value=PLAINTEXT, type_=sa.String()
                ),
            )
        )
        row_id = result.inserted_primary_key[0]
    engine.dispose()
    return row_id


def _raw_passphrase(url, row_id):
    engine = _engine(url)
    with engine.connect() as connection:
        value = connection.execute(
            text("SELECT passphrase FROM repositories WHERE id = :id"), {"id": row_id}
        ).scalar()
    engine.dispose()
    return value


@pytest.mark.unit
def test_upgrade_encrypts_existing_plaintext_passphrase(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    row_id = _insert_plaintext_repository(url)

    _migrate(url, REVISION)

    assert _raw_passphrase(url, row_id) != PLAINTEXT


@pytest.mark.unit
def test_downgrade_decrypts_passphrase_back_to_plaintext(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    row_id = _insert_plaintext_repository(url)
    _migrate(url, REVISION)

    _migrate(url, PREVIOUS, down=True)

    assert _raw_passphrase(url, row_id) == PLAINTEXT


@pytest.mark.unit
def test_is_already_encrypted_distinguishes_plaintext_from_ciphertext():
    assert _is_already_encrypted(encrypt_secret(PLAINTEXT)) is True
    assert _is_already_encrypted(PLAINTEXT) is False
