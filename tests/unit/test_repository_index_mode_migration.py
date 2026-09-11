"""Tests for revision e1f2a3b4c5d6 (repositories.index_mode, spec 6.8)."""

import pytest
from alembic import command
from sqlalchemy import inspect, text

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "e1f2a3b4c5d6"
PREVIOUS = "d0e1f2a3b4c5"


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
        return {c["name"] for c in inspect(engine).get_columns("repositories")}
    finally:
        engine.dispose()


@pytest.mark.unit
def test_upgrade_adds_and_downgrade_drops_the_column(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    assert "index_mode" not in _columns(url)

    _migrate(url, REVISION)
    assert "index_mode" in _columns(url)

    _migrate(url, PREVIOUS, down=True)
    assert "index_mode" not in _columns(url)


@pytest.mark.unit
def test_an_existing_repository_is_backfilled_to_full(tmp_path):
    """A row written before the column reads `full` afterwards, so nothing
    about an existing install changes until someone sets a mode."""
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    engine = _engine(url)
    # The repositories table carries a long tail of NOT NULL columns; build
    # the insert from the schema rather than naming them, so this test does
    # not need editing every time one is added.
    columns = inspect(engine).get_columns("repositories")
    values = {"name": "old", "path": "/tmp/old"}
    for column in columns:
        if column["name"] in values or column["name"] == "id":
            continue
        if column["nullable"] or column["default"] is not None:
            continue
        values[column["name"]] = (
            1 if str(column["type"]).upper().startswith("INT") else "x"
        )
    names = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)
    with engine.connect() as connection:
        connection.execute(
            text(f"INSERT INTO repositories ({names}) VALUES ({placeholders})"), values
        )
        connection.commit()
    engine.dispose()

    _migrate(url, REVISION)

    engine = _engine(url)
    with engine.connect() as connection:
        modes = [
            row[0]
            for row in connection.execute(text("SELECT index_mode FROM repositories"))
        ]
    engine.dispose()
    assert modes == ["full"]


@pytest.mark.unit
def test_revision_chains_on_the_previous_head_and_leaves_one_head():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config("sqlite://"))
    assert script.get_revision(REVISION).down_revision == PREVIOUS
    assert len(script.get_heads()) == 1
