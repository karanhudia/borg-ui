"""Unit tests for the DB job-history retention service.

Covers the two windows independently: log content (agent_job_logs rows +
inline `logs` columns) falls at log_retention_days, job rows of every kind
fall at cleanup_retention_days regardless of status — age comes from the
freshest timestamp, so genuinely live work never looks old.
"""

from datetime import timedelta

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
    purge_jobs_for_pruned_archives,
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
def test_pruned_archives_take_their_job_records_along(db, tmp_path):
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
    pruned_id, kept_id, agent_id = pruned.id, kept.id, agent_run.id

    removed = purge_jobs_for_pruned_archives(db, repo.id, {"host-old"})

    db.expunge_all()
    assert removed == 1
    assert db.get(BackupJob, pruned_id) is None
    assert db.get(BackupJob, kept_id) is not None
    # The linked agent job dies with its backup job, its log rows cascade.
    assert db.get(AgentJob, agent_id) is None
    assert db.query(AgentJobLog).count() == 0
    assert not log_file.exists()


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
    assert purge_jobs_for_pruned_archives(db, repo.id, {"series-name"}) == 0
    assert db.query(BackupJob).count() == 1


@pytest.mark.unit
def test_sweep_cascades_from_late_arriving_prune_logs(db, tmp_path):
    # The completion hook races log ingestion and can see an empty log; the
    # sweep re-parses the full agent log later and cascades idempotently.
    _settings(db)
    machine = _machine(db)
    repo = _repo(db)
    when = utc_now() - timedelta(hours=6)
    pruned_backup = BackupJob(
        repository_id=repo.id,
        status="completed",
        archive_name="host-old",
        completed_at=when,
        created_at=when,
    )
    db.add(pruned_backup)
    db.flush()
    prune_row = PruneJob(
        repository_id=repo.id,
        status="completed",
        completed_at=when,
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
        completed_at=when,
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
    pruned_id, prune_row_id = pruned_backup.id, prune_row.id

    removed = sweep_pruned_archive_records(db)

    db.expunge_all()
    assert removed == 1
    assert db.get(BackupJob, pruned_id) is None
    # The truncated stored log got repaired from the full agent log.
    assert "Pruning archive" in db.get(PruneJob, prune_row_id).logs
    # Idempotent: a second sweep finds nothing left to do.
    assert sweep_pruned_archive_records(db) == 0
