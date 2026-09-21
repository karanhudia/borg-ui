"""Tests for revision a7c3e9f1b5d2 (system_settings.last_reconcile_tick_at)."""

import pytest
from alembic import command
from sqlalchemy import inspect

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "a7c3e9f1b5d2"
PREVIOUS = "e7f8a9b0c1d2"


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


@pytest.mark.unit
def test_upgrade_adds_and_downgrade_drops_the_column(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    assert "last_reconcile_tick_at" not in _columns(url)
    _migrate(url, REVISION)
    assert "last_reconcile_tick_at" in _columns(url)
    _migrate(url, PREVIOUS, down=True)
    assert "last_reconcile_tick_at" not in _columns(url)
