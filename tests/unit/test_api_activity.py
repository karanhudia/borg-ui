"""
Unit tests for activity API - log buffer functionality.
"""

import pytest
from datetime import datetime, timedelta


def _set_log_save_policy(test_db, policy: str) -> None:
    from app.database.models import SystemSettings

    settings = test_db.query(SystemSettings).first()
    if settings is None:
        settings = SystemSettings()
        test_db.add(settings)
    settings.log_save_policy = policy
    test_db.commit()


def _create_activity_repository(test_db, name: str = "Policy Repo"):
    from app.database.models import Repository

    repo = Repository(
        name=name,
        path=f"/tmp/{name.lower().replace(' ', '-')}",
        encryption="none",
        compression="lz4",
        repository_type="local",
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


class TestBackupServiceLogBuffer:
    """Test BackupService log buffer methods"""

    def test_get_log_buffer_returns_tail(self):
        """Test that get_log_buffer returns last N lines"""
        from app.services.backup_service import BackupService

        service = BackupService()

        # Create a mock buffer with 100 lines
        job_id = 123
        service.log_buffers[job_id] = [f"line {i}" for i in range(100)]

        # Get last 10 lines
        result, buffer_exists = service.get_log_buffer(job_id, tail_lines=10)

        assert buffer_exists is True
        assert len(result) == 10
        assert result[0] == "line 90"
        assert result[-1] == "line 99"

    def test_get_log_buffer_returns_all_if_smaller(self):
        """Test that get_log_buffer returns all lines if buffer is smaller than tail_lines"""
        from app.services.backup_service import BackupService

        service = BackupService()

        # Create a small buffer
        job_id = 456
        service.log_buffers[job_id] = ["line 1", "line 2", "line 3"]

        # Request 500 lines
        result, buffer_exists = service.get_log_buffer(job_id, tail_lines=500)

        assert buffer_exists is True
        assert len(result) == 3
        assert result == ["line 1", "line 2", "line 3"]

    def test_get_log_buffer_empty_for_nonexistent_job(self):
        """Test that get_log_buffer returns empty list and False for nonexistent job"""
        from app.services.backup_service import BackupService

        service = BackupService()

        # Request buffer for job that doesn't exist
        result, buffer_exists = service.get_log_buffer(999, tail_lines=500)

        assert buffer_exists is False
        assert result == []

    def test_get_log_buffer_exists_but_empty(self):
        """Test that get_log_buffer distinguishes between 'buffer exists but empty' vs 'buffer doesn't exist'"""
        from app.services.backup_service import BackupService

        service = BackupService()

        # Create an empty buffer (job started but no logs yet)
        job_id = 789
        service.log_buffers[job_id] = []

        # Request buffer
        result, buffer_exists = service.get_log_buffer(job_id, tail_lines=500)

        # Buffer exists (True) but is empty
        assert buffer_exists is True
        assert result == []
        assert len(result) == 0


@pytest.mark.unit
class TestActivityLogDownloads:
    """Test download authentication and retrieval for activity logs."""

    def test_activity_log_download_accepts_bearer_header(
        self, test_client, admin_headers, test_db
    ):
        """Activity log download should reuse standard bearer auth."""
        from app.database.models import BackupJob

        job = BackupJob(
            repository="/test/repo",
            status="failed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            logs="line 1\nline 2",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/activity/backup/{job.id}/logs/download", headers=admin_headers
        )

        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")


@pytest.mark.unit
class TestRecentActivityEndpoint:
    """Test the aggregated recent activity feed."""

    def test_recent_activity_aggregates_job_types_and_schedule_metadata(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import (
            BackupJob,
            CheckJob,
            CompactJob,
            InstalledPackage,
            PackageInstallJob,
            PruneJob,
            Repository,
            RestoreCheckJob,
            RestoreJob,
            ScheduledJob,
        )

        _set_log_save_policy(test_db, "all_jobs")
        base = datetime(2024, 1, 1, 12, 0, 0)
        repository = Repository(
            name="Activity Repo",
            path="/tmp/activity-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)

        schedule = ScheduledJob(
            name="Nightly Activity",
            cron_expression="0 2 * * *",
            repository_id=repository.id,
            enabled=True,
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        package = InstalledPackage(
            name="borgmatic",
            install_command="apt-get install -y borgmatic",
            description="Backup helper",
            status="installed",
        )
        test_db.add(package)
        test_db.commit()
        test_db.refresh(package)

        jobs = [
            BackupJob(
                repository=repository.path,
                status="completed",
                started_at=base + timedelta(minutes=5),
                completed_at=base + timedelta(minutes=6),
                scheduled_job_id=schedule.id,
            ),
            RestoreJob(
                repository=repository.path,
                archive="archive-1",
                destination="/restore",
                status="completed",
                started_at=base + timedelta(minutes=4),
                completed_at=base + timedelta(minutes=5),
            ),
            CheckJob(
                repository_id=repository.id,
                repository_path=repository.path,
                status="completed",
                started_at=base + timedelta(minutes=3),
                completed_at=base + timedelta(minutes=4),
                scheduled_check=True,
            ),
            RestoreCheckJob(
                repository_id=repository.id,
                repository_path=repository.path,
                archive_name="archive-restore-check",
                status="completed",
                started_at=base + timedelta(minutes=2, seconds=30),
                completed_at=base + timedelta(minutes=3),
                scheduled_restore_check=True,
                logs="restore check complete",
            ),
            CompactJob(
                repository_id=repository.id,
                repository_path=repository.path,
                status="completed",
                started_at=base + timedelta(minutes=2),
                completed_at=base + timedelta(minutes=3),
            ),
            PruneJob(
                repository_id=repository.id,
                repository_path=repository.path,
                status="completed",
                started_at=base + timedelta(minutes=1),
                completed_at=base + timedelta(minutes=2),
                logs="prune complete",
            ),
            PackageInstallJob(
                package_id=package.id,
                status="completed",
                started_at=base,
                completed_at=base + timedelta(minutes=1),
                stdout="installed",
            ),
        ]
        test_db.add_all(jobs)
        test_db.commit()

        response = test_client.get("/api/activity/recent", headers=admin_headers)

        assert response.status_code == 200
        activity = response.json()
        assert len(activity) == 7
        assert activity[0]["type"] == "backup"
        assert activity[0]["triggered_by"] == "schedule"
        assert activity[0]["schedule_id"] == schedule.id
        assert activity[0]["schedule_name"] == schedule.name
        assert activity[0]["repository"] == repository.name
        check_activity = next(item for item in activity if item["type"] == "check")
        assert check_activity["triggered_by"] == "schedule"
        restore_check_activity = next(
            item for item in activity if item["type"] == "restore_check"
        )
        assert restore_check_activity["triggered_by"] == "schedule"
        assert restore_check_activity["archive_name"] == "archive-restore-check"
        assert restore_check_activity["has_logs"] is True
        assert activity[-1]["type"] == "package"
        assert activity[-1]["package_name"] == package.name

    def test_recent_activity_includes_rclone_sync_and_hydrate_jobs(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import Repository, RcloneSyncJob

        base = datetime(2024, 1, 1, 12, 0, 0)
        repository = Repository(
            name="Cloud Mirror Repo",
            path="/tmp/cloud-mirror-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)
        sync_job = RcloneSyncJob(
            repository_id=repository.id,
            direction="primary_to_remote",
            operation="sync",
            status="running",
            triggered_by="initial",
            started_at=base + timedelta(minutes=1),
            log_text="syncing repository",
        )
        hydrate_job = RcloneSyncJob(
            repository_id=repository.id,
            direction="remote_to_cache",
            operation="hydrate",
            status="failed",
            triggered_by="manual",
            started_at=base,
            completed_at=base + timedelta(seconds=30),
            log_text="hydrate failed",
            error_text="remote unavailable",
        )
        test_db.add_all([sync_job, hydrate_job])
        test_db.commit()
        test_db.refresh(sync_job)
        test_db.refresh(hydrate_job)

        response = test_client.get("/api/activity/recent", headers=admin_headers)

        assert response.status_code == 200
        activity = response.json()
        sync_activity = next(item for item in activity if item["type"] == "rclone_sync")
        hydrate_activity = next(
            item for item in activity if item["type"] == "rclone_hydrate"
        )
        assert sync_activity["id"] == sync_job.id
        assert sync_activity["status"] == "running"
        assert sync_activity["triggered_by"] == "initial"
        assert sync_activity["repository"] == repository.name
        assert sync_activity["repository_path"] == repository.path
        assert sync_activity["has_logs"] is True
        assert hydrate_activity["id"] == hydrate_job.id
        assert hydrate_activity["status"] == "failed"
        assert hydrate_activity["error_message"] == "remote unavailable"
        assert hydrate_activity["has_logs"] is True

    def test_recent_activity_marks_quiet_script_executions_loggable_for_all_jobs_policy(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import Script, ScriptExecution

        _set_log_save_policy(test_db, "all_jobs")
        script = Script(
            name="Clean Docker export",
            file_path="library/clean-docker-export.sh",
            category="custom",
            timeout=300,
        )
        test_db.add(script)
        test_db.flush()
        execution = ScriptExecution(
            script_id=script.id,
            hook_type="source-post-backup",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            exit_code=0,
            stdout="",
            stderr="",
            triggered_by="backup_plan",
        )
        test_db.add(execution)
        test_db.commit()

        response = test_client.get(
            "/api/activity/recent?job_type=script_execution",
            headers=admin_headers,
        )

        assert response.status_code == 200
        activity = response.json()
        assert len(activity) == 1
        assert activity[0]["id"] == execution.id
        assert activity[0]["type"] == "script_execution"
        assert activity[0]["has_logs"] is True

    def test_recent_activity_hides_quiet_script_logs_when_policy_skips_success(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import Script, ScriptExecution

        _set_log_save_policy(test_db, "failed_only")
        script = Script(
            name="Clean Docker export",
            file_path="library/clean-docker-export.sh",
            category="custom",
            timeout=300,
        )
        test_db.add(script)
        test_db.flush()
        execution = ScriptExecution(
            script_id=script.id,
            hook_type="source-post-backup",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            exit_code=0,
            stdout="",
            stderr="",
            triggered_by="backup_plan",
        )
        test_db.add(execution)
        test_db.commit()

        response = test_client.get(
            "/api/activity/recent?job_type=script_execution",
            headers=admin_headers,
        )

        assert response.status_code == 200
        activity = response.json()
        assert len(activity) == 1
        assert activity[0]["id"] == execution.id
        assert activity[0]["type"] == "script_execution"
        assert activity[0]["has_logs"] is False

    def test_recent_activity_marks_file_backed_rclone_logs_available(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import Repository, RcloneSyncJob

        _set_log_save_policy(test_db, "all_jobs")
        repository = Repository(
            name="Cloud File Logs Repo",
            path="/tmp/cloud-file-logs-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)
        job = RcloneSyncJob(
            repository_id=repository.id,
            direction="primary_to_remote",
            operation="sync",
            status="completed",
            triggered_by="initial",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_path="/tmp/rclone-sync.log",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            "/api/activity/recent?job_type=rclone_sync", headers=admin_headers
        )

        assert response.status_code == 200
        activity = response.json()
        assert activity[0]["id"] == job.id
        assert activity[0]["has_logs"] is True

    def test_recent_activity_uses_check_creation_time_when_start_time_is_missing(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import CheckJob, Repository

        repository = Repository(
            name="Pending Check Repo",
            path="/tmp/pending-check-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)

        completed_job = CheckJob(
            repository_id=repository.id,
            repository_path=repository.path,
            status="completed",
            started_at=datetime(2024, 1, 1, 10, 0, 0),
            completed_at=datetime(2024, 1, 1, 10, 5, 0),
            created_at=datetime(2024, 1, 1, 9, 59, 0),
        )
        pending_job = CheckJob(
            repository_id=repository.id,
            repository_path=repository.path,
            status="pending",
            started_at=None,
            created_at=datetime(2024, 1, 1, 11, 0, 0),
            scheduled_check=True,
        )
        test_db.add_all([completed_job, pending_job])
        test_db.commit()
        test_db.refresh(pending_job)

        response = test_client.get(
            "/api/activity/recent?job_type=check&limit=1",
            headers=admin_headers,
        )

        assert response.status_code == 200
        activity = response.json()
        assert len(activity) == 1
        assert activity[0]["id"] == pending_job.id
        assert activity[0]["status"] == "pending"
        assert activity[0]["started_at"] is None
        assert activity[0]["triggered_by"] == "schedule"

    def test_recent_activity_filters_by_type_and_status(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import (
            BackupJob,
            CheckJob,
            CompactJob,
            InstalledPackage,
            PackageInstallJob,
            PruneJob,
            Repository,
            RestoreJob,
        )

        repository = Repository(
            name="Filtered Repo",
            path="/tmp/filtered-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)

        completed_job = BackupJob(
            repository=repository.path,
            status="completed",
            started_at=datetime(2024, 1, 1, 10, 0, 0),
            completed_at=datetime(2024, 1, 1, 10, 1, 0),
        )
        pending_job = BackupJob(
            repository=repository.path,
            status="pending",
            started_at=datetime(2024, 1, 1, 11, 0, 0),
        )
        restore_pending = RestoreJob(
            repository=repository.path,
            archive="archive-1",
            destination="/restore",
            status="pending",
            started_at=datetime(2024, 1, 1, 9, 0, 0),
        )
        check_pending = CheckJob(
            repository_id=repository.id,
            repository_path=repository.path,
            status="pending",
            started_at=datetime(2024, 1, 1, 9, 5, 0),
        )
        compact_pending = CompactJob(
            repository_id=repository.id,
            repository_path=repository.path,
            status="pending",
            started_at=datetime(2024, 1, 1, 9, 10, 0),
        )
        prune_pending = PruneJob(
            repository_id=repository.id,
            repository_path=repository.path,
            status="pending",
            started_at=datetime(2024, 1, 1, 9, 15, 0),
        )
        package = InstalledPackage(
            name="restic",
            install_command="apt-get install -y restic",
            status="installed",
        )
        test_db.add(package)
        test_db.commit()
        test_db.refresh(package)
        package_pending = PackageInstallJob(
            package_id=package.id,
            status="pending",
            started_at=datetime(2024, 1, 1, 9, 20, 0),
        )
        test_db.add_all(
            [
                completed_job,
                pending_job,
                restore_pending,
                check_pending,
                compact_pending,
                prune_pending,
                package_pending,
            ]
        )
        test_db.commit()

        response = test_client.get(
            "/api/activity/recent?job_type=backup&status=completed",
            headers=admin_headers,
        )

        assert response.status_code == 200
        activity = response.json()
        assert len(activity) == 1
        assert activity[0]["id"] == completed_job.id
        assert activity[0]["status"] == "completed"
        assert activity[0]["type"] == "backup"


@pytest.mark.unit
class TestRecentActivityLogPolicy:
    """Test Activity has_logs serialization against SystemSettings.log_save_policy."""

    def test_mapping_output_uses_values_for_warning_detection(self):
        from types import SimpleNamespace

        from app.services.log_policy import job_has_logs_by_policy

        job = SimpleNamespace(status="completed")

        assert (
            job_has_logs_by_policy(
                job,
                "failed_and_warnings",
                output_text={
                    "stdout": "completed successfully",
                    "stderr": "WARNING: skipped one optional file",
                },
            )
            is True
        )

    def test_quiet_successful_backup_db_logs_hidden_under_failed_only(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import BackupJob

        _set_log_save_policy(test_db, "failed_only")
        repo = _create_activity_repository(test_db, "Policy Backup Repo")
        job = BackupJob(
            repository=repo.path,
            repository_id=repo.id,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            logs="quiet successful transcript",
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get(
            "/api/activity/recent?job_type=backup", headers=admin_headers
        )

        assert response.status_code == 200
        activity = response.json()
        assert activity[0]["id"] == job.id
        assert activity[0]["has_logs"] is False

    def test_quiet_successful_file_backed_check_hidden_under_failed_and_warnings(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import CheckJob

        _set_log_save_policy(test_db, "failed_and_warnings")
        repo = _create_activity_repository(test_db, "Policy Check Repo")
        job = CheckJob(
            repository_id=repo.id,
            repository_path=repo.path,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_file_path="/tmp/check-policy.log",
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get(
            "/api/activity/recent?job_type=check", headers=admin_headers
        )

        assert response.status_code == 200
        activity = response.json()
        assert activity[0]["id"] == job.id
        assert activity[0]["has_logs"] is False

    def test_quiet_successful_file_backed_check_visible_under_all_jobs(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import CheckJob

        _set_log_save_policy(test_db, "all_jobs")
        repo = _create_activity_repository(test_db, "All Jobs Check Repo")
        job = CheckJob(
            repository_id=repo.id,
            repository_path=repo.path,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_file_path="/tmp/check-all-jobs.log",
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get(
            "/api/activity/recent?job_type=check", headers=admin_headers
        )

        assert response.status_code == 200
        activity = response.json()
        assert activity[0]["id"] == job.id
        assert activity[0]["has_logs"] is True

    @pytest.mark.parametrize(
        "policy", ["failed_only", "failed_and_warnings", "all_jobs"]
    )
    def test_failed_restore_visible_under_all_policies(
        self, test_client, admin_headers, test_db, policy
    ):
        from app.database.models import RestoreJob

        _set_log_save_policy(test_db, policy)
        repo = _create_activity_repository(test_db, f"Failed Restore {policy}")
        job = RestoreJob(
            repository=repo.path,
            archive="archive-1",
            destination="/restore",
            status="failed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            error_message="restore failed",
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get(
            "/api/activity/recent?job_type=restore", headers=admin_headers
        )

        assert response.status_code == 200
        activity = response.json()
        assert activity[0]["id"] == job.id
        assert activity[0]["has_logs"] is True

    def test_quiet_successful_script_hidden_but_warning_visible_under_failed_and_warnings(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import Script, ScriptExecution

        _set_log_save_policy(test_db, "failed_and_warnings")
        quiet_script = Script(
            name="Quiet Policy Script",
            file_path="library/quiet-policy.sh",
            category="custom",
            timeout=300,
        )
        warning_script = Script(
            name="Warning Policy Script",
            file_path="library/warning-policy.sh",
            category="custom",
            timeout=300,
        )
        test_db.add_all([quiet_script, warning_script])
        test_db.flush()
        quiet_execution = ScriptExecution(
            script_id=quiet_script.id,
            hook_type="standalone",
            status="completed",
            started_at=datetime(2024, 1, 1, 10, 0, 0),
            completed_at=datetime(2024, 1, 1, 10, 0, 1),
            exit_code=0,
            stdout="completed successfully",
            stderr="",
            triggered_by="manual",
        )
        warning_execution = ScriptExecution(
            script_id=warning_script.id,
            hook_type="standalone",
            status="completed",
            started_at=datetime(2024, 1, 1, 10, 1, 0),
            completed_at=datetime(2024, 1, 1, 10, 1, 1),
            exit_code=0,
            stdout="completed with warning",
            stderr="WARNING: disk almost full",
            triggered_by="manual",
        )
        test_db.add_all([quiet_execution, warning_execution])
        test_db.commit()

        response = test_client.get(
            "/api/activity/recent?job_type=script_execution", headers=admin_headers
        )

        assert response.status_code == 200
        activity = response.json()
        rows = {row["id"]: row for row in activity}
        assert rows[quiet_execution.id]["has_logs"] is False
        assert rows[warning_execution.id]["has_logs"] is True

    def test_warning_package_output_visible_under_failed_and_warnings(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import InstalledPackage, PackageInstallJob

        _set_log_save_policy(test_db, "failed_and_warnings")
        package = InstalledPackage(
            name="policy-package",
            install_command="apt-get install -y policy-package",
            status="installed",
        )
        test_db.add(package)
        test_db.flush()
        job = PackageInstallJob(
            package_id=package.id,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            exit_code=0,
            stdout="WARNING: package already installed",
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get(
            "/api/activity/recent?job_type=package", headers=admin_headers
        )

        assert response.status_code == 200
        activity = response.json()
        assert activity[0]["id"] == job.id
        assert activity[0]["has_logs"] is True

    def test_quiet_successful_rclone_logs_hidden_under_failed_only(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import RcloneSyncJob

        _set_log_save_policy(test_db, "failed_only")
        repo = _create_activity_repository(test_db, "Policy Rclone Repo")
        job = RcloneSyncJob(
            repository_id=repo.id,
            direction="primary_to_remote",
            operation="sync",
            status="completed",
            triggered_by="manual",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_text="sync completed quietly",
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get(
            "/api/activity/recent?job_type=rclone_sync", headers=admin_headers
        )

        assert response.status_code == 200
        activity = response.json()
        assert activity[0]["id"] == job.id
        assert activity[0]["has_logs"] is False

    def test_running_log_capable_rclone_visible_under_failed_only(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import RcloneSyncJob

        _set_log_save_policy(test_db, "failed_only")
        repo = _create_activity_repository(test_db, "Running Rclone Repo")
        job = RcloneSyncJob(
            repository_id=repo.id,
            direction="primary_to_remote",
            operation="sync",
            status="running",
            triggered_by="manual",
            started_at=datetime.now(),
            log_path="/tmp/rclone-running.log",
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get(
            "/api/activity/recent?job_type=rclone_sync", headers=admin_headers
        )

        assert response.status_code == 200
        activity = response.json()
        assert activity[0]["id"] == job.id
        assert activity[0]["has_logs"] is True

    def test_pending_log_capable_check_hidden_under_all_jobs(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import CheckJob

        _set_log_save_policy(test_db, "all_jobs")
        repo = _create_activity_repository(test_db, "Pending Policy Check Repo")
        job = CheckJob(
            repository_id=repo.id,
            repository_path=repo.path,
            status="pending",
            started_at=None,
            log_file_path="/tmp/check-pending.log",
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get(
            "/api/activity/recent?job_type=check", headers=admin_headers
        )

        assert response.status_code == 200
        activity = response.json()
        assert activity[0]["id"] == job.id
        assert activity[0]["has_logs"] is False


@pytest.mark.unit
class TestActivityLogContracts:
    """Test route-contract edge cases for activity log endpoints."""

    def test_get_job_logs_rejects_invalid_job_type(self, test_client, admin_headers):
        response = test_client.get(
            "/api/activity/invalid/123/logs",
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"] == "backend.errors.activity.invalidJobType"
        )

    def test_get_job_logs_uses_file_backed_pagination(
        self, test_client, admin_headers, test_db, tmp_path
    ):
        from app.database.models import BackupJob

        _set_log_save_policy(test_db, "all_jobs")
        log_file = tmp_path / "activity-log.txt"
        log_file.write_text("line-1\nline-2\nline-3\nline-4\n")

        job = BackupJob(
            repository="/tmp/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_file_path=str(log_file),
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/activity/backup/{job.id}/logs?offset=1&limit=2",
            headers=admin_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_lines"] == 4
        assert payload["has_more"] is True
        assert [line["content"] for line in payload["lines"]] == ["line-2", "line-3"]
        assert [line["line_number"] for line in payload["lines"]] == [2, 3]

    def test_get_job_logs_hides_successful_file_logs_when_policy_skips_success(
        self, test_client, admin_headers, test_db, tmp_path
    ):
        from app.database.models import BackupJob

        _set_log_save_policy(test_db, "failed_only")
        log_file = tmp_path / "hidden-success.log"
        log_file.write_text("successful backup log\n", encoding="utf-8")
        job = BackupJob(
            repository="/tmp/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_file_path=str(log_file),
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/activity/backup/{job.id}/logs",
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.activity.noLogsAvailableForJob"
        )

    def test_download_job_logs_hides_successful_file_logs_when_policy_skips_success(
        self, test_client, admin_headers, test_db, tmp_path
    ):
        from app.database.models import BackupJob

        _set_log_save_policy(test_db, "failed_only")
        log_file = tmp_path / "hidden-download.log"
        log_file.write_text("successful backup log\n", encoding="utf-8")
        job = BackupJob(
            repository="/tmp/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_file_path=str(log_file),
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/activity/backup/{job.id}/logs/download",
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.activity.noLogsAvailableForJob"
        )

    def test_download_job_logs_without_logs_returns_404(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import BackupJob

        job = BackupJob(
            repository="/tmp/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/activity/backup/{job.id}/logs/download",
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.activity.noLogsAvailableForJob"
        )

    def test_get_job_logs_uses_database_log_fallback(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import BackupJob

        _set_log_save_policy(test_db, "all_jobs")
        job = BackupJob(
            repository="/tmp/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            logs="db line 1\ndb line 2\ndb line 3",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/activity/backup/{job.id}/logs?offset=1&limit=1",
            headers=admin_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_lines"] == 3
        assert payload["has_more"] is True
        assert payload["lines"][0]["content"] == "db line 2"

    def test_get_script_execution_logs_uses_stdout_and_stderr(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import Script, ScriptExecution

        script = Script(
            name="Plan Prepare",
            file_path="library/plan-prepare.sh",
            category="custom",
            timeout=300,
        )
        test_db.add(script)
        test_db.flush()
        execution = ScriptExecution(
            script_id=script.id,
            hook_type="pre-backup",
            status="failed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            exit_code=2,
            stdout="stdout line",
            stderr="stderr line",
            error_message="script failed",
            triggered_by="backup_plan",
        )
        test_db.add(execution)
        test_db.commit()
        test_db.refresh(execution)

        response = test_client.get(
            f"/api/activity/script_execution/{execution.id}/logs",
            headers=admin_headers,
        )

        assert response.status_code == 200
        contents = [line["content"] for line in response.json()["lines"]]
        assert "SCRIPT: Plan Prepare" in contents
        assert "stdout line" in contents
        assert "stderr line" in contents
        assert "script failed" in contents

    def test_running_agent_script_logs_stream_from_agent_job_logs(
        self, test_client, admin_headers, test_db
    ):
        # While an agent hook runs, its terminal stdout is not captured yet;
        # the log endpoint must stream the agent's live agent_job_logs instead.
        from app.database.models import AgentJob, AgentJobLog, ScriptExecution

        agent_job = AgentJob(
            agent_machine_id=1,
            job_type="script.run",
            status="running",
            payload={},
        )
        test_db.add(agent_job)
        test_db.flush()
        streamed = [
            ("stdout", "Starting script.run: backup-cluster-mariadb"),
            ("stdout", "Dumping database: ccnet_db -> /mnt/nfs/ccnet_db.sql.gz"),
            ("stderr", "warning: table locked briefly"),
        ]
        for seq, (stream, message) in enumerate(streamed):
            test_db.add(
                AgentJobLog(
                    agent_job_id=agent_job.id,
                    sequence=seq,
                    stream=stream,
                    message=message,
                    created_at=datetime.now(),
                )
            )
        execution = ScriptExecution(
            script_id=None,
            agent_script_name="backup-cluster-mariadb",
            hook_type="pre-backup",
            status="running",
            started_at=datetime.now(),
            stdout=None,
            stderr=None,
            agent_job_id=agent_job.id,
            triggered_by="backup_plan",
        )
        test_db.add(execution)
        test_db.commit()
        test_db.refresh(execution)

        response = test_client.get(
            f"/api/activity/script_execution/{execution.id}/logs",
            headers=admin_headers,
        )

        assert response.status_code == 200
        contents = [line["content"] for line in response.json()["lines"]]
        assert "SCRIPT: backup-cluster-mariadb" in contents
        assert "STATUS: running" in contents
        assert "Dumping database: ccnet_db -> /mnt/nfs/ccnet_db.sql.gz" in contents
        assert "warning: table locked briefly" in contents

    def test_get_script_execution_logs_hides_quiet_success_under_failed_only(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import Script, ScriptExecution

        _set_log_save_policy(test_db, "failed_only")
        script = Script(
            name="Quiet Script",
            file_path="library/quiet.sh",
            category="custom",
            timeout=300,
        )
        test_db.add(script)
        test_db.flush()
        execution = ScriptExecution(
            script_id=script.id,
            hook_type="pre-backup",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            exit_code=0,
            stdout="",
            stderr="",
            triggered_by="backup_plan",
        )
        test_db.add(execution)
        test_db.commit()
        test_db.refresh(execution)

        response = test_client.get(
            f"/api/activity/script_execution/{execution.id}/logs",
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.activity.noLogsAvailableForJob"
        )

    def test_get_package_job_logs_allows_warning_output_under_warning_policy(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import InstalledPackage, PackageInstallJob

        _set_log_save_policy(test_db, "failed_and_warnings")
        package = InstalledPackage(
            name="restic",
            install_command="apt-get install -y restic",
            status="installed",
        )
        test_db.add(package)
        test_db.flush()
        job = PackageInstallJob(
            package_id=package.id,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            exit_code=0,
            stdout="WARNING: package already installed",
            stderr="",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/activity/package/{job.id}/logs",
            headers=admin_headers,
        )

        assert response.status_code == 200
        contents = [line["content"] for line in response.json()["lines"]]
        assert "WARNING: package already installed" in contents

    def test_download_package_job_logs_hides_quiet_success_under_warning_policy(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import InstalledPackage, PackageInstallJob

        _set_log_save_policy(test_db, "failed_and_warnings")
        package = InstalledPackage(
            name="borgmatic",
            install_command="apt-get install -y borgmatic",
            status="installed",
        )
        test_db.add(package)
        test_db.flush()
        job = PackageInstallJob(
            package_id=package.id,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            exit_code=0,
            stdout="installed cleanly",
            stderr="",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/activity/package/{job.id}/logs/download",
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.activity.noLogsAvailableForJob"
        )

    def test_get_restore_check_job_logs_uses_activity_log_contract(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import Repository, RestoreCheckJob

        _set_log_save_policy(test_db, "all_jobs")
        repository = Repository(
            name="Restore Check Repo",
            path="/tmp/restore-check-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)

        job = RestoreCheckJob(
            repository_id=repository.id,
            repository_path=repository.path,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            logs="restore check line 1\nrestore check line 2",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/activity/restore_check/{job.id}/logs?offset=1&limit=1",
            headers=admin_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_lines"] == 2
        assert payload["has_more"] is False
        assert payload["lines"][0]["content"] == "restore check line 2"

    def test_get_rclone_sync_job_logs_uses_log_text_and_error_text(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import Repository, RcloneSyncJob

        repository = Repository(
            name="Cloud Logs Repo",
            path="/tmp/cloud-logs-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)
        job = RcloneSyncJob(
            repository_id=repository.id,
            direction="primary_to_remote",
            operation="sync",
            status="failed",
            triggered_by="initial",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_text="sync line 1\nsync line 2",
            error_text="remote unavailable",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/activity/rclone_sync/{job.id}/logs?offset=1&limit=1",
            headers=admin_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_lines"] == 3
        assert payload["has_more"] is True
        assert payload["lines"][0]["content"] == "sync line 2"

    def test_get_rclone_job_logs_hides_quiet_success_under_failed_only(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import Repository, RcloneSyncJob

        _set_log_save_policy(test_db, "failed_only")
        repository = Repository(
            name="Cloud Hidden Logs Repo",
            path="/tmp/cloud-hidden-logs-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)
        job = RcloneSyncJob(
            repository_id=repository.id,
            direction="primary_to_remote",
            operation="sync",
            status="completed",
            triggered_by="initial",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_text="sync completed quietly",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/activity/rclone_sync/{job.id}/logs",
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.activity.noLogsAvailableForJob"
        )

    def test_download_rclone_hydrate_job_logs_uses_database_text(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import Repository, RcloneSyncJob

        _set_log_save_policy(test_db, "all_jobs")
        repository = Repository(
            name="Cloud Hydrate Logs Repo",
            path="/tmp/cloud-hydrate-logs-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)
        job = RcloneSyncJob(
            repository_id=repository.id,
            direction="remote_to_cache",
            operation="hydrate",
            status="completed",
            triggered_by="manual",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_text="hydrated repository",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/activity/rclone_hydrate/{job.id}/logs/download",
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")
        assert response.content.decode() == "hydrated repository"

    def test_get_agent_backup_logs_hides_success_under_failed_only(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import AgentJob, AgentJobLog, BackupJob

        _set_log_save_policy(test_db, "failed_only")
        backup_job = BackupJob(
            repository="/tmp/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            execution_mode="agent",
        )
        test_db.add(backup_job)
        test_db.flush()
        agent_job = AgentJob(
            agent_machine_id=1,
            backup_job_id=backup_job.id,
            job_type="backup",
            status="completed",
            payload={},
        )
        test_db.add(agent_job)
        test_db.flush()
        test_db.add(
            AgentJobLog(
                agent_job_id=agent_job.id,
                sequence=1,
                stream="stdout",
                message="agent backup completed",
                created_at=datetime.now(),
            )
        )
        test_db.commit()
        test_db.refresh(backup_job)

        response = test_client.get(
            f"/api/activity/backup/{backup_job.id}/logs",
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.activity.noLogsAvailableForJob"
        )

    def test_delete_rclone_sync_job_removes_log_path(
        self, test_client, admin_headers, test_db, tmp_path
    ):
        from app.database.models import Repository, RcloneSyncJob

        repository = Repository(
            name="Cloud Delete Logs Repo",
            path="/tmp/cloud-delete-logs-repo",
            encryption="none",
            repository_type="local",
        )
        log_path = tmp_path / "rclone-sync.log"
        log_path.write_text("sync log", encoding="utf-8")
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)
        job = RcloneSyncJob(
            repository_id=repository.id,
            direction="primary_to_remote",
            operation="sync",
            status="completed",
            triggered_by="initial",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_path=str(log_path),
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.delete(
            f"/api/activity/rclone_sync/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        assert not log_path.exists()
        assert (
            test_db.query(RcloneSyncJob).filter(RcloneSyncJob.id == job.id).first()
            is None
        )

    def test_download_job_logs_uses_database_logs_when_no_file(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import BackupJob

        job = BackupJob(
            repository="/tmp/repo",
            status="failed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            logs="download me",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/activity/backup/{job.id}/logs/download",
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")

    def test_activity_log_download_accepts_proxy_auth(
        self, test_client, test_db, monkeypatch
    ):
        """Activity log download should work in proxy-auth mode without a token query param."""
        from app import config
        from app.database.models import BackupJob

        monkeypatch.setattr(config.settings, "disable_authentication", True)

        job = BackupJob(
            repository="/test/repo",
            status="failed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            logs="proxy log output",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/activity/backup/{job.id}/logs/download",
            headers={"X-Forwarded-User": "proxyuser"},
        )

        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")


@pytest.mark.unit
class TestDeleteJobEndpoint:
    """Test DELETE /api/activity/{job_type}/{job_id} endpoint"""

    def test_delete_backup_job_success_admin(self, test_client, admin_headers, test_db):
        """Test admin can successfully delete a completed backup job"""
        from app.database.models import BackupJob
        from datetime import datetime

        # Create a completed backup job
        job = BackupJob(
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/backup/{job_id}", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == job_id
        assert data["job_type"] == "backup"
        assert data["message"] == "backend.success.activity.jobDeleted"

        # Verify job is deleted from database
        deleted_job = test_db.query(BackupJob).filter(BackupJob.id == job_id).first()
        assert deleted_job is None

    def test_delete_job_non_admin_forbidden(self, test_client, auth_headers, test_db):
        """Test non-admin user cannot delete jobs"""
        from app.database.models import BackupJob
        from datetime import datetime

        # Create a completed backup job
        job = BackupJob(
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Try to delete as non-admin
        response = test_client.delete(
            f"/api/activity/backup/{job.id}", headers=auth_headers
        )

        assert response.status_code == 403
        data = response.json()
        assert data["detail"]["key"] == "backend.errors.activity.adminOnlyDelete"

        # Verify job is NOT deleted
        job_still_exists = (
            test_db.query(BackupJob).filter(BackupJob.id == job.id).first()
        )
        assert job_still_exists is not None

    def test_delete_running_job_fails(self, test_client, admin_headers, test_db):
        """Test cannot delete running job"""
        from app.database.models import BackupJob
        from datetime import datetime

        # Create a running backup job
        job = BackupJob(
            repository="/test/repo", status="running", started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Try to delete running job
        response = test_client.delete(
            f"/api/activity/backup/{job.id}", headers=admin_headers
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["key"] == "backend.errors.activity.cannotDeleteRunningJob"

        # Verify job is NOT deleted
        job_still_exists = (
            test_db.query(BackupJob).filter(BackupJob.id == job.id).first()
        )
        assert job_still_exists is not None

    def test_delete_pending_job_succeeds(self, test_client, admin_headers, test_db):
        """Test can delete pending job (useful for cleaning up stuck jobs)"""
        from app.database.models import BackupJob
        from datetime import datetime

        # Create a pending backup job
        job = BackupJob(
            repository="/test/repo", status="pending", started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Delete pending job (should succeed now)
        response = test_client.delete(
            f"/api/activity/backup/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "backend.success.activity.jobDeleted"

        # Verify job IS deleted
        job_deleted = test_db.query(BackupJob).filter(BackupJob.id == job.id).first()
        assert job_deleted is None

    def test_delete_failed_job_success(self, test_client, admin_headers, test_db):
        """Test admin can delete failed job"""
        from app.database.models import BackupJob
        from datetime import datetime

        # Create a failed backup job
        job = BackupJob(
            repository="/test/repo",
            status="failed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            error_message="Backup failed",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/backup/{job_id}", headers=admin_headers
        )

        assert response.status_code == 200

        # Verify job is deleted
        deleted_job = test_db.query(BackupJob).filter(BackupJob.id == job_id).first()
        assert deleted_job is None

    def test_delete_nonexistent_job_fails(self, test_client, admin_headers):
        """Test deleting non-existent job returns 404"""
        response = test_client.delete(
            "/api/activity/backup/99999", headers=admin_headers
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["key"] == "backend.errors.activity.jobNotFound"

    def test_delete_invalid_job_type(self, test_client, admin_headers):
        """Test deleting with invalid job type returns 400"""
        response = test_client.delete(
            "/api/activity/invalid_type/123", headers=admin_headers
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["key"] == "backend.errors.activity.invalidJobType"

    def test_delete_restore_job_success(self, test_client, admin_headers, test_db):
        """Test admin can delete completed restore job"""
        from app.database.models import RestoreJob
        from datetime import datetime

        # Create a completed restore job
        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/restore/path",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/restore/{job_id}", headers=admin_headers
        )

        assert response.status_code == 200

        # Verify job is deleted
        deleted_job = test_db.query(RestoreJob).filter(RestoreJob.id == job_id).first()
        assert deleted_job is None

    def test_delete_check_job_success(self, test_client, admin_headers, test_db):
        """Test admin can delete completed check job"""
        from app.database.models import CheckJob
        from datetime import datetime

        # Create a completed check job
        job = CheckJob(
            repository_id=1,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/check/{job_id}", headers=admin_headers
        )

        assert response.status_code == 200

        # Verify job is deleted
        deleted_job = test_db.query(CheckJob).filter(CheckJob.id == job_id).first()
        assert deleted_job is None

    def test_delete_compact_job_success(self, test_client, admin_headers, test_db):
        """Test admin can delete completed compact job"""
        from app.database.models import CompactJob
        from datetime import datetime

        # Create a completed compact job
        job = CompactJob(
            repository_id=1,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/compact/{job_id}", headers=admin_headers
        )

        assert response.status_code == 200

        # Verify job is deleted
        deleted_job = test_db.query(CompactJob).filter(CompactJob.id == job_id).first()
        assert deleted_job is None

    def test_delete_prune_job_success(self, test_client, admin_headers, test_db):
        """Test admin can delete completed prune job"""
        from app.database.models import PruneJob
        from datetime import datetime

        # Create a completed prune job
        job = PruneJob(
            repository_id=1,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/prune/{job_id}", headers=admin_headers
        )

        assert response.status_code == 200

        # Verify job is deleted
        deleted_job = test_db.query(PruneJob).filter(PruneJob.id == job_id).first()
        assert deleted_job is None

    def test_delete_job_with_log_file(
        self, test_client, admin_headers, test_db, tmp_path
    ):
        """Test deleting job also deletes log file"""
        from app.database.models import BackupJob
        from datetime import datetime

        # Create a temporary log file
        log_file = tmp_path / "test_log.txt"
        log_file.write_text("Test log content")
        assert log_file.exists()

        # Create a completed backup job with log file
        job = BackupJob(
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_file_path=str(log_file),
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/backup/{job_id}", headers=admin_headers
        )

        assert response.status_code == 200

        # Verify job is deleted
        deleted_job = test_db.query(BackupJob).filter(BackupJob.id == job_id).first()
        assert deleted_job is None

        # Verify log file is deleted
        assert not log_file.exists()

    def test_delete_cancelled_job_success(self, test_client, admin_headers, test_db):
        """Test admin can delete cancelled job"""
        from app.database.models import BackupJob
        from datetime import datetime

        # Create a cancelled backup job
        job = BackupJob(
            repository="/test/repo",
            status="cancelled",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/backup/{job_id}", headers=admin_headers
        )

        assert response.status_code == 200

        # Verify job is deleted
        deleted_job = test_db.query(BackupJob).filter(BackupJob.id == job_id).first()
        assert deleted_job is None

    def test_delete_job_unauthenticated(self, test_client, test_db):
        """Test deleting job without authentication fails"""
        from app.database.models import BackupJob
        from datetime import datetime

        # Create a completed backup job
        job = BackupJob(
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Try to delete without auth
        response = test_client.delete(f"/api/activity/backup/{job.id}")

        assert response.status_code == 401  # No authentication provided

        # Verify job is NOT deleted
        job_still_exists = (
            test_db.query(BackupJob).filter(BackupJob.id == job.id).first()
        )
        assert job_still_exists is not None


class TestGetJobLogsPlaceholderOffset:
    """Test that placeholder lines are only returned when offset=0 for running backup jobs."""

    def _make_running_backup_job(self):
        """Create a minimal fake job object with status='running'."""

        class FakeJob:
            id = 42
            status = "running"
            log_file_path = None
            logs = None

        return FakeJob()

    def test_a_no_buffer_offset_0_returns_placeholder(
        self, test_client, auth_headers, test_db
    ):
        """Test A: buffer_exists=False, offset=0 -> returns 5-line placeholder."""
        from unittest.mock import patch
        from app.database.models import BackupJob
        from datetime import datetime

        job = BackupJob(
            repository="/test/repo", status="running", started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        with patch(
            "app.api.activity.backup_service.get_log_buffer", return_value=([], False)
        ):
            response = test_client.get(
                f"/api/activity/backup/{job.id}/logs?offset=0", headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total_lines"] == 5
        assert len(data["lines"]) == 5

    def test_b_no_buffer_offset_5_returns_empty(
        self, test_client, auth_headers, test_db
    ):
        """Test B: buffer_exists=False, offset=5 -> returns empty response."""
        from unittest.mock import patch
        from app.database.models import BackupJob
        from datetime import datetime

        job = BackupJob(
            repository="/test/repo", status="running", started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        with patch(
            "app.api.activity.backup_service.get_log_buffer", return_value=([], False)
        ):
            response = test_client.get(
                f"/api/activity/backup/{job.id}/logs?offset=5", headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["lines"] == []
        assert data["total_lines"] == 0
        assert data["has_more"] is False

    def test_c_empty_buffer_offset_0_returns_placeholder(
        self, test_client, auth_headers, test_db
    ):
        """Test C: buffer_exists=True but empty, offset=0 -> returns 5-line placeholder."""
        from unittest.mock import patch
        from app.database.models import BackupJob
        from datetime import datetime

        job = BackupJob(
            repository="/test/repo", status="running", started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        with patch(
            "app.api.activity.backup_service.get_log_buffer", return_value=([], True)
        ):
            response = test_client.get(
                f"/api/activity/backup/{job.id}/logs?offset=0", headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total_lines"] == 5
        assert len(data["lines"]) == 5

    def test_d_empty_buffer_offset_5_returns_empty(
        self, test_client, auth_headers, test_db
    ):
        """Test D: buffer_exists=True but empty, offset=5 -> returns empty response."""
        from unittest.mock import patch
        from app.database.models import BackupJob
        from datetime import datetime

        job = BackupJob(
            repository="/test/repo", status="running", started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        with patch(
            "app.api.activity.backup_service.get_log_buffer", return_value=([], True)
        ):
            response = test_client.get(
                f"/api/activity/backup/{job.id}/logs?offset=5", headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["lines"] == []
        assert data["total_lines"] == 0
        assert data["has_more"] is False

    def test_e_buffer_with_lines_offset_0_returns_lines(
        self, test_client, auth_headers, test_db
    ):
        """Test E: buffer_exists=True, buffer has lines, offset=0 -> returns those lines."""
        from unittest.mock import patch
        from app.database.models import BackupJob
        from datetime import datetime

        job = BackupJob(
            repository="/test/repo", status="running", started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        real_lines = [
            "Creating archive...",
            "Files: 100 new, 0 changed",
            "Duration: 2.34 seconds",
        ]
        with patch(
            "app.api.activity.backup_service.get_log_buffer",
            return_value=(real_lines, True),
        ):
            response = test_client.get(
                f"/api/activity/backup/{job.id}/logs?offset=0", headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total_lines"] == 3
        assert len(data["lines"]) == 3
        assert data["lines"][0]["content"] == "Creating archive..."
        assert data["lines"][1]["content"] == "Files: 100 new, 0 changed"
        assert data["lines"][2]["content"] == "Duration: 2.34 seconds"
