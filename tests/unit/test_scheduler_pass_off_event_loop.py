"""The scheduler's pass waits for the database off the event loop.

Once a minute the pass dispatches the due scheduled backups, backup plans,
checks, restore checks and cloud mirrors, and runs the backup monitoring and
reports. Its reads and writes ran on the loop: a write lock held elsewhere, or
a pool with no free connection, then held every request of the process until
it was free. It also kept its capacity lock, on SQLite the database's one
write lock, and its connection across the awaits in between (a source probe,
an alert being sent).

The waits are laid out with the write lock, a lock or every pooled connection
held by the test, and given back from a thread after a while. With the pass
back on the loop the test's own coroutine cannot take its turn before that,
and the test fails. No test depends on how long anything takes.

The tests run on SQLite and, with BORG_TEST_POSTGRES_URL set, on PostgreSQL.
"""

import asyncio
import contextlib
import json
import os
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

import app.api.schedule as schedule_api
import app.services.backup_plan_execution_service as plan_service
import app.services.restore_check_scheduler as restore_check_scheduler
import app.services.schedule_availability as schedule_availability
from app.database.database import Base, register_utc_session_timezone
from app.database.models import (
    BackupPlan,
    BackupPlanRepository,
    BackupPlanRun,
    LicensingState,
    Operation,
    RcloneRemote,
    Repository,
    RepositoryStorage,
    ScheduledJob,
    ScheduledJobRepository,
    SSHConnection,
    SystemSettings,
)
from app.services.backup_plan_execution_service import backup_plan_execution_service
from app.services.notification_service import NotificationService
from app.services.operations.vocab import category_for

POSTGRES_URL = os.getenv("BORG_TEST_POSTGRES_URL")
# Long enough for the pass to reach its wait, short enough that a wait held on
# the loop fails the test instead of hanging it.
HOLD_SECONDS = 5
# Connections in the app's pool. The pass takes one at a time.
POOL_SIZE = 2
# The advisory lock `lock_backup_capacity_scope` takes on PostgreSQL.
CAPACITY_LOCK_ID = 276116


def _on_the_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _sqlite_engine(url, *, pool=QueuePool, busy_seconds=HOLD_SECONDS * 2):
    pooled = {"pool_size": POOL_SIZE, "max_overflow": 0} if pool is QueuePool else {}
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": busy_seconds},
        poolclass=pool,
        **({"pool_timeout": HOLD_SECONDS * 2} if pool is QueuePool else {}),
        **pooled,
    )

    @event.listens_for(engine, "connect")
    def pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@contextmanager
def _postgres_engines():
    """The app's pooled engine and one for the test's own connections, on a
    schema of their own: the other PostgreSQL tests drop `public`."""
    schema = f"scheduler_pass_{uuid.uuid4().hex}"
    admin = create_engine(POSTGRES_URL)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    options = {"options": f"-c search_path={schema}"}
    engine = create_engine(
        POSTGRES_URL,
        connect_args=options,
        poolclass=QueuePool,
        pool_size=POOL_SIZE,
        max_overflow=0,
        pool_timeout=HOLD_SECONDS * 2,
    )
    side = create_engine(POSTGRES_URL, connect_args=options, poolclass=NullPool)
    register_utc_session_timezone(engine)
    register_utc_session_timezone(side)
    try:
        Base.metadata.create_all(engine)
        yield engine, side
    finally:
        engine.dispose()
        side.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


@contextmanager
def _sqlite_engines(tmp_path):
    url = f"sqlite:///{tmp_path / 'scheduler-pass.db'}"
    engine = _sqlite_engine(url)
    # The test's own connections: a write gives up after a second.
    side = _sqlite_engine(url, pool=NullPool, busy_seconds=1)
    try:
        Base.metadata.create_all(engine)
        yield engine, side
    finally:
        engine.dispose()
        side.dispose()


class Database:
    """The app's sessions on a pool of POOL_SIZE connections, as in
    production, and the test's own connections beside that pool."""

    def __init__(self, kind: str, engine, side) -> None:
        self.kind = kind
        self.engine = engine
        self.side = side
        self.sessions = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def __call__(self):
        return self.sessions()


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=pytest.mark.skipif(
                not POSTGRES_URL, reason="BORG_TEST_POSTGRES_URL is not set"
            ),
        ),
    ]
)
def database(request, tmp_path, monkeypatch):
    engines = (
        _postgres_engines()
        if request.param == "postgresql"
        else _sqlite_engines(tmp_path)
    )
    with engines as (engine, side):
        db = Database(request.param, engine, side)
        for module in (schedule_api, plan_service, restore_check_scheduler):
            monkeypatch.setattr(module, "SessionLocal", db.sessions)
        yield db


@pytest.fixture
def sqlite_database(tmp_path, monkeypatch):
    with _sqlite_engines(tmp_path) as (engine, side):
        db = Database("sqlite", engine, side)
        for module in (schedule_api, plan_service, restore_check_scheduler):
            monkeypatch.setattr(module, "SessionLocal", db.sessions)
        yield db


@pytest.fixture(autouse=True)
def launches(monkeypatch):
    """What the pass launches does nothing; the list says what it launched."""
    launched: list[tuple] = []

    async def backup(backup_job_id, repository_path, scheduled_job_id, **kwargs):
        launched.append(("backup", scheduled_job_id))

    async def multi_repo(scheduled_job_id):
        launched.append(("multi-repo", scheduled_job_id))

    async def plan_run(run_id):
        launched.append(("plan", run_id))

    monkeypatch.setattr(
        schedule_api, "execute_scheduled_backup_with_maintenance", backup
    )
    monkeypatch.setattr(schedule_api, "execute_multi_repo_schedule_by_id", multi_repo)
    monkeypatch.setattr(backup_plan_execution_service, "execute_run", plan_run)
    monkeypatch.setattr(schedule_availability, "_ssh_reachable", lambda *a, **k: True)
    yield launched
    backup_plan_execution_service.live_run_ids.clear()
    schedule_api._active_scheduled_backup_runs.clear()


class _StopsAtSleep:
    """`asyncio` for the scheduler's module: its sleep after a pass ends the
    pass instead. The rest is the real module."""

    def __init__(self) -> None:
        self.slept = asyncio.Event()

    def __getattr__(self, name):
        return getattr(asyncio, name)

    async def sleep(self, seconds):
        self.slept.set()
        await asyncio.Event().wait()


async def _one_pass(monkeypatch) -> None:
    """One pass of `check_scheduled_jobs`, up to its sleep."""
    stops = _StopsAtSleep()
    monkeypatch.setattr(schedule_api, "asyncio", stops)
    task = asyncio.ensure_future(schedule_api.check_scheduled_jobs())
    try:
        await asyncio.wait_for(stops.slept.wait(), HOLD_SECONDS * 3)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _the_loop_runs_while(waiting, release) -> None:
    """`waiting` needs what the test holds. Run it, and see that the loop
    takes a turn while it waits: `release`, which gives it back, runs only
    after a while, from a thread."""
    released = threading.Event()
    timer_fired = threading.Event()
    given_back = threading.Lock()

    def on_time() -> None:
        timer_fired.set()
        give_back()

    def give_back() -> None:
        with given_back:  # once, from the timer or from the cleanup below
            if released.is_set():
                return
            released.set()
            release()

    timer = threading.Timer(HOLD_SECONDS / 2, on_time)
    timer.start()
    task = asyncio.ensure_future(waiting)
    try:
        await asyncio.sleep(0.05)
        assert not released.is_set(), "the pass waited on the loop"
        await asyncio.wait_for(task, HOLD_SECONDS * 4)
        # the pass ended only once the timer had given back what it waited for
        finished_on_its_own = timer_fired.is_set()
    finally:
        timer.cancel()
        held_back = not released.is_set()
        give_back()  # a test that failed early still gives back what it held
        if not task.done():
            task.cancel()
            with contextlib.suppress(BaseException):
                await task
    assert finished_on_its_own and not held_back, (
        "nothing waited for what the test held"
    )


# --- seeds ------------------------------------------------------------------

PAST = timedelta(minutes=1)


def _seed(db: Database, *rows) -> list[int]:
    with db() as session:
        session.add_all(rows)
        session.commit()
        return [row.id for row in rows]


def _repository(name: str, **columns) -> Repository:
    return Repository(
        name=name,
        path=f"/repos/{name}",
        encryption="none",
        repository_type="local",
        mode="full",
        **columns,
    )


def _settings(db: Database, **columns) -> None:
    _seed(db, SystemSettings(max_concurrent_scheduled_backups=10, **columns))


def _seed_due_check(db: Database) -> int:
    now = datetime.utcnow()
    [repository_id] = _seed(
        db,
        _repository(
            "due-check",
            check_cron_expression="0 3 * * *",
            check_schedule_enabled=True,
            next_scheduled_check=now - PAST,
        ),
    )
    return repository_id


def _seed_everything_due(db: Database) -> dict:
    """One of every kind the pass handles, each due."""
    now = datetime.utcnow()
    _settings(
        db,
        backup_monitoring_enabled=True,
        backup_reports_enabled=True,
        backup_reports_frequency="daily",
    )
    _seed(db, LicensingState(instance_id="scheduler-pass", plan="pro", status="active"))
    [ssh_id] = _seed(db, SSHConnection(host="source.invalid", username="u", port=22))
    [remote_id] = _seed(
        db, RcloneRemote(name="mirror-remote", provider="s3", config_source="managed")
    )
    single, linked, available, planned, checked, restored, mirrored = _seed(
        db,
        _repository("single"),
        _repository("linked"),
        _repository("available", source_ssh_connection_id=ssh_id),
        _repository("planned"),
        _repository(
            "checked",
            check_cron_expression="0 3 * * *",
            check_schedule_enabled=True,
            next_scheduled_check=now - PAST,
        ),
        _repository(
            "restored",
            restore_check_cron_expression="0 4 * * *",
            restore_check_schedule_enabled=True,
            restore_check_paths=json.dumps(["/etc/hostname"]),
            next_scheduled_restore_check=now - PAST,
        ),
        _repository("mirrored"),
    )
    cron = {"cron_expression": "0 2 * * *", "enabled": True, "next_run": now - PAST}
    single_job, linked_job, available_job = _seed(
        db,
        ScheduledJob(name="single schedule", repository_id=single, **cron),
        ScheduledJob(name="linked schedule", **cron),
        ScheduledJob(
            name="availability schedule",
            schedule_mode="availability",
            enabled=True,
            next_run=now - PAST,
        ),
    )
    _seed(
        db,
        ScheduledJobRepository(
            scheduled_job_id=linked_job, repository_id=linked, execution_order=0
        ),
        ScheduledJobRepository(
            scheduled_job_id=available_job, repository_id=available, execution_order=0
        ),
    )
    plan_columns = {
        "enabled": True,
        "source_directories": json.dumps(["/srv/project"]),
        "created_at": now,
        "schedule_enabled": True,
        "next_run": now - PAST,
    }
    cron_plan, availability_plan = _seed(
        db,
        BackupPlan(name="cron plan", cron_expression="0 3 * * *", **plan_columns),
        BackupPlan(
            name="availability plan",
            schedule_mode="availability",
            source_type="remote",
            source_ssh_connection_id=ssh_id,
            **plan_columns,
        ),
    )
    _seed(
        db,
        *(
            BackupPlanRepository(
                backup_plan_id=plan_id,
                repository_id=planned,
                enabled=True,
                execution_order=1,
                created_at=now,
            )
            for plan_id in (cron_plan, availability_plan)
        ),
    )
    _seed(
        db,
        RepositoryStorage(
            repository_id=mirrored,
            backend="rclone",
            rclone_remote_id=remote_id,
            rclone_remote_path="borg-ui/repositories/mirrored",
            cache_path="/repos/mirrored",
            sync_policy="scheduled",
            sync_status="current",
            sync_direction="primary_to_remote",
            sync_cron_expression="*/15 * * * *",
            sync_timezone="UTC",
            next_scheduled_sync_at=now - PAST,
        ),
    )
    return {
        "jobs": (single_job, linked_job, available_job),
        "plans": (cron_plan, availability_plan),
        "repositories": {
            "single": single,
            "checked": checked,
            "restored": restored,
            "mirrored": mirrored,
        },
    }


def _operations(db: Database) -> set[tuple[str, int]]:
    with db() as session:
        return {(row.kind, row.repository_id) for row in session.query(Operation).all()}


# --- the loop answers while the pass waits ----------------------------------


@pytest.mark.unit
async def test_the_loop_runs_while_the_pass_waits_for_sqlite_write_lock(
    sqlite_database, monkeypatch
):
    """SQLite takes one writer at a time: the pass waits for another
    connection's write to end."""
    db = sqlite_database
    _settings(db)
    repository_id = _seed_due_check(db)
    writer = db.side.connect()
    writer.exec_driver_sql("BEGIN IMMEDIATE")

    def release() -> None:
        writer.exec_driver_sql("ROLLBACK")
        writer.close()

    await _the_loop_runs_while(_one_pass(monkeypatch), release)

    assert ("check", repository_id) in _operations(db)


@pytest.mark.unit
async def test_the_loop_runs_while_the_pass_waits_for_a_connection(
    database, monkeypatch
):
    """Every connection of the pool is held: the pass waits for one."""
    _settings(database)
    repository_id = _seed_due_check(database)
    held = [database.engine.connect() for _ in range(POOL_SIZE)]

    def release() -> None:
        for connection in held:
            connection.close()

    await _the_loop_runs_while(_one_pass(monkeypatch), release)

    assert ("check", repository_id) in _operations(database)


@pytest.mark.unit
@pytest.mark.skipif(not POSTGRES_URL, reason="BORG_TEST_POSTGRES_URL is not set")
async def test_the_loop_runs_while_the_pass_waits_for_the_capacity_lock(
    tmp_path, monkeypatch
):
    """PostgreSQL: a manual backup start holds the backup capacity lock."""
    with _postgres_engines() as (engine, side):
        db = Database("postgresql", engine, side)
        for module in (schedule_api, plan_service, restore_check_scheduler):
            monkeypatch.setattr(module, "SessionLocal", db.sessions)
        _settings(db)
        repository_id = _seed_due_check(db)
        holder = side.connect()
        holder.begin()
        holder.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": CAPACITY_LOCK_ID},
        )

        def release() -> None:
            holder.rollback()
            holder.close()

        await _the_loop_runs_while(_one_pass(monkeypatch), release)

        assert ("check", repository_id) in _operations(db)


# --- nothing of the pass queries on the loop ---------------------------------


@pytest.mark.unit
async def test_no_statement_of_the_pass_runs_on_the_loop(
    database, launches, monkeypatch
):
    seeded = _seed_everything_due(database)
    on_the_loop: list[str] = []
    off_the_loop: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        (on_the_loop if _on_the_loop() else off_the_loop).append(statement)

    event.listen(database.engine, "before_cursor_execute", record)
    try:
        await _one_pass(monkeypatch)
        # what the pass launched has run
        await asyncio.sleep(0)
    finally:
        event.remove(database.engine, "before_cursor_execute", record)

    repositories = seeded["repositories"]
    single_job, linked_job, available_job = seeded["jobs"]
    assert {
        ("backup", repositories["single"]),
        ("check", repositories["checked"]),
        ("restore_check", repositories["restored"]),
        ("rclone_sync", repositories["mirrored"]),
    } <= _operations(database)
    assert ("backup", single_job) in launches
    # a schedule with linked repositories runs them in one task
    assert ("multi-repo", linked_job) in launches
    assert ("multi-repo", available_job) in launches
    with database() as session:
        runs = {run.backup_plan_id for run in session.query(BackupPlanRun).all()}
        settings = session.query(SystemSettings).one()
        assert settings.backup_monitoring_last_checked_at is not None
        assert settings.backup_reports_last_sent_at is not None
    assert runs == set(seeded["plans"])
    assert off_the_loop
    assert on_the_loop == []


# --- nothing is held across the awaits of the pass ----------------------------


def _write_beside(db: Database) -> str:
    """A write of another connection, as a request makes it. It gives up
    after a second on SQLite and does not wait on PostgreSQL."""
    with db.side.connect() as connection:
        try:
            if db.kind == "postgresql":
                connection.execute(text("SET lock_timeout = '1s'"))
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_id)"),
                    {"lock_id": CAPACITY_LOCK_ID},
                )
            connection.execute(text("UPDATE system_settings SET id = id"))
            connection.commit()
            return "written"
        except OperationalError as error:
            return str(error.orig)


AWAITS = ["backup-source-probe", "plan-source-probe", "stale-alert", "report"]


def _seed_for_await(db: Database, where: str) -> None:
    now = datetime.utcnow()
    _settings(
        db,
        backup_monitoring_enabled=where == "stale-alert",
        backup_reports_enabled=where == "report",
        backup_reports_frequency="daily",
        # a check of the monitoring a minute ago: not due again
        backup_monitoring_last_checked_at=None if where == "stale-alert" else now,
    )
    _seed(db, LicensingState(instance_id="scheduler-pass", plan="pro", status="active"))
    [ssh_id] = _seed(db, SSHConnection(host="source.invalid", username="u", port=22))
    [repository_id] = _seed(db, _repository("probed", source_ssh_connection_id=ssh_id))
    if where == "backup-source-probe":
        [job_id] = _seed(
            db,
            ScheduledJob(
                name="availability schedule",
                schedule_mode="availability",
                enabled=True,
                next_run=now - PAST,
            ),
        )
        _seed(
            db,
            ScheduledJobRepository(
                scheduled_job_id=job_id, repository_id=repository_id, execution_order=0
            ),
        )
    if where == "plan-source-probe":
        [plan_id] = _seed(
            db,
            BackupPlan(
                name="availability plan",
                enabled=True,
                source_directories=json.dumps(["/srv/project"]),
                created_at=now,
                schedule_enabled=True,
                next_run=now - PAST,
                schedule_mode="availability",
                source_type="remote",
                source_ssh_connection_id=ssh_id,
            ),
        )
        _seed(
            db,
            BackupPlanRepository(
                backup_plan_id=plan_id,
                repository_id=repository_id,
                enabled=True,
                execution_order=1,
                created_at=now,
            ),
        )


@pytest.mark.unit
@pytest.mark.parametrize("where", AWAITS)
async def test_the_pass_holds_no_lock_and_no_connection_while_it_awaits(
    database, monkeypatch, where
):
    """While the pass awaits (a source probe, an alert being sent) the loop
    serves everything else, and the pass keeps neither a write lock nor its
    connection: a write beside it goes through, and its pool is free."""
    _seed_for_await(database, where)
    seen: list[tuple[str, int]] = []

    def look() -> None:
        seen.append((_write_beside(database), database.engine.pool.checkedout()))

    def probe(*args, **kwargs) -> bool:
        look()  # in the probe's own thread
        return True

    async def send(*args, **kwargs) -> None:
        await asyncio.to_thread(look)

    monkeypatch.setattr(schedule_availability, "_ssh_reachable", probe)
    monkeypatch.setattr(NotificationService, "send_stale_backup_alert", send)
    monkeypatch.setattr(NotificationService, "send_backup_report", send)

    await _one_pass(monkeypatch)

    assert seen == [("written", 0)]


# --- the skips and refusals query off the loop as well -----------------------


def _availability_job(db: Database, repository_id: int, **columns) -> int:
    [job_id] = _seed(
        db,
        ScheduledJob(
            name="availability schedule",
            schedule_mode="availability",
            enabled=True,
            next_run=datetime.utcnow() - PAST,
            **columns,
        ),
    )
    _seed(
        db,
        ScheduledJobRepository(
            scheduled_job_id=job_id, repository_id=repository_id, execution_order=0
        ),
    )
    return job_id


def _plan(db: Database, repository_id: int, *, enabled_link=True, **columns) -> int:
    now = datetime.utcnow()
    [plan_id] = _seed(
        db,
        BackupPlan(
            enabled=True,
            source_directories=json.dumps(["/srv/project"]),
            created_at=now,
            schedule_enabled=True,
            next_run=now - PAST,
            **{"name": "due plan", "cron_expression": "0 3 * * *", **columns},
        ),
    )
    _seed(
        db,
        BackupPlanRepository(
            backup_plan_id=plan_id,
            repository_id=repository_id,
            enabled=enabled_link,
            execution_order=1,
            created_at=now,
        ),
    )
    return plan_id


def _recent_success(db: Database, repository_id: int, **owner) -> None:
    now = datetime.utcnow()
    if "scheduled_job_id" in owner:
        _seed(
            db,
            Operation(
                kind="backup",
                category=category_for("backup"),
                run_id=str(uuid.uuid4()),
                repository_id=repository_id,
                status="completed",
                trigger="schedule",
                completed_at=now,
                **owner,
            ),
        )
        return
    _seed(
        db,
        BackupPlanRun(
            backup_plan_id=owner["backup_plan_id"],
            trigger="schedule",
            status="completed",
            created_at=now,
            completed_at=now,
        ),
    )


def _skip_reasons(db: Database) -> list[str]:
    from app.database.models import AvailabilityScheduleSkip

    with db() as session:
        schedule = [row.reason for row in session.query(AvailabilityScheduleSkip)]
        plans = [
            row.skip_reason or row.status
            for row in session.query(BackupPlanRun).filter(
                BackupPlanRun.status.in_(("skipped", "failed"))
            )
        ]
        return schedule + plans


def _scenario(db: Database, name: str, monkeypatch, launches) -> callable:
    """Seed what makes the pass take one path that records a skip or a
    refusal, and return the check of its outcome."""
    _settings(db)
    licensed = name not in ("schedule-plan-required", "plan-plan-required")
    _seed(
        db,
        LicensingState(
            instance_id="scheduler-pass",
            plan="pro" if licensed else "community",
            status="active",
        ),
    )
    [ssh_id] = _seed(db, SSHConnection(host="source.invalid", username="u", port=22))
    borg_2 = {"borg_version": 2} if not licensed else {}
    [repository_id] = _seed(
        db, _repository("refused", source_ssh_connection_id=ssh_id, **borg_2)
    )
    unreachable = lambda *args, **kwargs: False  # noqa: E731

    if name == "schedule-plan-required":
        _seed(
            db,
            ScheduledJob(
                name="borg 2 schedule",
                cron_expression="0 2 * * *",
                enabled=True,
                repository_id=repository_id,
                next_run=datetime.utcnow() - PAST,
            ),
        )
        return lambda: _skip_reasons(db) == ["plan_required"]
    if name == "schedule-minimum-interval":
        job_id = _availability_job(db, repository_id, min_success_interval_minutes=60)
        _recent_success(db, repository_id, scheduled_job_id=job_id)
        return lambda: _skip_reasons(db) == ["minimum_interval_not_elapsed"]
    if name == "schedule-source-unavailable":
        _availability_job(db, repository_id)
        monkeypatch.setattr(schedule_availability, "_ssh_reachable", unreachable)
        return lambda: _skip_reasons(db) == ["source_unavailable"]
    if name == "schedule-dispatch-fails":
        [job_id] = _seed(
            db,
            ScheduledJob(
                name="failing schedule",
                cron_expression="not a cron expression",
                enabled=True,
                repository_id=repository_id,
                next_run=datetime.utcnow() - PAST,
            ),
        )

        def last_run_recorded() -> bool:
            with db() as session:
                return session.get(ScheduledJob, job_id).last_run is not None

        # the backup's operation and the schedule are one commit: a schedule
        # that fails leaves no queued backup and starts nothing
        return lambda: (
            last_run_recorded() and launches == [] and _operations(db) == set()
        )
    if name == "plan-minimum-interval":
        plan_id = _plan(
            db,
            repository_id,
            schedule_mode="availability",
            min_success_interval_minutes=60,
            cron_expression=None,
        )
        _recent_success(db, repository_id, backup_plan_id=plan_id)
        return lambda: _skip_reasons(db) == ["minimum_interval_not_elapsed"]
    if name == "plan-source-unavailable":
        _plan(
            db,
            repository_id,
            schedule_mode="availability",
            source_type="remote",
            source_ssh_connection_id=ssh_id,
            cron_expression=None,
        )
        monkeypatch.setattr(schedule_availability, "_ssh_reachable", unreachable)
        return lambda: _skip_reasons(db) == ["source_unavailable"]
    if name == "plan-plan-required":
        _plan(db, repository_id)
        return lambda: _skip_reasons(db) == ["plan_required"]
    if name == "plan-refused-before-a-run":
        _plan(db, repository_id, enabled_link=False)
        return lambda: _skip_reasons(db) == ["failed"]
    if name == "check-already-queued":
        with db() as session:
            repository = session.get(Repository, repository_id)
            repository.check_cron_expression = "0 3 * * *"
            repository.check_schedule_enabled = True
            repository.next_scheduled_check = datetime.utcnow() - PAST
            session.add(
                Operation(
                    kind="check",
                    category=category_for("check"),
                    run_id=str(uuid.uuid4()),
                    repository_id=repository_id,
                    status="queued",
                    trigger="manual",
                )
            )
            session.commit()

        def one_check() -> bool:
            with db() as session:
                return session.query(Operation).filter(
                    Operation.kind == "check"
                ).count() == 1 and _operations(db) == {("check", repository_id)}

        return one_check
    raise AssertionError(name)


SCENARIOS = [
    "schedule-plan-required",
    "schedule-minimum-interval",
    "schedule-source-unavailable",
    "schedule-dispatch-fails",
    "plan-minimum-interval",
    "plan-source-unavailable",
    "plan-plan-required",
    "plan-refused-before-a-run",
    "check-already-queued",
]


@pytest.mark.unit
@pytest.mark.parametrize("scenario", SCENARIOS)
async def test_no_statement_of_a_skip_or_refusal_runs_on_the_loop(
    database, launches, monkeypatch, scenario
):
    outcome = _scenario(database, scenario, monkeypatch, launches)
    sent: list[tuple] = []

    async def notify(*args, **kwargs) -> None:
        sent.append(args)

    monkeypatch.setattr(schedule_api, "_send_schedule_failure", notify)
    monkeypatch.setattr(plan_service, "_send_plan_required_notice", notify)
    on_the_loop: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if _on_the_loop():
            on_the_loop.append(statement)

    event.listen(database.engine, "before_cursor_execute", record)
    try:
        await _one_pass(monkeypatch)
        await asyncio.sleep(0)  # the notices that were started have run
    finally:
        event.remove(database.engine, "before_cursor_execute", record)

    assert outcome()
    if scenario.endswith("plan-required") or scenario == "schedule-dispatch-fails":
        assert len(sent) == 1
    assert on_the_loop == []


# --- the helper ----------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("ends", ["returns", "raises"])
async def test_a_transaction_off_the_loop_ends_in_its_thread(database, ends):
    """The work runs in a thread, and whether it returns or raises it leaves
    neither its lock nor its connection to the caller."""
    from app.database.database import run_transaction_off_loop
    from app.services.job_admission import lock_backup_capacity_scope

    _settings(database)
    threads: list[bool] = []

    def work(db) -> str:
        threads.append(_on_the_loop())
        lock_backup_capacity_scope(db)
        if ends == "raises":
            raise RuntimeError("failed under the lock")
        return "done"

    with database() as db:
        if ends == "raises":
            with pytest.raises(RuntimeError):
                await run_transaction_off_loop(db, work, db)
        else:
            assert await run_transaction_off_loop(db, work, db) == "done"
        assert database.engine.pool.checkedout() == 0
        assert await asyncio.to_thread(_write_beside, database) == "written"

    assert threads == [False]


# --- what changes between the steps -------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("reachable", [True, False], ids=["reached", "unreachable"])
@pytest.mark.parametrize("change", ["switched-off", "moved", "deleted"])
async def test_a_schedule_changed_while_its_source_is_probed_is_left_alone(
    database, launches, monkeypatch, change, reachable
):
    """Between its steps the pass holds no lock, and a request may change
    the schedule. The dispatch reads it again: a job switched off, moved or
    deleted meanwhile starts nothing and records no skip, and its new timing
    stays, whatever the probe found."""
    _settings(database)
    [repository_id] = _seed(database, _repository("probed"))
    with database() as session:
        session.get(Repository, repository_id).source_ssh_connection_id = _seed(
            database, SSHConnection(host="source.invalid", username="u", port=22)
        )[0]
        session.commit()
    job_id = _availability_job(database, repository_id)
    later = datetime(2999, 1, 1)

    def probe(*args, **kwargs) -> bool:
        with database.side.connect() as connection:
            if change == "switched-off":
                connection.execute(
                    text("UPDATE scheduled_jobs SET enabled = false WHERE id = :id"),
                    {"id": job_id},
                )
            elif change == "moved":
                connection.execute(
                    text("UPDATE scheduled_jobs SET next_run = :later WHERE id = :id"),
                    {"id": job_id, "later": later},
                )
            else:
                connection.execute(
                    text(
                        "DELETE FROM scheduled_job_repositories WHERE scheduled_job_id = :id"
                    ),
                    {"id": job_id},
                )
                connection.execute(
                    text("DELETE FROM scheduled_jobs WHERE id = :id"), {"id": job_id}
                )
            connection.commit()
        return reachable

    monkeypatch.setattr(schedule_availability, "_ssh_reachable", probe)

    await _one_pass(monkeypatch)

    assert launches == []
    assert _operations(database) == set()
    assert _skip_reasons(database) == []
    if change == "moved":
        with database() as session:
            assert session.get(ScheduledJob, job_id).next_run == later


@pytest.mark.unit
async def test_a_plan_deleted_while_its_source_is_probed_ends_nothing_else(
    database, launches, monkeypatch
):
    """A plan deleted between the steps is skipped, and the rest of the pass
    (here a due check) still runs."""
    _settings(database)
    _seed(
        database,
        LicensingState(instance_id="scheduler-pass", plan="pro", status="active"),
    )
    [ssh_id] = _seed(
        database, SSHConnection(host="source.invalid", username="u", port=22)
    )
    [repository_id] = _seed(database, _repository("planned"))
    plan_id = _plan(
        database,
        repository_id,
        schedule_mode="availability",
        source_type="remote",
        source_ssh_connection_id=ssh_id,
        cron_expression=None,
    )
    checked_id = _seed_due_check(database)

    def probe(*args, **kwargs) -> bool:
        with database.side.connect() as connection:
            connection.execute(
                text("DELETE FROM backup_plan_repositories WHERE backup_plan_id = :id"),
                {"id": plan_id},
            )
            connection.execute(
                text("DELETE FROM backup_plans WHERE id = :id"), {"id": plan_id}
            )
            connection.commit()
        return True

    monkeypatch.setattr(schedule_availability, "_ssh_reachable", probe)

    await _one_pass(monkeypatch)

    assert launches == []
    with database() as session:
        assert session.get(BackupPlan, plan_id) is None  # the probe deleted it
        assert session.query(BackupPlanRun).count() == 0
    assert ("check", checked_id) in _operations(database)


@pytest.mark.unit
async def test_a_plan_moved_while_its_source_is_probed_keeps_its_new_time(
    database, launches, monkeypatch
):
    """The probe fails, but the plan was moved meanwhile: no skip is
    recorded and the new time stays."""
    _settings(database)
    _seed(
        database,
        LicensingState(instance_id="scheduler-pass", plan="pro", status="active"),
    )
    [ssh_id] = _seed(
        database, SSHConnection(host="source.invalid", username="u", port=22)
    )
    [repository_id] = _seed(database, _repository("planned"))
    plan_id = _plan(
        database,
        repository_id,
        schedule_mode="availability",
        source_type="remote",
        source_ssh_connection_id=ssh_id,
        cron_expression=None,
    )
    later = datetime(2999, 1, 1)

    def probe(*args, **kwargs) -> bool:
        with database.side.connect() as connection:
            connection.execute(
                text("UPDATE backup_plans SET next_run = :later WHERE id = :id"),
                {"id": plan_id, "later": later},
            )
            connection.commit()
        return False

    monkeypatch.setattr(schedule_availability, "_ssh_reachable", probe)

    await _one_pass(monkeypatch)

    assert _skip_reasons(database) == []
    with database() as session:
        assert session.get(BackupPlan, plan_id).next_run == later


def _both_passes_read_first(monkeypatch) -> None:
    """Each pass waits, before it screens its first job, until the other one
    has read the due jobs too: both start from the same state."""
    both_read = threading.Barrier(2, timeout=HOLD_SECONDS)
    passes_waited: set[int] = set()
    real = schedule_api._screen_due_job

    def screen(db, job_id, now, notices):
        if id(db) not in passes_waited:
            passes_waited.add(id(db))
            both_read.wait()
        return real(db, job_id, now, notices)

    monkeypatch.setattr(schedule_api, "_screen_due_job", screen)


@pytest.mark.unit
async def test_two_passes_at_once_dispatch_a_schedule_once(
    database, launches, monkeypatch
):
    """A process being replaced runs its pass until it is stopped, and the
    new one may run its own meanwhile. Both find the schedule due; the one
    that dispatches holds the job until it has committed the next run, and
    the other then finds it no longer due. A schedule of linked repositories
    creates no operation at dispatch, so the repositories' admission cannot
    tell the two apart."""
    _settings(database)
    [repository_id] = _seed(database, _repository("linked"))
    [job_id] = _seed(
        database,
        ScheduledJob(
            name="linked schedule",
            cron_expression="0 2 * * *",
            enabled=True,
            next_run=datetime.utcnow() - PAST,
        ),
    )
    _seed(
        database,
        ScheduledJobRepository(
            scheduled_job_id=job_id, repository_id=repository_id, execution_order=0
        ),
    )
    first_held = threading.Event()
    go_on = threading.Event()
    dispatches: list[int] = []
    real = schedule_api._dispatch_due_scheduled_job

    def held_first(db, job, now, launches=None):
        dispatches.append(job.id)
        if len(dispatches) == 1:
            first_held.set()
            assert go_on.wait(HOLD_SECONDS)
        return real(db, job, now, launches)

    monkeypatch.setattr(schedule_api, "_dispatch_due_scheduled_job", held_first)
    _both_passes_read_first(monkeypatch)
    now = datetime.utcnow()
    with database() as one, database() as two:
        # both read the due jobs; the first dispatch is then held while the
        # other pass gets as far as it can
        first = asyncio.ensure_future(
            schedule_api.dispatch_due_scheduled_backups(one, now)
        )
        second = asyncio.ensure_future(
            schedule_api.dispatch_due_scheduled_backups(two, now)
        )
        assert await asyncio.to_thread(first_held.wait, HOLD_SECONDS)
        await asyncio.sleep(0.5)
        go_on.set()
        await asyncio.wait_for(asyncio.gather(first, second), HOLD_SECONDS * 4)
        await asyncio.sleep(0)

    assert launches == [("multi-repo", job_id)]


@pytest.mark.unit
@pytest.mark.skipif(not POSTGRES_URL, reason="BORG_TEST_POSTGRES_URL is not set")
async def test_the_claim_does_not_hold_up_an_insert_that_refers_to_the_job(
    launches, monkeypatch
):
    """PostgreSQL. A run-now holds the repository's lock and inserts its
    operation, whose foreign key on the job needs a key-share lock on the job
    row. The scheduler, holding its claim on the job, waits for that
    repository lock. A claim that blocked the key-share lock would be a
    deadlock, and one of the two would be aborted."""
    with _postgres_engines() as (engine, side):
        db = Database("postgresql", engine, side)
        for module in (schedule_api, plan_service, restore_check_scheduler):
            monkeypatch.setattr(module, "SessionLocal", db.sessions)
        _settings(db)
        [repository_id] = _seed(db, _repository("run-now"))
        [job_id] = _seed(
            db,
            ScheduledJob(
                name="single schedule",
                cron_expression="0 2 * * *",
                enabled=True,
                repository_id=repository_id,
                next_run=datetime.utcnow() - PAST,
            ),
        )
        waiting_for_the_repository = threading.Event()
        real_admission = schedule_api.ensure_repository_admission

        def admission(*args, **kwargs):
            waiting_for_the_repository.set()
            return real_admission(*args, **kwargs)

        monkeypatch.setattr(schedule_api, "ensure_repository_admission", admission)
        run_now = sessionmaker(bind=side)()
        try:
            run_now.execute(text("SET lock_timeout = '3s'"))
            run_now.query(Repository).filter(
                Repository.id == repository_id
            ).with_for_update().one()
            with db() as session:
                dispatch = asyncio.ensure_future(
                    schedule_api.dispatch_due_scheduled_backups(
                        session, datetime.utcnow()
                    )
                )
                assert await asyncio.to_thread(
                    waiting_for_the_repository.wait, HOLD_SECONDS
                )
                await asyncio.sleep(0.2)  # the claim is taken, the lock awaited

                def insert() -> str:
                    try:
                        run_now.add(
                            Operation(
                                kind="backup",
                                category=category_for("backup"),
                                run_id=str(uuid.uuid4()),
                                repository_id=repository_id,
                                scheduled_job_id=job_id,
                                status="completed",
                                trigger="schedule",
                                completed_at=datetime.utcnow(),
                            )
                        )
                        run_now.commit()
                        return "inserted"
                    except OperationalError as error:
                        run_now.rollback()
                        return str(error.orig)

                assert await asyncio.to_thread(insert) == "inserted"
                await asyncio.wait_for(dispatch, HOLD_SECONDS * 2)
        finally:
            run_now.close()

    assert launches == [("backup", job_id)]


@pytest.mark.unit
async def test_a_plan_whose_step_fails_leaves_the_rest_of_the_pass(
    database, launches, monkeypatch
):
    """A plan's step that fails (a lock that timed out, a row deleted
    between the steps) is logged; the next plan and the checks still run."""
    _settings(database)
    _seed(
        database,
        LicensingState(instance_id="scheduler-pass", plan="pro", status="active"),
    )
    [repository_id] = _seed(database, _repository("planned"))
    failing = _plan(database, repository_id, name="failing plan")
    second = _plan(database, repository_id, name="second plan")
    checked_id = _seed_due_check(database)
    real = plan_service.BackupPlanExecutionService._screen_due_plan

    def screen(self, db, plan_id, now):
        if plan_id == failing:
            raise OperationalError("SELECT", {}, Exception("lock timeout"))
        return real(self, db, plan_id, now)

    monkeypatch.setattr(
        plan_service.BackupPlanExecutionService, "_screen_due_plan", screen
    )

    await _one_pass(monkeypatch)

    with database() as session:
        runs = {run.backup_plan_id for run in session.query(BackupPlanRun)}
    assert runs == {second}
    assert ("check", checked_id) in _operations(database)


@pytest.mark.unit
async def test_a_refusal_is_not_recorded_for_a_plan_moved_meanwhile(
    database, launches, monkeypatch
):
    """The start refuses before inserting a run (no enabled repository);
    the plan was moved while it did. Its new time stays, and no refusal is
    recorded."""
    _settings(database)
    _seed(
        database,
        LicensingState(instance_id="scheduler-pass", plan="pro", status="active"),
    )
    [repository_id] = _seed(database, _repository("planned"))
    plan_id = _plan(database, repository_id, enabled_link=False)
    later = datetime(2999, 1, 1)
    real = plan_service.BackupPlanExecutionService._start_scheduled_run

    async def start(self, db, plan, now):
        try:
            return await real(self, db, plan, now)
        except ValueError:
            with database.side.connect() as connection:
                connection.execute(
                    text("UPDATE backup_plans SET next_run = :later WHERE id = :id"),
                    {"id": plan_id, "later": later},
                )
                connection.commit()
            raise

    monkeypatch.setattr(
        plan_service.BackupPlanExecutionService, "_start_scheduled_run", start
    )

    await _one_pass(monkeypatch)

    assert _skip_reasons(database) == []
    with database() as session:
        assert session.get(BackupPlan, plan_id).next_run == later


@pytest.mark.unit
async def test_a_failed_dispatch_leaves_a_later_dispatch_alone(
    database, launches, monkeypatch
):
    """The dispatch fails, and another pass has dispatched the job
    meanwhile: the failure does not write its own time over that one's."""
    _settings(database)
    [repository_id] = _seed(database, _repository("single"))
    [job_id] = _seed(
        database,
        ScheduledJob(
            name="single schedule",
            cron_expression="0 2 * * *",
            enabled=True,
            repository_id=repository_id,
            next_run=datetime.utcnow() - PAST,
        ),
    )
    other_run, later = datetime(2999, 1, 1, 2), datetime(2999, 1, 2, 2)
    sent: list[tuple] = []

    async def notify(*args, **kwargs) -> None:
        sent.append(args)

    def dispatched_elsewhere(db, job, now, launches=None):
        with database.side.connect() as connection:
            connection.execute(
                text(
                    "UPDATE scheduled_jobs SET last_run = :ran, next_run = :later "
                    "WHERE id = :id"
                ),
                {"id": job_id, "ran": other_run, "later": later},
            )
            connection.commit()
        raise RuntimeError("the dispatch failed")

    monkeypatch.setattr(schedule_api, "_send_schedule_failure", notify)
    with database() as db:
        # the dispatch's claim is replaced: the other pass writes meanwhile
        monkeypatch.setattr(
            schedule_api,
            "_dispatch_due_job_by_id",
            lambda db, job_id, now, launches: dispatched_elsewhere(db, None, now),
        )
        await schedule_api.dispatch_due_scheduled_backups(db, datetime.utcnow())
        await asyncio.sleep(0)

    with database() as session:
        assert session.get(ScheduledJob, job_id).last_run == other_run
    assert len(sent) == 1


@pytest.mark.unit
async def test_a_stale_backup_alert_is_sent_once_by_two_overlapping_schedulers(
    database, monkeypatch
):
    """A second scheduler checks the monitoring while the first one is
    sending its alert (a slow endpoint). The first recorded its check before
    sending, so the second finds it not due and sends nothing."""
    from app.services import backup_monitoring_service as monitoring

    _settings(database, backup_monitoring_enabled=True)
    _seed(database, _repository("never-backed-up"))
    sent: list[str] = []
    second: list[dict] = []

    async def send(db, *args, **kwargs) -> None:
        sent.append("alert")
        if len(sent) == 1:
            with database() as other:
                second.append(
                    await monitoring.run_backup_monitoring(other, datetime.utcnow())
                )

    monkeypatch.setattr(NotificationService, "send_stale_backup_alert", send)
    with database() as db:
        first = await monitoring.run_backup_monitoring(db, datetime.utcnow())

    assert first["alert_sent"] is True
    assert second == [{"skipped": True, "reason": "not_due", "stale_count": 0}]
    assert sent == ["alert"]
    with database() as session:
        settings = session.query(SystemSettings).one()
        assert settings.backup_monitoring_last_checked_at is not None
        assert settings.backup_monitoring_last_alert_sent_at is not None


@pytest.mark.unit
async def test_two_passes_at_once_keep_to_the_scheduled_backup_limit(
    database, launches, monkeypatch
):
    """One slot is free and two schedules of different repositories are
    due. Both passes count one free slot at their start. The first starts A;
    the second then finds A no longer due, and counts again under the
    capacity lock before it would start B: the slot is taken."""
    with database() as session:
        session.add(SystemSettings(max_concurrent_scheduled_backups=1))
        session.commit()
    repository_a, repository_b = _seed(
        database, _repository("first"), _repository("second")
    )
    due = datetime.utcnow() - PAST
    job_a, job_b = _seed(
        database,
        *(
            ScheduledJob(
                name=f"schedule {repository_id}",
                cron_expression="0 2 * * *",
                enabled=True,
                repository_id=repository_id,
                next_run=due,
            )
            for repository_id in (repository_a, repository_b)
        ),
    )
    first_held = threading.Event()
    go_on = threading.Event()
    dispatches: list[int] = []
    real = schedule_api._dispatch_due_scheduled_job

    def held_first(db, job, now, launches=None):
        dispatches.append(job.id)
        if len(dispatches) == 1:
            first_held.set()
            assert go_on.wait(HOLD_SECONDS)
        return real(db, job, now, launches)

    monkeypatch.setattr(schedule_api, "_dispatch_due_scheduled_job", held_first)
    _both_passes_read_first(monkeypatch)
    now = datetime.utcnow()
    with database() as one, database() as two:
        # both read the due jobs; the first dispatch is then held while the
        # other pass gets as far as it can
        first = asyncio.ensure_future(
            schedule_api.dispatch_due_scheduled_backups(one, now)
        )
        second = asyncio.ensure_future(
            schedule_api.dispatch_due_scheduled_backups(two, now)
        )
        assert await asyncio.to_thread(first_held.wait, HOLD_SECONDS)
        await asyncio.sleep(0.5)
        go_on.set()
        await asyncio.wait_for(asyncio.gather(first, second), HOLD_SECONDS * 4)
        await asyncio.sleep(0)

    assert launches == [("backup", job_a)]
    assert _operations(database) == {("backup", repository_a)}


@pytest.mark.unit
async def test_a_stale_backup_alert_that_cannot_be_prepared_is_tried_again(
    database, monkeypatch
):
    """The check is recorded before the alert is sent. When the alert cannot
    be prepared, the check counts as not made, and the next pass tries
    again."""
    from app.services import backup_monitoring_service as monitoring

    _settings(database, backup_monitoring_enabled=True)
    _seed(database, _repository("never-backed-up"))
    sent: list[str] = []

    async def fails(db, *args, **kwargs) -> None:
        # a failed statement in the session's transaction, as a preparation
        # that hits a timeout leaves it: aborted, on PostgreSQL
        def failing_statement() -> None:
            db.execute(text("SELECT * FROM no_such_table"))

        await asyncio.to_thread(failing_statement)

    monkeypatch.setattr(NotificationService, "send_stale_backup_alert", fails)
    with database() as db:
        with pytest.raises(Exception):
            await monitoring.run_backup_monitoring(db, datetime.utcnow())

    async def send(db, *args, **kwargs) -> None:
        sent.append("alert")

    monkeypatch.setattr(NotificationService, "send_stale_backup_alert", send)
    with database() as db:
        result = await monitoring.run_backup_monitoring(db, datetime.utcnow())

    assert result["alert_sent"] is True
    assert sent == ["alert"]


@pytest.mark.unit
async def test_a_skip_is_written_under_the_jobs_lock(database, monkeypatch):
    """The skip after a failed probe decides on the job under its lock, and
    holds it to the write: an edit of the schedule meanwhile waits, and is
    not overwritten by the skip's next check time."""
    _settings(database)
    [ssh_id] = _seed(
        database, SSHConnection(host="source.invalid", username="u", port=22)
    )
    [repository_id] = _seed(
        database, _repository("probed", source_ssh_connection_id=ssh_id)
    )
    job_id = _availability_job(database, repository_id)
    edits: list[str] = []
    real = schedule_api._record_availability_skip

    def edit_beside() -> str:
        with database.side.connect() as connection:
            try:
                if database.kind == "postgresql":
                    connection.execute(text("SET lock_timeout = '1s'"))
                connection.execute(
                    text("UPDATE scheduled_jobs SET next_run = :t WHERE id = :id"),
                    {"id": job_id, "t": datetime(2999, 1, 1)},
                )
                connection.commit()
                return "edited"
            except OperationalError:
                return "waited"

    def record_skip(*args, **kwargs):
        edits.append(edit_beside())
        return real(*args, **kwargs)

    monkeypatch.setattr(
        schedule_availability, "_ssh_reachable", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(schedule_api, "_record_availability_skip", record_skip)

    await _one_pass(monkeypatch)

    assert edits == ["waited"]
    assert _skip_reasons(database) == ["source_unavailable"]


@pytest.mark.unit
async def test_a_plan_required_skip_is_written_under_the_jobs_lock_on_a_new_install(
    database, monkeypatch
):
    """No licensing row yet: the first feature lookup creates it and
    commits. That happens before the claim, so the skip of a Borg 2 schedule
    is still written under the job's lock: an edit meanwhile waits."""
    _settings(database)
    [repository_id] = _seed(database, _repository("borg-2", borg_version=2))
    [job_id] = _seed(
        database,
        ScheduledJob(
            name="borg 2 schedule",
            cron_expression="0 2 * * *",
            enabled=True,
            repository_id=repository_id,
            next_run=datetime.utcnow() - PAST,
        ),
    )
    edits: list[str] = []
    real = schedule_api._record_availability_skip

    def edit_beside() -> str:
        with database.side.connect() as connection:
            try:
                if database.kind == "postgresql":
                    connection.execute(text("SET lock_timeout = '1s'"))
                connection.execute(
                    text("UPDATE scheduled_jobs SET next_run = :t WHERE id = :id"),
                    {"id": job_id, "t": datetime(2999, 1, 1)},
                )
                connection.commit()
                return "edited"
            except OperationalError:
                return "waited"

    def record_skip(*args, **kwargs):
        edits.append(edit_beside())
        return real(*args, **kwargs)

    async def notify(*args, **kwargs) -> None:
        pass

    monkeypatch.setattr(schedule_api, "_record_availability_skip", record_skip)
    monkeypatch.setattr(schedule_api, "_send_schedule_failure", notify)
    with database() as session:
        assert session.query(LicensingState).count() == 0

    await _one_pass(monkeypatch)

    assert edits == ["waited"]
    assert _skip_reasons(database) == ["plan_required"]
