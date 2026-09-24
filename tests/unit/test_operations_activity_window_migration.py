"""Tests for revision 5c7267e7aa2c (the Activity window index, #1120).

The Activity list orders operations by coalesce(started_at, created_at) and
pages on it. These tests pin that the revision and the model build the same
index and that the route's own window query is answered from it instead of
a scan and sort. The PostgreSQL plan test is skipped unless
BORG_TEST_POSTGRES_URL is set.
"""

import os
from datetime import datetime, timedelta

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import event, func, text
from sqlalchemy.orm import Session

from app.database.db_upgrade import _alembic_config, _engine
from app.database.models import Operation

REVISION = "5c7267e7aa2c"
PREVIOUS = "d4e5f6a7b8c9"
INDEX = "ix_operations_activity_window"

POSTGRES_URL = os.getenv("BORG_TEST_POSTGRES_URL")
requires_postgres = pytest.mark.skipif(
    not POSTGRES_URL, reason="BORG_TEST_POSTGRES_URL is not set"
)


def _migrate(url, target, *, down=False):
    engine = _engine(url)
    config = _alembic_config(url)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if down else command.upgrade)(config, target)
        connection.commit()
    engine.dispose()


def _index_sql(url):
    """The index's definition as the database stores it, or None."""
    engine = _engine(url)
    try:
        with engine.connect() as conn:
            if engine.dialect.name == "sqlite":
                query = "SELECT sql FROM sqlite_master WHERE name = :name"
            else:
                query = "SELECT indexdef FROM pg_indexes WHERE indexname = :name"
            return conn.execute(text(query), {"name": INDEX}).scalar()
    finally:
        engine.dispose()


def _window_query(session, before=None):
    """The window query of `_operation_activity_items` with its default
    filter: index rows other than follow-ups are left out."""
    started = func.coalesce(Operation.started_at, Operation.created_at)
    query = session.query(Operation).filter(
        ~((Operation.category == "index") & (Operation.trigger != "followup"))
    )
    if before is not None:
        query = query.filter(started < before)
    return query.order_by(started.desc(), Operation.id.desc()).limit(200)


@pytest.mark.unit
def test_upgrade_adds_and_downgrade_drops_the_index(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    assert _index_sql(url) is None

    _migrate(url, REVISION)
    assert "coalesce(started_at, created_at) DESC, id DESC" in _index_sql(url)

    _migrate(url, PREVIOUS, down=True)
    assert _index_sql(url) is None


@pytest.mark.unit
def test_revision_follows_the_previous_head():
    script = ScriptDirectory.from_config(_alembic_config("sqlite://"))
    assert script.get_revision(REVISION).down_revision == PREVIOUS
    heads = script.get_heads()
    assert len(heads) == 1
    assert REVISION in {r.revision for r in script.iterate_revisions(heads[0], "base")}


@pytest.mark.unit
def test_migration_and_model_build_the_same_index(tmp_path):
    """The model declares the index (so autogenerate keeps it) with the same
    definition the revision creates."""
    from app.database.database import Base
    import app.database.models  # noqa: F401 - registers the tables on Base

    migrated = f"sqlite:///{tmp_path / 'migrated.db'}"
    _migrate(migrated, "head")
    created = f"sqlite:///{tmp_path / 'created.db'}"
    engine = _engine(created)
    Base.metadata.create_all(engine)
    engine.dispose()

    assert _index_sql(migrated) == _index_sql(created)


def _statements_of(engine, request):
    """`(statement, parameters)` of every query `request()` runs on `engine`."""
    seen = []

    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = request()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 200
    return seen


@pytest.mark.unit
@pytest.mark.parametrize("page", ["first", "before"])
def test_the_routes_window_query_reads_the_index(
    test_client, test_db, admin_headers, page
):
    """The query the route really sends (first page and a `before` page) is
    answered by walking the index, not by scanning and sorting operations."""
    start = datetime(2026, 9, 1)
    for i in range(30):
        test_db.add(
            Operation(
                kind="backup",
                category="backup",
                status="completed",
                trigger="plan",
                run_id=f"run-{i}",
                started_at=start + timedelta(minutes=i),
            )
        )
    test_db.commit()
    url = "/api/activity/recent?limit=50"
    if page == "before":
        url += "&before=2026-09-01T00:20:00"

    engine = test_db.get_bind()
    seen = _statements_of(engine, lambda: test_client.get(url, headers=admin_headers))
    window = [
        (statement, parameters)
        for statement, parameters in seen
        if "FROM operations" in statement
        and "ORDER BY coalesce(operations.started_at, operations.created_at) DESC"
        in statement
    ]
    assert window, "the window query was not issued"

    for statement, parameters in window:
        with engine.connect() as conn:
            plan = " / ".join(
                row[3]
                for row in conn.exec_driver_sql(
                    "EXPLAIN QUERY PLAN " + statement, parameters
                )
            )
        assert INDEX in plan
        assert "TEMP B-TREE" not in plan


def _reset_postgres():
    engine = _engine(POSTGRES_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.mark.unit
@requires_postgres
def test_postgres_orders_the_window_from_the_index():
    """On PostgreSQL the ordering (and the `before` bound) come from the
    index. Sorting is priced out so the plan does not depend on the table's
    size: with the index the plan walks it and has no Sort node; without it
    the planner would still have to sort."""
    _reset_postgres()
    _migrate(POSTGRES_URL, "head")
    assert "COALESCE(started_at, created_at) DESC, id DESC" in _index_sql(POSTGRES_URL)

    engine = _engine(POSTGRES_URL)
    try:
        with Session(engine) as session:
            session.execute(text("SET LOCAL enable_sort = off"))
            for before in (None, datetime(2026, 9, 1)):
                statement = _window_query(session, before).statement.compile(engine)
                plan = "\n".join(
                    row[0]
                    for row in session.connection().exec_driver_sql(
                        "EXPLAIN " + str(statement), statement.params
                    )
                )
                assert f"Index Scan using {INDEX}" in plan
                assert "Sort" not in plan
    finally:
        engine.dispose()
