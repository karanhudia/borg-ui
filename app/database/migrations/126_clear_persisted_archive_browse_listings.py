"""Clear persisted archive browse listings from agent_jobs.result.

A ``repository.list_archive_contents`` job used to keep the archive's full
``borg list`` output in ``agent_jobs.result`` indefinitely. That output is
transient — it is cached once the browse request reads it and can be re-fetched
from the agent on demand — so it should never have been retained. On large
archives it is hundreds of MB per job, which bloats the database over time.

This migration clears it from existing rows and reclaims the freed space; the
code no longer persists it going forward.
"""

import structlog
from sqlalchemy import inspect, text

logger = structlog.get_logger()


def _bind(db):
    return db.get_bind() if hasattr(db, "get_bind") else db


def _has_table(db, table_name: str) -> bool:
    return table_name in inspect(_bind(db)).get_table_names()


def upgrade(db):
    # json_extract is SQLite-specific; borg-ui runs on SQLite. Skip elsewhere.
    if not _has_table(db, "agent_jobs") or _bind(db).dialect.name != "sqlite":
        return

    result = db.execute(
        text(
            "UPDATE agent_jobs SET result = NULL "
            "WHERE result IS NOT NULL "
            "AND json_extract(payload, '$.job_kind') = "
            "'repository.list_archive_contents'"
        )
    )
    db.commit()

    if not result.rowcount:
        return

    # Nulling only frees the pages for reuse; VACUUM shrinks the file on disk.
    # Migrations run during container startup with no other DB users, so the
    # whole-file rewrite is safe here. VACUUM must run outside a transaction
    # (AUTOCOMMIT), and it needs scratch space ~= the DB size — if that fails we
    # log and move on: the rows are already cleared, so the DB stops growing
    # regardless.
    try:
        db.execution_options(isolation_level="AUTOCOMMIT").execute(text("VACUUM"))
    except Exception as exc:  # pragma: no cover - environment-dependent
        logger.warning(
            "VACUUM after clearing browse listings failed; freed pages will be "
            "reused but the file was not shrunk",
            error=str(exc),
        )


def downgrade(db):
    # Irreversible: the cleared listings were transient and re-fetchable.
    pass
