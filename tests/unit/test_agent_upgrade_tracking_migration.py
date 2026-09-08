"""Tests for revision f7a2b8c4d1e5 (agent_machines upgrade tracking columns)."""

import pytest
from alembic import command
from sqlalchemy import inspect

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "f7a2b8c4d1e5"
PREVIOUS = "e5f6a7b8c9d0"
COLUMNS = {
    "desired_agent_version",
    "desired_borg_version",
    "upgrade_state",
    "upgrade_requested_at",
    "upgrade_target_version",
    "upgrade_error",
}


def _migrate(url, target, *, down=False):
    """Apply or revert the database at ``url`` to the requested revision."""
    engine = _engine(url)
    config = _alembic_config(url)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if down else command.upgrade)(config, target)
        connection.commit()
    engine.dispose()


def _columns(url):
    """Return the names of the columns currently on ``agent_machines``."""
    engine = _engine(url)
    try:
        return {c["name"] for c in inspect(engine).get_columns("agent_machines")}
    finally:
        engine.dispose()


@pytest.mark.unit
def test_upgrade_adds_and_downgrade_drops_the_columns(tmp_path):
    """The revision adds every tracking column and removes it on downgrade."""
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    assert not COLUMNS & _columns(url)

    _migrate(url, REVISION)
    assert COLUMNS <= _columns(url)

    _migrate(url, PREVIOUS, down=True)
    assert not COLUMNS & _columns(url)


@pytest.mark.unit
def test_revision_chains_on_the_previous_head_and_leaves_one_head():
    """The new revision extends the existing linear Alembic history."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config("sqlite://"))
    assert script.get_revision(REVISION).down_revision == PREVIOUS
    assert len(script.get_heads()) == 1
