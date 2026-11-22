"""The licensing row and a plan's feature access under concurrent requests.

The first lookups of a new install each created a licensing row when they ran
at once. A scheduled plan run checked its feature access before the start
only: the lookup ended the transaction, so it could not run under the plan's
start lock, and a license that lapsed in between still let the run start.

Reuses the harness of test_scheduler_pass_off_event_loop.py. The tests run on
SQLite and, with BORG_TEST_POSTGRES_URL set, on PostgreSQL.
"""

import asyncio
import threading
from datetime import datetime

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError

from app.database.models import (
    BackupPlan,
    BackupPlanRepository,
    BackupPlanRun,
    LicensingState,
)
import app.services.backup_plan_execution_service as plan_service
from app.services import licensing_service
from app.services.backup_plan_execution_service import backup_plan_execution_service
from tests.unit import test_scheduler_pass_off_event_loop as harness

# the harness's fixtures, for this module's tests
database = harness.database
launches = harness.launches


def _licensing_lock_free(database) -> bool:
    """Whether the test's own connection can take the licensing lock now."""
    with database.side.connect() as connection:
        if database.kind == "postgresql":
            return connection.execute(
                text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
                {"lock_id": licensing_service.LICENSING_LOCK_ID},
            ).scalar()
        try:
            connection.execute(text("UPDATE licensing_state SET id = id"))
            connection.commit()
            return True
        except OperationalError:
            return False


@pytest.mark.unit
async def test_two_first_licensing_lookups_create_one_row(database):
    """No licensing row exists yet. Two requests look it up at once: both
    find none, and only one row is created.

    Each lookup's first read of the row waits until the other one has read
    too, so both find none; what either does after that is not held up."""
    both_read = threading.Barrier(2)
    both_done = threading.Barrier(2)
    one_probe = threading.Lock()
    found_none: list[bool] = []
    unlocked: list[bool] = []

    def lookup() -> str:
        with database() as session:
            first_read = True

            @event.listens_for(session, "do_orm_execute")
            def read_together(orm_execute_state):
                nonlocal first_read
                if not first_read or not any(
                    mapper.class_ is LicensingState
                    for mapper in orm_execute_state.all_mappers
                ):
                    return None
                first_read = False
                rows = orm_execute_state.invoke_statement().freeze()
                found_none.append(not rows.data)
                both_read.wait(timeout=harness.HOLD_SECONDS)
                return rows()

            state = licensing_service.get_or_create_licensing_state(session)
            # Both lookups are over, their sessions still open: each one has
            # ended its transaction, and the lock with it. One probe at a
            # time, or one would find the other's.
            both_done.wait(timeout=harness.HOLD_SECONDS)
            with one_probe:
                unlocked.append(_licensing_lock_free(database))
            return state.instance_id

    first, second = await asyncio.wait_for(
        asyncio.gather(asyncio.to_thread(lookup), asyncio.to_thread(lookup)),
        harness.HOLD_SECONDS * 2,
    )

    assert found_none == [True, True]
    assert first == second
    assert unlocked == [True, True]
    with database() as session:
        assert session.query(LicensingState).count() == 1


@pytest.mark.unit
def test_a_first_lookup_without_commit_leaves_its_row_to_the_caller(database):
    """With `commit=False` the first lookup creates the row in the caller's
    open transaction: rolled back, no row is left."""
    with database() as session:
        state = licensing_service.get_or_create_licensing_state(session, commit=False)
        assert state.instance_id
        session.rollback()

    with database() as session:
        assert session.query(LicensingState).count() == 0


def _seed_plan_that_needs_pro(database) -> int:
    harness._settings(database)
    harness._seed(
        database, LicensingState(instance_id="licensing", plan="pro", status="active")
    )
    first, second = harness._seed(
        database, harness._repository("first"), harness._repository("second")
    )
    plan_id = harness._plan(database, first)
    harness._seed(
        database,
        BackupPlanRepository(
            backup_plan_id=plan_id,
            repository_id=second,
            enabled=True,
            execution_order=2,
            created_at=datetime.utcnow(),
        ),
    )
    return plan_id


@pytest.mark.unit
async def test_a_plan_whose_license_lapses_before_its_start_starts_no_run(
    database, monkeypatch, launches
):
    """A plan of two repositories needs Pro. The access check passes; the
    license lapses before the run is started: no run starts, the plan stays
    due, and the next pass records the refusal and sends its notice."""
    plan_id = _seed_plan_that_needs_pro(database)
    with database() as session:
        due = session.get(BackupPlan, plan_id).next_run
    notices: list[str] = []

    async def notice(plan_name, *args) -> None:
        notices.append(plan_name)

    monkeypatch.setattr(plan_service, "_send_plan_required_notice", notice)
    real = backup_plan_execution_service._check_access
    lapsed: list[bool] = []

    def check_then_lapse(db, plan_id, now, notices):
        decision = real(db, plan_id, now, notices)
        with database.side.connect() as connection:
            connection.execute(text("UPDATE licensing_state SET status = 'expired'"))
            connection.commit()
        lapsed.append(decision[0])
        return decision

    monkeypatch.setattr(
        backup_plan_execution_service, "_check_access", check_then_lapse
    )
    with database() as db:
        await backup_plan_execution_service.dispatch_due_runs(db, datetime.utcnow())
    await asyncio.sleep(0)

    assert lapsed == [True]
    assert [launch for launch in launches if launch[0] == "plan"] == []
    with database() as session:
        assert session.query(BackupPlanRun).count() == 0
        assert session.get(BackupPlan, plan_id).next_run == due

    with database() as db:
        await backup_plan_execution_service.dispatch_due_runs(db, datetime.utcnow())
    await asyncio.sleep(0)

    assert lapsed == [True, False]
    assert [launch for launch in launches if launch[0] == "plan"] == []
    assert harness._skip_reasons(database) == ["plan_required"]
    assert notices == ["due plan"]


@pytest.mark.unit
async def test_the_access_check_at_the_start_keeps_the_plan_locked(
    database, monkeypatch, launches
):
    """The access check before the start runs without the plan's lock; the
    one at the start runs under it and keeps it: a write to the plan waits
    until the run is started."""
    plan_id = _seed_plan_that_needs_pro(database)
    real = plan_service.evaluate_backup_plan_access
    edits: list[str] = []

    def edit_beside() -> str:
        with database.side.connect() as connection:
            try:
                if database.kind == "postgresql":
                    connection.execute(text("SET lock_timeout = '1s'"))
                connection.execute(
                    text("UPDATE backup_plans SET id = id WHERE id = :id"),
                    {"id": plan_id},
                )
                connection.commit()
                return "edited"
            except OperationalError:
                return "waited"

    def evaluate_then_edit(*args, **kwargs):
        decision = real(*args, **kwargs)
        edits.append(edit_beside())
        return decision

    monkeypatch.setattr(plan_service, "evaluate_backup_plan_access", evaluate_then_edit)
    with database() as db:
        await backup_plan_execution_service.dispatch_due_runs(db, datetime.utcnow())
    await asyncio.sleep(0)

    assert edits == ["edited", "waited"]
    assert len([launch for launch in launches if launch[0] == "plan"]) == 1
