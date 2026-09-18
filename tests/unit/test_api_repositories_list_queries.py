"""GET /api/repositories/ reads what each card needs once for the page (#1091)."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

from app.database.models import (
    AgentMachine,
    Operation,
    OperationRcloneDetails,
    RcloneRemote,
    Repository,
    RepositoryStorage,
    ScheduledJob,
    ScheduledJobRepository,
)


def _add_repositories(db, machine, remote, start, stop):
    """Each repository runs on the agent, has a schedule and a running prune;
    every other one is mirrored with rclone and has two syncs."""
    for i in range(start, stop):
        repo = Repository(
            name=f"repo-{i}",
            path=f"/repos/{i}",
            encryption="none",
            agent_machine_id=machine.id,
            execution_target="agent",
        )
        db.add(repo)
        db.flush()
        db.add_all(
            [
                ScheduledJob(
                    name=f"direct-{i}",
                    cron_expression="0 2 * * *",
                    repository_id=repo.id,
                    enabled=True,
                ),
                Operation(
                    repository_id=repo.id,
                    kind="prune",
                    category="maintenance",
                    status="running",
                    run_id=f"run-{i}",
                ),
            ]
        )
        if i % 2:
            db.add(RepositoryStorage(repository_id=repo.id, backend="local"))
            continue
        db.add(
            RepositoryStorage(
                repository_id=repo.id,
                backend="rclone",
                rclone_remote_id=remote.id,
                rclone_remote_path=f"repos/{i}",
            )
        )
        for n in range(2):
            sync = Operation(
                repository_id=repo.id,
                kind="rclone_sync",
                category="mirror",
                status="completed",
                run_id=f"sync-{i}-{n}",
            )
            db.add(sync)
            db.flush()
            db.add(OperationRcloneDetails(operation_id=sync.id))
    db.commit()


def _count_statements(test_client, test_db, admin_headers):
    statements = []

    def count(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = test_db.get_bind()
    event.listen(engine, "before_cursor_execute", count)
    try:
        response = test_client.get("/api/repositories/", headers=admin_headers)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert response.status_code == 200
    return response, statements


@pytest.mark.unit
def test_list_statement_count_does_not_grow_with_repositories(
    test_client, test_db, admin_headers
):
    machine = AgentMachine(
        name="machine", agent_id="agent-1", token_hash="x", token_prefix="p"
    )
    remote = RcloneRemote(name="remote", provider="s3", config_source="managed")
    test_db.add_all([machine, remote])
    test_db.commit()

    _add_repositories(test_db, machine, remote, 0, 3)
    response, three = _count_statements(test_client, test_db, admin_headers)
    assert len(response.json()["repositories"]) == 3

    _add_repositories(test_db, machine, remote, 3, 12)
    response, twelve = _count_statements(test_client, test_db, admin_headers)
    rows = response.json()["repositories"]
    assert len(rows) == 12
    assert sum(1 for row in rows if row.get("rclone_storage")) == 6

    assert len(twelve) == len(three)


@pytest.mark.unit
def test_list_statement_count_holds_when_the_decorative_columns_fail(
    test_client, test_db, admin_headers, monkeypatch
):
    """Both guarded helpers failing roll back twice; the rows are reloaded
    after each rollback, not refreshed one repository at a time."""

    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.api.repositories.storage_summaries", fail)
    monkeypatch.setattr("app.api.repositories.index_pending_kinds", fail)
    machine = AgentMachine(
        name="machine", agent_id="agent-1", token_hash="x", token_prefix="p"
    )
    remote = RcloneRemote(name="remote", provider="s3", config_source="managed")
    test_db.add_all([machine, remote])
    test_db.commit()

    _add_repositories(test_db, machine, remote, 0, 3)
    _, three = _count_statements(test_client, test_db, admin_headers)
    _add_repositories(test_db, machine, remote, 3, 12)
    response, twelve = _count_statements(test_client, test_db, admin_headers)

    rows = response.json()["repositories"]
    assert len(rows) == 12
    assert all(row["agent_machine_name"] == "machine" for row in rows)
    assert len(twelve) == len(three)


@pytest.mark.unit
def test_list_payload_for_a_mixed_page(test_client, test_db, admin_headers):
    machine = AgentMachine(
        name="machine-a",
        agent_id="agent-a",
        token_hash="x",
        token_prefix="p",
        status="online",
    )
    remote = RcloneRemote(name="remote", provider="s3", config_source="managed")
    test_db.add_all([machine, remote])
    test_db.flush()

    local = Repository(name="local", path="/repos/local", encryption="none")
    agent = Repository(
        name="agent",
        path="/repos/agent",
        encryption="none",
        agent_machine_id=machine.id,
        execution_target="agent",
    )
    mirrored = Repository(name="mirrored", path="/repos/mirrored", encryption="none")
    linked = Repository(name="linked", path="/repos/linked", encryption="none")
    test_db.add_all([local, agent, mirrored, linked])
    test_db.flush()

    # A disabled direct schedule loses to an enabled schedule linked through
    # the junction table.
    test_db.add(
        ScheduledJob(
            name="disabled-direct",
            cron_expression="0 1 * * *",
            repository_id=linked.id,
            enabled=False,
        )
    )
    shared = ScheduledJob(
        name="shared",
        cron_expression="0 3 * * *",
        enabled=True,
        next_run=datetime(2099, 1, 1, 3, 0, 0),
    )
    test_db.add(shared)
    test_db.flush()
    test_db.add_all(
        [
            ScheduledJobRepository(
                scheduled_job_id=shared.id, repository_id=linked.id, execution_order=0
            ),
            ScheduledJobRepository(
                scheduled_job_id=shared.id, repository_id=agent.id, execution_order=1
            ),
        ]
    )
    test_db.add(
        RepositoryStorage(
            repository_id=mirrored.id,
            backend="rclone",
            rclone_remote_id=remote.id,
            rclone_remote_path="repos/mirrored",
        )
    )
    older_sync = Operation(
        repository_id=mirrored.id,
        kind="rclone_sync",
        category="mirror",
        status="failed",
        run_id="sync-old",
        created_at=datetime(2026, 1, 1, 0, 0, 0),
    )
    newer_sync = Operation(
        repository_id=mirrored.id,
        kind="rclone_sync",
        category="mirror",
        status="completed",
        run_id="sync-new",
        created_at=datetime(2026, 1, 1, 0, 0, 0) + timedelta(hours=1),
    )
    test_db.add_all([older_sync, newer_sync])
    test_db.flush()
    test_db.add_all(
        [
            OperationRcloneDetails(operation_id=older_sync.id),
            OperationRcloneDetails(operation_id=newer_sync.id),
        ]
    )
    test_db.add_all(
        [
            Operation(
                repository_id=agent.id,
                kind="prune",
                category="maintenance",
                status="running",
                run_id="run-prune",
            ),
            # Finished or other kinds do not count as running maintenance.
            Operation(
                repository_id=local.id,
                kind="compact",
                category="maintenance",
                status="completed",
                run_id="run-compact",
            ),
            Operation(
                repository_id=local.id,
                kind="backup",
                category="backup",
                status="running",
                run_id="run-backup",
            ),
        ]
    )
    test_db.commit()

    response = test_client.get("/api/repositories/", headers=admin_headers)

    assert response.status_code == 200
    rows = {row["name"]: row for row in response.json()["repositories"]}

    assert rows["local"]["has_running_maintenance"] is False
    assert rows["local"]["has_schedule"] is False
    assert rows["local"]["agent_machine_name"] is None
    assert "rclone_storage" not in rows["local"]

    assert rows["agent"]["has_running_maintenance"] is True
    assert rows["agent"]["agent_machine_name"] == "machine-a"
    assert rows["agent"]["agent_machine_status"] == "online"
    assert rows["agent"]["schedule_name"] == "shared"

    assert rows["linked"]["has_schedule"] is True
    assert rows["linked"]["schedule_enabled"] is True
    assert rows["linked"]["schedule_name"] == "shared"
    assert rows["linked"]["next_run"] is not None

    assert rows["mirrored"]["storage_backend"] == "local"
    assert rows["mirrored"]["rclone_storage"]["rclone_remote_id"] == remote.id
    assert rows["mirrored"]["has_schedule"] is False
    latest = rows["mirrored"]["rclone_storage"]["latest_sync_job"]
    assert latest["id"] == newer_sync.id
    assert latest["status"] == "completed"


@pytest.mark.unit
def test_list_schedule_summary_names_the_soonest_enabled_schedule(
    test_client, test_db, admin_headers
):
    soon = datetime(2099, 1, 1, 1, 0, 0)
    later = datetime(2099, 1, 6, 1, 0, 0)
    repos = {
        name: Repository(name=name, path=f"/repos/{name}", encryption="none")
        for name in ("two-enabled", "untimed-first", "tie", "disabled", "untimed")
    }
    test_db.add_all(repos.values())
    test_db.flush()

    def schedule(repo, name, *, enabled=True, next_run=None):
        job = ScheduledJob(
            name=name,
            cron_expression="0 2 * * *",
            repository_id=repos[repo].id,
            enabled=enabled,
            next_run=next_run,
        )
        test_db.add(job)
        test_db.flush()
        return job

    # The lower id runs in five days, the higher id tomorrow; the linked
    # schedule is enabled too, but runs last.
    schedule("two-enabled", "weekly", next_run=later)
    schedule("two-enabled", "daily", next_run=soon)
    linked = ScheduledJob(
        name="linked",
        cron_expression="0 3 * * *",
        enabled=True,
        next_run=later + timedelta(days=1),
    )
    test_db.add(linked)
    test_db.flush()
    test_db.add(
        ScheduledJobRepository(
            scheduled_job_id=linked.id,
            repository_id=repos["two-enabled"].id,
            execution_order=0,
        )
    )
    # An enabled schedule without a next run does not hide one that has it.
    schedule("untimed-first", "no-next-run")
    schedule("untimed-first", "timed", next_run=later)
    # Same next run: the lower id.
    schedule("tie", "first", next_run=soon)
    schedule("tie", "second", next_run=soon)
    # Nothing enabled, or nothing timed: the previous choice.
    schedule("disabled", "off-1", enabled=False, next_run=soon)
    schedule("disabled", "off-2", enabled=False, next_run=later)
    schedule("untimed", "untimed-1")
    schedule("untimed", "untimed-2")
    test_db.commit()

    response = test_client.get("/api/repositories/", headers=admin_headers)

    assert response.status_code == 200
    rows = {row["name"]: row for row in response.json()["repositories"]}
    assert rows["two-enabled"]["schedule_name"] == "daily"
    assert rows["two-enabled"]["next_run"].startswith("2099-01-01T01:00:00")
    assert rows["untimed-first"]["schedule_name"] == "timed"
    assert rows["tie"]["schedule_name"] == "first"
    assert rows["disabled"]["schedule_name"] == "off-1"
    assert rows["disabled"]["schedule_enabled"] is False
    assert rows["disabled"]["next_run"] is None
    assert rows["untimed"]["schedule_name"] == "untimed-1"
    assert rows["untimed"]["schedule_enabled"] is True
    assert rows["untimed"]["next_run"] is None
