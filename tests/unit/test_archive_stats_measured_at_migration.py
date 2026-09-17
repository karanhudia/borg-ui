"""Tests for revision a3b4c5d6e7f8 (archives.stats_measured_at, spec 4.1)."""

from datetime import datetime

import pytest
from alembic import command
from sqlalchemy import inspect, text

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "a3b4c5d6e7f8"
PREVIOUS = "f2a3b4c5d6e7"


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
        return {c["name"] for c in inspect(engine).get_columns("archives")}
    finally:
        engine.dispose()


def _insert_repository(engine):
    # The repositories table carries a long tail of NOT NULL columns; build
    # the insert from the schema rather than naming them.
    columns = inspect(engine).get_columns("repositories")
    values = {"name": "old", "path": "/tmp/old"}
    for column in columns:
        if column["name"] in values or column["name"] == "id":
            continue
        if column["nullable"] or column["default"] is not None:
            continue
        values[column["name"]] = 0
    names = ", ".join(values)
    binds = ", ".join(f":{name}" for name in values)
    with engine.begin() as conn:
        conn.execute(
            text(f"INSERT INTO repositories ({names}) VALUES ({binds})"), values
        )


@pytest.mark.unit
def test_upgrade_adds_and_downgrade_drops_the_column(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    assert "stats_measured_at" not in _columns(url)
    _migrate(url, REVISION)
    assert "stats_measured_at" in _columns(url)
    _migrate(url, PREVIOUS, down=True)
    assert "stats_measured_at" not in _columns(url)


@pytest.mark.unit
def test_measured_rows_are_backfilled_from_first_seen_at(tmp_path):
    """A row that already carries sizes was measured in the listing run
    that created it, so first_seen_at is the honest date. A row without
    sizes stays NULL and is picked up by the info loop as before."""
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    engine = _engine(url)
    _insert_repository(engine)
    seen = datetime(2026, 9, 1, 2, 0, 0)
    with engine.begin() as conn:
        for borg_id, size in (("sized", 10), ("bare", None)):
            conn.execute(
                text(
                    "INSERT INTO archives (repository_id, borg_id, name, series, "
                    "start, original_size, history_state, history_truncated, "
                    "history_attempts, first_seen_at, last_seen_at) "
                    "VALUES (1, :bid, :bid, 'default', :seen, :size, 'pending', 0, 0, "
                    ":seen, :seen)"
                ),
                {"bid": borg_id, "seen": seen, "size": size},
            )
    engine.dispose()
    _migrate(url, REVISION)
    engine = _engine(url)
    with engine.connect() as conn:
        rows = dict(
            conn.execute(text("SELECT borg_id, stats_measured_at FROM archives")).all()
        )
    engine.dispose()
    assert rows["sized"] is not None and str(rows["sized"]).startswith("2026-09-01")
    assert rows["bare"] is None
