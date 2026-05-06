import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.database.models import Repository, RestoreJob
from app.services.restore_service import RestoreService


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
    job = RestoreJob(
        repository=restore_repository.path,
        archive="archive-1",
        destination=str(tmp_path / "restore-target"),
        status="pending",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


class TestRestoreServiceRouting:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_restore_routes_local_to_local(self):
        service = RestoreService()

        with patch.object(
            service, "_execute_local_to_local", new=AsyncMock()
        ) as mock_exec:
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

        with patch.object(
            service, "_execute_ssh_to_local", new=AsyncMock()
        ) as mock_exec:
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

        with patch.object(
            service, "_execute_local_to_ssh", new=AsyncMock()
        ) as mock_exec:
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
        refreshed = (
            verification.query(RestoreJob)
            .filter(RestoreJob.id == restore_job.id)
            .first()
        )
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
        refreshed = (
            verification.query(RestoreJob)
            .filter(RestoreJob.id == restore_job.id)
            .first()
        )
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
        refreshed = (
            verification.query(RestoreJob)
            .filter(RestoreJob.id == restore_job.id)
            .first()
        )
        assert refreshed.status == "completed"
        assert refreshed.progress == 100
        assert refreshed.progress_percent == 100.0
        assert "STDOUT:" in refreshed.logs

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
        refreshed = (
            verification.query(RestoreJob)
            .filter(RestoreJob.id == restore_job.id)
            .first()
        )
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
        refreshed = (
            verification.query(RestoreJob)
            .filter(RestoreJob.id == restore_job.id)
            .first()
        )
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
        refreshed = (
            verification.query(RestoreJob)
            .filter(RestoreJob.id == restore_job.id)
            .first()
        )
        assert refreshed.status == "failed"
        assert "restoreFailedExitCode" in refreshed.error_message
        notification_mock.send_restore_failure.assert_awaited_once()
        verification.close()


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
