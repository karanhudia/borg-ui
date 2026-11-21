"""The scheduled backup limit counts every run that takes a slot.

A schedule of linked repositories creates no backup operation when it is
dispatched: its backups are created one by one, after its pre-backup scripts.
Before its first backup, between two and after its last, its slot is known
only to the process that runs it; so is a backup's during its prune and
compact. The limit was counted as the larger of that process's runs and the
active scheduled backups in the database, which missed a backup in the
database that is not one of those runs (one started by hand, or by another
process) whenever such a run held no backup.

Reuses the harness of test_scheduler_pass_off_event_loop.py. The tests run on
SQLite and, with BORG_TEST_POSTGRES_URL set, on PostgreSQL.
"""

import asyncio
import contextlib
import uuid
from datetime import datetime, timedelta

import pytest

import app.api.schedule as schedule_api
from app.core.security import get_password_hash
from app.database.models import (
    AgentJob,
    AgentMachine,
    Operation,
    ScheduledJob,
    ScheduledJobRepository,
    SystemSettings,
)
from app.services.backup_service import backup_service
from app.services.operations.vocab import category_for
from tests.unit import test_scheduler_pass_off_event_loop as harness
from tests.unit.test_scheduler_pass_off_event_loop import PAST, _repository, _seed

# the harness's fixtures, for the tests here
database = harness.database
launches = harness.launches

RUN_LINKED_SCHEDULE = schedule_api.execute_multi_repo_schedule_by_id


def _linked_schedule(db, repository_id: int, next_run: datetime) -> int:
    [job_id] = _seed(
        db,
        ScheduledJob(
            name=f"linked schedule {repository_id}",
            cron_expression="0 2 * * *",
            enabled=True,
            next_run=next_run,
        ),
    )
    _seed(
        db,
        ScheduledJobRepository(
            scheduled_job_id=job_id, repository_id=repository_id, execution_order=0
        ),
    )
    return job_id


def _single_schedule(db, repository_id: int, next_run: datetime) -> int:
    [job_id] = _seed(
        db,
        ScheduledJob(
            name=f"schedule {repository_id}",
            cron_expression="0 2 * * *",
            enabled=True,
            repository_id=repository_id,
            next_run=next_run,
        ),
    )
    return job_id


def _running_backup(db, repository_id: int, scheduled_job_id: int) -> int:
    """A scheduled backup that runs, and is no run of this process: one
    started by hand, or by another process."""
    [operation_id] = _seed(
        db,
        Operation(
            kind="backup",
            category=category_for("backup"),
            run_id=str(uuid.uuid4()),
            repository_id=repository_id,
            status="running",
            trigger="schedule",
            scheduled_job_id=scheduled_job_id,
        ),
    )
    return operation_id


async def _pass(db, now: datetime) -> None:
    with db() as session:
        await schedule_api.dispatch_due_scheduled_backups(session, now)
    for _ in range(3):  # the launched tasks take their first steps
        await asyncio.sleep(0)


@pytest.fixture
async def held(monkeypatch, launches):
    """The runs the pass launches stay where the test puts them: a schedule
    of linked repositories in its pre-backup scripts, a single backup in its
    prune and compact (once `finish_backup` has ended its operation)."""
    tasks: list[asyncio.Task] = []
    state: dict = {}

    async def multi_repo(scheduled_job_id):
        launches.append(("multi-repo", scheduled_job_id))
        tasks.append(asyncio.current_task())
        await asyncio.Event().wait()

    async def backup(backup_job_id, repository_path, scheduled_job_id, **kwargs):
        launches.append(("backup", scheduled_job_id))
        tasks.append(asyncio.current_task())
        finish = state.get("finish_backup")
        if finish is not None:
            finish(backup_job_id)
        await asyncio.Event().wait()

    monkeypatch.setattr(schedule_api, "execute_multi_repo_schedule_by_id", multi_repo)
    monkeypatch.setattr(
        schedule_api, "execute_scheduled_backup_with_maintenance", backup
    )
    yield state, tasks
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.unit
async def test_a_linked_schedule_and_a_backup_it_does_not_run_both_hold_a_slot(
    database, launches, held
):
    """Two scheduled backups may run. One runs already, started by hand or
    by another process. This process starts a schedule of linked
    repositories, in its pre-backup scripts. Both slots are taken: the next
    pass starts nothing."""
    _seed(database, SystemSettings(max_concurrent_scheduled_backups=2))
    running_repo, linked, single = _seed(
        database, _repository("running"), _repository("linked"), _repository("single")
    )
    now = datetime.utcnow()
    running_job = _single_schedule(database, running_repo, now + timedelta(hours=1))
    _running_backup(database, running_repo, running_job)
    linked_job = _linked_schedule(database, linked, now - 2 * PAST)
    _single_schedule(database, single, now - PAST)

    await _pass(database, now)
    assert launches == [("multi-repo", linked_job)]

    await _pass(database, now + timedelta(seconds=1))

    assert launches == [("multi-repo", linked_job)]


@pytest.mark.unit
async def test_a_backup_in_its_prune_and_another_backup_both_hold_a_slot(
    database, launches, held
):
    """Two scheduled backups may run. One runs already, started by hand or
    by another process. This process starts a scheduled backup, whose
    operation has ended and which prunes and compacts now. Both slots are
    taken: the next pass starts nothing."""
    state, _ = held

    def finish(operation_id):
        with database() as session:
            session.get(Operation, operation_id).status = "completed"
            session.commit()

    state["finish_backup"] = finish
    _seed(database, SystemSettings(max_concurrent_scheduled_backups=2))
    running_repo, first, second = _seed(
        database, _repository("running"), _repository("first"), _repository("second")
    )
    now = datetime.utcnow()
    running_job = _single_schedule(database, running_repo, now + timedelta(hours=1))
    _running_backup(database, running_repo, running_job)
    first_job = _single_schedule(database, first, now - PAST)
    _single_schedule(database, second, now + timedelta(seconds=30))

    await _pass(database, now)
    assert launches == [("backup", first_job)]

    await _pass(database, now + timedelta(minutes=1))

    assert launches == [("backup", first_job)]


@pytest.mark.unit
async def test_a_linked_schedule_and_the_backup_it_runs_hold_one_slot(
    database, launches, monkeypatch
):
    """Two scheduled backups may run. This process starts a schedule of
    linked repositories, which runs the backup of its first repository: the
    backup and the run take one slot, and the next pass starts a second
    scheduled backup."""
    backup_runs = asyncio.Event()

    async def no_hooks_left(**kwargs):
        return None

    async def backup_running(operation_id):
        backup_runs.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(
        schedule_api, "execute_multi_repo_schedule_by_id", RUN_LINKED_SCHEDULE
    )
    monkeypatch.setattr(
        backup_service, "wait_for_post_hooks_after_restart", no_hooks_left
    )
    monkeypatch.setattr(schedule_api, "wait_out_backup_operation", backup_running)
    _seed(database, SystemSettings(max_concurrent_scheduled_backups=2))
    linked, single = _seed(database, _repository("linked"), _repository("single"))
    now = datetime.utcnow()
    _linked_schedule(database, linked, now - PAST)
    single_job = _single_schedule(database, single, now + timedelta(seconds=30))

    await _pass(database, now)
    [run] = [
        task
        for task in asyncio.all_tasks()
        if task.get_coro().__name__ == "execute_multi_repo_schedule_by_id"
    ]
    try:
        await asyncio.wait_for(backup_runs.wait(), 5)
        with database() as session:
            assert schedule_api._count_active_scheduled_backup_runs(session) == 1

        await _pass(database, now + timedelta(minutes=1))

        assert launches == [("backup", single_job)]
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)


@pytest.mark.unit
async def test_a_scheduled_backup_and_its_run_hold_one_slot(database, launches, held):
    """A scheduled backup of this process runs: its operation and its run
    take one slot."""
    _seed(database, SystemSettings(max_concurrent_scheduled_backups=2))
    [repository] = _seed(database, _repository("single"))
    now = datetime.utcnow()
    job = _single_schedule(database, repository, now - PAST)

    await _pass(database, now)

    assert launches == [("backup", job)]
    with database() as session:
        assert schedule_api._count_active_scheduled_backup_runs(session) == 1


@pytest.mark.unit
async def test_two_runs_of_one_linked_schedule_hold_a_slot_each(
    database, launches, held
):
    """A run of a schedule of linked repositories outlasts the schedule's
    interval, and the schedule is started again. Each run holds a slot until
    it ends."""
    _, tasks = held
    _seed(database, SystemSettings(max_concurrent_scheduled_backups=3))
    [linked] = _seed(database, _repository("linked"))
    now = datetime.utcnow()
    linked_job = _linked_schedule(database, linked, now - PAST)

    await _pass(database, now)
    with database() as session:
        session.get(ScheduledJob, linked_job).next_run = now
        session.commit()
    await _pass(database, now + timedelta(minutes=1))
    assert launches == [("multi-repo", linked_job)] * 2
    with database() as session:
        assert schedule_api._count_active_scheduled_backup_runs(session) == 2

    tasks[0].cancel()
    await asyncio.gather(tasks[0], return_exceptions=True)

    with database() as session:
        assert schedule_api._count_active_scheduled_backup_runs(session) == 1


@contextlib.contextmanager
def _run_of_this_process(run_key: str, operation_id=None):
    """A scheduled run of this process, holding `operation_id`."""
    task = asyncio.ensure_future(asyncio.Event().wait())
    schedule_api._track_scheduled_backup_task(task, run_key, operation_id)
    try:
        yield task
    finally:
        task.cancel()


@pytest.mark.unit
async def test_a_run_whose_backup_waits_for_an_agent_away_keeps_its_slot(
    database, launches
):
    """Two scheduled backups may run. One runs, started by hand. A backup
    this process started waits for an agent that is away. Its backup holds
    no slot (#1331), but its run keeps one, as it did before: the agent may
    come back and run it at any time. Both slots are taken: the next pass
    starts nothing."""
    _seed(database, SystemSettings(max_concurrent_scheduled_backups=2))
    now = datetime.utcnow()
    [away] = _seed(
        database,
        AgentMachine(
            name="laptop",
            agent_id="agt_laptop",
            token_hash=get_password_hash("agent-secret"),
            token_prefix="secret-laptop",
            status="offline",
            last_seen_at=now - timedelta(minutes=50),
            created_at=now - timedelta(days=30),
        ),
    )
    agent_repo, running_repo, single = _seed(
        database,
        _repository("laptop", executor_type="agent", agent_machine_id=away),
        _repository("running"),
        _repository("single"),
    )
    agent_job = _single_schedule(database, agent_repo, now + timedelta(hours=1))
    running_job = _single_schedule(database, running_repo, now + timedelta(hours=1))
    [waiting] = _seed(
        database,
        Operation(
            kind="backup",
            category=category_for("backup"),
            run_id=str(uuid.uuid4()),
            repository_id=agent_repo,
            status="running",
            trigger="schedule",
            scheduled_job_id=agent_job,
            params={"executor": "agent"},
        ),
    )
    _seed(
        database,
        AgentJob(
            agent_machine_id=away,
            operation_id=waiting,
            job_type="backup",
            status="queued",
            payload={"job_kind": "backup.create"},
        ),
    )
    _running_backup(database, running_repo, running_job)
    _single_schedule(database, single, now - PAST)

    with _run_of_this_process(f"backup:{waiting}", waiting):
        with database() as session:
            assert schedule_api._count_active_scheduled_backup_runs(session) == 2
        await _pass(database, now)

    assert launches == []


@pytest.mark.unit
async def test_a_backup_its_run_names_while_it_is_counted_is_counted_once(
    database, monkeypatch
):
    """A schedule of linked repositories names its first backup and commits
    it while the scheduler counts: found both in the database and in the
    run, it takes one slot."""
    [linked] = _seed(database, _repository("linked"))
    job = _linked_schedule(database, linked, datetime.utcnow() + timedelta(hours=1))
    run_key = f"schedule:{job}:1"
    real = schedule_api.scheduled_backups_holding_capacity

    def named_and_committed_meanwhile(db):
        if schedule_api._active_scheduled_backup_runs[run_key] is None:
            backup = _running_backup(database, linked, job)
            schedule_api._active_scheduled_backup_runs[run_key] = backup
        return real(db)

    monkeypatch.setattr(
        schedule_api,
        "scheduled_backups_holding_capacity",
        named_and_committed_meanwhile,
    )
    with _run_of_this_process(run_key):
        with database() as session:
            assert schedule_api._count_active_scheduled_backup_runs(session) == 1


@pytest.mark.unit
async def test_a_run_that_moves_on_while_it_is_counted_is_counted_once(
    database, monkeypatch
):
    """A schedule of linked repositories finishes its first backup and names
    its second while the scheduler reads the database: it takes one slot."""
    first_repo, second_repo = _seed(
        database, _repository("first"), _repository("second")
    )
    job = _linked_schedule(database, first_repo, datetime.utcnow() + timedelta(hours=1))
    first = _running_backup(database, first_repo, job)
    run_key = f"schedule:{job}:1"
    real = schedule_api.scheduled_backups_holding_capacity
    calls = []

    def moved_on_meanwhile(db):
        found = real(db)
        if not calls:
            with database() as session:
                session.get(Operation, first).status = "completed"
                session.commit()
            schedule_api._active_scheduled_backup_runs[run_key] = _running_backup(
                database, second_repo, job
            )
        calls.append(found)
        return found

    monkeypatch.setattr(
        schedule_api, "scheduled_backups_holding_capacity", moved_on_meanwhile
    )
    with _run_of_this_process(run_key, first):
        with database() as session:
            assert schedule_api._count_active_scheduled_backup_runs(session) == 1
