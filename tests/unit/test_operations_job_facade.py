"""Phase 5: an `operations` row wearing the legacy maintenance-job surface."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base,
    CheckJob,
    Operation,
    Repository,
    RestoreCheckJob,
)
from app.services.operations.job_facade import (
    MAINTENANCE_KINDS,
    MaintenanceJobFacade,
    claim_running,
    latest_maintenance_jobs_by_repository,
    legacy_status,
    maintenance_jobs_started_since,
    operation_status,
    resolve_agent_maintenance_job,
    resolve_maintenance_job,
)


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
def repository(db):
    repo = Repository(name="nas", path="/repo/nas", borg_version=1)
    db.add(repo)
    db.commit()
    return repo


def _operation(db, repository, *, kind="check", params=None, status="running"):
    op = Operation(
        repository_id=repository.id,
        kind=kind,
        category="maintenance",
        status=status,
        trigger="manual",
        priority=0,
        run_id="run-1",
        params=params or {},
    )
    db.add(op)
    db.commit()
    return op


def test_every_maintenance_kind_is_a_known_kind():
    from app.services.operations.vocab import KINDS

    for kind in MAINTENANCE_KINDS:
        assert kind in KINDS


def test_status_words_map_both_ways():
    assert operation_status("pending") == "queued"
    assert operation_status("running") == "running"
    assert operation_status("completed") == "completed"
    assert legacy_status("queued") == "pending"
    assert legacy_status("completed_with_warnings") == "completed_with_warnings"


def test_facade_writes_status_through_to_the_operation(db, repository):
    op = _operation(db, repository)
    job = MaintenanceJobFacade(db, op)

    job.status = "completed"
    db.commit()

    assert op.status == "completed"
    assert job.status == "completed"


def test_facade_maps_pending_to_queued(db, repository):
    op = _operation(db, repository, status="queued")
    job = MaintenanceJobFacade(db, op)

    assert job.status == "pending"

    job.status = "pending"
    assert op.status == "queued"


def test_facade_progress_is_an_integer_percent(db, repository):
    op = _operation(db, repository)
    job = MaintenanceJobFacade(db, op)

    job.progress = 40
    db.commit()

    assert op.progress_percent == 40.0
    assert job.progress == 40


def test_facade_reads_inputs_from_params(db, repository):
    op = _operation(
        db,
        repository,
        params={"max_duration": 3600, "extra_flags": "--verify-data"},
    )
    job = MaintenanceJobFacade(db, op)

    assert job.max_duration == 3600
    assert job.extra_flags == "--verify-data"
    assert job.scheduled_check is False


def test_facade_rejects_an_input_the_kind_does_not_have(db, repository):
    op = _operation(db, repository)
    job = MaintenanceJobFacade(db, op)

    with pytest.raises(AttributeError):
        job.keep_daily


def test_facade_writes_a_kind_specific_input_through_to_params(db, repository):
    op = _operation(
        db,
        repository,
        kind="restore_check",
        params={"probe_paths": "[]", "full_archive": False},
    )
    job = MaintenanceJobFacade(db, op)

    job.archive_name = "nightly-2026-09-01"
    db.commit()

    assert op.params["archive_name"] == "nightly-2026-09-01"
    assert job.archive_name == "nightly-2026-09-01"


def test_facade_logs_round_trip_through_the_log_file(db, repository, tmp_path):
    op = _operation(db, repository)
    # Write to a path this test owns. Letting the facade resolve one from
    # `settings.data_dir` puts `operation_<id>.log` in a directory other
    # suites read, and a monkeypatch of that setting is not reliable once an
    # earlier test has replaced the settings object.
    op.log_file_path = str(tmp_path / "operation.log")
    job = MaintenanceJobFacade(db, op)

    job.logs = "line one\nline two\n"
    db.commit()

    assert job.logs == "line one\nline two\n"
    assert job.has_logs is True


def test_facade_logs_setter_does_not_clobber_an_already_written_file(
    db, repository, tmp_path
):
    """The five migrated maintenance services (spec section 13 phase 5) write
    the real captured output straight to the log file, set
    `log_file_path`, and then assign `job.logs = "Logs saved to: X"` as a
    backwards-compatible marker for callers that still read the legacy
    `logs` column. For a legacy row those are two independent columns, so
    that marker write is harmless there; for a facade, `.logs` reads and
    writes through the same file `log_file_path` already points at, so the
    marker write silently overwrote the real content it was written next
    to. The setter must leave a file that already has content alone."""
    op = _operation(db, repository)
    log_path = tmp_path / "operation.log"
    log_path.write_text("real captured borg output\n", encoding="utf-8")
    op.log_file_path = str(log_path)
    job = MaintenanceJobFacade(db, op)

    job.logs = "Logs saved to: operation.log"
    db.commit()

    assert job.logs == "real captured borg output\n"


def test_facade_allocates_a_log_path_when_the_operation_has_none(
    db, repository, tmp_path, monkeypatch
):
    op = _operation(db, repository)
    target = tmp_path / "allocated.log"
    monkeypatch.setattr(
        "app.services.operations.runner.operation_log_path", lambda _id: target
    )
    job = MaintenanceJobFacade(db, op)

    job.logs = "allocated\n"
    db.commit()

    assert op.log_file_path == str(target)
    assert target.read_text() == "allocated\n"


def test_facade_has_no_logs_before_anything_is_written(db, repository):
    op = _operation(db, repository)
    job = MaintenanceJobFacade(db, op)

    assert job.logs == ""
    assert job.has_logs is False


def test_facade_identity_matches_the_operation(db, repository):
    op = _operation(db, repository)
    job = MaintenanceJobFacade(db, op)

    assert job.id == op.id
    assert job.repository_id == repository.id
    assert job.repository_path == repository.path


def test_resolve_prefers_an_operation_of_the_right_kind(db, repository):
    op = _operation(db, repository, kind="check")

    resolved = resolve_maintenance_job(db, op.id, "check")

    assert isinstance(resolved, MaintenanceJobFacade)
    assert resolved.id == op.id


def test_resolve_ignores_an_operation_of_another_kind(db, repository):
    op = _operation(db, repository, kind="prune")
    legacy = CheckJob(id=op.id, repository_id=repository.id, status="completed")
    db.add(legacy)
    db.commit()

    resolved = resolve_maintenance_job(db, op.id, "check")

    assert isinstance(resolved, CheckJob)


def test_resolve_falls_back_to_the_legacy_row(db, repository):
    legacy = CheckJob(repository_id=repository.id, status="completed")
    db.add(legacy)
    db.commit()

    resolved = resolve_maintenance_job(db, legacy.id, "check")

    assert isinstance(resolved, CheckJob)


def test_resolve_returns_none_when_nothing_matches(db):
    assert resolve_maintenance_job(db, 4242, "check") is None


def test_claim_running_claims_a_queued_operation_once(db, repository):
    op = _operation(db, repository, status="queued")
    started = datetime(2026, 9, 6, 12, 0, 0)

    assert claim_running(db, op.id, "check", started) == 1
    db.commit()
    db.refresh(op)
    assert op.status == "running"
    assert op.started_at == started

    op.status = "completed"
    db.commit()
    assert claim_running(db, op.id, "check", started) == 0


def test_claim_running_claims_a_manually_started_operation_once(db, repository):
    """A manual-start route pre-sets the row to "running" with no
    `started_at` before the executor ever calls `claim_running`; this must
    still succeed exactly once, recording the real execution start."""
    op = _operation(db, repository, status="running")
    started = datetime(2026, 9, 6, 12, 0, 0)

    assert claim_running(db, op.id, "check", started) == 1
    db.commit()
    db.refresh(op)
    assert op.started_at == started


def test_claim_running_rejects_an_already_started_running_operation(db, repository):
    """Two concurrent dispatches of the same id must not both report a
    successful claim. Before this, "running" alone was accepted regardless
    of `started_at`, so a second claim on an already-started row also
    returned 1 and could re-run the same work."""
    op = _operation(db, repository, status="running")
    first_started = datetime(2026, 9, 6, 12, 0, 0)
    assert claim_running(db, op.id, "check", first_started) == 1
    db.commit()

    second_started = datetime(2026, 9, 6, 12, 5, 0)
    assert claim_running(db, op.id, "check", second_started) == 0
    db.commit()
    db.refresh(op)
    assert op.started_at == first_started


def test_claim_running_still_claims_a_legacy_row(db, repository):
    legacy = CheckJob(repository_id=repository.id, status="pending")
    db.add(legacy)
    db.commit()
    started = datetime(2026, 9, 6, 12, 0, 0)

    assert claim_running(db, legacy.id, "check", started) == 1
    db.commit()
    db.refresh(legacy)
    assert legacy.status == "running"


def test_claim_running_claims_a_manually_started_legacy_row_once(db, repository):
    """A legacy row can also be pre-set to "running" with no `started_at`
    before the service claims it, same as a manual-start Operation."""
    legacy = CheckJob(repository_id=repository.id, status="running")
    db.add(legacy)
    db.commit()
    started = datetime(2026, 9, 6, 12, 0, 0)

    assert claim_running(db, legacy.id, "check", started) == 1
    db.commit()
    db.refresh(legacy)
    assert legacy.started_at == started


def test_claim_running_rejects_an_already_started_legacy_row(db, repository):
    """A second claim on a legacy row that already has `started_at` set
    must not also report success."""
    legacy = CheckJob(repository_id=repository.id, status="running")
    db.add(legacy)
    db.commit()
    first_started = datetime(2026, 9, 6, 12, 0, 0)
    assert claim_running(db, legacy.id, "check", first_started) == 1
    db.commit()

    second_started = datetime(2026, 9, 6, 12, 5, 0)
    assert claim_running(db, legacy.id, "check", second_started) == 0


def test_stats_live_in_the_operation_result(db, repository):
    """A service's `job.stats = ...` (a Borg 2 compact's statistics) lands
    in `result["stats"]`, next to what the executor puts there, instead of
    on the facade instance where a plain attribute write would leave it."""
    op = _operation(db, repository, kind="compact")
    job = MaintenanceJobFacade(db, op)
    assert job.stats is None

    job.stats = {"repository_size": 502_000}
    db.commit()
    db.refresh(op)
    assert op.result == {"stats": {"repository_size": 502_000}}
    assert job.stats == {"repository_size": 502_000}

    op.result = {"logs": True, "stats": {"repository_size": 502_000}}
    job.stats = {"repository_size": 1}
    assert op.result == {"logs": True, "stats": {"repository_size": 1}}

    job.stats = None
    assert op.result == {"logs": True}
    assert job.stats is None


def _twin_rows(db, repository):
    """An operation and a legacy check row sharing one id, on two different
    repositories: the two id spaces are independent sequences."""
    from datetime import datetime

    other = Repository(name="other", path="/repo/other", borg_version=1)
    db.add(other)
    db.commit()
    operation = Operation(
        kind="check",
        category="maintenance",
        status="running",
        repository_id=repository.id,
        run_id="run-twin",
        created_at=datetime(2026, 9, 1),
    )
    db.add(operation)
    db.flush()
    legacy = CheckJob(
        id=operation.id,
        repository_id=other.id,
        repository_path=other.path,
        status="completed",
        created_at=datetime(2026, 8, 1),
    )
    db.add(legacy)
    db.commit()
    return operation, legacy, other


def _payload(job_id, **maintenance_extra):
    return {
        "job_kind": "repository.check",
        "operation": {
            "maintenance_job": {"kind": "check", "id": job_id, **maintenance_extra}
        },
    }


def test_resolve_agent_job_follows_the_table_marker(db, repository):
    operation, legacy, _ = _twin_rows(db, repository)

    as_operation = resolve_agent_maintenance_job(
        db, _payload(operation.id, table="operations")
    )
    as_legacy = resolve_agent_maintenance_job(
        db, _payload(operation.id, table="check_jobs")
    )

    assert isinstance(as_operation, MaintenanceJobFacade)
    assert as_operation.id == operation.id
    assert as_legacy is legacy
    assert resolve_agent_maintenance_job(db, _payload(operation.id, table="x")) is None


def test_resolve_agent_job_breaks_a_table_less_tie_by_repository(db, repository):
    operation, legacy, other = _twin_rows(db, repository)

    payload = _payload(operation.id)
    payload["repository"] = {"id": other.id, "path": other.path}
    assert resolve_agent_maintenance_job(db, payload) is legacy

    payload["repository"] = {"id": repository.id, "path": repository.path}
    assert resolve_agent_maintenance_job(db, payload).id == operation.id

    # a repository neither row belongs to: nothing, never another
    # repository's row
    payload["repository"] = {"id": other.id + repository.id + 1, "path": "/x"}
    assert resolve_agent_maintenance_job(db, payload) is None

    # no repository in the payload: the operation, as before the marker
    assert isinstance(
        resolve_agent_maintenance_job(db, _payload(operation.id)), MaintenanceJobFacade
    )


def test_resolve_agent_job_rejects_bad_shapes(db, repository):
    assert resolve_agent_maintenance_job(db, None) is None
    assert (
        resolve_agent_maintenance_job(db, {"operation": {"maintenance_job": []}})
        is None
    )
    assert resolve_agent_maintenance_job(db, _payload("not-a-number")) is None
    assert resolve_agent_maintenance_job(db, _payload(0)) is None
    payload = _payload(1)
    payload["operation"]["maintenance_job"]["kind"] = "wipe"
    assert resolve_agent_maintenance_job(db, payload) is None
    assert resolve_agent_maintenance_job(db, _payload(1), kinds=("prune",)) is None


def test_started_since_unions_both_tables_newest_first(db, repository):
    since = datetime(2026, 9, 1)
    old = CheckJob(
        repository_id=repository.id,
        repository_path=repository.path,
        status="completed",
        started_at=datetime(2026, 8, 30),
    )
    legacy = CheckJob(
        repository_id=repository.id,
        repository_path=repository.path,
        status="completed",
        started_at=datetime(2026, 9, 2),
    )
    db.add_all([old, legacy])
    db.commit()
    op = _operation(db, repository, status="completed")
    op.started_at = datetime(2026, 9, 3)
    unrelated = _operation(db, repository, kind="prune", status="completed")
    unrelated.started_at = datetime(2026, 9, 4)
    db.commit()

    jobs = maintenance_jobs_started_since(db, "check", since)

    assert [(type(job).__name__, job.id) for job in jobs] == [
        ("MaintenanceJobFacade", op.id),
        ("CheckJob", legacy.id),
    ]
    assert jobs[0].repository_path == repository.path


def test_latest_by_repository_takes_the_newer_row_from_either_table(db):
    ops_repo = Repository(name="ops", path="/repo/ops", borg_version=1)
    legacy_repo = Repository(name="legacy", path="/repo/legacy", borg_version=1)
    idle_repo = Repository(name="idle", path="/repo/idle", borg_version=1)
    db.add_all([ops_repo, legacy_repo, idle_repo])
    db.commit()
    db.add_all(
        [
            RestoreCheckJob(
                repository_id=ops_repo.id,
                repository_path=ops_repo.path,
                status="completed",
                created_at=datetime(2026, 9, 1),
            ),
            RestoreCheckJob(
                repository_id=legacy_repo.id,
                repository_path=legacy_repo.path,
                status="failed",
                created_at=datetime(2026, 9, 5),
            ),
            RestoreCheckJob(
                repository_id=legacy_repo.id,
                repository_path=legacy_repo.path,
                status="completed",
                created_at=datetime(2026, 9, 4),
            ),
        ]
    )
    db.commit()
    newer = _operation(db, ops_repo, kind="restore_check", status="failed")
    newer.created_at = datetime(2026, 9, 2)
    older = _operation(db, legacy_repo, kind="restore_check", status="completed")
    older.created_at = datetime(2026, 9, 3)
    db.commit()

    latest = latest_maintenance_jobs_by_repository(
        db, "restore_check", [ops_repo.id, legacy_repo.id, idle_repo.id]
    )

    assert set(latest) == {ops_repo.id, legacy_repo.id}
    assert isinstance(latest[ops_repo.id], MaintenanceJobFacade)
    assert latest[ops_repo.id].id == newer.id
    assert isinstance(latest[legacy_repo.id], RestoreCheckJob)
    assert latest[legacy_repo.id].status == "failed"
    assert latest_maintenance_jobs_by_repository(db, "restore_check", []) == {}


def test_latest_by_repository_gives_a_tie_to_the_operation(db, repository):
    when = datetime(2026, 9, 6)
    db.add(
        RestoreCheckJob(
            repository_id=repository.id,
            repository_path=repository.path,
            status="failed",
            created_at=when,
        )
    )
    db.commit()
    op = _operation(db, repository, kind="restore_check", status="completed")
    op.created_at = when
    db.commit()

    latest = latest_maintenance_jobs_by_repository(db, "restore_check", [repository.id])

    assert isinstance(latest[repository.id], MaintenanceJobFacade)
    assert latest[repository.id].id == op.id


def test_latest_by_repository_reports_the_live_row_or_the_last_verdict(db, repository):
    failed = RestoreCheckJob(
        repository_id=repository.id,
        repository_path=repository.path,
        status="failed",
        created_at=datetime(2026, 9, 6),
    )
    db.add(failed)
    db.commit()
    queued = _operation(db, repository, kind="restore_check", status="queued")
    queued.created_at = datetime(2026, 9, 7)
    running = _operation(db, repository, kind="restore_check", status="running")
    running.created_at = datetime(2026, 9, 8)
    db.commit()

    live = latest_maintenance_jobs_by_repository(db, "restore_check", [repository.id])
    verdicts = latest_maintenance_jobs_by_repository(
        db, "restore_check", [repository.id], settled=True
    )

    assert live[repository.id].id == running.id
    assert live[repository.id].status == "running"
    assert isinstance(verdicts[repository.id], RestoreCheckJob)
    assert verdicts[repository.id].id == failed.id


def test_latest_by_repository_has_no_verdict_for_a_first_run_still_queued(
    db, repository
):
    pending = RestoreCheckJob(
        repository_id=repository.id,
        repository_path=repository.path,
        status="pending",
        created_at=datetime(2026, 9, 6),
    )
    db.add(pending)
    db.commit()
    queued = _operation(db, repository, kind="restore_check", status="queued")
    queued.created_at = datetime(2026, 9, 7)
    db.commit()

    live = latest_maintenance_jobs_by_repository(db, "restore_check", [repository.id])

    assert live[repository.id].id == queued.id
    assert live[repository.id].status == "pending"
    assert (
        latest_maintenance_jobs_by_repository(
            db, "restore_check", [repository.id], settled=True
        )
        == {}
    )


def test_latest_by_repository_survives_a_legacy_row_without_created_at(db, repository):
    db.add(
        RestoreCheckJob(
            repository_id=repository.id,
            repository_path=repository.path,
            status="failed",
        )
    )
    db.commit()
    # rows written before the column existed carry NULL; force it past the default
    db.query(RestoreCheckJob).update({"created_at": None})
    db.commit()
    assert db.query(RestoreCheckJob.created_at).scalar() is None
    op = _operation(db, repository, kind="restore_check", status="completed")
    op.created_at = datetime(2026, 9, 7)
    db.commit()

    latest = latest_maintenance_jobs_by_repository(db, "restore_check", [repository.id])

    assert latest[repository.id].id == op.id


def test_readers_name_an_unknown_kind(db, repository):
    with pytest.raises(ValueError, match="restorecheck"):
        maintenance_jobs_started_since(db, "restorecheck", datetime(2026, 9, 1))
    with pytest.raises(ValueError, match="restorecheck"):
        latest_maintenance_jobs_by_repository(db, "restorecheck", [repository.id])


def test_latest_by_repository_counts_a_skipped_run_as_the_verdict(db, repository):
    failed = _operation(db, repository, kind="restore_check", status="failed")
    failed.created_at = datetime(2026, 9, 6)
    skipped = _operation(db, repository, kind="restore_check", status="skipped")
    skipped.created_at = datetime(2026, 9, 7)
    skipped.skip_reason = "needs_backup"
    db.commit()

    verdicts = latest_maintenance_jobs_by_repository(
        db, "restore_check", [repository.id], settled=True
    )

    assert verdicts[repository.id].id == skipped.id
    assert verdicts[repository.id].skip_reason == "needs_backup"


def test_needs_backup_is_written_as_a_skip_and_read_back(db, repository):
    op = _operation(db, repository, kind="restore_check")
    job = MaintenanceJobFacade(db, op)

    job.status = "needs_backup"
    db.commit()
    db.refresh(op)

    assert (op.status, op.skip_reason) == ("skipped", "needs_backup")
    assert job.status == "needs_backup"
    assert operation_status("needs_backup") == "skipped"
    other = _operation(db, repository, kind="restore_check", status="skipped")
    other.skip_reason = "dependency_failed"
    assert MaintenanceJobFacade(db, other).status == "skipped"


def test_latest_by_repository_counts_a_legacy_row_without_status_as_settled(
    db, repository
):
    db.add(
        RestoreCheckJob(
            repository_id=repository.id,
            repository_path=repository.path,
            created_at=datetime(2026, 9, 6),
        )
    )
    db.commit()
    db.query(RestoreCheckJob).update({"status": None})
    db.commit()

    live = latest_maintenance_jobs_by_repository(db, "restore_check", [repository.id])
    verdicts = latest_maintenance_jobs_by_repository(
        db, "restore_check", [repository.id], settled=True
    )

    assert live[repository.id].id == verdicts[repository.id].id
