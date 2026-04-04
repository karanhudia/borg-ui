"""
Integration coverage for Borg-backed backup workflows.

These tests focus on gaps that are easy to miss in unit tests:
- A repository backed up from multiple source directories
- A scheduled job that fans out to multiple repositories
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.api.schedule import execute_multi_repo_schedule
from app.database.models import BackupJob, Repository, ScheduledJob, ScheduledJobRepository
from app.services.backup_service import backup_service

try:
    from .test_helpers import make_borg_env
except ImportError:
    from test_helpers import make_borg_env


def _init_borg_repo_with_sources(
    tmp_path: Path,
    borg_binary: str,
    borg_env: dict,
    test_db: Session,
    name: str,
    repo_dirname: str,
    sources: list[tuple[str, str]],
) -> tuple[Repository, Path, list[Path]]:
    repo_path = tmp_path / repo_dirname / "repo"
    repo_path.mkdir(parents=True)

    source_paths: list[Path] = []
    for source_dir_name, file_name in sources:
        source_dir = tmp_path / repo_dirname / source_dir_name
        source_dir.mkdir(parents=True)
        source_paths.append(source_dir)
        (source_dir / file_name).write_text(f"payload for {file_name}")

    result = subprocess.run(
        [borg_binary, "init", "--encryption=none", str(repo_path)],
        env=borg_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    repo = Repository(
        name=name,
        path=str(repo_path),
        encryption="none",
        compression="lz4",
        repository_type="local",
        mode="full",
        source_directories=json.dumps([str(path) for path in source_paths]),
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)

    return repo, repo_path, source_paths


def _list_borg_archive_paths(
    borg_binary: str,
    repo_path: Path,
    archive_name: str,
    borg_env: dict,
) -> set[str]:
    result = subprocess.run(
        [borg_binary, "list", "--json-lines", f"{repo_path}::{archive_name}"],
        env=borg_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    archive_paths: set[str] = set()
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        path = payload.get("path")
        if path:
            archive_paths.add(path)
    return archive_paths


def _get_single_archive_name(borg_binary: str, repo_path: Path, borg_env: dict) -> str:
    result = subprocess.run(
        [borg_binary, "list", "--short", str(repo_path)],
        env=borg_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    archives = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert archives, f"expected at least one archive in {repo_path}"
    return archives[-1]


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
        repo, repo_path, source_paths = _init_borg_repo_with_sources(
            tmp_path,
            borg_binary,
            borg_env,
            test_db,
            name="Multi Source Repo",
            repo_dirname="multi-source",
            sources=[
                ("alpha", "alpha-only.txt"),
                ("beta", "beta-only.txt"),
            ],
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

        archive_name = _get_single_archive_name(borg_binary, repo_path, borg_env)
        archive_paths = _list_borg_archive_paths(borg_binary, repo_path, archive_name, borg_env)

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
        repo1, repo1_path, _ = _init_borg_repo_with_sources(
            tmp_path,
            borg_binary,
            borg_env,
            test_db,
            name="Scheduled Repo One",
            repo_dirname="schedule-one",
            sources=[("source", "repo-one.txt")],
        )
        repo2, repo2_path, _ = _init_borg_repo_with_sources(
            tmp_path,
            borg_binary,
            borg_env,
            test_db,
            name="Scheduled Repo Two",
            repo_dirname="schedule-two",
            sources=[("source", "repo-two.txt")],
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

        archive1 = _get_single_archive_name(borg_binary, repo1_path, borg_env)
        archive2 = _get_single_archive_name(borg_binary, repo2_path, borg_env)

        paths1 = _list_borg_archive_paths(borg_binary, repo1_path, archive1, borg_env)
        paths2 = _list_borg_archive_paths(borg_binary, repo2_path, archive2, borg_env)

        assert any(path.endswith("repo-one.txt") for path in paths1)
        assert any(path.endswith("repo-two.txt") for path in paths2)
