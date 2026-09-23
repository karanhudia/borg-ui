"""Tests for revision c3d4e5f6a7b8 (system_settings.paused_stages)."""

import json

import pytest
from alembic import command
from sqlalchemy import inspect, text

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "c3d4e5f6a7b8"
PREVIOUS = "b2c3d4e5f6a7"
ALL = ["archives", "retention", "history", "stats"]


def _migrate(url, target, *, down=False):
    engine = _engine(url)
    config = _alembic_config(url)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if down else command.upgrade)(config, target)
        connection.commit()
    engine.dispose()


def _run(url, sql):
    engine = _engine(url)
    try:
        with engine.begin() as connection:
            result = connection.execute(text(sql))
            return result.fetchall() if result.returns_rows else None
    finally:
        engine.dispose()


def _columns(url):
    engine = _engine(url)
    try:
        return {c["name"] for c in inspect(engine).get_columns("system_settings")}
    finally:
        engine.dispose()


def _seed(url, column, value):
    """One settings row with `column` set. The other NOT NULL columns
    without a server default get a zero, which the tests never read."""
    required = [
        name
        for _, name, _, notnull, default, pk in _run(
            url, "PRAGMA table_info(system_settings)"
        )
        if notnull and default is None and not pk and name != column
    ]
    columns = ", ".join(["id", column, *required])
    values = ", ".join(["1", str(value), *["0"] * len(required)])
    _run(url, "DELETE FROM system_settings")
    _run(url, f"INSERT INTO system_settings ({columns}) VALUES ({values})")


@pytest.mark.unit
@pytest.mark.parametrize("paused,expected", [(1, ALL), (0, [])])
def test_upgrade_carries_the_global_pause_over(tmp_path, paused, expected):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    _seed(url, "background_paused", paused)
    _migrate(url, REVISION)
    assert "background_paused" not in _columns(url)
    stored = _run(url, "SELECT paused_stages FROM system_settings")[0][0]
    assert json.loads(stored) == expected


@pytest.mark.unit
@pytest.mark.parametrize("stages,expected", [(ALL, 1), (["history"], 0), ([], 0)])
def test_downgrade_is_paused_only_when_every_stage_was(tmp_path, stages, expected):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, REVISION)
    _seed(url, "paused_stages", f"'{json.dumps(stages)}'")
    _migrate(url, PREVIOUS, down=True)
    assert "paused_stages" not in _columns(url)
    assert _run(url, "SELECT background_paused FROM system_settings")[0][0] == expected
