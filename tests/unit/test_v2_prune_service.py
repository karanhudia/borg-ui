from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.borg2 import borg2
from app.database.models import PruneJob, Repository
from app.services.v2.prune_service import PruneV2Service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_prune_marks_job_complete_and_updates_repo(db_engine):
    testing_session_local = sessionmaker(bind=db_engine)
    session = testing_session_local()
    repo = Repository(
        name="V2 Repo",
        path="/tmp/v2-repo",
        encryption="repokey-aes-ocb",
        repository_type="local",
        borg_version=2,
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)

    job = PruneJob(repository_id=repo.id, repository_path=repo.path, status="pending")
    session.add(job)
    session.commit()
    session.refresh(job)
    repo_id = repo.id
    job_id = job.id
    session.close()

    service = PruneV2Service()

    with (
        patch("app.services.v2.prune_service.SessionLocal", testing_session_local),
        patch(
            "app.services.v2.prune_service.borg2.prune_archives",
            new=AsyncMock(
                return_value={"success": True, "stdout": "pruned", "stderr": ""}
            ),
        ),
    ):
        await service.execute_prune(job_id, repo_id, 0, 7, 4, 6, 0, 1, dry_run=False)

    verification = testing_session_local()
    refreshed_job = verification.query(PruneJob).filter(PruneJob.id == job_id).first()

    assert refreshed_job.status == "completed"
    assert refreshed_job.completed_at is not None
    assert refreshed_job.has_logs is True
    verification.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_prune_marks_job_failed_on_borg_error(db_engine):
    testing_session_local = sessionmaker(bind=db_engine)
    session = testing_session_local()
    repo = Repository(
        name="V2 Repo",
        path="/tmp/v2-repo",
        encryption="repokey-aes-ocb",
        repository_type="local",
        borg_version=2,
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)

    job = PruneJob(repository_id=repo.id, repository_path=repo.path, status="pending")
    session.add(job)
    session.commit()
    session.refresh(job)
    repo_id = repo.id
    job_id = job.id
    session.close()

    service = PruneV2Service()

    with (
        patch("app.services.v2.prune_service.SessionLocal", testing_session_local),
        patch(
            "app.services.v2.prune_service.borg2.prune_archives",
            new=AsyncMock(
                return_value={"success": False, "stdout": "", "stderr": "boom"}
            ),
        ),
    ):
        await service.execute_prune(job_id, repo_id, 0, 7, 4, 6, 0, 1, dry_run=True)

    verification = testing_session_local()
    refreshed_job = verification.query(PruneJob).filter(PruneJob.id == job_id).first()

    assert refreshed_job.status == "failed"
    assert refreshed_job.error_message == "boom"
    assert isinstance(refreshed_job.completed_at, datetime)
    verification.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_borg2_prune_command_omits_stats_flag():
    with patch(
        "app.core.borg2.borg2._run",
        new=AsyncMock(return_value={"success": True, "stdout": "", "stderr": ""}),
    ) as mock_run:
        await borg2.prune_archives(
            repository="/tmp/v2-repo",
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=6,
            keep_yearly=1,
            dry_run=False,
        )

    cmd = mock_run.await_args.args[0]
    assert cmd[:3] == [borg2.borg_cmd, "-r", "/tmp/v2-repo"]
    assert "prune" in cmd
    assert "--stats" not in cmd
    assert "--list" in cmd
