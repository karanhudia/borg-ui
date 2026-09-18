"""Tests for revision b4c5d6e7f8a9 (prune_comparisons, spec 4.5)."""

import pytest
from alembic import command
from sqlalchemy import inspect

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "b4c5d6e7f8a9"
PREVIOUS = "a3b4c5d6e7f8"


def _migrate(url, target, *, down=False):
    engine = _engine(url)
    config = _alembic_config(url)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if down else command.upgrade)(config, target)
        connection.commit()
    engine.dispose()


def _tables(url):
    engine = _engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


@pytest.mark.unit
def test_upgrade_creates_and_downgrade_drops_the_table(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    assert "prune_comparisons" not in _tables(url)
    _migrate(url, REVISION)
    assert "prune_comparisons" in _tables(url)
    engine = _engine(url)
    columns = {c["name"] for c in inspect(engine).get_columns("prune_comparisons")}
    engine.dispose()
    assert {
        "repository_id",
        "candidate",
        "label",
        "retention",
        "kept_count",
        "deleted_count",
        "freed_at_least",
        "partial_measure",
        "operation_id",
        "archive_count_at",
        "computed_at",
    } <= columns
    _migrate(url, PREVIOUS, down=True)
    assert "prune_comparisons" not in _tables(url)
