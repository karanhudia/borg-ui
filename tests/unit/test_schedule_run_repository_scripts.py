"""`run_repository_scripts` on a multi-repository schedule: off, the
repositories' own pre/post-backup scripts do not run; on, they run once,
from the schedule on a server repository and from the agent backup on an
agent repository."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.api.schedule import execute_multi_repo_schedule
from app.database.models import (
    Operation,
    Repository,
    RepositoryScript,
    ScheduledJob,
    ScheduledJobRepository,
)
from tests.unit.test_agent_repository_server_borg import _agent


def _schedule(db, repo, run_repository_scripts):
    if repo.agent_machine_id:
        db.add(
            RepositoryScript(
                repository_id=repo.id,
                agent_script_name="stop-db",
                hook_type="pre-backup",
                execution_order=1,
                enabled=True,
            )
        )
    schedule = ScheduledJob(
        name="nightly",
        cron_expression="0 2 * * *",
        enabled=True,
        run_repository_scripts=run_repository_scripts,
    )
    db.add(schedule)
    db.commit()
    db.add(
        ScheduledJobRepository(
            scheduled_job_id=schedule.id, repository_id=repo.id, execution_order=1
        )
    )
    db.commit()
    return schedule


def _repo(db, *, agent):
    repo = Repository(
        name="repo",
        path="/repos/repo",
        encryption="none",
        repository_type="local",
        source_directories=json.dumps(["/data"]),
        pre_backup_script="echo inline",
        **(
            {
                "executor_type": "agent",
                "execution_target": "agent",
                "agent_machine_id": _agent(db).id,
            }
            if agent
            else {}
        ),
    )
    db.add(repo)
    db.commit()
    return repo


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent", "run_repository_scripts", "skip_hooks", "schedule_runs_them"),
    [
        (False, False, True, False),
        (False, True, True, True),
        (True, False, True, False),
        (True, True, False, False),
    ],
)
async def test_the_flag_decides_whether_repository_scripts_run(
    test_db, agent, run_repository_scripts, skip_hooks, schedule_runs_them
):
    repo = _repo(test_db, agent=agent)
    schedule = _schedule(test_db, repo, run_repository_scripts)

    with (
        patch(
            "app.api.schedule.wait_out_backup_operation",
            new=AsyncMock(return_value="completed"),
        ),
        patch("app.api.schedule.run_script_from_library", new=AsyncMock()),
        patch(
            "app.services.script_library_executor.ScriptLibraryExecutor"
            ".execute_inline_script",
            new=AsyncMock(return_value={"success": True, "logs": ""}),
        ) as inline_script,
    ):
        await execute_multi_repo_schedule(schedule, test_db)

    operation = test_db.query(Operation).filter_by(kind="backup").one()
    # the backup skips the repository's scripts unless it is the one to run them
    assert bool(operation.params.get("skip_hooks")) is skip_hooks
    assert inline_script.await_count == (1 if schedule_runs_them else 0)
