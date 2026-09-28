"""Archive stats already measured survive a refusal of the next archive.

`fill_archive_info` queues one `repository.archive_info` agent job per
archive. When another job takes the repository in between, the next
admission refuses, and a refused admission rolls the session back to let go
of its write lock. Each archive's stats are therefore committed as they are
measured, or the refusal would take the last one with it.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.database.models import Archive, Repository
from app.services.job_admission import REPOSITORY_OPERATION_ACTIVE_KEY
from app.services.operations.executors import index


def _info(nfiles):
    return {
        "success": True,
        "stdout": json.dumps(
            {
                "archives": [
                    {
                        "stats": {
                            "nfiles": nfiles,
                            "original_size": 1000,
                            "compressed_size": 900,
                            "deduplicated_size": 100,
                        },
                        "end": None,
                        "duration": 1.5,
                    }
                ]
            }
        ),
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_measured_archive_keeps_its_stats_when_the_next_is_refused(test_db):
    repo = Repository(
        name="agent-repo",
        path="/repos/agent-repo",
        encryption="none",
        repository_type="local",
        executor_type="agent",
    )
    test_db.add(repo)
    test_db.commit()
    start = datetime(2026, 9, 1, 12, 0, 0)
    archives = []
    for offset, name in enumerate(["older", "newer"]):
        archive = Archive(
            repository_id=repo.id,
            borg_id=f"id-{name}",
            name=name,
            series="series",
            start=start + timedelta(hours=offset),
            first_seen_at=start,
            last_seen_at=start,
        )
        test_db.add(archive)
        archives.append(archive)
    test_db.commit()

    async def archive_info(db, _repository, archive, *, timeout_seconds):
        if archive.name == "older":
            return _info(nfiles=42)
        # What a refused admission does: release the lock, then 409.
        db.rollback()
        raise HTTPException(
            status_code=409, detail={"key": REPOSITORY_OPERATION_ACTIVE_KEY}
        )

    with (
        patch.object(
            index, "_agent_archive_info", new=AsyncMock(side_effect=archive_info)
        ),
        patch.object(index, "agent_timezone_for_repository", return_value="UTC"),
        patch.object(index, "get_operation_timeouts", return_value={"info_timeout": 5}),
        pytest.raises(HTTPException),
    ):
        await index.fill_archive_info(test_db, repo, archives, {}, limit=10)

    test_db.expire_all()
    stored = {a.name: a for a in test_db.query(Archive).all()}
    assert stored["older"].nfiles == 42
    assert stored["older"].stats_measured_at is not None
    assert stored["newer"].nfiles is None
