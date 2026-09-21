"""GET /api/activity/recent reads what its backups need once per window (#1090)."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

from app.database.models import (
    AgentJob,
    AgentJobLog,
    AgentMachine,
    Archive,
    BackupPlan,
    BackupPlanRun,
    Operation,
    OperationBackupDetails,
    Repository,
    ScheduledJob,
    SystemSettings,
)
from tests.utils.statements import count_statements

START = datetime(2026, 9, 1, 2, 0, 0)


def _set_log_save_policy(db, policy):
    settings = db.query(SystemSettings).first()
    if settings is None:
        settings = SystemSettings()
        db.add(settings)
    settings.log_save_policy = policy
    db.commit()


def _add_plan_runs(db, repo, machine, plan, start, stop):
    """One plan run per index, shaped like an agent installation's: a backup
    with its archive, agent job and log lines, then prune, compact and an
    index follow-up."""
    for i in range(start, stop):
        at = START + timedelta(hours=i)
        run = BackupPlanRun(
            backup_plan_id=plan.id, trigger="schedule", status="completed"
        )
        db.add(run)
        db.flush()
        backup = Operation(
            repository_id=repo.id,
            kind="backup",
            category="backup",
            status="completed",
            trigger="plan",
            run_id=f"run-{i}",
            execution_mode="agent",
            backup_plan_run_id=run.id,
            started_at=at,
            completed_at=at + timedelta(minutes=1),
        )
        db.add(backup)
        db.flush()
        db.add(
            OperationBackupDetails(operation_id=backup.id, archive_name=f"archive-{i}")
        )
        db.add(
            Archive(
                repository_id=repo.id,
                borg_id=f"{i:064x}",
                name=f"archive-{i}",
                series="archive",
                start=at,
                backup_operation_id=backup.id,
            )
        )
        agent_job = AgentJob(
            agent_machine_id=machine.id,
            operation_id=backup.id,
            job_type="backup",
            status="completed",
            payload={},
        )
        db.add(agent_job)
        db.flush()
        db.add_all(
            AgentJobLog(
                agent_job_id=agent_job.id,
                sequence=n,
                stream="stdout",
                created_at=at,
                # The newest run's log holds the word the default policy
                # looks for, so its answer has to come from the log lines.
                message="Warning: file changed" if (i, n) == (stop - 1, 1) else "A f",
            )
            for n in range(2)
        )
        previous = backup
        for n, (kind, category, trigger) in enumerate(
            (
                ("prune", "maintenance", "plan"),
                ("compact", "maintenance", "plan"),
                ("archive_sync", "index", "followup"),
            ),
            start=1,
        ):
            step = Operation(
                repository_id=repo.id,
                kind=kind,
                category=category,
                status="completed",
                trigger=trigger,
                run_id=f"run-{i}",
                backup_plan_run_id=run.id,
                depends_on_id=previous.id,
                started_at=at + timedelta(minutes=1 + n),
                completed_at=at + timedelta(minutes=2 + n),
            )
            db.add(step)
            db.flush()
            previous = step
    db.commit()


def _seed(db):
    machine = AgentMachine(
        name="machine", agent_id="agent-1", token_hash="x", token_prefix="p"
    )
    repo = Repository(name="repo", path="/repos/one", encryption="none")
    plan = BackupPlan(name="nightly", enabled=True, source_directories="[]")
    db.add_all([machine, repo, plan])
    db.commit()
    return repo, machine, plan


def _recent(test_client, test_db, admin_headers):
    """The list's rows and the number of statements the request issued."""
    response, statements = count_statements(
        test_db,
        lambda: test_client.get("/api/activity/recent?limit=50", headers=admin_headers),
    )
    return response.json(), statements


@pytest.mark.unit
@pytest.mark.parametrize("policy", ["failed_and_warnings", "all_jobs"])
def test_statement_count_does_not_grow_with_backups(
    test_client, test_db, admin_headers, policy
):
    _set_log_save_policy(test_db, policy)
    repo, machine, plan = _seed(test_db)

    _add_plan_runs(test_db, repo, machine, plan, 0, 3)
    rows, three = _recent(test_client, test_db, admin_headers)
    assert len([row for row in rows if row["type"] == "backup"]) == 3

    _add_plan_runs(test_db, repo, machine, plan, 3, 12)
    rows, twelve = _recent(test_client, test_db, admin_headers)
    assert len([row for row in rows if row["type"] == "backup"]) == 12

    assert twelve == three


@pytest.mark.unit
def test_backup_rows_keep_their_looked_up_fields(test_client, test_db, admin_headers):
    _set_log_save_policy(test_db, "failed_and_warnings")
    repo, machine, plan = _seed(test_db)
    _add_plan_runs(test_db, repo, machine, plan, 0, 3)
    schedule = ScheduledJob(
        name="direct", cron_expression="0 2 * * *", repository_id=repo.id
    )
    test_db.add(schedule)
    test_db.flush()
    scheduled = Operation(
        repository_id=repo.id,
        kind="backup",
        category="backup",
        status="failed",
        trigger="schedule",
        run_id="run-scheduled",
        scheduled_job_id=schedule.id,
        started_at=START + timedelta(days=1),
    )
    test_db.add(scheduled)
    test_db.flush()
    test_db.add(OperationBackupDetails(operation_id=scheduled.id))
    test_db.commit()

    rows, _ = _recent(test_client, test_db, admin_headers)
    backups = {
        row["archive_name"] or "scheduled": row
        for row in rows
        if row["type"] == "backup"
    }

    assert set(backups) == {"archive-0", "archive-1", "archive-2", "scheduled"}
    for i in range(3):
        row = backups[f"archive-{i}"]
        assert row["triggered_by"] == "backup_plan"
        assert row["backup_plan_id"] == plan.id
        assert row["backup_plan_name"] == "nightly"
        assert row["archive_borg_id"] == f"{i:064x}"
    # A clean agent backup has logs under the default policy only when a log
    # line carries a warning, and only the newest run's does.
    assert [backups[f"archive-{i}"]["has_logs"] for i in range(3)] == [
        False,
        False,
        True,
    ]
    assert backups["scheduled"]["triggered_by"] == "schedule"
    assert backups["scheduled"]["schedule_name"] == "direct"
    assert backups["scheduled"]["archive_borg_id"] is None
    assert backups["scheduled"]["has_logs"] is True


@pytest.mark.unit
def test_a_requeued_backup_keeps_its_logs_hidden(test_client, test_db, admin_headers):
    """A backup back in the queue is pending again. The policy refuses a
    pending job whatever its log says, the warning line of its first attempt
    included."""
    _set_log_save_policy(test_db, "failed_and_warnings")
    repo, machine, plan = _seed(test_db)
    _add_plan_runs(test_db, repo, machine, plan, 0, 1)
    backup = test_db.query(Operation).filter(Operation.kind == "backup").one()
    rows, _ = _recent(test_client, test_db, admin_headers)
    assert [row["has_logs"] for row in rows if row["type"] == "backup"] == [True]

    backup.status = "queued"
    test_db.commit()
    rows, _ = _recent(test_client, test_db, admin_headers)
    assert [row["has_logs"] for row in rows if row["type"] == "backup"] == [False]


@pytest.mark.unit
def test_archives_are_read_by_repository_and_name_pairs(test_db):
    """Two repositories share their archive names. Each backup gets its own
    repository's archive, and the other repository's same-name rows are not
    read for it."""
    from app.services.operations.backup_facade import (
        archive_borg_ids_for,
        backup_facades,
    )

    repo, machine, plan = _seed(test_db)
    other = Repository(name="other", path="/repos/two", encryption="none")
    test_db.add(other)
    test_db.commit()
    _add_plan_runs(test_db, repo, machine, plan, 0, 1)
    _add_plan_runs(test_db, other, machine, plan, 1, 2)
    # The names each repository's backup does not ask for, stored in both.
    for repository, name, borg_id in (
        (repo, "archive-1", "a" * 64),
        (other, "archive-0", "b" * 64),
    ):
        test_db.add(
            Archive(
                repository_id=repository.id,
                borg_id=borg_id,
                name=name,
                series="archive",
                start=START,
            )
        )
    test_db.commit()
    jobs = backup_facades(
        test_db, test_db.query(Operation).filter(Operation.kind == "backup").all()
    )

    rows = []
    engine = test_db.get_bind()

    def loaded(conn, cursor, statement, parameters, context, executemany):
        if "FROM archives" in statement:
            rows.extend(cursor.connection.execute(statement, parameters).fetchall())

    event.listen(engine, "before_cursor_execute", loaded)
    try:
        borg_ids = archive_borg_ids_for(test_db, jobs)
    finally:
        event.remove(engine, "before_cursor_execute", loaded)

    by_repository = {job.repository_id: borg_ids[job.id] for job in jobs}
    assert by_repository == {repo.id: f"{0:064x}", other.id: f"{1:064x}"}
    assert len(rows) == 2
