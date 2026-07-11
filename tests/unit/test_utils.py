import json
from datetime import datetime, timezone

import pytest
from unittest.mock import patch, mock_open, MagicMock
from app.utils.datetime_utils import serialize_datetime
from app.utils.process_utils import (
    is_process_alive,
    break_repository_lock,
    cleanup_orphaned_jobs,
    cleanup_orphaned_mounts,
    reconcile_stale_backup_maintenance,
    reconcile_orphaned_maintenance_jobs,
)
from app.database.models import (
    AgentJob,
    AgentMachine,
    BackupJob,
    BackupPlan,
    BackupPlanRun,
    BackupPlanRunRepository,
    CheckJob,
    CompactJob,
    DeleteArchiveJob,
    PruneJob,
    Repository,
)

# (maintenance_kind, model, extra required kwargs, agent-payload job_kind) for the
# four maintenance job types the reaper reconciles.
_MAINTENANCE_CASES = [
    ("prune", PruneJob, {}, "repository.prune"),
    ("compact", CompactJob, {}, "repository.compact"),
    ("check", CheckJob, {}, "repository.check"),
    (
        "delete_archive",
        DeleteArchiveJob,
        {"archive_name": "arch-1"},
        "repository.delete_archive",
    ),
]
from app.core.security import get_password_hash

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
        repo = Repository(
            id=1,
            path="ssh://user@host/repo",
            connection_id=1,  # SSH repo has connection_id
            remote_path="/usr/bin/borg",
        )

        mock_run.return_value.returncode = 0

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
            "-o StrictHostKeyChecking=no",
            "-o UserKnownHostsFile=/dev/null",
            "-o LogLevel=ERROR",
        ]:
            assert option in borg_rsh

    def test_cleanup_orphaned_jobs(self):
        """Test cleanup of orphaned jobs"""
        # Create mock session
        mock_db = MagicMock()

        # Setup mock jobs
        mock_backup_job = MagicMock(spec=BackupJob)
        mock_backup_job.id = 1
        mock_backup_job.repository = "repo1"
        mock_backup_job.maintenance_status = "running_prune"

        mock_prune_job = MagicMock(spec=PruneJob)
        mock_prune_job.id = 2
        mock_prune_job.repository_id = 10
        mock_prune_job.repository_path = "repo1"

        mock_compact_job = MagicMock(spec=CompactJob)
        mock_compact_job.id = 3
        mock_compact_job.repository_id = 11
        mock_compact_job.repository_path = "repo2"
        mock_compact_job.process_pid = 123
        mock_compact_job.process_start_time = 456

        mock_compact_backup_job = MagicMock(spec=BackupJob)
        mock_compact_backup_job.id = 4
        mock_compact_backup_job.repository = "repo2"
        mock_compact_backup_job.maintenance_status = "running_compact"

        # Setup query chain
        query_results = [
            [mock_backup_job],  # stale backup maintenance jobs
            [mock_backup_job],  # running backup jobs
            [],  # running restore jobs
            [],  # running check jobs
            [],  # running restore check jobs
            [mock_prune_job],  # running prune jobs
            [mock_compact_job],  # running compact jobs
            [],  # active backup plan runs
            [mock_backup_job],  # backup jobs stuck in running_prune
            [],  # repository lookup for orphaned compact job
            [mock_compact_backup_job],  # backup jobs stuck in running_compact
        ]

        def build_query(result):
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.all.return_value = result
            mock_query.first.return_value = None
            return mock_query

        mock_db.query.side_effect = [build_query(result) for result in query_results]

        # Execute
        with patch("app.utils.process_utils.is_process_alive", return_value=False):
            cleanup_orphaned_jobs(mock_db)

        # Verify backup job was marked failed
        assert mock_backup_job.status == "failed"
        assert (
            json.loads(mock_backup_job.error_message)["key"]
            == "backend.errors.service.containerRestartedDuringBackup"
        )
        assert mock_backup_job.completed_at is not None
        assert mock_backup_job.maintenance_status == "prune_failed"

        assert mock_prune_job.status == "failed"
        assert (
            json.loads(mock_prune_job.error_message)["key"]
            == "backend.errors.service.containerRestartedDuringOperation"
        )
        assert mock_prune_job.completed_at is not None

        assert mock_compact_job.status == "failed"
        assert (
            json.loads(mock_compact_job.error_message.split("\n")[0])["key"]
            == "backend.errors.service.containerRestartedDuringOperation"
        )
        assert mock_compact_job.completed_at is not None
        assert mock_compact_backup_job.maintenance_status == "compact_failed"

        # Verify commit was called
        mock_db.commit.assert_called_once()

    def test_cleanup_orphaned_jobs_normalizes_stale_backup_maintenance_without_child_job(
        self,
    ):
        """Test stale backup maintenance state is repaired even without a running child job"""
        mock_db = MagicMock()

        stale_backup_job = MagicMock(spec=BackupJob)
        stale_backup_job.id = 10
        stale_backup_job.repository = "repo-stale"
        stale_backup_job.status = "running"
        stale_backup_job.maintenance_status = "running_prune"
        stale_backup_job.completed_at = None
        stale_backup_job.error_message = None

        query_results = [
            [stale_backup_job],  # stale backup maintenance jobs
            [],  # running backup jobs
            [],  # running restore jobs
            [],  # running check jobs
            [],  # running restore check jobs
            [],  # running prune jobs
            [],  # running compact jobs
            [],  # active backup plan runs
        ]

        def build_query(result):
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.all.return_value = result
            mock_query.first.return_value = None
            return mock_query

        mock_db.query.side_effect = [build_query(result) for result in query_results]

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

        backup_job = BackupJob(
            repository=repo.path,
            repository_id=repo.id,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            maintenance_status="running_check",
        )
        db_session.add(backup_job)
        db_session.commit()

        cleanup_orphaned_jobs(db_session)

        db_session.refresh(backup_job)
        assert backup_job.status == "completed"
        assert backup_job.maintenance_status == "check_failed"

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
        backup_job = BackupJob(
            repository=repo.path,
            repository_id=repo.id,
            status="completed",
            started_at=old,
            completed_at=old,
            maintenance_status="running_prune",
        )
        db_session.add(backup_job)
        db_session.commit()

        reaped = reconcile_stale_backup_maintenance(db_session)

        assert reaped == 1
        db_session.refresh(backup_job)
        assert backup_job.maintenance_status == "prune_failed"
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
        backup_job = BackupJob(
            repository=repo.path,
            repository_id=repo.id,
            status="completed",
            started_at=old,
            completed_at=old,
            maintenance_status="running_prune",
        )
        # a genuinely running prune child for the same repo -> must be preserved
        db_session.add(
            PruneJob(
                repository_id=repo.id,
                repository_path=repo.path,
                status="running",
            )
        )
        db_session.add(backup_job)
        db_session.commit()

        reaped = reconcile_stale_backup_maintenance(db_session)

        assert reaped == 0
        db_session.refresh(backup_job)
        assert backup_job.maintenance_status == "running_prune"

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
        backup_job = BackupJob(
            repository=repo.path,
            repository_id=repo.id,
            status="completed",
            started_at=now,
            completed_at=now,  # just finished -> under the age threshold
            maintenance_status="running_prune",
        )
        db_session.add(backup_job)
        db_session.commit()

        reaped = reconcile_stale_backup_maintenance(db_session)

        assert reaped == 0
        db_session.refresh(backup_job)
        assert backup_job.maintenance_status == "running_prune"

    def test_reap_once_runs_all_three_reaper_passes(self):
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
            patch(
                "app.utils.process_utils.reconcile_orphaned_maintenance_jobs",
                return_value=1,
            ) as m_orphan,
        ):
            from app.services.agent_job_reaper import _reap_once

            total = _reap_once()

        assert total == 6
        m_agent.assert_called_once()
        m_maint.assert_called_once()
        m_orphan.assert_called_once()

    @pytest.mark.parametrize("kind, model, extra, job_kind", _MAINTENANCE_CASES)
    def test_reconcile_orphaned_reaps_old_pending_without_agent_job(
        self, db_session, kind, model, extra, job_kind
    ):
        from datetime import timedelta

        repo = Repository(
            name=f"Orphan {kind} Repo",
            path=f"/repos/orphan-{kind}",
            encryption="none",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.flush()
        # pending maintenance job created long ago, no agent job was ever queued
        job = model(
            repository_id=repo.id,
            repository_path=repo.path,
            status="pending",
            created_at=datetime.utcnow() - timedelta(minutes=10),
            **extra,
        )
        db_session.add(job)
        db_session.commit()

        reaped = reconcile_orphaned_maintenance_jobs(db_session)

        assert reaped == 1
        db_session.refresh(job)
        assert job.status == "failed"

    @pytest.mark.parametrize("kind, model, extra, job_kind", _MAINTENANCE_CASES)
    def test_reconcile_orphaned_preserves_pending_with_active_agent_job(
        self, db_session, kind, model, extra, job_kind
    ):
        from datetime import timedelta

        repo = Repository(
            name=f"Dispatched {kind} Repo",
            path=f"/repos/dispatched-{kind}",
            encryption="none",
            repository_type="local",
        )
        agent = AgentMachine(
            name="Agent",
            agent_id="agt_orphan_test",
            token_hash=get_password_hash("secret"),
            token_prefix="secret",
            status="online",
        )
        db_session.add_all([repo, agent])
        db_session.flush()
        job = model(
            repository_id=repo.id,
            repository_path=repo.path,
            status="pending",
            created_at=datetime.utcnow() - timedelta(minutes=10),
            **extra,
        )
        db_session.add(job)
        db_session.flush()
        # a live agent job IS queued for this maintenance job -> must be preserved
        db_session.add(
            AgentJob(
                agent_machine_id=agent.id,
                job_type="repository",
                status="queued",
                payload={
                    "job_kind": job_kind,
                    "operation": {
                        "maintenance_job": {"kind": kind, "id": job.id},
                    },
                },
            )
        )
        db_session.commit()

        reaped = reconcile_orphaned_maintenance_jobs(db_session)

        assert reaped == 0
        db_session.refresh(job)
        assert job.status == "pending"

    def test_reconcile_orphaned_preserves_row_that_turns_running_mid_reap(
        self, db_session
    ):
        from datetime import timedelta
        from unittest.mock import patch

        repo = Repository(
            name="Racing Prune Repo",
            path="/repos/racing-prune",
            encryption="none",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.flush()
        prune = PruneJob(
            repository_id=repo.id,
            repository_path=repo.path,
            status="pending",
            created_at=datetime.utcnow() - timedelta(minutes=10),
        )
        db_session.add(prune)
        db_session.commit()

        # Simulate a concurrent dispatch that flips the row to 'running' after it
        # is selected as a candidate but before the guarded UPDATE. The
        # correlation check still reports no active agent job, so only the
        # WHERE status == 'pending' guard can prevent a spurious 'failed'.
        def _flip_to_running(db, kind, job_id):
            db.query(PruneJob).filter(PruneJob.id == job_id).update(
                {PruneJob.status: "running"}, synchronize_session=False
            )
            db.commit()
            return False

        with patch(
            "app.utils.process_utils._has_active_agent_job_for",
            side_effect=_flip_to_running,
        ):
            reaped = reconcile_orphaned_maintenance_jobs(db_session)

        assert reaped == 0
        db_session.refresh(prune)
        assert prune.status == "running"

    def test_reconcile_orphaned_preserves_when_correlation_appears_after_update(
        self, db_session
    ):
        from datetime import timedelta
        from unittest.mock import patch

        repo = Repository(
            name="Late Dispatch Repo",
            path="/repos/late-dispatch",
            encryption="none",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.flush()
        prune = PruneJob(
            repository_id=repo.id,
            repository_path=repo.path,
            status="pending",
            created_at=datetime.utcnow() - timedelta(minutes=10),
        )
        db_session.add(prune)
        db_session.commit()

        # No agent job at candidate-selection time (first call -> False), but one
        # appears before the re-check after the guarded UPDATE (second call ->
        # True). The row must be rolled back to 'pending', not reaped.
        with patch(
            "app.utils.process_utils._has_active_agent_job_for",
            side_effect=[False, True],
        ):
            reaped = reconcile_orphaned_maintenance_jobs(db_session)

        assert reaped == 0
        db_session.refresh(prune)
        assert prune.status == "pending"

    def test_reconcile_orphaned_skips_fresh_pending(self, db_session):
        repo = Repository(
            name="Fresh Orphan Repo",
            path="/repos/fresh-orphan",
            encryption="none",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.flush()
        prune = PruneJob(
            repository_id=repo.id,
            repository_path=repo.path,
            status="pending",
            created_at=datetime.utcnow(),  # just created -> under age threshold
        )
        db_session.add(prune)
        db_session.commit()

        reaped = reconcile_orphaned_maintenance_jobs(db_session)

        assert reaped == 0
        db_session.refresh(prune)
        assert prune.status == "pending"

    @patch("app.utils.process_utils.is_process_alive", return_value=True)
    def test_cleanup_orphaned_jobs_preserves_running_check_with_live_child_process(
        self, mock_is_process_alive, db_session
    ):
        repo = Repository(
            name="Live Check Repo",
            path="/repos/live-check",
            encryption="none",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.flush()

        backup_job = BackupJob(
            repository=repo.path,
            repository_id=repo.id,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            maintenance_status="running_check",
        )
        check_job = CheckJob(
            repository_id=repo.id,
            repository_path=repo.path,
            status="running",
            process_pid=1234,
            process_start_time=5678,
        )
        db_session.add_all([backup_job, check_job])
        db_session.commit()

        cleanup_orphaned_jobs(db_session)

        db_session.refresh(backup_job)
        db_session.refresh(check_job)
        assert backup_job.status == "completed"
        assert backup_job.maintenance_status == "running_check"
        assert check_job.status == "running"
        assert check_job.completed_at is None
        mock_is_process_alive.assert_called_once_with(1234, 5678)

    @patch("app.utils.process_utils.break_repository_lock", return_value=True)
    @patch("app.utils.process_utils.is_process_alive", return_value=False)
    def test_cleanup_orphaned_jobs_marks_running_check_parent_when_child_process_dead(
        self, mock_is_process_alive, mock_break_repository_lock, db_session
    ):
        repo = Repository(
            name="Dead Check Repo",
            path="/repos/dead-check",
            encryption="none",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.flush()

        backup_job = BackupJob(
            repository=repo.path,
            repository_id=repo.id,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            maintenance_status="running_check",
        )
        check_job = CheckJob(
            repository_id=repo.id,
            repository_path=repo.path,
            status="running",
            process_pid=4321,
            process_start_time=8765,
        )
        db_session.add_all([backup_job, check_job])
        db_session.commit()

        cleanup_orphaned_jobs(db_session)

        db_session.refresh(backup_job)
        db_session.refresh(check_job)
        assert backup_job.status == "completed"
        assert backup_job.maintenance_status == "check_failed"
        assert check_job.status == "failed"
        assert check_job.completed_at is not None
        mock_is_process_alive.assert_called_once_with(4321, 8765)
        mock_break_repository_lock.assert_called_once_with(repo)

    @patch("app.utils.process_utils.break_repository_lock", return_value=True)
    @patch("app.utils.process_utils.is_process_alive", return_value=False)
    def test_cleanup_orphaned_jobs_matches_running_check_parent_by_repository_path(
        self, mock_is_process_alive, mock_break_repository_lock, db_session
    ):
        repo = Repository(
            name="Legacy Check Repo",
            path="/repos/legacy-check",
            encryption="none",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.flush()

        backup_job = BackupJob(
            repository=repo.path,
            repository_id=None,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            maintenance_status="running_check",
        )
        check_job = CheckJob(
            repository_id=repo.id,
            repository_path=repo.path,
            status="running",
            process_pid=2468,
            process_start_time=1357,
        )
        db_session.add_all([backup_job, check_job])
        db_session.commit()

        cleanup_orphaned_jobs(db_session)

        db_session.refresh(backup_job)
        db_session.refresh(check_job)
        assert backup_job.status == "completed"
        assert backup_job.maintenance_status == "check_failed"
        assert check_job.status == "failed"
        mock_is_process_alive.assert_called_once_with(2468, 1357)
        mock_break_repository_lock.assert_called_once_with(repo)

    @patch("app.utils.process_utils.break_repository_lock", return_value=True)
    @patch("app.utils.process_utils.is_process_alive", return_value=False)
    def test_cleanup_orphaned_jobs_does_not_match_running_check_parent_by_path_when_repository_id_differs(
        self, mock_is_process_alive, mock_break_repository_lock, db_session
    ):
        mock_is_process_alive.side_effect = lambda pid, _start_time: pid == 9753
        repo = Repository(
            name="Path Check Repo",
            path="/repos/path-check",
            encryption="none",
            repository_type="local",
        )
        other_repo = Repository(
            name="Other Path Check Repo",
            path="/repos/other-path-check",
            encryption="none",
            repository_type="local",
        )
        db_session.add_all([repo, other_repo])
        db_session.flush()

        backup_job = BackupJob(
            repository=repo.path,
            repository_id=other_repo.id,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            maintenance_status="running_check",
        )
        check_job = CheckJob(
            repository_id=repo.id,
            repository_path=repo.path,
            status="running",
            process_pid=3579,
            process_start_time=2468,
        )
        live_check_job = CheckJob(
            repository_id=other_repo.id,
            repository_path=repo.path,
            status="running",
            process_pid=9753,
            process_start_time=8642,
        )
        db_session.add_all([backup_job, check_job, live_check_job])
        db_session.commit()

        cleanup_orphaned_jobs(db_session)

        db_session.refresh(backup_job)
        db_session.refresh(check_job)
        db_session.refresh(live_check_job)
        assert backup_job.status == "completed"
        assert backup_job.maintenance_status == "running_check"
        assert check_job.status == "failed"
        assert live_check_job.status == "running"
        mock_is_process_alive.assert_any_call(3579, 2468)
        mock_is_process_alive.assert_any_call(9753, 8642)
        mock_break_repository_lock.assert_called_once_with(repo)

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

        backup_job = BackupJob(
            repository=repo.path,
            repository_id=repo.id,
            backup_plan_id=plan.id,
            backup_plan_run_id=run.id,
            status="running",
            started_at=datetime.utcnow(),
            progress=42,
        )
        db_session.add(backup_job)
        db_session.flush()

        child = BackupPlanRunRepository(
            backup_plan_run_id=run.id,
            repository_id=repo.id,
            backup_job_id=backup_job.id,
            status="running",
            started_at=datetime.utcnow(),
        )
        db_session.add(child)
        db_session.commit()

        cleanup_orphaned_jobs(db_session)

        db_session.refresh(backup_job)
        db_session.refresh(child)
        db_session.refresh(run)

        assert backup_job.status == "failed"
        assert child.status == "failed"
        assert child.completed_at is not None
        assert run.status == "failed"
        assert run.completed_at is not None

    def test_cleanup_orphaned_jobs_marks_pending_backup_job_failed(self, db_session):
        """Pending backup jobs are in-memory work and cannot resume after restart"""
        repo = Repository(
            name="Manual Repo",
            path="/repos/manual",
            encryption="none",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.flush()

        backup_job = BackupJob(
            repository=repo.path,
            repository_id=repo.id,
            status="pending",
            progress=12,
        )
        db_session.add(backup_job)
        db_session.commit()

        cleanup_orphaned_jobs(db_session)

        db_session.refresh(backup_job)

        assert backup_job.status == "failed"
        assert backup_job.completed_at is not None
        assert (
            json.loads(backup_job.error_message)["key"]
            == "backend.errors.service.containerRestartedDuringBackup"
        )

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
