"""restore plan links lost to the foreign-key cascade

Revision ID: c8e1f4a7b2d9
Revises: b7d2e9f4a1c3
Create Date: 2026-10-01

A pre-Alembic database upgraded to 2.3.4 through 2.3.6 lost every row that
cascades from `backup_plans`: the rebuild of that table in a4b5c6d7e8f9 ran
with SQLite foreign keys on, and its DROP TABLE deleted through every ON
DELETE CASCADE (#860). `backup_plan_repositories` and `backup_plan_scripts`
were emptied; `backup_plan_runs` and `script_executions` had their plan set
to NULL. The upgrade keeps the old database next to the new one as the
rollback, and that file still has the rows, so they are read back from it.

Only what is still missing is restored. A plan that has any repository link
or hook again was repaired by hand and is left exactly as it is; a run or
execution that already names a plan is left alone. Without a rollback file,
or on an install that never took the hit, this does nothing.
"""

import logging
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "c8e1f4a7b2d9"
down_revision = "b7d2e9f4a1c3"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

# The children emptied by the cascade, each keyed by the plan they belong to.
# A plan that still has rows in the table was repaired by hand: skipped.
_EMPTIED = ("backup_plan_repositories", "backup_plan_scripts")
# The children whose plan was set to NULL. Restored row by row, by id.
_UNLINKED = ("backup_plan_runs", "script_executions")


def _rollback_path() -> Path | None:
    """The pre-upgrade SQLite file, wherever the upgrade left it.

    SQLite in place: `<name>_bak<ext>` next to the live file. Postgres: the
    source itself, untouched at DATA_DIR/borg.db (see db_upgrade._finalise).
    During the transfer that first creates the rollback the live file is
    still `<name>_new<ext>`, so the lookup misses and this is a no-op; by
    then the cascade is fixed and there is nothing to restore anyway.
    """
    url = op.get_bind().engine.url
    if url.get_backend_name() == "sqlite":
        if not url.database or url.database == ":memory:":
            return None
        live = Path(url.database)
        return live.with_name(f"{live.stem}_bak{live.suffix}")
    from app.config import settings

    return Path(settings.data_dir) / "borg.db"


def _ids(conn, table: str, where: str = "") -> set:
    return {r[0] for r in conn.execute(sa.text(f"SELECT id FROM {table} {where}"))}


def upgrade() -> None:
    rollback = _rollback_path()
    if rollback is None or not rollback.is_file():
        return

    bind = op.get_bind()
    # Read through reflection, as the transfer does: SQLite keeps datetimes as
    # text and only the column type turns them back into what an insert takes.
    old_engine = sa.create_engine(f"sqlite:///file:{rollback}?mode=ro&uri=true")
    try:
        old_meta = sa.MetaData()
        old_meta.reflect(bind=old_engine)
        with old_engine.connect() as old:
            plans = _ids(bind, "backup_plans")

            for name in _EMPTIED:
                source = old_meta.tables.get(name)
                if source is None:
                    continue
                table = sa.Table(name, sa.MetaData(), autoload_with=bind)
                common = [c.name for c in table.columns if c.name in source.columns]
                # Parents the row points at other than the plan; a row whose
                # parent is gone would have been dropped by the transfer too.
                present = {
                    fk.parent.name: _ids(bind, fk.column.table.name)
                    for fk in table.foreign_keys
                    if fk.parent.name != "backup_plan_id" and fk.parent.name in common
                }
                touched = {
                    r[0]
                    for r in bind.execute(
                        sa.text(f"SELECT DISTINCT backup_plan_id FROM {name}")
                    )
                }
                rows = old.execute(
                    source.select().with_only_columns(*[source.c[c] for c in common])
                )
                restore = [
                    dict(zip(common, r))
                    for r in rows
                    if r._mapping["backup_plan_id"] in plans
                    and r._mapping["backup_plan_id"] not in touched
                    and all(
                        r._mapping[col] is None or r._mapping[col] in ids
                        for col, ids in present.items()
                    )
                ]
                if restore:
                    bind.execute(table.insert(), restore)
                    log.info(
                        "%s: restored %d rows from %s", name, len(restore), rollback
                    )

            for name in _UNLINKED:
                source = old_meta.tables.get(name)
                if (
                    source is None
                    or "backup_plan_id" not in source.columns
                    or not inspect(bind).has_table(name)
                ):
                    continue
                unlinked = _ids(bind, name, "WHERE backup_plan_id IS NULL")
                if not unlinked:
                    continue
                fixes = [
                    {"id": r.id, "plan": r.backup_plan_id}
                    for r in old.execute(
                        sa.select(source.c.id, source.c.backup_plan_id).where(
                            source.c.backup_plan_id.is_not(None)
                        )
                    )
                    if r.id in unlinked and r.backup_plan_id in plans
                ]
                if fixes:
                    bind.execute(
                        sa.text(
                            f"UPDATE {name} SET backup_plan_id = :plan WHERE id = :id"
                        ),
                        fixes,
                    )
                    log.info("%s: relinked %d rows to their plan", name, len(fixes))
    finally:
        old_engine.dispose()


def downgrade() -> None:
    # Rows read back from the rollback are indistinguishable from rows the
    # operator added; there is nothing to undo.
    pass
