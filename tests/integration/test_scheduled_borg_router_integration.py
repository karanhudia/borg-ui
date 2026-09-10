import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.schedule import execute_scheduled_backup_with_maintenance
from app.database.models import Operation, Repository, ScheduledJob


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scheduled_maintenance_dispatches_v2_repo_through_borg_router(db_session):
    repo = Repository(
        name="V2 Repo",
        path="/tmp/v2-repo",
        encryption="repokey-aes-ocb",
        repository_type="local",
        source_directories=json.dumps(["/tmp/data"]),
        mode="full",
        borg_version=2,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    schedule = ScheduledJob(
        name="Nightly",
        cron_expression="0 2 * * *",
        enabled=True,
        repository_id=repo.id,
        run_prune_after=True,
        run_compact_after=True,
        prune_keep_daily=3,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(schedule)
    db_session.commit()
    db_session.refresh(schedule)

    # Phase 8: a scheduled backup is an operations row that the runner drives,
    # and this test is about what happens after it succeeds, so the row starts
    # out completed and the wait in the function under test returns at once.
    backup_job = Operation(
        repository_id=repo.id,
        kind="backup",
        category="backup",
        status="completed",
        trigger="schedule",
        priority=5,
        run_id="scheduled-run-1",
        scheduled_job_id=schedule.id,
        params={"executor": "server"},
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(backup_job)
    db_session.commit()
    db_session.refresh(backup_job)

    fake_router = SimpleNamespace(prune=AsyncMock(), compact=AsyncMock())

    with (
        patch("app.api.schedule.BorgRouter", return_value=fake_router),
        patch("app.api.schedule.get_db", return_value=iter([db_session])),
    ):
        await execute_scheduled_backup_with_maintenance(
            backup_job.id, repo.path, schedule.id
        )

    fake_router.prune.assert_awaited_once()
    fake_router.compact.assert_awaited_once()
