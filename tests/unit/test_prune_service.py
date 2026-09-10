import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.database.models import Repository
from app.services.prune_service import PruneService
from app.services.operations.job_facade import resolve_maintenance_job
from app.database.models import OperationBackupDetails
from tests.utils.operations import seed_job_operation


class EmptyAsyncStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class FakeProcess:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.pid = 123
        self.stdout = EmptyAsyncStream()
        self.stderr = EmptyAsyncStream()

    async def wait(self):
        return self.returncode


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_prune_command_includes_keep_within(db_engine):
    testing_session_local = sessionmaker(bind=db_engine)
    session = testing_session_local()
    repo = Repository(
        name="V1 Repo",
        path="/tmp/v1-repo",
        encryption="repokey",
        repository_type="local",
        borg_version=1,
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)

    job = seed_job_operation(
        session,
        "prune",
        repository_id=repo.id,
        repository_path=repo.path,
        status="pending",
    )
    session.commit()
    session.refresh(job)
    repo_id = repo.id
    job_id = job.id
    session.close()

    service = PruneService()

    with (
        patch("app.services.prune_service.SessionLocal", testing_session_local),
        patch(
            "app.services.prune_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch(
            "app.services.prune_service.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=FakeProcess(0)),
        ) as create_subprocess,
    ):
        await service.execute_prune(
            job_id,
            repo_id,
            0,
            7,
            4,
            6,
            0,
            1,
            dry_run=True,
            keep_within="1d",
        )

    cmd = list(create_subprocess.await_args.args)
    assert "--keep-within=1d" in cmd


class LinesAsyncStream:
    def __init__(self, lines):
        self._lines = list(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._lines:
            raise StopAsyncIteration
        return self._lines.pop(0)


def _log_record(message):
    """One `--log-json` record as borg prints it (one JSON object per line)."""
    return (
        json.dumps(
            {
                "type": "log_message",
                "time": 1758000000.0,
                "message": message,
                "levelname": "INFO",
                "name": "borg.output.list",
            }
        )
        + "\n"
    ).encode()


class PruningFakeProcess(FakeProcess):
    def __init__(self, pruned_names, trailing_lines=0):
        super().__init__(returncode=0)
        lines = [
            _log_record(
                f"Pruning archive: {name}        Mon, 2026-07-20 03:00:00 [aa00] (1/1)"
            )
            for name in pruned_names
        ]
        # --list chatter after the prune lines, enough to overflow the buffer
        lines += [
            _log_record(f"Keeping archive: keep-{i}") for i in range(trailing_lines)
        ]
        self.stderr = LinesAsyncStream(lines)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_prune_marks_the_jobs_of_pruned_archives(db_engine):
    """The server-side prune is a production call site of the mark: the
    backup job of a pruned archive stays and records the prune."""
    testing_session_local = sessionmaker(bind=db_engine)
    session = testing_session_local()
    repo = Repository(
        name="V1 Repo",
        path="/tmp/v1-repo",
        encryption="repokey",
        repository_type="local",
        borg_version=1,
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)
    backup = seed_job_operation(
        session,
        "backup",
        repository_id=repo.id,
        status="completed",
        archive_name="host-old",
    )
    job = seed_job_operation(
        session,
        "prune",
        repository_id=repo.id,
        repository_path=repo.path,
        status="pending",
    )
    session.commit()
    repo_id, job_id, backup_id = repo.id, job.id, backup.id
    session.close()

    with (
        patch("app.services.prune_service.SessionLocal", testing_session_local),
        patch(
            "app.services.prune_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch(
            "app.services.prune_service.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=PruningFakeProcess(["host-old"])),
        ),
    ):
        await PruneService().execute_prune(job_id, repo_id, 0, 7, 4, 6, 0, 1)

    session = testing_session_local()
    row = session.get(OperationBackupDetails, backup_id)
    assert row is not None and row.archive_pruned_at is not None
    assert resolve_maintenance_job(session, job_id, "prune").status == "completed"
    session.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_prune_marks_archives_whose_lines_left_the_log_buffer(db_engine):
    """The in-memory log buffer keeps the last 1000 lines only; a prune line
    that scrolled out of it must still mark the job, since the names are
    collected while the output streams."""
    testing_session_local = sessionmaker(bind=db_engine)
    session = testing_session_local()
    repo = Repository(
        name="V1 Repo",
        path="/tmp/v1-repo",
        encryption="repokey",
        repository_type="local",
        borg_version=1,
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)
    backup = seed_job_operation(
        session,
        "backup",
        repository_id=repo.id,
        status="completed",
        archive_name="host-old",
    )
    job = seed_job_operation(
        session,
        "prune",
        repository_id=repo.id,
        repository_path=repo.path,
        status="pending",
    )
    session.commit()
    repo_id, job_id, backup_id = repo.id, job.id, backup.id
    session.close()

    with (
        patch("app.services.prune_service.SessionLocal", testing_session_local),
        patch(
            "app.services.prune_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch(
            "app.services.prune_service.asyncio.create_subprocess_exec",
            new=AsyncMock(
                return_value=PruningFakeProcess(["host-old"], trailing_lines=1200)
            ),
        ),
    ):
        await PruneService().execute_prune(job_id, repo_id, 0, 7, 4, 6, 0, 1)

    session = testing_session_local()
    assert session.get(OperationBackupDetails, backup_id).archive_pruned_at is not None
    prune_row = resolve_maintenance_job(session, job_id, "prune")
    # proof that the buffer really lost the line
    assert "Pruning archive" not in (prune_row.logs or "")
    session.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_prune_matches_names_that_json_escapes(db_engine):
    """`--log-json` escapes quotes and backslashes inside the record; the
    name is matched from the decoded message, not the raw line."""
    name = 'quote"d\\name'
    testing_session_local = sessionmaker(bind=db_engine)
    session = testing_session_local()
    repo = Repository(
        name="V1 Repo",
        path="/tmp/v1-repo",
        encryption="repokey",
        repository_type="local",
        borg_version=1,
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)
    backup = seed_job_operation(
        session, "backup", repository_id=repo.id, status="completed", archive_name=name
    )
    job = seed_job_operation(
        session,
        "prune",
        repository_id=repo.id,
        repository_path=repo.path,
        status="pending",
    )
    session.commit()
    repo_id, job_id, backup_id = repo.id, job.id, backup.id
    session.close()

    with (
        patch("app.services.prune_service.SessionLocal", testing_session_local),
        patch(
            "app.services.prune_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch(
            "app.services.prune_service.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=PruningFakeProcess([name])),
        ),
    ):
        await PruneService().execute_prune(job_id, repo_id, 0, 7, 4, 6, 0, 1)

    session = testing_session_local()
    assert session.get(OperationBackupDetails, backup_id).archive_pruned_at is not None
    session.close()


@pytest.mark.unit
def test_log_message_falls_back_to_the_raw_line():
    from app.services.prune_service import _log_message

    assert _log_message("Pruning archive: x") == "Pruning archive: x"
    assert _log_message("{not json") == "{not json"
    progress = '{"type": "progress", "current": 1}'
    assert _log_message(progress) == progress
    assert _log_message('{"message": "Pruning archive: y"}') == "Pruning archive: y"
