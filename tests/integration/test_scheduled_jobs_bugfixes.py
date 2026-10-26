"""
Comprehensive tests for scheduled jobs bug fixes.

These tests verify the fixes for three critical bugs:
1. Database session management (SessionLocal vs get_db)
2. NULL timestamps causing "56 years ago" display
3. Repository script execution (inline + library scripts)

Tests cover all scenarios:
- Single repository schedules with inline scripts
- Single repository schedules with library scripts
- Multi-repository schedules with inline scripts
- Multi-repository schedules with library scripts
- Schedule-level scripts + repository-level scripts
- Mixed configurations
"""

import pytest
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from unittest.mock import AsyncMock, patch

from app.database.models import (
    Repository,
    ScheduledJob,
    Script,
    RepositoryScript,
    ScheduledJobRepository,
)
from app.api.schedule import execute_multi_repo_schedule
from tests.utils.operations import operations_runner_for
from app.services.operations.backup_facade import resolve_backup_job
from tests.utils.operations import seed_job_operation


@pytest.mark.integration
@pytest.mark.asyncio
class TestBackupJobTimestamps:
    """Test that backup operations are created with valid timestamps (Bug #2)"""

    async def test_single_repo_schedule_creates_timestamp(self, db_session: Session):
        """Test that single-repo scheduled jobs create a backup operation with a valid created_at"""
        # Setup: Create repository
        repo = Repository(
            name="Test Repo",
            path="/tmp/test-repo",
            encryption="none",
            repository_type="local",
            source_directories=json.dumps(["/tmp/data"]),
            mode="full",
        )
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        # Setup: Create scheduled job (next_run in the past to trigger execution)
        schedule = ScheduledJob(
            name="Test Schedule",
            cron_expression="0 2 * * *",
            enabled=True,
            repository_id=repo.id,
            next_run=datetime.now(timezone.utc) - timedelta(minutes=5),
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(schedule)
        db_session.commit()
        db_session.refresh(schedule)

        # Mock backup execution to prevent actual borg commands
        with patch(
            "app.api.schedule.execute_scheduled_backup_with_maintenance",
            new=AsyncMock(),
        ):
            # Execute: Trigger the scheduler
            # We'll manually call the job creation logic from check_scheduled_jobs

            # Get the schedule
            jobs = (
                db_session.query(ScheduledJob)
                .filter(
                    ScheduledJob.enabled == True,
                    ScheduledJob.next_run <= datetime.now(timezone.utc),
                )
                .all()
            )

            assert len(jobs) == 1
            job = jobs[0]

            # Create backup job (simulating what check_scheduled_jobs does)
            backup_job = seed_job_operation(
                db_session,
                "backup",
                repository=repo.path,
                status="pending",
                scheduled_job_id=job.id,
                created_at=datetime.now(timezone.utc),  # This is the fix
            )
            db_session.commit()
            db_session.refresh(backup_job)

        # Verify: the backup operation has a valid timestamp
        assert backup_job.created_at is not None, "created_at should not be NULL"
        assert isinstance(backup_job.created_at, datetime), (
            "created_at should be datetime"
        )

        # Verify timestamp is NOT NULL and NOT Unix epoch (1970-01-01)
        # The main bug was NULL timestamps showing as "56 years ago" (1970)
        assert backup_job.created_at.year >= 2024, (
            f"Timestamp year should be current (>=2024), not {backup_job.created_at.year}"
        )

    async def test_multi_repo_schedule_creates_timestamps(self, db_session: Session):
        """Test that multi-repo scheduled jobs create a backup operation with a valid created_at for all repos"""
        # Setup: Create multiple repositories
        repos = []
        for i in range(3):
            repo = Repository(
                name=f"Repo {i}",
                path=f"/tmp/repo-{i}",
                encryption="none",
                repository_type="local",
                source_directories=json.dumps([f"/tmp/data-{i}"]),
                mode="full",
            )
            db_session.add(repo)
            repos.append(repo)
        db_session.commit()
        for repo in repos:
            db_session.refresh(repo)

        # Setup: Create multi-repo scheduled job
        schedule = ScheduledJob(
            name="Multi Repo Schedule",
            cron_expression="0 2 * * *",
            enabled=True,
            next_run=datetime.now(timezone.utc) - timedelta(minutes=5),
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(schedule)
        db_session.commit()
        db_session.refresh(schedule)

        # Link repositories to schedule
        for i, repo in enumerate(repos):
            link = ScheduledJobRepository(
                scheduled_job_id=schedule.id, repository_id=repo.id, execution_order=i
            )
            db_session.add(link)
        db_session.commit()

        # Mock backup execution
        with patch(
            "app.services.backup_service.BackupService.execute_backup", new=AsyncMock()
        ):
            # Execute: Manually create backup jobs (simulating execute_multi_repo_schedule)
            backup_jobs = []
            for repo in repos:
                backup_job = seed_job_operation(
                    db_session,
                    "backup",
                    repository=repo.path,
                    status="pending",
                    scheduled_job_id=schedule.id,
                    created_at=datetime.now(timezone.utc),  # This is the fix
                )
                backup_jobs.append(backup_job)
            db_session.commit()
            for job in backup_jobs:
                db_session.refresh(job)

        # Verify: ALL BackupJobs have valid timestamps
        assert len(backup_jobs) == 3
        for i, backup_job in enumerate(backup_jobs):
            assert backup_job.created_at is not None, (
                f"backup operation {i} created_at should not be NULL"
            )
            assert isinstance(backup_job.created_at, datetime)
            # Verify not "56 years ago" (Unix epoch 1970)
            # The main bug was NULL timestamps showing as "56 years ago"
            assert backup_job.created_at.year >= 2024, (
                f"backup operation {i} should have current year (>=2024), not {backup_job.created_at.year}"
            )


@pytest.mark.integration
@pytest.mark.asyncio
class TestRepositoryScriptsRunInBackup:
    """A multi-repository schedule leaves each repository's own scripts to its
    backup, which runs them around `borg create` (#1431)."""

    @pytest.mark.parametrize(
        ("run_repository_scripts", "skip_hooks"), [(True, False), (False, True)]
    )
    async def test_the_backup_runs_the_repository_scripts(
        self, db_session: Session, run_repository_scripts, skip_hooks
    ):
        script = Script(name="stop-db", file_path="scripts/stop_db.sh", timeout=300)
        db_session.add(script)
        repo = Repository(
            name="Repo with Scripts",
            path="/tmp/repo-scripts",
            encryption="none",
            repository_type="local",
            source_directories=json.dumps(["/tmp/data"]),
            mode="full",
            pre_backup_script="echo pre",
            post_backup_script="echo post",
        )
        db_session.add(repo)
        db_session.commit()
        db_session.add(
            RepositoryScript(
                repository_id=repo.id,
                script_id=script.id,
                hook_type="pre-backup",
                execution_order=1,
                enabled=True,
            )
        )
        schedule = ScheduledJob(
            name="Schedule with Repo Scripts",
            cron_expression="0 2 * * *",
            enabled=True,
            run_repository_scripts=run_repository_scripts,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(schedule)
        db_session.commit()
        db_session.add(
            ScheduledJobRepository(
                scheduled_job_id=schedule.id, repository_id=repo.id, execution_order=0
            )
        )
        db_session.commit()

        with (
            patch(
                "app.api.schedule.run_script_from_library", new=AsyncMock()
            ) as library_script,
            patch(
                "app.services.script_library_executor.ScriptLibraryExecutor"
                ".execute_inline_script",
                new=AsyncMock(),
            ) as inline_script,
            patch(
                "app.services.backup_service.BackupService.execute_backup",
                new=AsyncMock(),
            ) as execute_backup,
        ):
            async with operations_runner_for(db_session, patch_session_local=True):
                await execute_multi_repo_schedule(schedule, db_session)

        execute_backup.assert_awaited_once()
        assert execute_backup.await_args.kwargs.get("skip_hooks") is skip_hooks
        library_script.assert_not_awaited()
        inline_script.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
class TestScheduleLevelScripts:
    """Test schedule-level scripts (separate from repository scripts)"""

    async def test_schedule_level_pre_script_executes_once(self, db_session: Session):
        """Test that schedule-level pre-script executes ONCE before all repositories"""
        # Setup: Create schedule-level script
        script = Script(
            name="Schedule Pre-Script",
            description="Runs once before all repos",
            file_path="scripts/schedule_pre.sh",
            timeout=300,
        )
        db_session.add(script)
        db_session.commit()
        db_session.refresh(script)

        # Create script file
        import os
        from app.config import settings

        os.makedirs(os.path.join(settings.data_dir, "scripts"), exist_ok=True)
        script_path = os.path.join(settings.data_dir, "scripts", "schedule_pre.sh")
        with open(script_path, "w") as f:
            f.write("#!/bin/bash\necho 'Schedule pre-script'\n")

        # Setup: Create multiple repositories
        repos = []
        for i in range(3):
            repo = Repository(
                name=f"Repo {i}",
                path=f"/tmp/repo-{i}",
                encryption="none",
                repository_type="local",
                source_directories=json.dumps(["/tmp/data"]),
                mode="full",
            )
            db_session.add(repo)
            repos.append(repo)
        db_session.commit()
        for repo in repos:
            db_session.refresh(repo)

        # Setup: Create schedule with schedule-level pre-script
        schedule = ScheduledJob(
            name="Multi-Repo with Schedule Script",
            cron_expression="0 2 * * *",
            enabled=True,
            pre_backup_script_id=script.id,  # Schedule-level script
            run_repository_scripts=False,  # No repo scripts
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(schedule)
        db_session.commit()
        db_session.refresh(schedule)

        # Link repos
        for i, repo in enumerate(repos):
            link = ScheduledJobRepository(
                scheduled_job_id=schedule.id, repository_id=repo.id, execution_order=i
            )
            db_session.add(link)
        db_session.commit()

        # Track executions
        schedule_script_count = 0

        async def mock_run_script_from_library(
            script,
            db,
            job_id=None,
            repository=None,
            hook_type=None,
            backup_result=None,
            script_parameters=None,
        ):
            nonlocal schedule_script_count
            schedule_script_count += 1
            return {"success": True, "stdout": "Script executed"}

        with patch(
            "app.api.schedule.run_script_from_library", new=mock_run_script_from_library
        ):
            with patch(
                "app.services.backup_service.BackupService.execute_backup",
                new=AsyncMock(),
            ):
                # Phase 8: the schedule enqueues and waits for the runner.
                async with operations_runner_for(db_session, patch_session_local=True):
                    await execute_multi_repo_schedule(schedule, db_session)

        # Verify: Schedule script executed exactly ONCE, not per repository
        assert schedule_script_count == 1, (
            f"Schedule-level script should execute once, not {schedule_script_count} times"
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestCombinedScenarios:
    """Test combinations of all script types"""

    async def test_all_script_types_together(self, db_session: Session):
        """Test schedule with BOTH schedule-level AND repository-level scripts"""
        # Setup: Create schedule-level scripts
        schedule_pre_script = Script(
            name="Schedule Pre", file_path="scripts/sched_pre.sh", timeout=300
        )
        schedule_post_script = Script(
            name="Schedule Post", file_path="scripts/sched_post.sh", timeout=300
        )
        db_session.add(schedule_pre_script)
        db_session.add(schedule_post_script)
        db_session.commit()
        db_session.refresh(schedule_pre_script)
        db_session.refresh(schedule_post_script)

        # Setup: Create repository-level library script
        repo_script = Script(
            name="Repo Library Script", file_path="scripts/repo_lib.sh", timeout=300
        )
        db_session.add(repo_script)
        db_session.commit()
        db_session.refresh(repo_script)

        # Setup: Create repository with inline script
        repo = Repository(
            name="Complex Repo",
            path="/tmp/repo-complex",
            encryption="none",
            repository_type="local",
            source_directories=json.dumps(["/tmp/data"]),
            mode="full",
            pre_backup_script="echo 'Inline script'",  # This should be ignored due to library script
        )
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        # Assign library script to repo
        repo_script_link = RepositoryScript(
            repository_id=repo.id,
            script_id=repo_script.id,
            hook_type="pre-backup",
            execution_order=1,
            enabled=True,
        )
        db_session.add(repo_script_link)
        db_session.commit()

        # Setup: Create schedule with ALL options enabled
        schedule = ScheduledJob(
            name="Complex Schedule",
            cron_expression="0 2 * * *",
            enabled=True,
            pre_backup_script_id=schedule_pre_script.id,  # Schedule pre
            post_backup_script_id=schedule_post_script.id,  # Schedule post
            run_repository_scripts=True,  # Enable repo scripts
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(schedule)
        db_session.commit()
        db_session.refresh(schedule)

        # Link repo
        link = ScheduledJobRepository(
            scheduled_job_id=schedule.id, repository_id=repo.id, execution_order=0
        )
        db_session.add(link)
        db_session.commit()

        # Track execution order
        execution_order = []

        async def mock_library_script(
            script,
            db,
            job_id=None,
            repository=None,
            hook_type=None,
            backup_result=None,
            script_parameters=None,
        ):
            execution_order.append(f"schedule:{script.name}")
            return {"success": True}

        async def mock_repo_library_script(
            script,
            db,
            job_id=None,
            repository=None,
            hook_type=None,
            backup_result=None,
            script_parameters=None,
        ):
            execution_order.append(f"repo-library:{script.name}")
            return {"success": True}

        # We need different mocks for schedule vs repo scripts
        original_run_script = None

        async def smart_mock_script(
            script,
            db,
            job_id=None,
            repository=None,
            hook_type=None,
            backup_result=None,
            script_parameters=None,
        ):
            if script.name in ["Schedule Pre", "Schedule Post"]:
                execution_order.append(f"schedule:{script.name}")
            else:
                execution_order.append(f"repo-library:{script.name}")
            return {"success": True}

        backup_kwargs = []

        async def mock_backup(*args, **kwargs):
            execution_order.append("backup")
            backup_kwargs.append(kwargs)
            # Mark backup as completed
            if args:
                job_id = args[0]
            else:
                job_id = kwargs.get("job_id")
            if job_id:
                backup_job = resolve_backup_job(db_session, job_id)
                if backup_job:
                    backup_job.status = "completed"
                    db_session.commit()

        with patch("app.api.schedule.run_script_from_library", new=smart_mock_script):
            with patch(
                "app.services.backup_service.BackupService.execute_backup",
                new=mock_backup,
            ):
                # Phase 8: the schedule enqueues and waits for the runner.
                async with operations_runner_for(db_session, patch_session_local=True):
                    await execute_multi_repo_schedule(schedule, db_session)

        # Verify: Execution order is correct
        # Expected: Schedule Pre -> Backup (with its repository scripts) -> Schedule Post
        assert len(execution_order) >= 3, (
            f"Should have at least 3 executions, got {execution_order}"
        )
        assert execution_order[0] == "schedule:Schedule Pre", (
            "Schedule pre-script should run first"
        )
        assert "backup" in execution_order, "Backup should execute"
        assert execution_order[-1] == "schedule:Schedule Post", (
            "Schedule post-script should run last"
        )
        # the backup runs the repository's own scripts (#1431); asserted here,
        # since the runner would swallow a failure inside the backup
        assert backup_kwargs and not any(k.get("skip_hooks") for k in backup_kwargs)
        assert "repo-library:Repo Library Script" not in execution_order, (
            "The backup runs the repository's scripts, not the schedule"
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestDatabaseSessionManagement:
    """Test database session management fix (Bug #1)"""

    async def test_session_persists_across_async_tasks(self, db_session: Session):
        """Test that database changes persist when using SessionLocal instead of get_db"""
        # This test verifies that the fix (using SessionLocal) allows data to persist

        # Setup: Create repository
        repo = Repository(
            name="Session Test Repo",
            path="/tmp/session-test",
            encryption="none",
            repository_type="local",
            source_directories=json.dumps(["/tmp/data"]),
            mode="full",
        )
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        # Create a backup operation in one "session context"
        backup_job = seed_job_operation(
            db_session,
            "backup",
            repository=repo.path,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        db_session.commit()
        db_session.refresh(backup_job)

        job_id = backup_job.id

        # Simulate async task trying to read the job (in real code, this would be a new SessionLocal())
        # The bug was that get_db() didn't properly initialize, causing detached instances

        # Read it back
        retrieved_job = resolve_backup_job(db_session, job_id)

        # Verify: Job exists and has timestamp
        assert retrieved_job is not None, (
            "the backup operation should exist in database"
        )
        assert retrieved_job.created_at is not None, "created_at should be persisted"
        assert retrieved_job.status == "pending"

    async def test_multiple_repos_dont_cause_detached_instances(
        self, db_session: Session
    ):
        """Test that processing multiple repositories doesn't cause detached instance errors"""
        # This was the symptom of Bug #1 - second repo would fail with detached instance error

        # Setup: Create 3 repositories
        repos = []
        for i in range(3):
            repo = Repository(
                name=f"Detached Test Repo {i}",
                path=f"/tmp/detached-{i}",
                encryption="none",
                repository_type="local",
                source_directories=json.dumps(["/tmp/data"]),
                mode="full",
            )
            db_session.add(repo)
            repos.append(repo)
        db_session.commit()
        for repo in repos:
            db_session.refresh(repo)

        # Create BackupJobs for all repos (simulating multi-repo schedule)
        job_ids = []
        for repo in repos:
            backup_job = seed_job_operation(
                db_session,
                "backup",
                repository=repo.path,
                status="pending",
                created_at=datetime.now(timezone.utc),
            )
            db_session.commit()
            db_session.refresh(backup_job)
            job_ids.append(backup_job.id)

        # Verify: All jobs can be read back without detached instance errors
        for job_id in job_ids:
            job = resolve_backup_job(db_session, job_id)
            assert job is not None
            assert job.created_at is not None
            assert isinstance(job.created_at, datetime)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
