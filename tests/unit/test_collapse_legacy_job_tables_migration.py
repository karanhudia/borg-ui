"""Tests for revision d0e1f2a3b4c5 (collapse of the legacy job tables)."""

from datetime import datetime

import pytest
from alembic import command
from sqlalchemy import MetaData, insert, inspect, select

from app.database import legacy_job_tables as legacy
from app.database.db_upgrade import _alembic_config, _engine

REVISION = "d0e1f2a3b4c5"
# The last revision whose schema still holds the legacy job tables; the
# collapse chains onto the head that landed after it.
PREVIOUS = "b8c9d0e1f2a3"
PARENT = "c9d0e1f2a3b4"
NOW = datetime(2026, 9, 1, 12, 0, 0)

# The NOT NULL columns of `repositories` that carry no server default.
REPOSITORY_FLAGS = dict(
    execution_target="local",
    executor_type="server",
    borg_version=1,
    check_schedule_enabled=False,
    check_timezone="UTC",
    notify_on_check_success=False,
    notify_on_check_failure=False,
    restore_check_schedule_enabled=False,
    restore_check_timezone="UTC",
    restore_check_full_archive=False,
    restore_check_canary_enabled=False,
    notify_on_restore_check_success=False,
    notify_on_restore_check_failure=False,
)


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


def _columns(url, table):
    engine = _engine(url)
    try:
        return {c["name"] for c in inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


@pytest.mark.unit
def test_upgrade_copies_then_drops_and_downgrade_recreates_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    engine = _engine(url)
    with engine.begin() as connection:
        meta = MetaData()
        meta.reflect(bind=connection)
        connection.execute(
            insert(meta.tables["repositories"]).values(
                id=1,
                name="r",
                path="/srv/r",
                encryption="none",
                compression="lz4",
                mode="full",
                created_at=NOW,
                **REPOSITORY_FLAGS,
            )
        )
        connection.execute(
            insert(legacy.backup_jobs).values(
                id=1,
                repository="/srv/r",
                repository_id=1,
                status="completed",
                created_at=NOW,
            )
        )
        connection.execute(
            insert(legacy.check_jobs).values(
                id=1, repository_id=1, status="completed", created_at=NOW
            )
        )
        connection.execute(
            insert(legacy.repository_wipe_jobs).values(
                id=1,
                repository_id=1,
                status="previewed",
                run_compact=True,
                created_at=NOW,
            )
        )
    engine.dispose()

    _migrate(url, REVISION)
    assert not (set(legacy.LEGACY_JOB_TABLE_NAMES) & _tables(url))
    assert "repository_wipe_jobs" in _tables(url)
    assert "backup_job_id" not in _columns(url, "agent_jobs")
    assert "backup_job_id" not in _columns(url, "script_executions")
    assert "backup_job_id" not in _columns(url, "backup_plan_run_repositories")
    engine = _engine(url)
    with engine.connect() as connection:
        meta = MetaData()
        meta.reflect(bind=connection)
        kinds = (
            connection.execute(select(meta.tables["operations"].c.kind)).scalars().all()
        )
        assert sorted(kinds) == ["backup", "check"]
        previews = (
            connection.execute(select(legacy.repository_wipe_jobs.c.status))
            .scalars()
            .all()
        )
        assert previews == ["previewed"]
    engine.dispose()

    _migrate(url, PREVIOUS, down=True)
    assert set(legacy.LEGACY_JOB_TABLE_NAMES) <= _tables(url)
    assert "backup_job_id" in _columns(url, "agent_jobs")
    engine = _engine(url)
    with engine.connect() as connection:
        assert connection.execute(select(legacy.backup_jobs.c.id)).all() == []
    engine.dispose()


@pytest.mark.unit
def test_an_executed_wipe_of_a_deleted_repository_is_left_in_place(
    tmp_path, monkeypatch
):
    """`repository_wipe_jobs` is the one legacy table that survives, so a row
    the copy cannot take (its repository is gone, and an operation's
    repository is a real foreign key) must stay rather than be deleted with
    the copied ones: the row is the only record left of that wipe."""
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    url = f"sqlite:///{tmp_path / 'orphan.db'}"
    _migrate(url, PREVIOUS)
    engine = _engine(url)
    with engine.begin() as connection:
        # The column is ON DELETE SET NULL, so a dangling id only exists where
        # SQLite ran without foreign keys enforced, which is where these rows
        # come from; the insert needs the same freedom.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.execute(
            insert(legacy.repository_wipe_jobs).values(
                id=1,
                repository_id=404,  # a repository that is no longer there
                status="completed",
                run_compact=False,
                created_at=NOW,
            )
        )
    engine.dispose()

    _migrate(url, REVISION)

    engine = _engine(url)
    with engine.connect() as connection:
        meta = MetaData()
        meta.reflect(bind=connection)
        assert connection.execute(select(meta.tables["operations"].c.kind)).all() == []
        left = connection.execute(
            select(
                legacy.repository_wipe_jobs.c.id,
                legacy.repository_wipe_jobs.c.status,
            )
        ).all()
        assert left == [(1, "completed")]
    engine.dispose()


@pytest.mark.unit
def test_revision_chains_on_the_previous_head_and_leaves_one_head():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config("sqlite://"))
    assert script.get_revision(REVISION).down_revision == PARENT
    assert len(script.get_heads()) == 1
