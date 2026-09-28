import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

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
    # and this test is about what happens after it succeeds: the row is
    # completed while the function under test waits for it, on a session of
    # its own, so maintenance runs only when that wait saw the completion.
    backup_job = Operation(
        repository_id=repo.id,
        kind="backup",
        category="backup",
        status="running",
        trigger="schedule",
        priority=5,
        run_id="scheduled-run-1",
        scheduled_job_id=schedule.id,
        params={"executor": "server"},
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(backup_job)
    db_session.commit()
    db_session.refresh(backup_job)

    operation_id = backup_job.id
    fixture_sessions = sessionmaker(bind=db_session.get_bind())

    def _complete_backup():
        session = fixture_sessions()
        try:
            operation = session.get(Operation, operation_id)
            operation.status = "completed"
            operation.completed_at = datetime.now(timezone.utc)
            session.commit()
        finally:
            session.close()

    fake_router = SimpleNamespace(prune=AsyncMock(), compact=AsyncMock())

    with (
        patch("app.api.schedule.BorgRouter", return_value=fake_router),
        patch("app.api.schedule.get_db", return_value=iter([db_session])),
        patch("app.database.database.SessionLocal", fixture_sessions),
    ):
        asyncio.get_running_loop().call_later(0.05, _complete_backup)
        # In production the task opens a fresh session; this one has the row
        # loaded, so it forgets it and reads the completion like a fresh one.
        db_session.expire_all()
        await execute_scheduled_backup_with_maintenance(
            operation_id, repo.path, schedule.id
        )

    fake_router.prune.assert_awaited_once()
    fake_router.compact.assert_awaited_once()
