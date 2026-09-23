"""Tests for revision c3d4e5f6a7b8 (system_settings.paused_stages).

The JSON value has to bind and read as JSON on PostgreSQL too, where a text
parameter for a json column is refused; those runs are skipped unless
BORG_TEST_POSTGRES_URL is set."""

import json
import os

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy import inspect, text

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "c3d4e5f6a7b8"
PREVIOUS = "b2c3d4e5f6a7"
ALL = ["archives", "retention", "history", "stats"]
POSTGRES_URL = os.getenv("BORG_TEST_POSTGRES_URL")


@pytest.fixture(params=["sqlite", "postgres"])
def url(request, tmp_path):
    if request.param == "sqlite":
        return f"sqlite:///{tmp_path / 'borg.db'}"
    if not POSTGRES_URL:
        pytest.skip("BORG_TEST_POSTGRES_URL is not set")
    engine = _engine(POSTGRES_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    return POSTGRES_URL


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
        return inspect(engine).get_columns("system_settings")
    finally:
        engine.dispose()


def _seed(url, column, value):
    """One settings row with `column` set. The other NOT NULL columns
    without a server default get a zero value of their type, which the
    tests never read."""
    filler = {sa.Boolean: False, sa.Integer: 0, sa.String: "", sa.Float: 0.0}
    values = {"id": 1, column: value}
    for info in _columns(url):
        if info["nullable"] or info["default"] is not None or info["name"] in values:
            continue
        values[info["name"]] = next(
            zero for kind, zero in filler.items() if isinstance(info["type"], kind)
        )
    kinds = {info["name"]: info["type"] for info in _columns(url)}
    kinds["paused_stages"] = sa.JSON()
    table = sa.table(
        "system_settings", *(sa.column(name, kinds[name]) for name in values)
    )
    engine = _engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(sa.delete(table))
            connection.execute(sa.insert(table).values(**values))
    finally:
        engine.dispose()


def _read(url, column, kind):
    table = sa.table("system_settings", sa.column(column, kind))
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            return connection.execute(sa.select(table.c[column])).scalar_one()
    finally:
        engine.dispose()


@pytest.mark.unit
@pytest.mark.parametrize("paused,expected", [(True, ALL), (False, [])])
def test_upgrade_carries_the_global_pause_over(url, paused, expected):
    _migrate(url, PREVIOUS)
    _seed(url, "background_paused", paused)
    _migrate(url, REVISION)
    assert "background_paused" not in {c["name"] for c in _columns(url)}
    stored = _read(url, "paused_stages", sa.JSON())
    assert (json.loads(stored) if isinstance(stored, str) else stored) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "stages,expected", [(ALL, True), (["history"], False), ([], False)]
)
def test_downgrade_is_paused_only_when_every_stage_was(url, stages, expected):
    _migrate(url, REVISION)
    _seed(url, "paused_stages", stages)
    _migrate(url, PREVIOUS, down=True)
    assert "paused_stages" not in {c["name"] for c in _columns(url)}
    assert bool(_read(url, "background_paused", sa.Boolean())) is expected
