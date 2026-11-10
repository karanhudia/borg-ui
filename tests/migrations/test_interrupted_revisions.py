"""No revision can leave a SQLite database that will not boot.

Up to 2.4.8 SQLite DDL was committed statement by statement, so a boot that
died inside a revision kept part of it without the version bump and every
later boot failed on what was already there: a different revision, and a
different error, for each install it happened to (dashboard ceb689cdb82a467c,
e9d33421b6cb1d9b, 845116f75ba79586). Two properties close that for every
revision, including ones not written yet:

- a revision now runs in one real transaction, so dying inside it leaves
  nothing behind;
- a database an older release already left half-way through any revision,
  after any statement, is finished on the next boot.
"""

import shutil

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, text

from app.database.database import Base
from app.database.db_upgrade import (
    _alembic_config,
    _engine,
    _sqlite_url,
    _upgrade_to,
    alembic_init,
)

SCRIPT = ScriptDirectory.from_config(_alembic_config("sqlite://"))
# The baseline is left out: a database with tables and no recorded revision
# is refused before any DDL (test_interrupted_baseline_refuses_to_modify_durable_tables).
REVISIONS = [r for r in SCRIPT.walk_revisions() if r.down_revision is not None]


class _Killed(BaseException):
    """Not an Exception: nothing on the way out may clean up, as with a kill."""


def _schema(db) -> list[tuple]:
    engine = create_engine(_sqlite_url(db))
    try:
        with engine.connect() as conn:
            names = conn.execute(
                text(
                    "SELECT type, name FROM sqlite_master "
                    "WHERE name NOT LIKE 'sqlite_%' ORDER BY 1, 2"
                )
            ).all()
            columns = [
                (table, row[1])
                for kind, table in names
                if kind == "table"
                for row in conn.exec_driver_sql(f'PRAGMA table_info("{table}")')
            ]
            # Rows too: a revision that backfills must leave the same values
            # whether it ran once or was finished after an interruption.
            rows = [
                (table, repr(tuple(row)))
                for kind, table in names
                if kind == "table" and table != "alembic_version"
                for row in conn.exec_driver_sql(f'SELECT * FROM "{table}"')
            ]
        return [tuple(n) for n in names] + sorted(columns) + sorted(rows)
    finally:
        engine.dispose()


def _seed_rows_a_backfill_reads(db) -> None:
    """Settings rows in both states the paused-stages backfill (c3d4e5f6a7b8)
    tells apart, so the row comparison has values that can come out wrong."""
    engine = create_engine(_sqlite_url(db))
    try:
        with engine.begin() as conn:
            info = conn.exec_driver_sql("PRAGMA table_info(system_settings)").all()
            if "background_paused" not in {column[1] for column in info}:
                return
            # whatever else this revision's schema requires, by its type
            required = {
                name: "" if "CHAR" in kind.upper() or "TEXT" in kind.upper() else 0
                for _, name, kind, notnull, default, pk in info
                if notnull and default is None and not pk
            }
            for row_id, paused in ((1, 1), (2, 0)):
                row = {**required, "id": row_id, "background_paused": paused}
                conn.execute(
                    text(
                        f"INSERT INTO system_settings ({', '.join(row)}) "
                        f"VALUES ({', '.join(':' + name for name in row)})"
                    ),
                    row,
                )
    finally:
        engine.dispose()


def _run_as_an_older_release_until_killed(db, revision: str, kill_after: int) -> bool:
    """Apply `revision` with the driver's own transaction handling, dying
    after its Nth statement. False once the revision has fewer statements."""
    engine = create_engine(_sqlite_url(db))
    seen = 0

    def count(conn, cursor, statement, parameters, context, executemany):
        nonlocal seen
        if statement.lstrip().upper().startswith(("PRAGMA", "SELECT")):
            return
        seen += 1
        if seen == kill_after:
            raise _Killed()

    event.listen(engine, "after_cursor_execute", count)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            context = MigrationContext.configure(
                conn,
                opts={
                    "render_as_batch": True,
                    "target_metadata": Base.metadata,
                    "fn": lambda rev, _ctx: SCRIPT._upgrade_revs(revision, rev),
                },
            )
            with Operations.context(context):
                context.run_migrations()
        return False
    except BaseException:
        if seen < kill_after:
            raise
        return True
    finally:
        engine.dispose()


@pytest.mark.unit
def test_a_revision_that_dies_part_way_leaves_nothing_behind(tmp_path):
    db = tmp_path / "borg.db"
    url = _sqlite_url(db)
    _upgrade_to(url, "b9d2c5e7f1a4")
    before = _schema(db)

    engine = _engine(url)

    def die(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("CREATE INDEX ix_operations_kind"):
            raise RuntimeError("disk I/O error")

    event.listen(engine, "after_cursor_execute", die)
    with pytest.raises(RuntimeError, match="disk I/O error"):
        _upgrade_to(url, "head", engine)
    engine.dispose()

    # `operations` was created before the failure and is gone with it
    assert _schema(db) == before
    assert alembic_init(db).action == "migrated"
    assert alembic_init(db).action == "skipped"


@pytest.mark.unit
@pytest.mark.parametrize("revision", REVISIONS, ids=lambda r: r.revision)
def test_a_revision_an_older_release_left_half_applied_is_finished(tmp_path, revision):
    parents = revision.down_revision
    parents = parents if isinstance(parents, tuple) else (parents,)
    before = tmp_path / "before.db"
    for parent in parents:
        _upgrade_to(_sqlite_url(before), parent)
    _seed_rows_a_backfill_reads(before)
    clean = tmp_path / "clean.db"
    shutil.copy(before, clean)
    _upgrade_to(_sqlite_url(clean), revision.revision)
    expected = _schema(clean)

    kill_after = 1
    while True:
        db = tmp_path / "borg.db"
        shutil.copy(before, db)
        if not _run_as_an_older_release_until_killed(db, revision.revision, kill_after):
            break
        _upgrade_to(_sqlite_url(db), revision.revision)
        assert _schema(db) == expected, f"killed after statement {kill_after}"
        kill_after += 1
