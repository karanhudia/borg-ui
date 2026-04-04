"""
Integration coverage for Borg-backed backup workflows.

These tests focus on gaps that are easy to miss in unit tests:
- A repository backed up from multiple source directories
- A scheduled job that fans out to multiple repositories
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.api.schedule import execute_multi_repo_schedule
from app.database.models import BackupJob, ScheduledJob, ScheduledJobRepository
from app.services.backup_service import backup_service
from tests.utils.borg import (
    create_registered_local_repository,
    get_latest_archive_name,
    list_archive_paths,
)

try:
    from .test_helpers import make_borg_env
except ImportError:
    from test_helpers import make_borg_env


@pytest.mark.integration
@pytest.mark.requires_borg
@pytest.mark.asyncio
class TestMultiSourceBackupIntegration:
    """Real Borg backup coverage for repositories with multiple source directories."""

    async def test_backup_includes_all_source_directories(
        self,
        test_db: Session,
        borg_binary: str,
        tmp_path: Path,
    ):
        borg_env = make_borg_env(str(tmp_path))
        repo, repo_path, _source_path = create_registered_local_repository(
            test_db=test_db,
            borg_binary=borg_binary,
            tmp_path=tmp_path / "multi-source",
            name="Multi Source Repo",
            slug="multi-source",
            source_files={
                "alpha/alpha-only.txt": "payload for alpha-only.txt",
                "beta/beta-only.txt": "payload for beta-only.txt",
            },
            borg_env=borg_env,
        )

        job = BackupJob(
            repository=repo.path,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        notification_mock = MagicMock()
        notification_mock.send_backup_start = AsyncMock(return_value=None)
        notification_mock.send_backup_success = AsyncMock(return_value=None)
        notification_mock.send_backup_warning = AsyncMock(return_value=None)
        notification_mock.send_backup_failure = AsyncMock(return_value=None)

        with patch("app.services.backup_service.notification_service", notification_mock):
            with patch("app.services.backup_service.mqtt_service.sync_state_with_db"):
                with patch.dict("os.environ", borg_env, clear=False):
                    await backup_service.execute_backup(job.id, repo.path, test_db)

        test_db.refresh(job)
        assert job.status in ["completed", "completed_with_warnings"]

        archive_name = get_latest_archive_name(borg_binary, repo_path, env=borg_env)
        archive_paths = list_archive_paths(borg_binary, repo_path, archive_name, env=borg_env)

        assert any(path.endswith("alpha-only.txt") for path in archive_paths)
        assert any(path.endswith("beta-only.txt") for path in archive_paths)


@pytest.mark.integration
@pytest.mark.requires_borg
@pytest.mark.asyncio
class TestMultiRepoScheduledBackupIntegration:
    """Real Borg coverage for a scheduled backup that targets multiple repositories."""

    async def test_multi_repo_schedule_creates_backups_for_every_repository(
        self,
        test_db: Session,
        borg_binary: str,
        tmp_path: Path,
    ):
        borg_env = make_borg_env(str(tmp_path))
        repo1, repo1_path, _ = create_registered_local_repository(
            test_db=test_db,
            borg_binary=borg_binary,
            tmp_path=tmp_path / "schedule-one",
            name="Scheduled Repo One",
            slug="schedule-one",
            source_files={"source/repo-one.txt": "payload for repo-one.txt"},
            borg_env=borg_env,
        )
        repo2, repo2_path, _ = create_registered_local_repository(
            test_db=test_db,
            borg_binary=borg_binary,
            tmp_path=tmp_path / "schedule-two",
            name="Scheduled Repo Two",
            slug="schedule-two",
            source_files={"source/repo-two.txt": "payload for repo-two.txt"},
            borg_env=borg_env,
        )

        schedule = ScheduledJob(
            name="Nightly Multi Repo",
            cron_expression="* * * * *",
            enabled=True,
            run_repository_scripts=False,
            run_prune_after=False,
            run_compact_after=False,
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        test_db.add_all(
            [
                ScheduledJobRepository(
                    scheduled_job_id=schedule.id,
                    repository_id=repo1.id,
                    execution_order=0,
                ),
                ScheduledJobRepository(
                    scheduled_job_id=schedule.id,
                    repository_id=repo2.id,
                    execution_order=1,
                ),
            ]
        )
        test_db.commit()

        notification_mock = MagicMock()
        notification_mock.send_schedule_failure = AsyncMock(return_value=None)

        with patch("app.api.schedule.notification_service", notification_mock):
            with patch("app.services.backup_service.notification_service", notification_mock):
                with patch("app.services.backup_service.mqtt_service.sync_state_with_db"):
                    with patch.dict("os.environ", borg_env, clear=False):
                        await execute_multi_repo_schedule(schedule, test_db)

        test_db.refresh(schedule)

        backup_jobs = (
            test_db.query(BackupJob)
            .filter(BackupJob.scheduled_job_id == schedule.id)
            .order_by(BackupJob.id.asc())
            .all()
        )
        assert len(backup_jobs) == 2
        assert all(job.status in ["completed", "completed_with_warnings"] for job in backup_jobs)

        archive1 = get_latest_archive_name(borg_binary, repo1_path, env=borg_env)
        archive2 = get_latest_archive_name(borg_binary, repo2_path, env=borg_env)

        paths1 = list_archive_paths(borg_binary, repo1_path, archive1, env=borg_env)
        paths2 = list_archive_paths(borg_binary, repo2_path, archive2, env=borg_env)

        assert any(path.endswith("repo-one.txt") for path in paths1)
        assert any(path.endswith("repo-two.txt") for path in paths2)
