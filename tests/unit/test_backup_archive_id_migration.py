"""Tests for revision b7d2e9f4a1c3 (operation_backup_details.archive_id)."""

import pytest
from alembic import command
from sqlalchemy import inspect

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "b7d2e9f4a1c3"
PREVIOUS = "a4c8e2f6b1d9"


def _migrate(url, target, *, down=False):
    engine = _engine(url)
    config = _alembic_config(url)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if down else command.upgrade)(config, target)
        connection.commit()
    engine.dispose()


def _columns(url):
    engine = _engine(url)
    try:
        return {
            c["name"] for c in inspect(engine).get_columns("operation_backup_details")
        }
    finally:
        engine.dispose()


@pytest.mark.unit
def test_upgrade_adds_and_downgrade_drops_the_column(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    assert "archive_id" not in _columns(url)

    _migrate(url, REVISION)
    assert "archive_id" in _columns(url)

    _migrate(url, PREVIOUS, down=True)
    assert "archive_id" not in _columns(url)


@pytest.mark.unit
def test_revision_chains_on_the_previous_head_and_leaves_one_head():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config("sqlite://"))
    assert script.get_revision(REVISION).down_revision == PREVIOUS
    assert script.get_heads() == [REVISION]
