"""A Borg 2 backup once the plan no longer includes Borg 2: refused on every
path, and a scheduled one skipped visibly and announced once."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import schedule as schedule_api
from app.database.models import (
    AvailabilityScheduleSkip,
    BackupPlanRun,
    Operation,
    ScheduledJob,
)
from app.services.backup_plan_execution_service import backup_plan_execution_service
from app.services.operations.backup_facade import create_backup_operation
from tests.unit.test_api_backup_plans import (
    _create_repo,
    _create_scheduled_plan,
    _set_plan,
)


def _v2_repo(test_db):
    return _create_repo(test_db, "Borg 2", "/repos/borg2", borg_version=2)


def _close(coro):
    coro.close()
    return MagicMock()


@pytest.mark.unit
def test_borg2_backup_is_refused_where_every_backup_is_created(test_db):
    _set_plan(test_db, "community")
    repo = _v2_repo(test_db)

    with pytest.raises(HTTPException) as refused:
        create_backup_operation(test_db, repo, trigger="manual", executor="server")

    assert refused.value.status_code == 403
    assert refused.value.detail["feature"] == "borg_v2"
    assert test_db.query(Operation).count() == 0

    _set_plan(test_db, "pro")
    with patch("app.services.operations.enqueue.wake_runner"):
        create_backup_operation(test_db, repo, trigger="manual", executor="server")
    assert test_db.query(Operation).count() == 1


@pytest.mark.unit
def test_borg1_backup_is_not_affected(test_db):
    _set_plan(test_db, "community")
    repo = _create_repo(test_db, "Borg 1", "/repos/borg1")

    with patch("app.services.operations.enqueue.wake_runner"):
        create_backup_operation(test_db, repo, trigger="manual", executor="server")

    assert test_db.query(Operation).count() == 1


@pytest.mark.unit
def test_legacy_backup_start_refuses_borg2_on_community(
    test_client: TestClient, admin_headers, test_db
):
    _set_plan(test_db, "community")
    repo = _v2_repo(test_db)

    response = test_client.post(
        "/api/backup/start", json={"repository": repo.path}, headers=admin_headers
    )

    assert response.status_code == 403
    assert response.json()["detail"]["feature"] == "borg_v2"


@pytest.mark.unit
def test_plan_run_refuses_borg2_on_community(
    test_client: TestClient, admin_headers, test_db
):
    _set_plan(test_db, "community")
    plan = _create_scheduled_plan(test_db, [_v2_repo(test_db)])

    response = test_client.post(
        f"/api/backup-plans/{plan.id}/run", headers=admin_headers
    )

    assert response.status_code == 403
    assert response.json()["detail"]["feature"] == "borg_v2"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduled_plan_is_skipped_visibly_and_announced_once(test_db):
    _set_plan(test_db, "community")
    now = datetime(2026, 1, 1, 2, 0)
    plan = _create_scheduled_plan(
        test_db, [_v2_repo(test_db)], next_run=now - timedelta(minutes=1)
    )

    with (
        patch(
            "app.services.backup_plan_execution_service._send_plan_required_notice",
            new_callable=AsyncMock,
        ) as notice,
        patch(
            "app.services.backup_plan_execution_service.asyncio.create_task",
            side_effect=_close,
        ),
    ):
        assert await backup_plan_execution_service.dispatch_due_runs(test_db, now) == 0
        plan.next_run = now
        test_db.commit()
        later = now + timedelta(days=1)
        assert (
            await backup_plan_execution_service.dispatch_due_runs(test_db, later) == 0
        )

    runs = test_db.query(BackupPlanRun).filter_by(backup_plan_id=plan.id).all()
    assert [(r.status, r.skip_reason, r.trigger) for r in runs] == [
        ("skipped", "plan_required", "schedule"),
        ("skipped", "plan_required", "schedule"),
    ]
    assert notice.call_count == 1
    assert "Borg 2 repositories need the Pro plan" in notice.call_args.args[2]
    assert test_db.query(Operation).count() == 0
    test_db.refresh(plan)
    assert plan.next_run > later


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduled_job_is_skipped_visibly_and_announced_once(test_db):
    _set_plan(test_db, "community")
    repo = _v2_repo(test_db)
    now = datetime(2026, 1, 1, 2, 0)
    job = ScheduledJob(
        name="Nightly",
        cron_expression="0 2 * * *",
        enabled=True,
        repository_id=repo.id,
        next_run=now - timedelta(minutes=1),
    )
    test_db.add(job)
    test_db.commit()

    with (
        patch(
            "app.api.schedule._send_schedule_failure", new_callable=AsyncMock
        ) as notice,
        patch("app.api.schedule.asyncio.create_task", side_effect=_close),
        patch("app.api.schedule._dispatch_due_scheduled_job") as dispatch,
    ):
        await schedule_api.dispatch_due_scheduled_backups(test_db, now)
        job.next_run = now
        test_db.commit()
        await schedule_api.dispatch_due_scheduled_backups(
            test_db, now + timedelta(days=1)
        )

    dispatch.assert_not_called()
    skips = test_db.query(AvailabilityScheduleSkip).filter_by(scheduled_job_id=job.id)
    assert [s.reason for s in skips] == ["plan_required", "plan_required"]
    assert notice.call_count == 1
    test_db.refresh(job)
    assert job.next_run > now + timedelta(days=1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduled_job_dispatches_borg2_on_pro(test_db):
    _set_plan(test_db, "pro")
    repo = _v2_repo(test_db)
    now = datetime(2026, 1, 1, 2, 0)
    job = ScheduledJob(
        name="Nightly",
        cron_expression="0 2 * * *",
        enabled=True,
        repository_id=repo.id,
        next_run=now - timedelta(minutes=1),
    )
    test_db.add(job)
    test_db.commit()

    with patch(
        "app.api.schedule._dispatch_due_scheduled_job", return_value="k"
    ) as dispatch:
        await schedule_api.dispatch_due_scheduled_backups(test_db, now)

    dispatch.assert_called_once()
    assert test_db.query(AvailabilityScheduleSkip).count() == 0
