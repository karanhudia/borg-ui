"""Unit tests for the DB job-history retention service.

Covers the two windows independently: log content (agent_job_logs rows +
inline `logs` columns) falls at log_retention_days, job rows of every kind
fall at cleanup_retention_days regardless of status — age comes from the
freshest timestamp, so genuinely live work never looks old.
"""

from datetime import timedelta
from pathlib import Path

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    AgentJob,
    AgentJobLog,
    AgentMachine,
    Base,
    BackupPlan,
    BackupPlanRun,
    Operation,
    OperationBackupDetails,
    Repository,
    RepositoryWipeJob,
    ScriptExecution,
    SystemSettings,
    utc_now,
)
from app.services.operations.job_facade import resolve_maintenance_job
from tests.utils.operations import seed_job_operation
from app.services.job_history_retention import (
    archive_names_from_prune_output,
    mark_jobs_of_pruned_archives,
    purge_job_rows,
    run_retention,
    sweep_pruned_archive_records,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    # Mirror production: FK enforcement on, so ondelete=CASCADE fires.
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _settings(db, **overrides):
    kwargs = {
        "log_retention_days": 30,
        "cleanup_retention_days": 90,
        # all_jobs so the age windows are tested in isolation; the policy
        # phase has its own tests below.
        "log_save_policy": "all_jobs",
        "auto_cleanup": True,
        **overrides,
    }
    settings = SystemSettings(**kwargs)
    db.add(settings)
    db.commit()
    return settings


def _machine(db):
    machine = AgentMachine(
        name="m", agent_id="a-1", token_hash="h", token_prefix="p", status="online"
    )
    db.add(machine)
    db.commit()
    return machine


def _agent_job(db, machine, status, age_days, log_lines=0, active_days=None):
    when = utc_now() - timedelta(days=age_days)
    job = AgentJob(
        agent_machine_id=machine.id,
        job_type="backup",
        status=status,
        payload={},
        completed_at=when if status not in ("queued", "running") else None,
        created_at=when,
        updated_at=utc_now() - timedelta(days=active_days)
        if active_days is not None
        else when,
    )
    db.add(job)
    db.commit()
    for seq in range(log_lines):
        db.add(
            AgentJobLog(
                agent_job_id=job.id,
                sequence=seq,
                stream="stderr",
                message=f"line {seq}",
                created_at=when,
            )
        )
    db.commit()
    return job


@pytest.mark.unit
def test_old_agent_job_logs_deleted_recent_and_live_kept(db):
    settings = _settings(db)
    machine = _machine(db)
    old = _agent_job(db, machine, "completed", age_days=40, log_lines=3)
    fresh = _agent_job(db, machine, "completed", age_days=2, log_lines=2)
    # Started long ago but still moving: updated_at is fresh, so it never
    # looks old — status plays no role anymore.
    live = _agent_job(db, machine, "running", age_days=40, log_lines=2, active_days=0)

    results = run_retention(db, settings)

    assert results["agent_log_rows_deleted"] == 3
    remaining = {row.agent_job_id for row in db.query(AgentJobLog)}
    assert remaining == {fresh.id, live.id}
    # 40 days < cleanup_retention_days: the job row itself survives.
    assert db.get(AgentJob, old.id) is not None


@pytest.mark.unit
def test_log_files_deleted_history_kept(db):
    """An operation's log is a file (spec 6.1): the log window takes the file
    and leaves the row, which is the record that the run happened."""
    settings = _settings(db)
    when = utc_now() - timedelta(days=40)
    repo = Repository(name="r", path="/tmp/r")
    db.add(repo)
    db.commit()
    job = seed_job_operation(
        db,
        "backup",
        repository_id=repo.id,
        status="completed",
        completed_at=when,
        created_at=when,
        logs="borg output " * 100,
        error_message="kept",
        nfiles=123,
    )
    check = seed_job_operation(
        db,
        "check",
        repository_id=repo.id,
        status="completed",
        completed_at=when,
        created_at=when,
        logs="check output",
    )
    backup_log, check_log = job.log_file_path, check.log_file_path

    results = run_retention(db, settings)

    assert results["operation_log_files_deleted"] == 2
    db.refresh(job)
    db.refresh(check)
    assert not Path(backup_log).exists()
    assert not Path(check_log).exists()
    assert job.log_file_path is None and check.log_file_path is None
    assert job.error_message == "kept"  # history stays
    assert db.get(OperationBackupDetails, job.id).nfiles == 123


@pytest.mark.unit
def test_expired_job_rows_deleted_and_agent_logs_cascade(db):
    settings = _settings(db)
    machine = _machine(db)
    expired = _agent_job(db, machine, "failed", age_days=120, log_lines=2)
    kept = _agent_job(db, machine, "completed", age_days=40)
    old_backup = seed_job_operation(
        db,
        "backup",
        status="completed",
        completed_at=utc_now() - timedelta(days=120),
        created_at=utc_now() - timedelta(days=120),
    )
    db.commit()
    expired_id, kept_id = expired.id, kept.id

    results = run_retention(db, settings)

    # Bulk deletes bypass the identity map; drop it before re-reading.
    db.expunge_all()
    assert db.get(AgentJob, expired_id) is None
    assert db.get(AgentJob, kept_id) is not None
    # The expired job's log rows are counted by the log phase (they aged past
    # log_retention_days too), and nothing dangles afterwards.
    assert db.query(AgentJobLog).count() == 0
    assert results["job_rows_deleted"] == 2


@pytest.mark.unit
def test_row_purge_ignores_legacy_auto_cleanup_flag(db):
    # Retention is a property, not an option: the pre-existing auto_cleanup
    # settings flag must not disable the row purge.
    settings = _settings(db, auto_cleanup=False)
    machine = _machine(db)
    expired = _agent_job(db, machine, "completed", age_days=120, log_lines=2)
    expired_id = expired.id

    results = run_retention(db, settings)

    db.expunge_all()
    assert results["job_rows_deleted"] == 1
    assert db.get(AgentJob, expired_id) is None
    assert results["agent_log_rows_deleted"] == 2
    assert db.query(AgentJobLog).count() == 0


@pytest.mark.unit
def test_age_rules_regardless_of_status(db):
    settings = _settings(db)
    machine = _machine(db)
    # A job queued for an agent that never came back: blocked history, not
    # in-flight work. It falls with the window like everything else.
    zombie = _agent_job(db, machine, "queued", age_days=120, log_lines=1)
    zombie_id = zombie.id
    # A wipe preview, the only thing `repository_wipe_jobs` still holds.
    wipe = RepositoryWipeJob(
        repository_id=None,
        status="previewed",
        created_at=utc_now() - timedelta(days=400),
        dry_run_output="preview",
    )
    db.add(wipe)
    db.commit()

    results = run_retention(db, settings)

    db.expunge_all()
    assert db.get(AgentJob, zombie_id) is None
    assert db.query(RepositoryWipeJob).count() == 0
    assert results["job_rows_deleted"] == 2


@pytest.mark.unit
def test_plan_runs_and_script_executions_fall_with_the_window(db):
    settings = _settings(db)
    when = utc_now() - timedelta(days=120)
    plan = BackupPlan(name="p", enabled=True, source_directories='["/data"]')
    db.add(plan)
    db.flush()
    run = BackupPlanRun(
        backup_plan_id=plan.id,
        trigger="scheduled",
        status="completed",
        completed_at=when,
        created_at=when,
    )
    db.add(run)
    db.flush()
    execution = ScriptExecution(
        backup_plan_run_id=run.id,
        hook_type="pre-backup",
        status="completed",
        started_at=when,
        completed_at=when,
        stdout="hook output",
    )
    db.add(execution)
    db.commit()

    results = run_retention(db, settings)

    # The plan run falls with the window; its hook execution dies with it
    # via the DB-level cascade (and is not double-counted).
    assert db.query(BackupPlanRun).count() == 0
    assert db.query(ScriptExecution).count() == 0
    assert results["job_rows_deleted"] >= 1


@pytest.mark.unit
def test_policy_drops_success_logs_regardless_of_age(db):
    settings = _settings(db, log_save_policy="failed_and_warnings")
    machine = _machine(db)
    success = _agent_job(db, machine, "completed", age_days=1, log_lines=3)
    warned = _agent_job(db, machine, "completed_with_warnings", age_days=1, log_lines=2)
    failed = _agent_job(db, machine, "failed", age_days=1, log_lines=2)
    fresh_backup = seed_job_operation(
        db,
        "backup",
        status="completed",
        completed_at=utc_now() - timedelta(days=1),
        created_at=utc_now() - timedelta(days=1),
        logs="clean success output",
        error_message=None,
    )
    db.commit()

    results = run_retention(db, settings)

    # Day-old logs, way inside the age window - the policy drops them anyway.
    assert results["policy_log_rows_deleted"] == 3
    assert results["policy_operation_log_files_deleted"] == 1
    remaining = {row.agent_job_id for row in db.query(AgentJobLog)}
    assert remaining == {warned.id, failed.id}
    db.refresh(fresh_backup)
    assert fresh_backup.log_file_path is None
    # Job rows themselves stay: only the windows delete history.
    assert db.get(AgentJob, success.id) is not None


@pytest.mark.unit
def test_policy_failed_only_also_drops_warning_logs(db):
    settings = _settings(db, log_save_policy="failed_only")
    machine = _machine(db)
    warned = _agent_job(db, machine, "completed_with_warnings", age_days=1, log_lines=2)
    failed = _agent_job(db, machine, "failed", age_days=1, log_lines=2)

    results = run_retention(db, settings)

    assert results["policy_log_rows_deleted"] == 2
    remaining = {row.agent_job_id for row in db.query(AgentJobLog)}
    assert remaining == {failed.id}
    assert db.get(AgentJob, warned.id) is not None


# --- pruned-archive cascade ---------------------------------------------------


@pytest.mark.unit
def test_prune_output_parsing_matches_wrapped_and_raw_lines():
    output = "\n".join(
        [
            # Verbatim production line (borg 1.4, counter before the colon):
            '{"type": "log_message", "time": 1784753129.6, "message": "Pruning'
            " archive (1/1):                       k3s01-1784673920"
            "                     Tue, 2026-07-21 22:45:21 [ede859194d6f292b56"
            '7bf50fdc1d989d114eb91192313ddbe5a14e8a294c444c]", "levelname":'
            ' "INFO", "name": "borg.output.list"}',
            '{"message": "Pruning archives   0%", "type": "progress_percent"}',
            "Pruning archive: host-2026-06-01-1748700000"
            "            Sun, 2026-06-01 03:00:12 [abcdef0123] (1/3)",
            '{"type": "log_message", "message": "Pruning archive: host-x'
            '                     Mon, 2026-05-05 04:00:00 [ff00aa] (2/3)"}',
            "Would prune:     kept-by-dry-run"
            "                  Tue, 2026-04-01 02:00:00 [aa] (1/1)",
            "Keeping archive: fresh-one"
            "                 Wed, 2026-07-22 03:00:00 [bb] (1/1)",
        ]
    )
    assert archive_names_from_prune_output(output) == {
        "k3s01-1784673920",
        "host-2026-06-01-1748700000",
        "host-x",
    }


def _repo(db, borg_version=1):
    repo = Repository(
        name=f"r{borg_version}", path=f"/tmp/r{borg_version}", borg_version=borg_version
    )
    db.add(repo)
    db.commit()
    return repo


@pytest.mark.unit
def test_pruned_archives_mark_their_job_records_and_keep_them(db, tmp_path):
    """The job row is the record that the backup ran: a prune marks it and
    leaves it, its agent job, its log rows and its log file alone."""
    _settings(db)
    machine = _machine(db)
    repo = _repo(db)
    log_file = tmp_path / "backup_1.log"
    log_file.write_text("borg output")
    when = utc_now() - timedelta(days=3)
    pruned = seed_job_operation(
        db,
        "backup",
        repository_id=repo.id,
        status="completed",
        archive_name="host-old",
        log_file_path=str(log_file),
        completed_at=when,
        created_at=when,
    )
    kept = seed_job_operation(
        db,
        "backup",
        repository_id=repo.id,
        status="completed",
        archive_name="host-new",
        completed_at=when,
        created_at=when,
    )
    db.add_all([pruned, kept])
    db.flush()
    agent_run = _agent_job(db, machine, "completed", age_days=3, log_lines=2)
    agent_run.operation_id = pruned.id
    db.commit()
    repo_id = repo.id
    pruned_id, kept_id, agent_id = pruned.id, kept.id, agent_run.id

    marked = mark_jobs_of_pruned_archives(db, repo_id, {"host-old"})

    db.expunge_all()
    assert marked == 1
    pruned_row = db.get(OperationBackupDetails, pruned_id)
    assert pruned_row is not None and pruned_row.archive_pruned_at is not None
    assert db.get(Operation, pruned_id).status == "completed"
    assert db.get(OperationBackupDetails, kept_id).archive_pruned_at is None
    assert db.get(AgentJob, agent_id) is not None
    assert db.query(AgentJobLog).count() == 2
    assert log_file.exists()
    # A second prune report for the same archive changes nothing.
    first_mark = pruned_row.archive_pruned_at
    assert mark_jobs_of_pruned_archives(db, repo_id, {"host-old"}) == 0
    db.expunge_all()
    assert db.get(OperationBackupDetails, pruned_id).archive_pruned_at == first_mark


@pytest.mark.unit
def test_marked_rows_fall_with_cleanup_retention_like_any_other(db):
    _settings(db, cleanup_retention_days=30)
    repo = _repo(db)
    old = utc_now() - timedelta(days=40)
    recent = utc_now() - timedelta(days=3)
    db.add_all(
        [
            seed_job_operation(
                db,
                "backup",
                repository_id=repo.id,
                status="completed",
                archive_name="host-a",
                completed_at=old,
                created_at=old,
            ),
            seed_job_operation(
                db,
                "backup",
                repository_id=repo.id,
                status="completed",
                archive_name="host-b",
                completed_at=recent,
                created_at=recent,
            ),
        ]
    )
    db.commit()
    repo_id = repo.id
    assert mark_jobs_of_pruned_archives(db, repo_id, {"host-a", "host-b"}) == 2

    # The mark is not "activity": age comes from the job's own timestamps.
    assert purge_job_rows(db, utc_now() - timedelta(days=30)) == 1
    db.expunge_all()
    assert [d.archive_name for d in db.query(OperationBackupDetails).all()] == [
        "host-b"
    ]


@pytest.mark.unit
def test_borg2_repositories_are_skipped(db):
    _settings(db)
    repo = _repo(db, borg_version=2)
    when = utc_now() - timedelta(days=3)
    job = seed_job_operation(
        db,
        "backup",
        repository_id=repo.id,
        status="completed",
        archive_name="series-name",
        completed_at=when,
        created_at=when,
    )
    db.commit()

    # An archive series shares one name across archives: a name match would
    # hit jobs whose archives still exist, so borg2 is skipped for now.
    assert mark_jobs_of_pruned_archives(db, repo.id, {"series-name"}) == 0
    db.expunge_all()
    assert db.query(OperationBackupDetails).one().archive_pruned_at is None


def _late_prune_log_scenario(db):
    """An agent prune whose 'Pruning archive:' line arrived after the
    completion hook ran (the hook saw a truncated log). Returns the ids of
    the pruned backup's job and of the prune job, and when the prune finished."""
    machine = _machine(db)
    repo = _repo(db)
    when = utc_now() - timedelta(hours=6)
    pruned_backup = seed_job_operation(
        db,
        "backup",
        repository_id=repo.id,
        status="completed",
        archive_name="host-old",
        completed_at=when - timedelta(hours=1),
        created_at=when - timedelta(hours=1),
    )
    db.flush()
    finished = when + timedelta(minutes=5)
    prune_row = seed_job_operation(
        db,
        "prune",
        repository_id=repo.id,
        status="completed",
        started_at=when,
        completed_at=finished,
        created_at=when,
        logs="Starting repository.prune",  # truncated by the race
        has_logs=True,
    )
    db.flush()
    prune_agent_job = AgentJob(
        agent_machine_id=machine.id,
        job_type="repository",
        status="completed",
        payload={
            "job_kind": "repository.prune",
            "operation": {"maintenance_job": {"kind": "prune", "id": prune_row.id}},
        },
        claimed_at=when,
        completed_at=finished,
        created_at=when,
        updated_at=when,
    )
    db.add(prune_agent_job)
    db.flush()
    for seq, message in enumerate(
        [
            "Starting repository.prune",
            "Pruning archive: host-old"
            "                     Mon, 2026-07-20 03:00:00 [aa00] (1/1)",
        ]
    ):
        db.add(
            AgentJobLog(
                agent_job_id=prune_agent_job.id,
                sequence=seq,
                stream="stderr",
                message=message,
                created_at=when,
            )
        )
    db.commit()
    return pruned_backup.id, prune_row.id, finished


@pytest.mark.unit
def test_sweep_marks_from_late_arriving_prune_logs(db):
    _settings(db)
    pruned_id, prune_row_id, prune_finished = _late_prune_log_scenario(db)

    # The daily pass is what runs the sweep; it reports the count.
    assert run_retention(db)["pruned_archive_records_marked"] == 1

    db.expunge_all()
    row = db.get(OperationBackupDetails, pruned_id)
    # the recorded time is when the prune finished, not when the pass ran
    assert row is not None and row.archive_pruned_at == prune_finished
    # The operation's own log file is left as the executor wrote it: the
    # facade's `logs` setter is a no-op once the file has content, so the
    # repair the legacy text column needed no longer applies.
    assert resolve_maintenance_job(db, prune_row_id, "prune") is not None
    # Idempotent: a second sweep finds nothing left to do.
    assert sweep_pruned_archive_records(db) == 0


@pytest.mark.unit
def test_retention_covers_every_surviving_job_table():
    """Phase 9 left one job table plus the rows that are not operations: agent
    jobs, wipe previews, script executions, plan runs and availability
    skips."""
    from app.database.models import AvailabilityScheduleSkip
    from app.services.job_history_retention import _JOB_TABLES

    models = {model for model, _ in _JOB_TABLES}
    assert models == {
        AgentJob,
        Operation,
        RepositoryWipeJob,
        ScriptExecution,
        BackupPlanRun,
        AvailabilityScheduleSkip,
    }


def test_sweep_runs_before_the_save_policy_drops_the_logs_it_reads(db):
    """Under the default policy the pass deletes the log rows of every
    completed agent job regardless of age; the sweep must read the prune
    log first or it never marks anything."""
    _settings(db, log_save_policy="failed_and_warnings")
    pruned_id, _, _ = _late_prune_log_scenario(db)

    results = run_retention(db)

    assert results["pruned_archive_records_marked"] == 1
    assert results["policy_log_rows_deleted"] == 2  # the logs did go afterwards
    db.expunge_all()
    assert db.get(OperationBackupDetails, pruned_id).archive_pruned_at is not None


@pytest.mark.unit
def test_a_backup_that_ran_after_the_prune_keeps_its_reused_name(db):
    """Borg 1 lets a name be reused once its archive is gone: a job created
    once the prune was under way made a different archive and must not be
    marked, even when a late sweep re-reads that prune's log."""
    _settings(db)
    repo = _repo(db)
    prune_started = utc_now() - timedelta(hours=6)
    prune_finished = prune_started + timedelta(minutes=5)
    before_prune = prune_started - timedelta(hours=1)
    # queued while the prune ran, created its archive once the lock was free
    during_prune = prune_started + timedelta(minutes=2)
    after_prune = prune_started + timedelta(hours=1)
    db.add_all(
        [
            seed_job_operation(
                db,
                "backup",
                repository_id=repo.id,
                status="completed",
                archive_name="weekly",
                completed_at=before_prune,
                created_at=before_prune,
            ),
            seed_job_operation(
                db,
                "backup",
                repository_id=repo.id,
                status="completed",
                archive_name="weekly",
                completed_at=prune_finished + timedelta(minutes=1),
                created_at=during_prune,
            ),
            seed_job_operation(
                db,
                "backup",
                repository_id=repo.id,
                status="completed",
                archive_name="weekly",
                completed_at=after_prune,
                created_at=after_prune,
            ),
        ]
    )
    db.commit()
    marked = mark_jobs_of_pruned_archives(
        db,
        repo.id,
        {"weekly"},
        created_before=prune_started,
        pruned_at=prune_finished,
    )
    assert marked == 1
    db.expunge_all()
    rows = (
        db.query(OperationBackupDetails)
        .join(Operation, Operation.id == OperationBackupDetails.operation_id)
        .order_by(Operation.created_at)
        .all()
    )
    # the recorded time is when the prune finished, not when it started
    assert rows[0].archive_pruned_at == prune_finished
    assert rows[1].archive_pruned_at is None
    assert rows[2].archive_pruned_at is None


@pytest.mark.unit
def test_agent_prune_completion_marks_the_pruned_archives_jobs(db):
    """The agents API completion hook is a production call site."""
    from app.api.agents import _finish_linked_repository_operation_job

    _settings(db)
    machine = _machine(db)
    repo = _repo(db)
    when = utc_now() - timedelta(hours=1)
    backup = seed_job_operation(
        db,
        "backup",
        repository_id=repo.id,
        status="completed",
        archive_name="host-old",
        completed_at=when,
        created_at=when,
    )
    prune_row = seed_job_operation(
        db,
        "prune",
        repository_id=repo.id,
        status="running",
        started_at=utc_now(),
        created_at=when,
    )
    db.add_all([backup, prune_row])
    db.flush()
    agent_job = AgentJob(
        agent_machine_id=machine.id,
        job_type="repository",
        status="completed",
        payload={
            "job_kind": "repository.prune",
            "operation": {"maintenance_job": {"kind": "prune", "id": prune_row.id}},
        },
        claimed_at=utc_now(),
        started_at=utc_now(),
        created_at=when,
        updated_at=when,
    )
    db.add(agent_job)
    db.flush()
    db.add(
        AgentJobLog(
            agent_job_id=agent_job.id,
            sequence=0,
            stream="stderr",
            message="Pruning archive: host-old"
            "                     Mon, 2026-07-20 03:00:00 [aa00] (1/1)",
            created_at=when,
        )
    )
    db.commit()
    backup_id = backup.id

    _finish_linked_repository_operation_job(
        agent_job, db, status_value="completed", completed_at=utc_now()
    )
    db.commit()

    db.expunge_all()
    row = db.get(OperationBackupDetails, backup_id)
    assert row is not None and row.archive_pruned_at is not None


@pytest.mark.unit
def test_operations_rows_fall_with_cleanup_retention(db):
    from app.database.models import Operation
    from app.services.operations.enqueue import enqueue

    settings = _settings(db)
    repo = Repository(name="ops", path="/tmp/ops", encryption="none", compression="lz4")
    db.add(repo)
    db.commit()
    old = enqueue(db, "stats", repository_id=repo.id)
    old.status = "completed"
    old.created_at = utc_now() - timedelta(days=200)
    old.completed_at = utc_now() - timedelta(days=200)
    fresh = enqueue(db, "stats", repository_id=repo.id)
    fresh.status = "completed"
    fresh.completed_at = utc_now()
    db.commit()
    old_id, fresh_id = old.id, fresh.id
    run_retention(db, settings)
    ids = {o.id for o in db.query(Operation)}
    assert fresh_id in ids and old_id not in ids


@pytest.mark.unit
def test_operation_log_files_follow_both_retention_windows(db, tmp_path):
    """Operations log to files, not to an inline column, so the row sweep and
    the log sweep must both reach the files or they outlive everything."""
    from app.database.models import Operation
    from app.services.operations.enqueue import enqueue

    settings = _settings(db)
    repo = Repository(
        name="ops-logs", path="/tmp/ops-logs", encryption="none", compression="lz4"
    )
    db.add(repo)
    db.commit()

    def _op(age_days):
        op = enqueue(db, "stats", repository_id=repo.id)
        op.status = "completed"
        op.completed_at = utc_now() - timedelta(days=age_days)
        path = tmp_path / f"operation_{op.id}.log"
        path.write_text("borg output")
        op.log_file_path = str(path)
        db.commit()
        return op, path

    purged_row, purged_log = _op(200)
    aged_log_op, aged_log = _op(60)
    fresh_op, fresh_log = _op(0)
    purged_row_id, aged_id, fresh_id = purged_row.id, aged_log_op.id, fresh_op.id

    run_retention(db, settings)
    db.expunge_all()

    # Row past cleanup_retention_days: row and file both gone.
    assert db.get(Operation, purged_row_id) is None
    assert not purged_log.exists()
    # Row past log_retention_days only: file gone, row and its history kept.
    assert db.get(Operation, aged_id) is not None
    assert db.get(Operation, aged_id).log_file_path is None
    assert not aged_log.exists()
    # Fresh row: untouched.
    assert db.get(Operation, fresh_id).log_file_path == str(fresh_log)
    assert fresh_log.exists()


@pytest.mark.unit
def test_row_purge_takes_log_files_along_for_every_model(db, tmp_path):
    # #895: deleting expired rows must unlink their log_file_path files -
    # uniformly, not as an Operation-only special case.
    from app.database.models import Repository

    settings = _settings(db)
    repo = Repository(
        name="Retention Repo",
        path="/tmp/retention-repo",
        encryption="none",
        repository_type="local",
    )
    db.add(repo)
    db.commit()
    old = utc_now() - timedelta(days=120)
    fresh = utc_now() - timedelta(days=10)

    expired_files = []
    kept_file = tmp_path / "kept_check.log"
    kept_file.write_text("keep me", encoding="utf-8")
    missing_file = tmp_path / "already_gone.log"  # never created

    for index, kind in enumerate(("check", "compact", "restore_check")):
        log_file = tmp_path / f"expired_{index}.log"
        log_file.write_text("old log", encoding="utf-8")
        expired_files.append(log_file)
        seed_job_operation(
            db,
            kind,
            repository_id=repo.id,
            status="completed",
            completed_at=old,
            created_at=old,
            log_file_path=str(log_file),
        )
    # An expired row whose file is already gone must not break the purge.
    db.add(
        seed_job_operation(
            db,
            "check",
            repository_id=repo.id,
            status="failed",
            completed_at=old,
            created_at=old,
            log_file_path=str(missing_file),
        )
    )
    # A row inside the window keeps row AND file.
    db.add(
        seed_job_operation(
            db,
            "check",
            repository_id=repo.id,
            status="completed",
            completed_at=fresh,
            created_at=fresh,
            log_file_path=str(kept_file),
        )
    )
    db.commit()

    run_retention(db, settings)

    db.expunge_all()
    for log_file in expired_files:
        assert not log_file.exists()
    assert kept_file.exists()
    assert db.query(Operation).filter(Operation.kind == "check").count() == 1


@pytest.mark.unit
def test_orphaned_log_files_are_swept_by_age_unless_referenced(
    db, tmp_path, monkeypatch
):
    # Files whose rows were purged before file cleanup existed have no row
    # pointing at them anymore - only an age-based filesystem sweep can
    # reclaim them. Referenced and young files must survive.
    import os
    import time as time_module

    from app.services.job_history_retention import sweep_orphaned_log_files

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(
        "app.services.job_history_retention.app_config.data_dir", str(tmp_path)
    )

    old_ts = time_module.time() - 200 * 86400

    orphan_old = log_dir / "check_job_1_20260101_000000.log"
    orphan_old.write_text("orphan", encoding="utf-8")
    os.utime(orphan_old, (old_ts, old_ts))

    referenced_old = log_dir / "check_job_2_20260101_000000.log"
    referenced_old.write_text("still referenced", encoding="utf-8")
    os.utime(referenced_old, (old_ts, old_ts))

    orphan_young = log_dir / "check_job_3_20260901_000000.log"
    orphan_young.write_text("young orphan", encoding="utf-8")

    not_a_log = log_dir / "notes.txt"
    not_a_log.write_text("keep", encoding="utf-8")
    os.utime(not_a_log, (old_ts, old_ts))

    repo = Repository(
        name="Sweep Repo",
        path="/tmp/sweep-repo",
        encryption="none",
        repository_type="local",
    )
    db.add(repo)
    db.commit()
    db.add(
        seed_job_operation(
            db,
            "check",
            repository_id=repo.id,
            status="completed",
            completed_at=utc_now(),
            created_at=utc_now(),
            log_file_path=str(referenced_old),
        )
    )
    db.commit()

    removed = sweep_orphaned_log_files(db, utc_now() - timedelta(days=90))

    assert removed == 1
    assert not orphan_old.exists()
    assert referenced_old.exists()
    assert orphan_young.exists()
    assert not_a_log.exists()


@pytest.mark.unit
def test_shared_log_file_survives_when_a_live_row_still_references_it(db, tmp_path):
    # log_file_path is not unique: an expired and a retained row can name the
    # same file - purging the expired row must not take the survivor's log.

    settings = _settings(db)
    old = utc_now() - timedelta(days=120)
    fresh = utc_now() - timedelta(days=10)

    shared = tmp_path / "shared_check.log"
    shared.write_text("shared", encoding="utf-8")
    solo = tmp_path / "solo_check.log"
    solo.write_text("solo", encoding="utf-8")

    repo = Repository(
        name="Shared Log Repo",
        path="/tmp/shared-log-repo",
        encryption="none",
        repository_type="local",
    )
    db.add(repo)
    db.commit()
    db.add_all(
        [
            seed_job_operation(
                db,
                "check",
                repository_id=repo.id,
                status="completed",
                completed_at=old,
                created_at=old,
                log_file_path=str(shared),
            ),
            seed_job_operation(
                db,
                "check",
                repository_id=repo.id,
                status="completed",
                completed_at=fresh,
                created_at=fresh,
                log_file_path=str(shared),
            ),
            seed_job_operation(
                db,
                "check",
                repository_id=repo.id,
                status="completed",
                completed_at=old,
                created_at=old,
                log_file_path=str(solo),
            ),
        ]
    )
    db.commit()

    run_retention(db, settings)

    db.expunge_all()
    assert shared.exists()
    assert not solo.exists()


def _phase6_operation(db, kind, *, age_days, status="completed"):
    from app.database.models import Operation

    completed = utc_now() - timedelta(days=age_days)
    op = Operation(
        repository_id=None,
        kind=kind,
        category={"wipe": "maintenance", "restore": "restore"}.get(kind, "mirror"),
        status=status,
        trigger="manual",
        priority=0,
        run_id=f"run-{kind}-{age_days}",
        created_at=completed,
        started_at=completed,
        completed_at=completed,
    )
    db.add(op)
    db.commit()
    return op


@pytest.mark.unit
def test_deleting_an_operation_takes_its_extension_rows(db):
    """Spec 7.8: extension rows must not outlive their operation. They have no
    timestamp of their own, so the cascade on operations.id is what enforces
    it; this pins that the cascade is actually configured."""
    from app.database.models import (
        Operation,
        OperationRcloneDetails,
        OperationRestoreDetails,
        OperationWipeDetails,
    )
    from app.services.operations.details import (
        rclone_details,
        restore_details,
        wipe_details,
    )

    settings = _settings(db)
    wipe_op = _phase6_operation(db, "wipe", age_days=400)
    rclone_op = _phase6_operation(db, "rclone_sync", age_days=400)
    restore_op = _phase6_operation(db, "restore", age_days=400)
    wipe_details(db, wipe_op).archive_count = 2
    rclone_details(db, rclone_op).operation = "sync"
    restore_details(db, restore_op).archive = "a"
    db.commit()

    run_retention(db, settings)

    db.expunge_all()
    assert db.query(Operation).count() == 0
    assert db.query(OperationWipeDetails).count() == 0
    assert db.query(OperationRcloneDetails).count() == 0
    assert db.query(OperationRestoreDetails).count() == 0


@pytest.mark.unit
def test_extension_log_columns_are_cleared_at_the_log_window(db):
    """Inside the cleanup window but outside the log window: the row stays and
    its captured output goes, matching what the legacy columns did."""
    from app.database.models import (
        Operation,
        OperationRcloneDetails,
        OperationWipeDetails,
    )
    from app.services.operations.details import rclone_details, wipe_details

    settings = _settings(db)
    wipe_op = _phase6_operation(db, "wipe", age_days=60)
    rclone_op = _phase6_operation(db, "rclone_sync", age_days=60)
    wipe_row = wipe_details(db, wipe_op)
    wipe_row.dry_run_output = "would delete archive-a"
    wipe_row.archive_count = 3
    rclone_row = rclone_details(db, rclone_op)
    rclone_row.log_text = "copied 2 files"
    rclone_row.error_text = "a warning"
    db.commit()
    wipe_id, rclone_id = wipe_op.id, rclone_op.id

    results = run_retention(db, settings)

    db.expunge_all()
    assert db.query(Operation).count() == 2
    assert results["operation_detail_logs_cleared"] == 2
    assert db.get(OperationRcloneDetails, rclone_id).log_text is None
    assert db.get(OperationRcloneDetails, rclone_id).error_text is None
    assert db.get(OperationWipeDetails, wipe_id).dry_run_output is None
    # History stays: only the bulky captured output goes.
    assert db.get(OperationWipeDetails, wipe_id).archive_count == 3


@pytest.mark.unit
def test_recent_extension_log_columns_are_kept(db):
    from app.database.models import OperationRcloneDetails
    from app.services.operations.details import rclone_details

    settings = _settings(db)
    rclone_op = _phase6_operation(db, "rclone_sync", age_days=2)
    rclone_details(db, rclone_op).log_text = "copied 2 files"
    db.commit()
    rclone_id = rclone_op.id

    run_retention(db, settings)

    db.expunge_all()
    assert db.get(OperationRcloneDetails, rclone_id).log_text == "copied 2 files"


@pytest.mark.unit
def test_sweep_marks_only_the_repository_of_the_prune_it_resolves(
    db, monkeypatch, tmp_path
):
    """The prune's payload names its operation. Another repository's backup of
    the same archive name must not be marked from it, and a data directory
    that cannot be written loses the log repair, not the marking."""
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    _settings(db)
    machine = _machine(db)
    repo_b = _repo(db)
    repo_a = Repository(
        name="other", path="/repo/other", encryption="none", borg_version=1
    )
    db.add(repo_a)
    db.flush()
    when = utc_now() - timedelta(hours=6)
    finished = when + timedelta(minutes=5)
    backups = {
        repo.id: seed_job_operation(
            db,
            "backup",
            repository_id=repo.id,
            status="completed",
            archive_name="host-old",
            completed_at=when - timedelta(hours=1),
            created_at=when - timedelta(hours=1),
        ).id
        for repo in (repo_b, repo_a)
    }
    prune = seed_job_operation(
        db,
        "prune",
        repository_id=repo_b.id,
        status="completed",
        started_at=when,
        completed_at=finished,
        created_at=when,
    )
    agent_job = AgentJob(
        agent_machine_id=machine.id,
        job_type="repository",
        status="completed",
        payload={
            "job_kind": "repository.prune",
            "operation": {
                "maintenance_job": {
                    "kind": "prune",
                    "id": prune.id,
                    "table": "operations",
                }
            },
        },
        claimed_at=when,
        completed_at=finished,
        created_at=when,
        updated_at=when,
    )
    db.add(agent_job)
    db.flush()
    db.add(
        AgentJobLog(
            agent_job_id=agent_job.id,
            sequence=0,
            stream="stderr",
            message="Pruning archive: host-old"
            "                     Mon, 2026-07-20 03:00:00 [aa00] (1/1)",
            created_at=when,
        )
    )
    db.commit()
    repo_a_id, repo_b_id, prune_id = repo_a.id, repo_b.id, prune.id

    with patch("builtins.open", side_effect=OSError("read-only file system")):
        assert sweep_pruned_archive_records(db) == 1
    db.expunge_all()
    assert db.get(OperationBackupDetails, backups[repo_b_id]).archive_pruned_at == (
        finished
    )
    db.query(OperationBackupDetails).filter(
        OperationBackupDetails.operation_id == backups[repo_b_id]
    ).update({OperationBackupDetails.archive_pruned_at: None})
    db.commit()

    assert sweep_pruned_archive_records(db) == 1

    db.expunge_all()
    assert db.get(OperationBackupDetails, backups[repo_b_id]).archive_pruned_at == (
        finished
    )
    assert db.get(OperationBackupDetails, backups[repo_a_id]).archive_pruned_at is None
    # the repair wrote the full log to the operation's own file
    repaired = resolve_maintenance_job(db, prune_id, "prune")
    assert "Pruning archive: host-old" in repaired.logs


@pytest.mark.unit
def test_sweep_ignores_a_prune_payload_from_a_dropped_table(db):
    """An agent job queued before the collapse names an id from a table that
    is gone; the sweep must not mark anything from an operation that happens
    to hold that id."""
    _settings(db)
    machine = _machine(db)
    repo = _repo(db)
    when = utc_now() - timedelta(hours=6)
    finished = when + timedelta(minutes=5)
    pruned = seed_job_operation(
        db,
        "backup",
        repository_id=repo.id,
        status="completed",
        archive_name="host-old",
        completed_at=when - timedelta(hours=1),
        created_at=when - timedelta(hours=1),
    )
    prune = seed_job_operation(
        db,
        "prune",
        repository_id=repo.id,
        status="completed",
        started_at=when,
        completed_at=finished,
        created_at=when,
    )
    agent_job = AgentJob(
        agent_machine_id=machine.id,
        job_type="repository",
        status="completed",
        payload={
            "job_kind": "repository.prune",
            "operation": {
                "maintenance_job": {
                    "kind": "prune",
                    "id": prune.id,
                    "table": "prune_jobs",
                }
            },
        },
        claimed_at=when,
        completed_at=finished,
        created_at=when,
        updated_at=when,
    )
    db.add(agent_job)
    db.flush()
    db.add(
        AgentJobLog(
            agent_job_id=agent_job.id,
            sequence=0,
            stream="stderr",
            message="Pruning archive: host-old"
            "                     Mon, 2026-07-20 03:00:00 [aa00] (1/1)",
            created_at=when,
        )
    )
    db.commit()
    pruned_id = pruned.id

    assert sweep_pruned_archive_records(db) == 0

    db.expunge_all()
    assert db.get(OperationBackupDetails, pruned_id).archive_pruned_at is None
