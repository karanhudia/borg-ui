"""Tests for revision c4d5e6f7a8b9 (operations kind/started_at index) and the
merge revision d5e6f7a8b9c0 that joins it with the prune comparisons."""

from alembic import command
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import inspect

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "c4d5e6f7a8b9"
PREVIOUS = "a3b4c5d6e7f8"
SIBLING = "b4c5d6e7f8a9"
MERGE = "d5e6f7a8b9c0"
INDEX = "ix_operations_kind_started_at"


def _migrate(url, target, *, down=False):
    engine = _engine(url)
    config = _alembic_config(url)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if down else command.upgrade)(config, target)
        connection.commit()
    engine.dispose()


def _schema(url):
    engine = _engine(url)
    try:
        inspector = inspect(engine)
        return (
            {index["name"] for index in inspector.get_indexes("operations")},
            set(inspector.get_table_names()),
        )
    finally:
        engine.dispose()


@pytest.mark.unit
def test_upgrade_adds_and_downgrade_drops_the_index(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    assert INDEX not in _schema(url)[0]

    _migrate(url, REVISION)
    assert INDEX in _schema(url)[0]

    _migrate(url, PREVIOUS, down=True)
    assert INDEX not in _schema(url)[0]


@pytest.mark.unit
def test_merge_revision_joins_the_prune_comparisons_branch():
    """c4d5e6f7a8b9 keeps its original parent (installs applied it there);
    d5e6f7a8b9c0 joins it with the prune comparisons so the graph has one
    head."""
    script = ScriptDirectory.from_config(_alembic_config("sqlite://"))
    assert script.get_revision(REVISION).down_revision == PREVIOUS
    assert script.get_revision(SIBLING).down_revision == PREVIOUS
    assert set(script.get_revision(MERGE).down_revision) == {REVISION, SIBLING}
    # one head, with the merge on the way to it (later revisions chain on
    # top of it, so the head itself moves as migrations are added)
    heads = script.get_heads()
    assert len(heads) == 1
    assert MERGE in {r.revision for r in script.iterate_revisions(heads[0], "base")}


@pytest.mark.unit
def test_install_at_the_index_revision_receives_the_prune_comparisons(tmp_path):
    """The state of an install that applied c4d5e6f7a8b9 before the prune
    comparisons existed: upgrading to head creates their table and keeps
    the index."""
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, REVISION)
    indexes, tables = _schema(url)
    assert INDEX in indexes
    assert "prune_comparisons" not in tables

    _migrate(url, "head")
    indexes, tables = _schema(url)
    assert INDEX in indexes
    assert "prune_comparisons" in tables


@pytest.mark.unit
def test_fresh_install_applies_both_branches(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, "head")
    indexes, tables = _schema(url)
    assert INDEX in indexes
    assert "prune_comparisons" in tables
