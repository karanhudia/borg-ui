import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.database.models import Repository, SSHConnection
from app.services.restore_service import RestoreService
from app.services.operations.restore_facade import resolve_restore_job
from tests.utils.operations import seed_job_operation


class AsyncReadStream:
    def __init__(self, chunks=None):
        self._chunks = [
            chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
            for chunk in (chunks or [])
        ]
        self._index = 0

    async def read(self, _size):
        if self._index >= len(self._chunks):
            return b""
        value = self._chunks[self._index]
        self._index += 1
        return value


class AsyncIterStream:
    def __init__(self, lines=None):
        self._lines = [
            line if isinstance(line, bytes) else line.encode("utf-8")
            for line in (lines or [])
        ]
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._lines):
            raise StopAsyncIteration
        value = self._lines[self._index]
        self._index += 1
        return value


class FakeStdin:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeRestoreProcess:
    def __init__(self, returncode=0, stderr_chunks=None, stdout_lines=None, pid=1234):
        self.returncode = returncode
        self.stderr = AsyncReadStream(stderr_chunks)
        self.stdout = AsyncIterStream(stdout_lines)
        self.stdin = FakeStdin()
        self.pid = pid
        self.terminated = False
        self.killed = False

    async def wait(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


@pytest.fixture
def testing_session_local(db_session):
    return sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)


@pytest.fixture
def restore_repository(db_session):
    repo = Repository(
        name="Restore Repo",
        path="/tmp/restore-repo",
        encryption="none",
        compression="lz4",
        repository_type="local",
        passphrase="secret",
        bypass_lock=True,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


@pytest.fixture
def restore_job(db_session, restore_repository, tmp_path):
    """The restore the service drives, through the facade that carries the
    attribute surface it reads (`repository`, `archive`, `destination`)."""
    job = seed_job_operation(
        db_session,
        "restore",
        repository=restore_repository.path,
        archive="archive-1",
        destination=str(tmp_path / "restore-target"),
        status="pending",
    )
    db_session.commit()
    return resolve_restore_job(db_session, job.id)


@pytest.fixture
def restore_operation(db_session, restore_repository, tmp_path, monkeypatch):
    from app.database.models import Operation
    from app.services.operations.details import restore_details

    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    op = Operation(
        repository_id=restore_repository.id,
        kind="restore",
        category="restore",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-service",
        params={"archive_name": "archive-1", "paths": []},
    )
    db_session.add(op)
    db_session.flush()
    details = restore_details(db_session, op)
    details.archive = "archive-1"
    details.destination = str(tmp_path / "restore-target")
    details.repository_type = "local"
    details.destination_type = "local"
    db_session.commit()
    db_session.refresh(op)
    return op


class TestRestoreServiceRouting:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_restore_routes_local_to_local(self):
        service = RestoreService()

        with (
            patch.object(
                service, "_execute_local_to_local", new=AsyncMock()
            ) as mock_exec,
            patch.object(service, "_is_agent_restore", return_value=False),
        ):
            await service.execute_restore(1, "/repo", "arch", "/dest")

        mock_exec.assert_awaited_once_with(
            1,
            "/repo",
            "arch",
            "/dest",
            None,
            restore_layout="preserve_path",
            path_metadata=None,
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_restore_routes_ssh_to_local(self):
        service = RestoreService()

        with (
            patch.object(
                service, "_execute_ssh_to_local", new=AsyncMock()
            ) as mock_exec,
            patch.object(service, "_is_agent_restore", return_value=False),
        ):
            await service.execute_restore(
                1,
                "/repo",
                "arch",
                "/dest",
                repository_type="ssh",
                destination_type="local",
            )

        mock_exec.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_restore_routes_local_to_ssh(self):
        service = RestoreService()

        with (
            patch.object(
                service, "_execute_local_to_ssh", new=AsyncMock()
            ) as mock_exec,
            patch.object(service, "_is_agent_restore", return_value=False),
        ):
            await service.execute_restore(
                1,
                "/repo",
                "arch",
                "/dest",
                repository_type="local",
                destination_type="ssh",
                destination_connection_id=9,
            )

        mock_exec.assert_awaited_once_with(
            1,
            "/repo",
            "arch",
            "/dest",
            None,
            9,
            restore_layout="preserve_path",
            path_metadata=None,
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_restore_marks_unsupported_mode_failed(
        self, testing_session_local, db_session, restore_job
    ):
        service = RestoreService()

        with patch("app.services.restore_service.SessionLocal", testing_session_local):
            await service.execute_restore(
                restore_job.id,
                restore_job.repository,
                restore_job.archive,
                restore_job.destination,
                repository_type="ssh",
                destination_type="ssh",
            )

        verification = testing_session_local()
        refreshed = resolve_restore_job(verification, restore_job.id)
        assert refreshed.status == "failed"
        assert "unsupportedExecutionMode" in refreshed.error_message
        verification.close()


class TestRestoreServiceExecution:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_local_restore_returns_when_job_missing(self, testing_session_local):
        service = RestoreService()

        with patch("app.services.restore_service.SessionLocal", testing_session_local):
            await service._execute_local_to_local(999, "/repo", "arch", "/dest", None)

        assert service.running_processes == {}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ssh_restore_mounts_destination_with_preserve_symlinks(
        self, testing_session_local, db_session, restore_job
    ):
        # Restore-to-SSH must mount the destination faithfully (issue #751, write
        # side): under follow_symlinks borg's attr step fails on every symlink.
        connection = SSHConnection(host="example.com", username="borg", port=22)
        db_session.add(connection)
        db_session.commit()
        db_session.refresh(connection)

        captured = {}

        async def fake_mount(**kwargs):
            captured.update(kwargs)
            return "/tmp/x", []  # empty -> aborts the restore right after the mount

        service = RestoreService()
        with (
            patch("app.services.restore_service.SessionLocal", testing_session_local),
            patch(
                "app.services.mount_service.mount_service.mount_ssh_paths_shared",
                new=fake_mount,
            ),
        ):
            try:
                await service._execute_local_to_ssh(
                    restore_job.id,
                    restore_job.repository,
                    "archive-1",
                    "/dest",
                    destination_connection_id=connection.id,
                )
            except Exception:
                pass  # only the mount kwargs matter here

        assert captured.get("preserve_symlinks") is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_local_restore_marks_failed_when_destination_creation_fails(
        self, testing_session_local, restore_job
    ):
        service = RestoreService()

        with (
            patch("app.services.restore_service.SessionLocal", testing_session_local),
            patch(
                "app.services.restore_service.Path.mkdir",
                side_effect=PermissionError("no permission"),
            ),
        ):
            await service._execute_local_to_local(
                restore_job.id,
                restore_job.repository,
                restore_job.archive,
                restore_job.destination,
                None,
            )

        verification = testing_session_local()
        refreshed = resolve_restore_job(verification, restore_job.id)
        assert refreshed.status == "failed"
        assert "failedCreateDestinationDir" in refreshed.error_message
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_local_restore_success_updates_job_and_sends_notification(
        self, testing_session_local, restore_job, restore_repository
    ):
        service = RestoreService()
        process = FakeRestoreProcess(
            returncode=0,
            stderr_chunks=[
                json.dumps(
                    {
                        "type": "progress_percent",
                        "current": 10,
                        "total": 20,
                        "info": ["docs/report.txt"],
                        "finished": False,
                    }
                )
                + "\n"
            ],
            stdout_lines=[b"restored\n"],
        )

        notification_mock = SimpleNamespace(
            send_restore_success=AsyncMock(return_value=None),
            send_restore_failure=AsyncMock(return_value=None),
        )

        with (
            patch("app.services.restore_service.SessionLocal", testing_session_local),
            patch(
                "app.services.restore_service.asyncio.create_subprocess_exec",
                return_value=process,
            ),
            patch(
                "app.services.restore_service.notification_service",
                notification_mock,
            ),
        ):
            await service._execute_local_to_local(
                restore_job.id,
                restore_job.repository,
                restore_job.archive,
                restore_job.destination,
                None,
            )

        verification = testing_session_local()
        refreshed = resolve_restore_job(verification, restore_job.id)
        assert refreshed.status == "completed"
        assert refreshed.progress == 100
        assert refreshed.progress_percent == 100.0
        assert "STDOUT:" in refreshed.logs

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_local_restore_root_created_destination_inherits_existing_parent_owner(
        self, testing_session_local, restore_job, tmp_path
    ):
        parent = tmp_path / "parent"
        parent.mkdir()
        destination = parent / "new" / "child"
        parent_stat = parent.stat()
        service = RestoreService()
        process = FakeRestoreProcess(
            returncode=0,
            stderr_chunks=[
                b'{"type":"progress_percent","current":1,"total":1,"finished":true}\n'
            ],
            stdout_lines=[b"restored\n"],
        )

        notification_mock = SimpleNamespace(
            send_restore_success=AsyncMock(return_value=None),
            send_restore_failure=AsyncMock(return_value=None),
        )

        with (
            patch("app.services.restore_service.SessionLocal", testing_session_local),
            patch("app.services.restore_service.os.geteuid", return_value=0),
            patch("app.services.restore_service.os.chown") as chown_mock,
            patch(
                "app.services.restore_service.asyncio.create_subprocess_exec",
                return_value=process,
            ),
            patch(
                "app.services.restore_service.notification_service",
                notification_mock,
            ),
        ):
            await service._execute_local_to_local(
                restore_job.id,
                restore_job.repository,
                restore_job.archive,
                str(destination),
                None,
            )

        assert destination.exists()
        chown_mock.assert_has_calls(
            [
                call(str(parent / "new"), parent_stat.st_uid, parent_stat.st_gid),
                call(str(destination), parent_stat.st_uid, parent_stat.st_gid),
            ],
            any_order=False,
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_local_restore_uses_borg2_extract_shape_for_v2_repositories(
        self, testing_session_local, restore_job, restore_repository
    ):
        restore_repository.borg_version = 2
        session = testing_session_local()
        session.merge(restore_repository)
        session.commit()
        session.close()

        service = RestoreService()
        process = FakeRestoreProcess(
            returncode=0,
            stderr_chunks=[
                b'{"type":"progress_percent","current":1,"total":1,"finished":true}\n'
            ],
            stdout_lines=[b"restored\n"],
        )

        notification_mock = SimpleNamespace(
            send_restore_success=AsyncMock(return_value=None),
            send_restore_failure=AsyncMock(return_value=None),
        )

        with (
            patch("app.services.restore_service.SessionLocal", testing_session_local),
            patch(
                "app.services.restore_service.asyncio.create_subprocess_exec",
                return_value=process,
            ) as mock_exec,
            patch(
                "app.services.restore_service.notification_service",
                notification_mock,
            ),
            patch("app.core.borg2.borg2.borg_cmd", "borg2"),
        ):
            await service._execute_local_to_local(
                restore_job.id,
                restore_job.repository,
                restore_job.archive,
                restore_job.destination,
                ["etc/hosts"],
            )

        cmd = mock_exec.call_args.args
        assert cmd[0] == "borg2"
        assert "-r" in cmd
        assert restore_job.repository in cmd
        assert "extract" in cmd
        assert "archive-1" in cmd
        notification_mock.send_restore_success.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_local_restore_contents_only_adds_strip_components(
        self, testing_session_local, restore_job, restore_repository
    ):
        service = RestoreService()
        process = FakeRestoreProcess(
            returncode=0,
            stderr_chunks=[
                b'{"type":"progress_percent","current":1,"total":1,"finished":true}\n'
            ],
            stdout_lines=[b"restored\n"],
        )

        notification_mock = SimpleNamespace(
            send_restore_success=AsyncMock(return_value=None),
            send_restore_failure=AsyncMock(return_value=None),
        )

        with (
            patch("app.services.restore_service.SessionLocal", testing_session_local),
            patch(
                "app.services.restore_service.asyncio.create_subprocess_exec",
                return_value=process,
            ) as mock_exec,
            patch(
                "app.services.restore_service.notification_service",
                notification_mock,
            ),
        ):
            await service._execute_local_to_local(
                restore_job.id,
                restore_job.repository,
                restore_job.archive,
                restore_job.destination,
                ["home/username/folder1/folder2"],
                restore_layout="contents_only",
                path_metadata=[
                    {"path": "home/username/folder1/folder2", "type": "directory"}
                ],
            )

        cmd = list(mock_exec.call_args.args)
        assert "--strip-components" in cmd
        strip_index = cmd.index("--strip-components")
        assert cmd[strip_index + 1] == "4"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_local_restore_warning_with_zero_files_becomes_failed(
        self, testing_session_local, restore_job
    ):
        service = RestoreService()
        process = FakeRestoreProcess(
            returncode=1,
            stderr_chunks=[b"permission denied\n"],
            stdout_lines=[],
        )

        notification_mock = SimpleNamespace(
            send_restore_success=AsyncMock(return_value=None),
            send_restore_failure=AsyncMock(return_value=None),
        )

        with (
            patch("app.services.restore_service.SessionLocal", testing_session_local),
            patch(
                "app.services.restore_service.asyncio.create_subprocess_exec",
                return_value=process,
            ),
            patch(
                "app.services.restore_service.notification_service",
                notification_mock,
            ),
        ):
            await service._execute_local_to_local(
                restore_job.id,
                restore_job.repository,
                restore_job.archive,
                restore_job.destination,
                None,
            )

        verification = testing_session_local()
        refreshed = resolve_restore_job(verification, restore_job.id)
        assert refreshed.status == "failed"
        assert "restoreFailedZeroFilesPermission" in refreshed.error_message
        notification_mock.send_restore_failure.assert_awaited_once()
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_local_restore_warning_with_files_becomes_completed_with_warnings(
        self, testing_session_local, restore_job
    ):
        service = RestoreService()
        process = FakeRestoreProcess(
            returncode=1,
            stderr_chunks=[
                json.dumps(
                    {
                        "type": "progress_percent",
                        "current": 10,
                        "total": 10,
                        "info": ["docs/report.txt"],
                        "finished": False,
                    }
                )
                + "\n"
            ],
            stdout_lines=[],
        )

        notification_mock = SimpleNamespace(
            send_restore_success=AsyncMock(return_value=None),
            send_restore_failure=AsyncMock(return_value=None),
        )

        with (
            patch("app.services.restore_service.SessionLocal", testing_session_local),
            patch(
                "app.services.restore_service.asyncio.create_subprocess_exec",
                return_value=process,
            ),
            patch(
                "app.services.restore_service.notification_service",
                notification_mock,
            ),
        ):
            await service._execute_local_to_local(
                restore_job.id,
                restore_job.repository,
                restore_job.archive,
                restore_job.destination,
                None,
            )

        verification = testing_session_local()
        refreshed = resolve_restore_job(verification, restore_job.id)
        assert refreshed.status == "completed_with_warnings"
        assert "restoreCompletedWithWarnings" in refreshed.error_message
        notification_mock.send_restore_success.assert_awaited_once()
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_local_restore_nonwarning_exit_marks_failed(
        self, testing_session_local, restore_job
    ):
        service = RestoreService()
        process = FakeRestoreProcess(
            returncode=2, stderr_chunks=[b"boom\n"], stdout_lines=[]
        )

        notification_mock = SimpleNamespace(
            send_restore_success=AsyncMock(return_value=None),
            send_restore_failure=AsyncMock(return_value=None),
        )

        with (
            patch("app.services.restore_service.SessionLocal", testing_session_local),
            patch(
                "app.services.restore_service.asyncio.create_subprocess_exec",
                return_value=process,
            ),
            patch(
                "app.services.restore_service.notification_service",
                notification_mock,
            ),
        ):
            await service._execute_local_to_local(
                restore_job.id,
                restore_job.repository,
                restore_job.archive,
                restore_job.destination,
                None,
            )

        verification = testing_session_local()
        refreshed = resolve_restore_job(verification, restore_job.id)
        assert refreshed.status == "failed"
        assert "restoreFailedExitCode" in refreshed.error_message
        notification_mock.send_restore_failure.assert_awaited_once()
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_local_restore_on_an_operation_writes_the_row_and_its_log_file(
        self, testing_session_local, restore_operation, restore_repository, tmp_path
    ):
        from app.database.models import Operation, OperationRestoreDetails

        service = RestoreService()
        process = FakeRestoreProcess(
            returncode=0,
            stderr_chunks=[
                json.dumps(
                    {
                        "type": "progress_percent",
                        "current": 10,
                        "total": 20,
                        "info": ["docs/report.txt"],
                        "finished": False,
                    }
                )
                + "\n"
            ],
            stdout_lines=[b"restored\n"],
        )
        notification_mock = SimpleNamespace(
            send_restore_success=AsyncMock(return_value=None),
            send_restore_failure=AsyncMock(return_value=None),
        )

        with (
            patch("app.services.restore_service.SessionLocal", testing_session_local),
            patch(
                "app.services.restore_service.asyncio.create_subprocess_exec",
                return_value=process,
            ),
            patch(
                "app.services.restore_service.notification_service", notification_mock
            ),
        ):
            await service._execute_local_to_local(
                restore_operation.id,
                restore_repository.path,
                "archive-1",
                str(tmp_path / "restore-target"),
                None,
            )

        verification = testing_session_local()
        op = verification.get(Operation, restore_operation.id)
        details = verification.get(OperationRestoreDetails, restore_operation.id)
        assert op.status == "completed"
        assert op.progress_percent == 100.0
        assert op.log_file_path == str(tmp_path / "logs" / f"operation_{op.id}.log")
        assert "STDOUT:" in (tmp_path / "logs" / f"operation_{op.id}.log").read_text()
        assert details.original_size == 20
        assert details.restored_size == 10
        assert details.nfiles == 1
        assert details.current_file == "docs/report.txt"
        notification_mock.send_restore_success.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_agent_terminal_state_lands_on_the_operation(
        self, db_session, restore_operation
    ):
        from app.database.models import Operation
        from app.services.operations.restore_facade import RestoreJobFacade

        service = RestoreService()
        job = RestoreJobFacade(db_session, restore_operation)
        agent_job = SimpleNamespace(
            id=1, status="completed", result={"warning": True, "return_code": 1}
        )
        with patch.object(service, "_collect_agent_job_logs", return_value="agent log"):
            service._apply_agent_restore_terminal(db_session, job, agent_job)
        db_session.commit()

        op = db_session.get(Operation, restore_operation.id)
        assert op.status == "completed_with_warnings"
        assert op.progress_percent == 100.0
        assert json.loads(op.error_message)["params"]["exitCode"] == 1
        assert op.log_file_path is not None
        assert job.logs == "agent log"


class TestRestoreServiceCancellation:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cancel_restore_returns_false_when_job_not_running(self):
        service = RestoreService()

        assert await service.cancel_restore(999) is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cancel_restore_terminates_process_gracefully(self):
        service = RestoreService()
        process = FakeRestoreProcess()
        process.wait = AsyncMock(return_value=0)
        service.running_processes[7] = process

        result = await service.cancel_restore(7)

        assert result is True
        assert process.terminated is True
        process.wait.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cancel_restore_force_kills_after_timeout(self):
        service = RestoreService()
        process = FakeRestoreProcess()
        process.wait = AsyncMock(return_value=0)
        service.running_processes[9] = process

        timeout_then_success = [asyncio.TimeoutError(), None]

        async def fake_wait_for(awaitable, timeout):
            outcome = timeout_then_success.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return await awaitable

        with patch(
            "app.services.restore_service.asyncio.wait_for", side_effect=fake_wait_for
        ):
            result = await service.cancel_restore(9)

        assert result is True
        assert process.terminated is True
        assert process.killed is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cancel_restore_returns_false_on_exception(self):
        service = RestoreService()
        process = Mock()
        process.terminate.side_effect = RuntimeError("bad")
        service.running_processes[5] = process

        assert await service.cancel_restore(5) is False


def _agent_job_row(db_session, status, *, capabilities=("jobs.cancel",)):
    from datetime import datetime

    from app.core.security import get_password_hash
    from app.database.models import AgentJob, AgentMachine

    agent = AgentMachine(
        name=f"restore-agent-{status}",
        agent_id=f"agt_restore_{status}",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=list(capabilities),
    )
    db_session.add(agent)
    db_session.commit()
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status=status,
        payload={"job_kind": "repository.restore"},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()
    return job


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_agent_restore_takes_a_queued_job_off_the_queue(
    testing_session_local, db_session
):
    """No agent picks up a `cancel_requested` job, so one nobody took is
    cancelled outright instead of waiting for the stall timeout."""
    from app.database.models import AgentJob

    job = _agent_job_row(db_session, "queued")
    service = RestoreService()
    service.agent_restore_jobs[7] = job.id
    dispatch = AsyncMock(return_value=True)

    with (
        patch("app.services.restore_service.SessionLocal", testing_session_local),
        patch(
            "app.services.agent_job_dispatcher.dispatch_agent_cancel_if_connected",
            dispatch,
        ),
    ):
        assert await service.cancel_restore(7) is True

    db_session.expire_all()
    assert db_session.get(AgentJob, job.id).status == "canceled"
    dispatch.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_agent_restore_asks_the_agent_that_took_the_job(
    testing_session_local, db_session
):
    from app.database.models import AgentJob

    job = _agent_job_row(db_session, "running")
    service = RestoreService()
    service.agent_restore_jobs[8] = job.id
    dispatch = AsyncMock(return_value=True)

    with (
        patch("app.services.restore_service.SessionLocal", testing_session_local),
        patch(
            "app.services.agent_job_dispatcher.dispatch_agent_cancel_if_connected",
            dispatch,
        ),
    ):
        assert await service.cancel_restore(8) is True

    db_session.expire_all()
    assert db_session.get(AgentJob, job.id).status == "cancel_requested"
    dispatch.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancel_retry_does_not_count_as_agent_activity(
    testing_session_local, db_session
):
    """The watcher asks again while the command does not reach the agent;
    a write each time would hold off the stall timer and the reaper."""
    from datetime import datetime

    from app.database.models import AgentJob

    job = _agent_job_row(db_session, "running")
    service = RestoreService()
    service.agent_restore_jobs[9] = job.id

    with (
        patch("app.services.restore_service.SessionLocal", testing_session_local),
        patch(
            "app.services.agent_job_dispatcher.dispatch_agent_cancel_if_connected",
            AsyncMock(return_value=False),
        ),
    ):
        assert await service.cancel_restore(9) is False
        db_session.query(AgentJob).filter(AgentJob.id == job.id).update(
            {AgentJob.updated_at: datetime(2026, 1, 1)}, synchronize_session=False
        )
        db_session.commit()
        assert await service.cancel_restore(9) is False

    db_session.expire_all()
    stored = db_session.get(AgentJob, job.id)
    assert stored.status == "cancel_requested"
    assert stored.updated_at == datetime(2026, 1, 1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_finished_restore_job_gets_no_cancel_command(
    testing_session_local, db_session
):
    job = _agent_job_row(db_session, "completed")
    service = RestoreService()
    service.agent_restore_jobs[10] = job.id
    dispatch = AsyncMock(return_value=True)

    with (
        patch("app.services.restore_service.SessionLocal", testing_session_local),
        patch(
            "app.services.agent_job_dispatcher.dispatch_agent_cancel_if_connected",
            dispatch,
        ),
    ):
        assert await service.cancel_restore(10) is False

    dispatch.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_stall_timeout_yields_to_a_verdict_that_landed_first(
    testing_session_local, db_session
):
    """The wait read `running`; the agent's completion committed before the
    timeout wrote. The verdict stands, the timeout does nothing."""
    from sqlalchemy.orm import sessionmaker

    from app.database.models import AgentJob

    job = _agent_job_row(db_session, "running")
    stale = db_session.get(AgentJob, job.id)
    assert stale.status == "running"
    other = sessionmaker(bind=db_session.get_bind())()
    try:
        other.query(AgentJob).filter(AgentJob.id == job.id).update(
            {AgentJob.status: "completed"}, synchronize_session=False
        )
        other.commit()
    finally:
        other.close()

    stopped = await RestoreService()._stop_stalled_agent_job(
        db_session, stale, "agent did not complete the restore in time"
    )

    assert stopped is False
    db_session.expire_all()
    assert db_session.get(AgentJob, job.id).status == "completed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_stall_timeout_leaves_the_job_of_an_agent_that_cannot_stop_it(
    testing_session_local, db_session
):
    """An agent before `jobs.cancel` reports `canceled` at once and lets a
    silent Borg run on: its job stays live, so admission keeps counting the
    work, and no cancel is sent. A verdict that landed first still stands."""
    from sqlalchemy.orm import sessionmaker

    from app.database.models import AgentJob

    job = _agent_job_row(db_session, "running", capabilities=())
    stale = db_session.get(AgentJob, job.id)
    dispatch = AsyncMock(return_value=True)
    with patch(
        "app.services.agent_job_dispatcher.dispatch_agent_cancel_if_connected",
        dispatch,
    ):
        stopped = await RestoreService()._stop_stalled_agent_job(
            db_session, stale, "agent did not complete the restore in time"
        )
        assert stopped is True
        db_session.expire_all()
        assert db_session.get(AgentJob, job.id).status == "running"

        other = sessionmaker(bind=db_session.get_bind())()
        try:
            other.query(AgentJob).filter(AgentJob.id == job.id).update(
                {AgentJob.status: "completed"}, synchronize_session=False
            )
            other.commit()
        finally:
            other.close()
        assert (
            await RestoreService()._stop_stalled_agent_job(
                db_session, stale, "agent did not complete the restore in time"
            )
            is False
        )
    dispatch.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_stall_timeout_only_resends_a_cancel_already_asked_for(
    testing_session_local, db_session
):
    from app.database.models import AgentJob

    job = _agent_job_row(db_session, "cancel_requested")
    row = db_session.get(AgentJob, job.id)
    row.error_message = "Cancelled by user"
    db_session.commit()
    before = row.updated_at
    dispatch = AsyncMock(return_value=True)
    with patch(
        "app.services.agent_job_dispatcher.dispatch_agent_cancel_if_connected",
        dispatch,
    ):
        stopped = await RestoreService()._stop_stalled_agent_job(
            db_session, row, "agent did not complete the restore in time"
        )

    assert stopped is True
    dispatch.assert_awaited_once()
    db_session.expire_all()
    row = db_session.get(AgentJob, job.id)
    assert row.status == "cancel_requested"
    assert row.error_message == "Cancelled by user"
    assert row.updated_at == before
