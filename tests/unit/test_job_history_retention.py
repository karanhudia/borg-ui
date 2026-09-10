"""Unit tests for the DB job-history retention service.

Covers the two windows independently: log content (agent_job_logs rows +
inline `logs` columns) falls at log_retention_days, job rows of every kind
fall at cleanup_retention_days regardless of status — age comes from the
freshest timestamp, so genuinely live work never looks old.
"""

from datetime import timedelta

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    AgentJob,
    PruneJob,
    AgentJobLog,
    AgentMachine,
    Base,
    BackupJob,
    BackupPlan,
    BackupPlanRun,
    Repository,
    CheckJob,
    RepositoryWipeJob,
    ScriptExecution,
    SystemSettings,
    utc_now,
)
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
def test_inline_logs_cleared_history_kept(db):
    settings = _settings(db)
    when = utc_now() - timedelta(days=40)
    job = BackupJob(
        status="completed",
        completed_at=when,
        created_at=when,
        logs="borg output " * 100,
        error_message="kept",
        nfiles=123,
    )
    repo = Repository(name="r", path="/tmp/r")
    db.add(repo)
    db.commit()
    check = CheckJob(
        repository_id=repo.id,
        status="completed",
        completed_at=when,
        created_at=when,
        logs="check output",
        has_logs=True,
    )
    db.add_all([job, check])
    db.commit()

    results = run_retention(db, settings)

    assert results["inline_logs_cleared"] == 2
    db.refresh(job)
    db.refresh(check)
    assert job.logs is None
    assert job.error_message == "kept"  # history stays
    assert job.nfiles == 123
    assert check.logs is None
    assert check.has_logs is False


@pytest.mark.unit
def test_expired_job_rows_deleted_and_agent_logs_cascade(db):
    settings = _settings(db)
    machine = _machine(db)
    expired = _agent_job(db, machine, "failed", age_days=120, log_lines=2)
    kept = _agent_job(db, machine, "completed", age_days=40)
    old_backup = BackupJob(
        status="completed",
        completed_at=utc_now() - timedelta(days=120),
        created_at=utc_now() - timedelta(days=120),
    )
    db.add(old_backup)
    db.commit()
    expired_id, kept_id = expired.id, kept.id

    results = run_retention(db, settings)

    # Bulk deletes bypass the identity map; drop it before re-reading.
    db.expunge_all()
    assert db.get(AgentJob, expired_id) is None
    assert db.get(AgentJob, kept_id) is not None
    assert db.query(BackupJob).count() == 0
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
    wipe = RepositoryWipeJob(
        repository_id=None,
        status="previewed",  # never reached a terminal status
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
    fresh_backup = BackupJob(
        status="completed",
        completed_at=utc_now() - timedelta(days=1),
        created_at=utc_now() - timedelta(days=1),
        logs="clean success output",
        error_message=None,
    )
    db.add(fresh_backup)
    db.commit()

    results = run_retention(db, settings)

    # Day-old logs, way inside the age window - the policy drops them anyway.
    assert results["policy_log_rows_deleted"] == 3
    assert results["policy_inline_logs_cleared"] == 1
    remaining = {row.agent_job_id for row in db.query(AgentJobLog)}
    assert remaining == {warned.id, failed.id}
    db.refresh(fresh_backup)
    assert fresh_backup.logs is None
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
    pruned = BackupJob(
        repository_id=repo.id,
        status="completed",
        archive_name="host-old",
        log_file_path=str(log_file),
        completed_at=when,
        created_at=when,
    )
    kept = BackupJob(
        repository_id=repo.id,
        status="completed",
        archive_name="host-new",
        completed_at=when,
        created_at=when,
    )
    db.add_all([pruned, kept])
    db.flush()
    agent_run = _agent_job(db, machine, "completed", age_days=3, log_lines=2)
    agent_run.backup_job_id = pruned.id
    db.commit()
    repo_id = repo.id
    pruned_id, kept_id, agent_id = pruned.id, kept.id, agent_run.id

    marked = mark_jobs_of_pruned_archives(db, repo_id, {"host-old"})

    db.expunge_all()
    assert marked == 1
    pruned_row = db.get(BackupJob, pruned_id)
    assert pruned_row is not None and pruned_row.archive_pruned_at is not None
    assert pruned_row.status == "completed"
    assert db.get(BackupJob, kept_id).archive_pruned_at is None
    assert db.get(AgentJob, agent_id) is not None
    assert db.query(AgentJobLog).count() == 2
    assert log_file.exists()
    # A second prune report for the same archive changes nothing.
    first_mark = pruned_row.archive_pruned_at
    assert mark_jobs_of_pruned_archives(db, repo_id, {"host-old"}) == 0
    db.expunge_all()
    assert db.get(BackupJob, pruned_id).archive_pruned_at == first_mark


@pytest.mark.unit
def test_marked_rows_fall_with_cleanup_retention_like_any_other(db):
    _settings(db, cleanup_retention_days=30)
    repo = _repo(db)
    old = utc_now() - timedelta(days=40)
    recent = utc_now() - timedelta(days=3)
    db.add_all(
        [
            BackupJob(
                repository_id=repo.id,
                status="completed",
                archive_name="host-a",
                completed_at=old,
                created_at=old,
            ),
            BackupJob(
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
    assert [j.archive_name for j in db.query(BackupJob).all()] == ["host-b"]


@pytest.mark.unit
def test_borg2_repositories_are_skipped(db):
    _settings(db)
    repo = _repo(db, borg_version=2)
    when = utc_now() - timedelta(days=3)
    job = BackupJob(
        repository_id=repo.id,
        status="completed",
        archive_name="series-name",
        completed_at=when,
        created_at=when,
    )
    db.add(job)
    db.commit()

    # An archive series shares one name across archives: a name match would
    # hit jobs whose archives still exist, so borg2 is skipped for now.
    assert mark_jobs_of_pruned_archives(db, repo.id, {"series-name"}) == 0
    db.expunge_all()
    assert db.query(BackupJob).one().archive_pruned_at is None


def _late_prune_log_scenario(db):
    """An agent prune whose 'Pruning archive:' line arrived after the
    completion hook ran (the hook saw a truncated log). Returns the ids of
    the pruned backup's job and of the prune job, and when the prune finished."""
    machine = _machine(db)
    repo = _repo(db)
    when = utc_now() - timedelta(hours=6)
    pruned_backup = BackupJob(
        repository_id=repo.id,
        status="completed",
        archive_name="host-old",
        completed_at=when - timedelta(hours=1),
        created_at=when - timedelta(hours=1),
    )
    db.add(pruned_backup)
    db.flush()
    finished = when + timedelta(minutes=5)
    prune_row = PruneJob(
        repository_id=repo.id,
        status="completed",
        started_at=when,
        completed_at=finished,
        created_at=when,
        logs="Starting repository.prune",  # truncated by the race
        has_logs=True,
    )
    db.add(prune_row)
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
    row = db.get(BackupJob, pruned_id)
    # the recorded time is when the prune finished, not when the pass ran
    assert row is not None and row.archive_pruned_at == prune_finished
    # The truncated stored log got repaired from the full agent log.
    assert "Pruning archive" in db.get(PruneJob, prune_row_id).logs
    # Idempotent: a second sweep finds nothing left to do.
    assert sweep_pruned_archive_records(db) == 0


@pytest.mark.unit
def test_retention_covers_operations_and_the_legacy_maintenance_tables():
    """Phase 5 moved the five maintenance kinds to `operations`, but their
    legacy tables still hold pre-migration history that must keep aging out
    until phase 9 deletes the tables outright."""
    from app.database.models import (
        CompactJob,
        DeleteArchiveJob,
        Operation,
        RestoreCheckJob,
    )
    from app.services.job_history_retention import _JOB_TABLES

    models = {model for model, _ in _JOB_TABLES}
    assert Operation in models
    assert {CheckJob, PruneJob, CompactJob, RestoreCheckJob, DeleteArchiveJob} <= models


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
    assert db.get(BackupJob, pruned_id).archive_pruned_at is not None


@pytest.mark.unit
def test_jobs_that_carry_only_the_repository_path_are_marked_too(db):
    """Rows written before repository_id existed (or after the FK was
    nulled) match by path, as every other job-to-repository lookup does."""
    _settings(db)
    repo = _repo(db)
    when = utc_now() - timedelta(days=3)
    db.add(
        BackupJob(
            repository=repo.path + "/",
            status="completed",
            archive_name="host-old",
            completed_at=when,
            created_at=when,
        )
    )
    db.commit()
    assert mark_jobs_of_pruned_archives(db, repo.id, {"host-old"}) == 1
    db.expunge_all()
    assert db.query(BackupJob).one().archive_pruned_at is not None


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
            BackupJob(
                repository_id=repo.id,
                status="completed",
                archive_name="weekly",
                completed_at=before_prune,
                created_at=before_prune,
            ),
            BackupJob(
                repository_id=repo.id,
                status="completed",
                archive_name="weekly",
                completed_at=prune_finished + timedelta(minutes=1),
                created_at=during_prune,
            ),
            BackupJob(
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
    rows = db.query(BackupJob).order_by(BackupJob.created_at).all()
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
    backup = BackupJob(
        repository_id=repo.id,
        status="completed",
        archive_name="host-old",
        completed_at=when,
        created_at=when,
    )
    prune_row = PruneJob(
        repository_id=repo.id, status="running", started_at=utc_now(), created_at=when
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
    row = db.get(BackupJob, backup_id)
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
    from app.database.models import CheckJob, CompactJob, Repository, RestoreCheckJob

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

    for index, model in enumerate((CheckJob, CompactJob, RestoreCheckJob)):
        log_file = tmp_path / f"expired_{index}.log"
        log_file.write_text("old log", encoding="utf-8")
        expired_files.append(log_file)
        db.add(
            model(
                repository_id=repo.id,
                status="completed",
                completed_at=old,
                created_at=old,
                log_file_path=str(log_file),
            )
        )
    # An expired row whose file is already gone must not break the purge.
    db.add(
        CheckJob(
            repository_id=repo.id,
            status="failed",
            completed_at=old,
            created_at=old,
            log_file_path=str(missing_file),
        )
    )
    # A row inside the window keeps row AND file.
    db.add(
        CheckJob(
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
    from app.database.models import CheckJob as CheckJobModel

    assert db.query(CheckJobModel).count() == 1


@pytest.mark.unit
def test_orphaned_log_files_are_swept_by_age_unless_referenced(
    db, tmp_path, monkeypatch
):
    # Files whose rows were purged before file cleanup existed have no row
    # pointing at them anymore - only an age-based filesystem sweep can
    # reclaim them. Referenced and young files must survive.
    import os
    import time as time_module

    from app.database.models import CheckJob
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
        CheckJob(
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
    from app.database.models import CheckJob

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
            CheckJob(
                repository_id=repo.id,
                status="completed",
                completed_at=old,
                created_at=old,
                log_file_path=str(shared),
            ),
            CheckJob(
                repository_id=repo.id,
                status="completed",
                completed_at=fresh,
                created_at=fresh,
                log_file_path=str(shared),
            ),
            CheckJob(
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
def test_sweep_resolves_an_operations_backed_prune_by_its_table(
    db, monkeypatch, tmp_path
):
    """Since phase 5 an agent prune's `maintenance_job` names an `operations`
    row, and its payload says so. The sweep must read that row, not the
    legacy `prune_jobs` row that happens to share the id (the id spaces are
    separate): here that decoy belongs to another repository, whose backup
    must not be marked."""
    import uuid

    from app.database.models import Operation

    # the repaired log is a file under data_dir
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
    backups = {}
    for repo, name in ((repo_b, "host-old"), (repo_a, "host-old")):
        job = BackupJob(
            repository_id=repo.id,
            status="completed",
            archive_name=name,
            completed_at=when - timedelta(hours=1),
            created_at=when - timedelta(hours=1),
        )
        db.add(job)
        db.flush()
        backups[repo.id] = job.id
    operation = Operation(
        kind="prune",
        category="maintenance",
        status="completed",
        repository_id=repo_b.id,
        run_id=str(uuid.uuid4()),
        started_at=when,
        completed_at=finished,
        created_at=when,
    )
    db.add(operation)
    db.flush()
    decoy = PruneJob(
        id=operation.id,
        repository_id=repo_a.id,
        status="completed",
        started_at=when,
        completed_at=finished,
        created_at=when,
        logs="decoy",
        has_logs=True,
    )
    db.add(decoy)
    agent_job = AgentJob(
        agent_machine_id=machine.id,
        job_type="repository",
        status="completed",
        payload={
            "job_kind": "repository.prune",
            "operation": {
                "maintenance_job": {
                    "kind": "prune",
                    "id": operation.id,
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

    repo_a_id, repo_b_id, operation_id = repo_a.id, repo_b.id, operation.id

    # A data directory that cannot be written loses the log repair, not the
    # marking (the retention pass must not abort on it).
    with patch("builtins.open", side_effect=OSError("read-only file system")):
        assert sweep_pruned_archive_records(db) == 1
    db.expunge_all()
    assert db.get(BackupJob, backups[repo_b_id]).archive_pruned_at == finished
    db.query(BackupJob).filter(BackupJob.id == backups[repo_b_id]).update(
        {BackupJob.archive_pruned_at: None}, synchronize_session=False
    )
    db.commit()

    assert sweep_pruned_archive_records(db) == 1

    db.expunge_all()
    assert db.get(BackupJob, backups[repo_b_id]).archive_pruned_at == finished
    assert db.get(BackupJob, backups[repo_a_id]).archive_pruned_at is None
    assert db.get(PruneJob, operation_id).logs == "decoy"
    # The operation keeps its log in a file; the repair writes the full log
    # there (the facade's own setter would leave an existing file alone).
    from app.services.operations.job_facade import MaintenanceJobFacade

    repaired = MaintenanceJobFacade(db, db.get(Operation, operation_id))
    assert "Pruning archive: host-old" in repaired.logs


@pytest.mark.unit
def test_sweep_resolves_a_table_less_prune_by_its_repository(db):
    """An agent prune queued by the build before the table marker names an
    `operations` id without saying so. The payload's repository tells it
    apart from a legacy row sharing the id."""
    import uuid

    from app.database.models import Operation

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
    pruned = BackupJob(
        repository_id=repo_b.id,
        status="completed",
        archive_name="host-old",
        completed_at=when - timedelta(hours=1),
        created_at=when - timedelta(hours=1),
    )
    db.add(pruned)
    db.flush()
    operation = Operation(
        kind="prune",
        category="maintenance",
        status="completed",
        repository_id=repo_b.id,
        run_id=str(uuid.uuid4()),
        started_at=when,
        completed_at=finished,
        created_at=when,
    )
    db.add(operation)
    db.flush()
    db.add(
        PruneJob(
            id=operation.id,
            repository_id=repo_a.id,
            status="completed",
            started_at=when,
            completed_at=finished,
            created_at=when,
        )
    )
    agent_job = AgentJob(
        agent_machine_id=machine.id,
        job_type="repository",
        status="completed",
        payload={
            "job_kind": "repository.prune",
            "repository": {"id": repo_b.id, "path": repo_b.path},
            "operation": {"maintenance_job": {"kind": "prune", "id": operation.id}},
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

    assert sweep_pruned_archive_records(db) == 1

    db.expunge_all()
    assert db.get(BackupJob, pruned_id).archive_pruned_at == finished
