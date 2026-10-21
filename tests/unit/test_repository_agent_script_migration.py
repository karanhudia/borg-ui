"""Tests for revision c4e532c20d7b (repository_scripts.agent_script_name).

The PostgreSQL runs are skipped unless BORG_TEST_POSTGRES_URL is set."""

import os
from datetime import datetime

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy import inspect, text

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "c4e532c20d7b"
PREVIOUS = "c8e1f4a7b2d9"
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


def _insert(url, table_name, **values):
    """One row with `values`; the other NOT NULL columns without a default
    get a zero value of their type, which the tests never read."""
    engine = _engine(url)
    try:
        columns = inspect(engine).get_columns(table_name)
        filler = {
            sa.Boolean: False,
            sa.Integer: 0,
            sa.String: "",
            sa.Float: 0.0,
            sa.DateTime: datetime(2026, 10, 8),
        }
        for info in columns:
            if info["nullable"] or info["default"] is not None:
                continue
            if info["name"] in values or info["name"] == "id":
                continue
            values[info["name"]] = next(
                zero for kind, zero in filler.items() if isinstance(info["type"], kind)
            )
        table = sa.table(
            table_name,
            *(
                sa.column(info["name"], info["type"])
                for info in columns
                if info["name"] in values
            ),
        )
        with engine.begin() as connection:
            return connection.execute(
                sa.insert(table).values(**values).returning(sa.column("id"))
            ).scalar_one()
    finally:
        engine.dispose()


def _rows(url):
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            return [
                dict(row._mapping)
                for row in connection.execute(
                    text("SELECT * FROM repository_scripts ORDER BY id")
                )
            ]
    finally:
        engine.dispose()


def _schema(url):
    engine = _engine(url)
    try:
        inspector = inspect(engine)
        columns = {
            c["name"]: c["nullable"]
            for c in inspector.get_columns("repository_scripts")
        }
        indexes = {i["name"] for i in inspector.get_indexes("repository_scripts")}
        return columns, indexes
    finally:
        engine.dispose()


def _seed(url):
    repository_id = _insert(url, "repositories", name="nas", path="/repos/nas")
    script_id = _insert(url, "scripts", name="stop-db", file_path="library/stop-db.sh")
    hook_id = _insert(
        url,
        "repository_scripts",
        repository_id=repository_id,
        script_id=script_id,
        hook_type="pre-backup",
        execution_order=2.5,
        custom_timeout=900,
    )
    return repository_id, script_id, hook_id


@pytest.mark.unit
def test_upgrade_keeps_the_hooks_and_lets_a_hook_name_an_agent_script(url):
    _migrate(url, PREVIOUS)
    repository_id, script_id, hook_id = _seed(url)
    before = _rows(url)
    _, indexes_before = _schema(url)

    _migrate(url, REVISION)

    columns, indexes = _schema(url)
    assert columns["agent_script_name"] is True
    assert columns["script_id"] is True
    assert indexes == indexes_before
    [row] = _rows(url)
    assert {k: v for k, v in row.items() if k != "agent_script_name"} == before[0]
    assert row["agent_script_name"] is None
    agent_hook = _insert(
        url,
        "repository_scripts",
        repository_id=repository_id,
        agent_script_name="backup-postgres",
        hook_type="post-backup",
    )
    assert agent_hook > hook_id


@pytest.mark.unit
def test_the_sqlite_rebuild_keeps_autoincrement(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, REVISION)
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            sql = connection.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'repository_scripts'"
                )
            ).scalar_one()
    finally:
        engine.dispose()
    assert "AUTOINCREMENT" in sql


@pytest.mark.unit
def test_downgrade_drops_the_agent_hooks_and_keeps_the_library_ones(url):
    _migrate(url, PREVIOUS)
    repository_id, script_id, hook_id = _seed(url)
    _migrate(url, REVISION)
    _insert(
        url,
        "repository_scripts",
        repository_id=repository_id,
        agent_script_name="backup-postgres",
        hook_type="pre-backup",
    )

    _migrate(url, PREVIOUS, down=True)

    columns, _ = _schema(url)
    assert "agent_script_name" not in columns
    assert columns["script_id"] is False
    assert [(r["id"], r["script_id"]) for r in _rows(url)] == [(hook_id, script_id)]


@pytest.mark.unit
def test_revision_chains_on_the_previous_head_and_leaves_one_head():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config("sqlite://"))
    assert script.get_revision(REVISION).down_revision == PREVIOUS
    assert script.get_heads() == [REVISION]
