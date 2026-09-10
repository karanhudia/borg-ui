import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Repository, SystemSettings
from app.services.operations import lanes
from app.services.operations.details import backup_details
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
def test_a_running_backup_operation_blocks_the_lane(db, repo, settings):
    _running(db, "backup", repo)
    check = enqueue(db, "check", repository_id=repo.id)
    assert lanes.can_start(db, check, settings) is False


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


@pytest.mark.unit
def test_bypass_does_not_start_a_listing_while_write_maintenance_runs(
    db, repo, settings
):
    """The backup follow-up chain is enqueued when the backup completes,
    while the plan still runs prune and compact on the same repository.
    Admission refuses a listing during those (409), so bypass_lock must
    not dispatch it; it waits in the queue and runs once they finish."""
    settings.bypass_lock_on_list = True
    db.commit()
    op = enqueue(db, "archive_sync", repository_id=repo.id, trigger="followup")

    # a running backup is what bypass is for: the listing may start
    backup = _running(db, "backup", repo)
    details = backup_details(db, backup)
    db.commit()
    assert lanes.write_maintenance_running(db, repo.id) is False
    assert lanes.can_start(db, op, settings) is True

    # the plan moved on to prune: same backup row, its maintenance_status
    # (status stays a backup status)
    backup.status = "completed"
    details.maintenance_status = "running_prune"
    db.commit()
    assert lanes.write_maintenance_running(db, repo.id) is True
    assert lanes.can_start(db, op, settings) is False
    details.maintenance_status = "prune_completed"
    db.commit()
    assert lanes.write_maintenance_running(db, repo.id) is False

    # a queued prune operation counts before it runs: the listing would
    # otherwise overlap it when another tick starts the prune
    queued_prune = enqueue(db, "prune", repository_id=repo.id)
    assert lanes.can_start(db, op, settings) is False
    queued_prune.status = "completed"
    db.commit()
    assert lanes.can_start(db, op, settings) is True

    # a running compact operation on its own
    compact = _running(db, "compact", repo)
    assert lanes.can_start(db, op, settings) is False
    compact.status = "completed"
    db.commit()
    assert lanes.can_start(db, op, settings) is True
