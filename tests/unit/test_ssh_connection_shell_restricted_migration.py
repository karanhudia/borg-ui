"""Tests for revision c9d0e1f2a3b4 (ssh_connections.shell_restricted)."""

from alembic import command
import pytest
from sqlalchemy import inspect

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "c9d0e1f2a3b4"
PREVIOUS = "b8c9d0e1f2a3"


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
        return {c["name"] for c in inspect(engine).get_columns("ssh_connections")}
    finally:
        engine.dispose()


@pytest.mark.unit
def test_upgrade_adds_and_downgrade_drops_the_column(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    assert "shell_restricted" not in _columns(url)

    _migrate(url, REVISION)
    assert "shell_restricted" in _columns(url)

    _migrate(url, PREVIOUS, down=True)
    assert "shell_restricted" not in _columns(url)
