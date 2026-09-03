import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    BackupJob,
    Base,
    CheckJob,
    Repository,
    SystemSettings,
)
from app.services.operations import lanes
from app.services.operations.enqueue import enqueue


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def repo(db):
    r = Repository(name="r", path="/tmp/r", encryption="none", compression="lz4")
    db.add(r)
    db.commit()
    return r


@pytest.fixture()
def settings(db):
    s = SystemSettings()
    db.add(s)
    db.commit()
    return s


def _running(db, kind, repo, trigger="manual"):
    op = enqueue(db, kind, repository_id=repo.id, trigger=trigger)
    op.status = "running"
    db.commit()
    return op


def _other_repo(db):
    other = Repository(name="o", path="/tmp/o", encryption="none", compression="lz4")
    db.add(other)
    db.commit()
    return other


@pytest.mark.unit
def test_lane_free_without_running_work(db, repo, settings):
    op = enqueue(db, "history_index", repository_id=repo.id)
    assert lanes.lane_free(db, repo.id) is True
    assert lanes.can_start(db, op, settings) is True


@pytest.mark.unit
def test_exclusive_blocks_second_exclusive_on_same_repo(db, repo, settings):
    _running(db, "history_index", repo)
    second = enqueue(db, "history_index", repository_id=repo.id)
    assert lanes.can_start(db, second, settings) is False


@pytest.mark.unit
def test_exclusive_does_not_block_other_repo(db, repo, settings):
    other = _other_repo(db)
    _running(db, "history_index", repo)
    op = enqueue(db, "history_index", repository_id=other.id)
    assert lanes.can_start(db, op, settings) is True


@pytest.mark.unit
def test_legacy_running_backup_blocks_lane(db, repo, settings):
    db.add(
        BackupJob(repository=repo.path, repository_id=repo.id, status="running_prune")
    )
    db.commit()
    assert lanes.legacy_running_exclusive(db, repo.id) is True
    op = enqueue(db, "history_index", repository_id=repo.id)
    assert lanes.can_start(db, op, settings) is False


@pytest.mark.unit
def test_legacy_completed_check_does_not_block(db, repo, settings):
    db.add(
        CheckJob(repository_id=repo.id, repository_path=repo.path, status="completed")
    )
    db.commit()
    assert lanes.legacy_running_exclusive(db, repo.id) is False


@pytest.mark.unit
def test_index_kind_waits_without_bypass_and_runs_with_bypass(db, repo, settings):
    _running(db, "history_index", repo)
    op = enqueue(db, "stats", repository_id=repo.id)
    assert lanes.can_start(db, op, settings) is False
    settings.bypass_lock_on_list = True
    db.commit()
    assert lanes.can_start(db, op, settings) is True
    settings.bypass_lock_on_list = False
    repo.bypass_lock = True
    db.commit()
    assert lanes.can_start(db, op, settings) is True


@pytest.mark.unit
def test_index_workers_limit(db, repo, settings):
    settings.index_workers = 1
    db.commit()
    other = _other_repo(db)
    _running(db, "stats", repo)
    op = enqueue(db, "stats", repository_id=other.id)
    assert lanes.global_slot_available(db, op, settings) is False
    settings.index_workers = 2
    db.commit()
    assert lanes.global_slot_available(db, op, settings) is True


@pytest.mark.unit
def test_pause_only_affects_followup_and_reconcile(db, repo, settings):
    settings.background_paused = True
    db.commit()
    followup = enqueue(db, "stats", repository_id=repo.id, trigger="followup")
    reconcile = enqueue(db, "stats", repository_id=repo.id, trigger="reconcile")
    manual = enqueue(db, "stats", repository_id=repo.id, trigger="manual")
    assert lanes.can_start(db, followup, settings) is False
    assert lanes.can_start(db, reconcile, settings) is False
    assert lanes.can_start(db, manual, settings) is True


@pytest.mark.unit
def test_backup_limits_by_trigger(db, repo, settings):
    settings.max_concurrent_backups = 1
    settings.max_concurrent_scheduled_backups = 1
    db.commit()
    other = _other_repo(db)
    _running(db, "backup", repo, trigger="manual")
    manual = enqueue(db, "backup", repository_id=other.id, trigger="manual")
    scheduled = enqueue(db, "backup", repository_id=other.id, trigger="schedule")
    assert lanes.global_slot_available(db, manual, settings) is False
    assert lanes.global_slot_available(db, scheduled, settings) is True


@pytest.mark.unit
def test_scheduled_check_limit(db, repo, settings):
    settings.max_concurrent_scheduled_checks = 1
    db.commit()
    other = _other_repo(db)
    _running(db, "check", repo, trigger="schedule")
    scheduled = enqueue(db, "check", repository_id=other.id, trigger="schedule")
    manual = enqueue(db, "check", repository_id=other.id, trigger="manual")
    assert lanes.global_slot_available(db, scheduled, settings) is False
    assert lanes.global_slot_available(db, manual, settings) is True


@pytest.mark.unit
def test_system_kind_has_no_lane(db, settings):
    op = enqueue(db, "package_install", repository_id=None)
    assert lanes.can_start(db, op, settings) is True


@pytest.mark.unit
def test_defaults_when_settings_row_missing(db, repo):
    op = enqueue(db, "stats", repository_id=repo.id)
    assert lanes.can_start(db, op, None) is True
