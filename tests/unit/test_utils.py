import json
from datetime import datetime, timezone

from unittest.mock import patch, mock_open, MagicMock
from app.utils.datetime_utils import serialize_datetime
from app.utils.process_utils import (
    is_process_alive,
    break_repository_lock,
    cleanup_orphaned_jobs,
    cleanup_orphaned_mounts,
    reconcile_stale_backup_maintenance,
)
from app.database.models import (
    BackupPlan,
    BackupPlanRun,
    BackupPlanRunRepository,
    Operation,
    Repository,
)

from app.services.operations.details import backup_details
from tests.utils.operations import seed_job_operation

# ==========================================
# Datetime Utils Tests
# ==========================================


class TestDatetimeUtils:
    def test_serialize_none(self):
        """Test serializing None returns None"""
        assert serialize_datetime(None) is None

    def test_serialize_naive_datetime(self):
        """Test naive datetime (DB format) is treated as UTC"""
        dt = datetime(2025, 1, 1, 12, 0, 0)  # Naive
        serialized = serialize_datetime(dt)
        assert serialized == "2025-01-01T12:00:00+00:00"

    def test_serialize_aware_datetime(self):
        """Test aware datetime is converted to UTC"""
        # Let's use a manual offset for clarity +01:00
        from datetime import timedelta

        tz_plus_1 = timezone(timedelta(hours=1))

        dt = datetime(2025, 1, 1, 13, 0, 0, tzinfo=tz_plus_1)
        serialized = serialize_datetime(dt)
        # 13:00 +01:00 is 12:00 UTC
        assert serialized == "2025-01-01T12:00:00+00:00"


# ==========================================
# Process Utils Tests
# ==========================================


class TestProcessUtils:
    def test_is_process_alive_no_pid(self):
        """Test returns False for invalid inputs"""
        assert is_process_alive(None, 123) is False
        assert is_process_alive(123, None) is False

    @patch("builtins.open", new_callable=mock_open)
    def test_is_process_alive_success(self, mock_file):
        """Test active process detection"""
        # Format of /proc/pid/stat: pid (name) state ppid ... starttime (22nd field, index 21)
        # util.py: fields = stat_data.split(')')[1].split()
        #          current_start_time = int(fields[19])
        # fields[0] is state (field 3). fields[19] is field 22.
        # We need 19 fields before start_time (indices 0-18)

        # Create mock content with enough fields
        # 19 fields of padding to make starttime index 19
        padding = " ".join(["0"] * 19)
        # Start time is 1000
        content = f"123 (test) {padding} 1000 0 0"

        mock_file.return_value.read.return_value = content

        # Should return True if start times match
        assert is_process_alive(123, 1000) is True

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_is_process_alive_not_found(self, mock_file):
        """Test process not found"""
        assert is_process_alive(123, 1000) is False

    @patch("builtins.open", new_callable=mock_open)
    def test_is_process_alive_pid_reused(self, mock_file):
        """Test PID reuse detection"""
        # Mock content with DIFFERENT start time (2000 vs 1000)
        padding = " ".join(["0"] * 19)
        content = f"123 (test) {padding} 2000 0 0"
        mock_file.return_value.read.return_value = content

        assert is_process_alive(123, 1000) is False

    @patch("subprocess.run")
    def test_break_repository_lock_local_success(self, mock_run):
        """Test breaking lock for local repo"""
        repo = Repository(
            id=1, path="/tmp/repo", repository_type="local", passphrase="secret"
        )

        mock_run.return_value.returncode = 0

        assert break_repository_lock(repo) is True

        # Verify command
        args = mock_run.call_args[0][0]
        assert args == ["borg", "break-lock", "/tmp/repo"]

        # Verify env
        env = mock_run.call_args[1]["env"]
        assert env["BORG_PASSPHRASE"] == "secret"

    @patch("subprocess.run")
    def test_break_repository_lock_ssh_success(self, mock_run):
        """Test breaking lock for SSH repo"""
        from app.utils import borg_env

        repo = Repository(
            id=1,
            path="ssh://user@host/repo",
            connection_id=1,  # SSH repo has connection_id
            remote_path="/usr/bin/borg",
        )

        mock_run.return_value.returncode = 0

        # The repository carries no session here, so its connection is looked
        # up by id; this test is about the command shape, not that lookup.
        with patch.object(
            borg_env,
            "host_key_ssh_opts_for_connection_id",
            return_value=["-o", "StrictHostKeyChecking=accept-new"],
        ):
            assert break_repository_lock(repo) is True

        # Verify command includes remote-path
        args = mock_run.call_args[0][0]
        assert "--remote-path" in args
        assert "/usr/bin/borg" in args

        # Verify SSH setup
        env = mock_run.call_args[1]["env"]
        assert "BORG_RSH" in env
        borg_rsh = env["BORG_RSH"]
        assert borg_rsh.startswith("ssh ")
        for option in [
            "-o BatchMode=yes",
            "-o PreferredAuthentications=publickey",
            "-o PasswordAuthentication=no",
            "-o NumberOfPasswordPrompts=0",
            "-o StrictHostKeyChecking=accept-new",
            "-o LogLevel=ERROR",
        ]:
            assert option in borg_rsh
        assert "-o StrictHostKeyChecking=no" not in borg_rsh
        assert "-o UserKnownHostsFile=/dev/null" not in borg_rsh

    @patch("subprocess.run")
    def test_break_repository_lock_fails_rather_than_skipping_verification(
        self, mock_run
    ):
        """A connection that cannot be loaded must not mean "connect anyway".

        The repository is attached to a connection, so a pinned host key may
        well exist. Running borg against that host without checking it is worse
        than failing the lock recovery and saying so.
        """
        from app.utils import borg_env

        repo = Repository(
            id=1,
            path="ssh://user@host/repo",
            connection_id=1,
            remote_path="/usr/bin/borg",
        )

        with patch.object(
            borg_env,
            "host_key_ssh_opts_for_connection_id",
            side_effect=RuntimeError("database is gone"),
        ):
            assert break_repository_lock(repo) is False

        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_break_repository_lock_ssh_verifies_a_pinned_host_key(self, mock_run):
        """A repository whose connection has a pinned key verifies against it."""
        from app.database.models import SSHConnection
        from app.utils import process_utils

        connection = SSHConnection(
            id=1,
            host="host",
            username="user",
            port=22,
            known_host_key="host ssh-ed25519 AAAA",
        )
        repo = Repository(
            id=1,
            path="ssh://user@host/repo",
            connection_id=1,
            remote_path="/usr/bin/borg",
        )

        mock_run.return_value.returncode = 0

        with (
            patch.object(process_utils, "object_session", return_value=MagicMock()),
            patch.object(
                process_utils,
                "resolve_repository_ssh_connection",
                return_value=connection,
            ),
            patch.object(process_utils, "resolve_repo_ssh_key_file", return_value=None),
        ):
            assert break_repository_lock(repo) is True

        borg_rsh = mock_run.call_args[1]["env"]["BORG_RSH"]
        assert "-o StrictHostKeyChecking=yes" in borg_rsh
        assert "-o StrictHostKeyChecking=accept-new" not in borg_rsh
        assert "-o UserKnownHostsFile=/dev/null" not in borg_rsh

    def test_cleanup_orphaned_jobs_normalizes_stale_backup_maintenance_without_child_job(
        self,
    ):
        """Test stale backup maintenance state is repaired even without a running child job"""
        mock_db = MagicMock()

        stale_backup_job = MagicMock()
        stale_backup_job.id = 10
        stale_backup_job.repository = "repo-stale"
        stale_backup_job.status = "running"
        stale_backup_job.maintenance_status = "running_prune"
        stale_backup_job.completed_at = None
        stale_backup_job.error_message = None

        query_results = [
            [],  # active backup plan runs
        ]

        def build_query(result):
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.all.return_value = result
            mock_query.first.return_value = None
            return mock_query

        mock_db.query.side_effect = [build_query(result) for result in query_results]

        with patch(
            "app.utils.process_utils.backup_jobs_in_maintenance",
            return_value=[stale_backup_job],
        ):
            cleanup_orphaned_jobs(mock_db)

        assert stale_backup_job.status == "failed"
        assert stale_backup_job.maintenance_status == "prune_failed"
        assert stale_backup_job.completed_at is not None
        assert (
            json.loads(stale_backup_job.error_message)["key"]
            == "backend.errors.service.containerRestartedDuringOperation"
        )
        mock_db.commit.assert_called_once()

    def test_cleanup_orphaned_jobs_normalizes_completed_backup_running_check_without_child_job(
        self, db_session
    ):
        repo = Repository(
            name="Check Repo",
            path="/repos/check",
            encryption="none",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.flush()

        backup_job = seed_job_operation(
            db_session,
            "backup",
            repository=repo.path,
            repository_id=repo.id,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            maintenance_status="running_check",
        )
        db_session.commit()

        cleanup_orphaned_jobs(db_session)

        db_session.refresh(backup_job)
        assert backup_job.status == "completed"
        assert (
            backup_details(db_session, backup_job).maintenance_status == "check_failed"
        )

    def test_reconcile_stale_backup_maintenance_reaps_stuck_prune_without_child(
        self, db_session
    ):
        from datetime import timedelta

        repo = Repository(
            name="Stuck Prune Repo",
            path="/repos/stuck-prune",
            encryption="none",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.flush()
        old = datetime.utcnow() - timedelta(minutes=10)
        backup_job = seed_job_operation(
            db_session,
            "backup",
            repository=repo.path,
            repository_id=repo.id,
            status="completed",
            started_at=old,
            completed_at=old,
            maintenance_status="running_prune",
        )
        db_session.commit()

        reaped = reconcile_stale_backup_maintenance(db_session)

        assert reaped == 1
        db_session.refresh(backup_job)
        assert (
            backup_details(db_session, backup_job).maintenance_status == "prune_failed"
        )
        assert backup_job.status == "completed"  # backup itself stays completed

    def test_reconcile_stale_backup_maintenance_preserves_live_prune(self, db_session):
        from datetime import timedelta

        repo = Repository(
            name="Live Prune Repo",
            path="/repos/live-prune",
            encryption="none",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.flush()
        old = datetime.utcnow() - timedelta(minutes=10)
        backup_job = seed_job_operation(
            db_session,
            "backup",
            repository=repo.path,
            repository_id=repo.id,
            status="completed",
            started_at=old,
            completed_at=old,
            maintenance_status="running_prune",
        )
        # a genuinely running prune child for the same repo -> must be preserved
        db_session.add(
            seed_job_operation(
                db_session,
                "prune",
                repository_id=repo.id,
                repository_path=repo.path,
                status="running",
            )
        )
        db_session.commit()

        reaped = reconcile_stale_backup_maintenance(db_session)

        assert reaped == 0
        db_session.refresh(backup_job)
        assert (
            backup_details(db_session, backup_job).maintenance_status == "running_prune"
        )

    def test_reconcile_stale_backup_maintenance_preserves_live_inline_operation(
        self, db_session
    ):
        """The post-backup prune, compact and check run inline through
        `start_inline_maintenance`, which writes the step
        as a `running` child operation, which the reconciler must see so a
        long-running inline prune is not reaped as stuck mid-run."""
        from datetime import timedelta

        repo = Repository(
            name="Live Inline Prune Repo",
            path="/repos/live-inline-prune",
            encryption="none",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.flush()
        old = datetime.utcnow() - timedelta(minutes=10)
        backup_job = seed_job_operation(
            db_session,
            "backup",
            repository=repo.path,
            repository_id=repo.id,
            status="completed",
            started_at=old,
            completed_at=old,
            maintenance_status="running_prune",
        )
        db_session.add(
            Operation(
                repository_id=repo.id,
                kind="prune",
                category="maintenance",
                status="running",
                trigger="manual",
                priority=0,
                run_id="run-1",
            )
        )
        db_session.commit()

        reaped = reconcile_stale_backup_maintenance(db_session)

        assert reaped == 0
        db_session.refresh(backup_job)
        assert (
            backup_details(db_session, backup_job).maintenance_status == "running_prune"
        )

    def test_reconcile_stale_backup_maintenance_skips_fresh(self, db_session):
        repo = Repository(
            name="Fresh Prune Repo",
            path="/repos/fresh-prune",
            encryption="none",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.flush()
        now = datetime.utcnow()
        backup_job = seed_job_operation(
            db_session,
            "backup",
            repository=repo.path,
            repository_id=repo.id,
            status="completed",
            started_at=now,
            completed_at=now,  # just finished -> under the age threshold
            maintenance_status="running_prune",
        )
        db_session.commit()

        reaped = reconcile_stale_backup_maintenance(db_session)

        assert reaped == 0
        db_session.refresh(backup_job)
        assert (
            backup_details(db_session, backup_job).maintenance_status == "running_prune"
        )

    def test_reap_once_runs_both_reaper_passes(self):
        # The background loop must run the agent-job reaper, the maintenance
        # status reconciler AND the orphaned-*_job reaper each tick.
        with (
            patch("app.services.agent_job_reaper.SessionLocal"),
            patch(
                "app.services.agent_job_reaper.reap_stale_agent_jobs",
                return_value=2,
            ) as m_agent,
            patch(
                "app.utils.process_utils.reconcile_stale_backup_maintenance",
                return_value=3,
            ) as m_maint,
        ):
            from app.services.agent_job_reaper import _reap_once

            total = _reap_once()

        assert total == 5
        m_agent.assert_called_once()
        m_maint.assert_called_once()

    def test_cleanup_orphaned_jobs_finishes_interrupted_backup_plan_run(
        self, db_session
    ):
        """Interrupted plan backups should not remain active after startup cleanup"""
        repo = Repository(
            name="Plan Repo",
            path="/repos/plan",
            encryption="none",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.flush()

        plan = BackupPlan(
            name="Plan",
            source_directories=json.dumps(["/src"]),
            repositories=[],
        )
        db_session.add(plan)
        db_session.flush()

        run = BackupPlanRun(
            backup_plan_id=plan.id,
            trigger="manual",
            status="running",
            started_at=datetime.utcnow(),
        )
        db_session.add(run)
        db_session.flush()

        backup_job = seed_job_operation(
            db_session,
            "backup",
            repository=repo.path,
            repository_id=repo.id,
            backup_plan_id=plan.id,
            backup_plan_run_id=run.id,
            status="running",
            started_at=datetime.utcnow(),
            progress=42,
        )
        db_session.flush()

        child = BackupPlanRunRepository(
            backup_plan_run_id=run.id,
            repository_id=repo.id,
            backup_operation_id=backup_job.id,
            status="running",
            started_at=datetime.utcnow(),
        )
        db_session.add(child)
        db_session.commit()

        cleanup_orphaned_jobs(db_session)

        db_session.refresh(child)
        db_session.refresh(run)

        # The backup operation itself is failed by the runner's recovery (spec
        # 7.6); this sweep normalises the plan run and its children.
        assert child.status == "failed"
        assert child.completed_at is not None
        assert run.status == "failed"
        assert run.completed_at is not None

    @patch("app.utils.process_utils.settings")
    @patch("app.utils.process_utils.subprocess.run")
    def test_cleanup_orphaned_mounts_handles_managed_mount_dir_names(
        self, mock_run, mock_settings, tmp_path
    ):
        managed_mount_base = tmp_path / "mounts"
        managed_mount_base.mkdir()
        orphaned_dir = managed_mount_base / "manual-backup-2026-01-15T16_24_12"
        orphaned_dir.mkdir()

        mock_settings.data_dir = str(tmp_path)
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout=f"borgfs on {orphaned_dir} type fuse.borgfs (rw,nosuid,nodev,relatime,user_id=0,group_id=0)",
            ),
            MagicMock(returncode=0, stderr=""),
        ]

        cleanup_orphaned_mounts()

        assert not orphaned_dir.exists()
        assert mock_run.call_args_list[1][0][0] == [
            "fusermount",
            "-uz",
            str(orphaned_dir),
        ]
