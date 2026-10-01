"""Tests for revision c8e1f4a7b2d9: plan links read back from the rollback.

Mirrors an install that upgraded a 2.2.x database to 2.3.4-2.3.6 and lost
the rows that cascade from backup_plans (#860): the upgrade is run, the
damage is applied to the live file, and the file is stamped back to the
revision before the repair so the next upgrade runs it."""

import pytest
from sqlalchemy import create_engine, text

from app.database.db_upgrade import alembic_init
from app.database.models import (
    BackupPlan,
    BackupPlanRepository,
    BackupPlanRun,
    Repository,
)
from tests.unit.test_db_upgrade import _legacy_db, _open

PREVIOUS = "b7d2e9f4a1c3"


def _populate(s):
    repos = [Repository(name=f"r{i}", path=f"/srv/r{i}") for i in range(2)]
    plan = BackupPlan(name="nightly", source_directories='["/data"]')
    s.add_all([*repos, plan])
    s.flush()
    s.add(
        BackupPlanRepository(
            backup_plan_id=plan.id, repository_id=repos[0].id, execution_order=1
        )
    )
    s.add(BackupPlanRun(backup_plan_id=plan.id, trigger="schedule", status="completed"))


def _damaged_install(tmp_path, *, hand_repaired=False):
    """A 2.2.x database upgraded, then hit by the cascade and stamped back."""
    db = tmp_path / "borg.db"
    _legacy_db(db, _populate)
    assert alembic_init(db).action == "transferred"
    assert (tmp_path / "borg_bak.db").exists()
    with create_engine(f"sqlite:///{db}").begin() as c:
        c.execute(text("DELETE FROM backup_plan_repositories"))
        c.execute(text("UPDATE backup_plan_runs SET backup_plan_id = NULL"))
        if hand_repaired:
            c.execute(
                text(
                    "INSERT INTO backup_plan_repositories (backup_plan_id, "
                    "repository_id, enabled, execution_order, compression_source, "
                    "created_at) VALUES (1, 2, 1, 1, 'plan', CURRENT_TIMESTAMP)"
                )
            )
        c.execute(text(f"UPDATE alembic_version SET version_num = '{PREVIOUS}'"))
    return db


def _links(db):
    s = _open(db)
    try:
        return sorted(
            (l.backup_plan_id, l.repository_id, l.enabled)
            for l in s.query(BackupPlanRepository).all()
        )
    finally:
        s.close()


def _run_plan_ids(db):
    s = _open(db)
    try:
        return [r.backup_plan_id for r in s.query(BackupPlanRun).all()]
    finally:
        s.close()


@pytest.mark.unit
def test_lost_links_and_run_plans_come_back_from_the_rollback(tmp_path):
    db = _damaged_install(tmp_path)
    assert _links(db) == []
    assert _run_plan_ids(db) == [None]

    assert alembic_init(db).action == "migrated"

    assert _links(db) == [(1, 1, True)]
    assert _run_plan_ids(db) == [1]


@pytest.mark.unit
def test_a_plan_repaired_by_hand_is_left_alone(tmp_path):
    db = _damaged_install(tmp_path, hand_repaired=True)

    alembic_init(db)

    # The operator's choice of repository stands; the old link is not re-added.
    assert _links(db) == [(1, 2, True)]
    # Runs cannot be relinked by hand, so those are still restored.
    assert _run_plan_ids(db) == [1]


@pytest.mark.unit
def test_without_a_rollback_file_nothing_changes(tmp_path):
    db = _damaged_install(tmp_path)
    (tmp_path / "borg_bak.db").unlink()

    assert alembic_init(db).action == "migrated"

    assert _links(db) == []
    assert _run_plan_ids(db) == [None]


@pytest.mark.unit
def test_an_install_that_never_took_the_hit_is_unchanged(tmp_path):
    db = tmp_path / "borg.db"
    _legacy_db(db, _populate)

    assert alembic_init(db).action == "transferred"

    assert _links(db) == [(1, 1, True)]
    assert _run_plan_ids(db) == [1]
