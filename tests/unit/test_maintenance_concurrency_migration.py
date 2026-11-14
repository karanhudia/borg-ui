"""Tests for revision d3e8a1c6b2f9 (maintenance concurrency settings)."""

import pytest
from alembic import command
from sqlalchemy import inspect

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "d3e8a1c6b2f9"
PREVIOUS = "f7a4417c5d4d"


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
        return {c["name"] for c in inspect(engine).get_columns("system_settings")}
    finally:
        engine.dispose()


COLUMNS = {"max_concurrent_maintenance", "maintenance_counts_toward_backup_limit"}


@pytest.mark.unit
def test_upgrade_adds_and_downgrade_drops_the_columns(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    assert not COLUMNS & _columns(url)
    _migrate(url, REVISION)
    assert COLUMNS <= _columns(url)
    _migrate(url, PREVIOUS, down=True)
    assert not COLUMNS & _columns(url)
