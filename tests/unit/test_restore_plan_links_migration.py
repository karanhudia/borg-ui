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
    """Two plans, each with its own repository and one past run."""
    repos = [Repository(name=f"r{i}", path=f"/srv/r{i}") for i in range(1, 4)]
    plans = [BackupPlan(name=n, source_directories='["/data"]') for n in ("a", "b")]
    s.add_all([*repos, *plans])
    s.flush()
    for plan, repo in zip(plans, repos):
        s.add(
            BackupPlanRepository(
                backup_plan_id=plan.id, repository_id=repo.id, execution_order=1
            )
        )
        s.add(
            BackupPlanRun(
                backup_plan_id=plan.id, trigger="schedule", status="completed"
            )
        )


def _upgraded(tmp_path):
    db = tmp_path / "borg.db"
    _legacy_db(db, _populate)
    assert alembic_init(db).action == "transferred"
    assert (tmp_path / "borg_bak.db").exists()
    return db


def _stamp_back(db, *statements):
    with create_engine(f"sqlite:///{db}").begin() as c:
        for sql in statements:
            c.execute(text(sql))
        c.execute(text(f"UPDATE alembic_version SET version_num = '{PREVIOUS}'"))


CASCADE = (
    "DELETE FROM backup_plan_repositories",
    "UPDATE backup_plan_runs SET backup_plan_id = NULL",
)
HAND_REPAIR_PLAN_A = (
    # Reuses id 1, as SQLite does once the table is empty.
    "INSERT INTO backup_plan_repositories (backup_plan_id, repository_id, enabled, "
    "execution_order, compression_source, created_at) "
    "VALUES (1, 3, 1, 1, 'plan', CURRENT_TIMESTAMP)"
)


def _links(db):
    s = _open(db)
    try:
        return sorted(
            (l.backup_plan_id, l.repository_id)
            for l in s.query(BackupPlanRepository).all()
        )
    finally:
        s.close()


def _run_plans(db):
    s = _open(db)
    try:
        return sorted((r.id, r.backup_plan_id) for r in s.query(BackupPlanRun).all())
    finally:
        s.close()


@pytest.mark.unit
def test_lost_links_and_run_plans_come_back_from_the_rollback(tmp_path):
    db = _upgraded(tmp_path)
    _stamp_back(db, *CASCADE)
    assert _links(db) == []

    assert alembic_init(db).action == "migrated"

    assert _links(db) == [(1, 1), (2, 2)]
    assert _run_plans(db) == [(1, 1), (2, 2)]


@pytest.mark.unit
def test_a_plan_repaired_by_hand_keeps_its_choice_and_its_reused_id(tmp_path):
    db = _upgraded(tmp_path)
    _stamp_back(db, *CASCADE, HAND_REPAIR_PLAN_A)

    alembic_init(db)

    # Plan a keeps the operator's repository; plan b gets its old one back
    # under a fresh id, next to the hand-added row that took id 1.
    assert _links(db) == [(1, 3), (2, 2)]
    assert _run_plans(db) == [(1, 1), (2, 2)]


@pytest.mark.unit
def test_a_plan_emptied_on_purpose_after_a_clean_upgrade_stays_empty(tmp_path):
    db = _upgraded(tmp_path)
    # No cascade: the runs still name their plans. The operator removed b's
    # only repository.
    _stamp_back(db, "DELETE FROM backup_plan_repositories WHERE backup_plan_id = 2")

    assert alembic_init(db).action == "migrated"

    assert _links(db) == [(1, 1)]


@pytest.mark.unit
def test_a_reused_plan_id_with_another_name_gets_nothing(tmp_path):
    db = _upgraded(tmp_path)
    # The cascade ran, then the operator deleted plan b and created plan c,
    # which took id 2. Plan a's evidence triggers the repair; c is not b.
    _stamp_back(
        db,
        *CASCADE,
        "DELETE FROM backup_plan_runs WHERE id = 2",
        "UPDATE backup_plans SET name = 'c' WHERE id = 2",
    )

    alembic_init(db)

    assert _links(db) == [(1, 1)]
    assert _run_plans(db) == [(1, 1)]


@pytest.mark.unit
def test_without_a_rollback_file_nothing_changes(tmp_path):
    db = _upgraded(tmp_path)
    _stamp_back(db, *CASCADE)
    (tmp_path / "borg_bak.db").unlink()

    assert alembic_init(db).action == "migrated"

    assert _links(db) == []


@pytest.mark.unit
def test_an_install_that_never_took_the_hit_is_unchanged(tmp_path):
    db = _upgraded(tmp_path)

    assert _links(db) == [(1, 1), (2, 2)]
    assert _run_plans(db) == [(1, 1), (2, 2)]
