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

Restored only where the rollback proves the cascade ran: a run or hook
execution whose plan is NULL here but named in the rollback, with that plan
still present under the same name. An empty plan alone is no proof; an
operator may have emptied it on purpose after a clean upgrade. The plan name
is checked on every id, because SQLite reuses the id of a deleted plan.

Only what is still missing is restored. A plan that has any repository link
or hook again was repaired by hand and is left exactly as it is; rows get
fresh ids, since links added by hand after the cascade reused the old ones.
Without a rollback file, or on an install that never took the hit, this
does nothing.
"""

import logging
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "c8e1f4a7b2d9"
down_revision = "b7d2e9f4a1c3"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

# The children emptied by the cascade, each keyed by the plan they belong to.
# A plan that still has rows in the table was repaired by hand: skipped.
_EMPTIED = ("backup_plan_repositories", "backup_plan_scripts")
# The children whose plan was set to NULL. Restored row by row, by id, and
# the evidence that the cascade ran at all.
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


def _plans(conn, table) -> dict:
    return {r.id: r.name for r in conn.execute(sa.select(table.c.id, table.c.name))}


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
        if "backup_plans" not in old_meta.tables:
            return
        live_meta = sa.MetaData()
        live_meta.reflect(bind=bind)
        with old_engine.connect() as old:
            old_plans = _plans(old, old_meta.tables["backup_plans"])
            live_plans = _plans(bind, live_meta.tables["backup_plans"])
            # The same plan on both sides: same id and same name. An id alone
            # is not enough, SQLite hands a deleted plan's id to the next one.
            same = {
                pid for pid, name in live_plans.items() if old_plans.get(pid) == name
            }

            relink: dict[str, list[dict]] = {}
            for name in _UNLINKED:
                source = old_meta.tables.get(name)
                if (
                    source is None
                    or "backup_plan_id" not in source.columns
                    or name not in live_meta.tables
                ):
                    continue
                unlinked = _ids(bind, name, "WHERE backup_plan_id IS NULL")
                if not unlinked:
                    continue
                relink[name] = [
                    {"id": r.id, "plan": r.backup_plan_id}
                    for r in old.execute(
                        sa.select(source.c.id, source.c.backup_plan_id).where(
                            source.c.backup_plan_id.is_not(None)
                        )
                    )
                    if r.id in unlinked and r.backup_plan_id in same
                ]

            if not any(relink.values()):
                # Nothing lost its plan while the plan stayed: the cascade did
                # not run here. An empty plan is then the operator's doing.
                return

            for name, fixes in relink.items():
                if fixes:
                    bind.execute(
                        sa.text(
                            f"UPDATE {name} SET backup_plan_id = :plan WHERE id = :id"
                        ),
                        fixes,
                    )
                    log.info("%s: relinked %d rows to their plan", name, len(fixes))

            for name in _EMPTIED:
                source = old_meta.tables.get(name)
                table = live_meta.tables.get(name)
                if source is None or table is None:
                    continue
                # Fresh ids: links added by hand after the cascade reused the
                # old ones, and the id is not referenced by anything.
                common = [
                    c.name
                    for c in table.columns
                    if c.name in source.columns and c.name != "id"
                ]
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
                    if r._mapping["backup_plan_id"] in same
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
    finally:
        old_engine.dispose()


def downgrade() -> None:
    # Rows read back from the rollback are indistinguishable from rows the
    # operator added; there is nothing to undo.
    pass
