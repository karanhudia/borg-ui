from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.database.models import PruneJob, Repository
from app.services.prune_service import PruneService


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

    job = PruneJob(repository_id=repo.id, repository_path=repo.path, status="pending")
    session.add(job)
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
