"""#1393, #1388: the server runs no Borg for an agent repository.

A repository bound to a managed agent is reached by the agent: its machine
holds the credentials and runs Borg. Each entry point below once ran Borg on
the server for such a repository. `asyncio.create_subprocess_exec` is
replaced by a recorder, so a server-side Borg run shows up as a recorded
command line; the agent's side shows up as the agent jobs queued for it.
"""

import asyncio
import inspect
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.borg_router import BorgRouter
from app.core.security import get_password_hash
from app.database.models import (
    AgentJob,
    AgentMachine,
    LicensingState,
    Operation,
    Repository,
    RepositoryScript,
    RepositoryWipeJob,
    ScheduledJob,
    ScheduledJobRepository,
    User,
)
from tests.utils.operations import seed_job_operation

ARCHIVE_ID = "a" * 64


@pytest.fixture
def server_borg(monkeypatch):
    """Every Borg command the server starts itself."""
    calls: list[list[str]] = []

    async def record(*args, **kwargs):
        argv = [str(arg) for arg in args]
        if argv and "borg" in os.path.basename(argv[0]):
            calls.append(argv)
        raise OSError("no subprocesses in this test")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", record)
    return calls


def _enable_borg_v2(db):
    state = db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="test-instance-1393")
        db.add(state)
    state.plan = "pro"
    state.status = "active"
    state.is_trial = False
    db.commit()


def _agent(db):
    agent = AgentMachine(
        name="Host",
        agent_id="agt_host",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=[
            "backup.create",
            "repository.info",
            "repository.archive_info",
            "repository.list_archives",
            "repository.list_archive_contents",
            "repository.extract_archive_file",
            "repository.delete_archive",
            "repository.prune",
            "repository.compact",
        ],
        borg_versions=[
            {"major": 1, "version": "1.4.5", "path": "/usr/bin/borg"},
            {"major": 2, "version": "2.0.0b25", "path": "/usr/local/bin/borg2"},
        ],
    )
    db.add(agent)
    db.commit()
    return agent


def _repo(db, agent, *, borg_version=2, name="repo", **kw):
    repo = Repository(
        name=name,
        path=kw.pop("path", f"/repos/{name}"),
        encryption="none",
        repository_type="local",
        borg_version=borg_version,
        executor_type="agent",
        execution_target="agent",
        agent_machine_id=agent.id,
        source_directories=json.dumps(["/data"]),
        **kw,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


def _agent_jobs(db, job_kind=None):
    db.expire_all()
    jobs = db.query(AgentJob).order_by(AgentJob.id).all()
    return [
        job
        for job in jobs
        if job_kind is None or (job.payload or {}).get("job_kind") == job_kind
    ]


def _completed(stdout=""):
    return {"success": True, "return_code": 0, "stdout": stdout}


def _agent_answers(db, *outcomes):
    """A wait for the agent: the job ends (so the next one is admitted),
    and the wait returns the next result or raises the next error."""
    pending = list(outcomes)

    async def wait(_db, agent_job_id, **_kwargs):
        outcome = pending.pop(0) if len(pending) > 1 else pending[0]
        if callable(outcome):
            outcome = outcome()
        job = db.get(AgentJob, agent_job_id)
        timed_out = getattr(outcome, "status_code", None) == 504
        if not timed_out:  # a timed-out wait leaves the job where it was
            job.status = "failed" if isinstance(outcome, BaseException) else "completed"
            db.commit()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    return AsyncMock(side_effect=wait)


# -- backups -------------------------------------------------------------------


@pytest.mark.unit
class TestBackupExecutor:
    def test_v2_backup_run_queues_an_agent_backup(
        self, test_client, admin_headers, test_db
    ):
        _enable_borg_v2(test_db)
        repo = _repo(test_db, _agent(test_db))

        with patch(
            "app.api.v2.backups.wait_out_backup_operation",
            new=AsyncMock(return_value="failed"),
        ):
            response = test_client.post(
                "/api/v2/backup/run",
                json={"repository_id": repo.id},
                headers=admin_headers,
            )

        assert response.status_code == 500, response.text
        operation = test_db.query(Operation).filter_by(kind="backup").one()
        assert operation.params["executor"] == "agent"
        assert operation.execution_mode == "agent"
        # the server's stable Borg 2 series name, not one per hour
        assert operation.params["archive_name"] == "manual-backup"

    def test_schedule_run_now_queues_an_agent_backup(
        self, test_client, admin_headers, test_db
    ):
        repo = _repo(test_db, _agent(test_db))
        schedule = ScheduledJob(
            name="nightly",
            cron_expression="0 2 * * *",
            repository_id=repo.id,
            enabled=True,
        )
        test_db.add(schedule)
        test_db.commit()

        with (
            patch(
                "app.api.schedule.execute_scheduled_backup_with_maintenance",
                new=lambda *args, **kwargs: object(),
            ),
            patch("app.api.schedule.asyncio.create_task"),
        ):
            response = test_client.post(
                f"/api/schedule/{schedule.id}/run-now", headers=admin_headers
            )

        assert response.status_code == 200, response.text
        operation = test_db.query(Operation).filter_by(kind="backup").one()
        assert operation.params["executor"] == "agent"
        assert operation.execution_mode == "agent"

    def test_due_schedule_queues_an_agent_backup(self, test_db):
        from datetime import datetime

        from app.api.schedule import _dispatch_due_scheduled_job

        repo = _repo(test_db, _agent(test_db))
        schedule = ScheduledJob(
            name="nightly",
            cron_expression="0 2 * * *",
            repository_id=repo.id,
            enabled=True,
        )
        test_db.add(schedule)
        test_db.commit()

        with (
            patch(
                "app.api.schedule.execute_scheduled_backup_with_maintenance",
                new=lambda *args, **kwargs: object(),
            ),
            patch("app.api.schedule.asyncio.create_task"),
            patch("app.api.schedule._track_scheduled_backup_task"),
        ):
            _dispatch_due_scheduled_job(test_db, schedule, datetime.utcnow())

        operation = test_db.query(Operation).filter_by(kind="backup").one()
        assert operation.params["executor"] == "agent"

    @pytest.mark.asyncio
    async def test_multi_repository_schedule_leaves_the_hooks_to_the_agent(
        self, test_db
    ):
        from app.api.schedule import execute_multi_repo_schedule

        repo = _repo(test_db, _agent(test_db))
        test_db.add(
            RepositoryScript(
                repository_id=repo.id,
                agent_script_name="stop-db",
                hook_type="pre-backup",
                execution_order=1,
                enabled=True,
            )
        )
        schedule = ScheduledJob(
            name="multi",
            cron_expression="0 2 * * *",
            enabled=True,
            run_repository_scripts=True,
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.add(
            ScheduledJobRepository(
                scheduled_job_id=schedule.id,
                repository_id=repo.id,
                execution_order=1,
            )
        )
        test_db.commit()

        with (
            patch(
                "app.api.schedule.wait_out_backup_operation",
                new=AsyncMock(return_value="failed"),
            ),
            patch(
                "app.api.schedule.run_script_from_library", new=AsyncMock()
            ) as server_script,
            patch(
                "app.services.script_library_executor.ScriptLibraryExecutor"
                ".execute_inline_script",
                new=AsyncMock(),
            ) as inline_script,
        ):
            await execute_multi_repo_schedule(schedule, test_db)

        operation = test_db.query(Operation).filter_by(kind="backup").one()
        assert operation.params["executor"] == "agent"
        # The agent backup runs the repository's own hooks on the agent.
        assert not operation.params.get("skip_hooks")
        server_script.assert_not_awaited()
        inline_script.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_backup_queued_for_the_server_runs_on_the_agent_it_moved_to(
        self, test_db
    ):
        from app.services.operations.backup_facade import create_backup_operation
        from app.services.operations.executors import backup as backup_executor

        repo = Repository(
            name="moved",
            path="/repos/moved",
            encryption="none",
            repository_type="local",
            borg_version=2,
            source_directories=json.dumps(["/data"]),
        )
        test_db.add(repo)
        test_db.commit()
        job = create_backup_operation(
            test_db, repo, trigger="manual", executor="server"
        )
        # The repository moves to an agent while the backup waits in the queue.
        agent = _agent(test_db)
        repo.executor_type = "agent"
        repo.execution_target = "agent"
        repo.agent_machine_id = agent.id
        test_db.commit()

        operation = test_db.get(Operation, job.id)
        ctx = SimpleNamespace(
            db=test_db,
            operation_id=operation.id,
            repository_id=repo.id,
            params=dict(operation.params),
            cancelled=lambda: False,
        )

        async def agent_backup(ctx, job, repository, params):
            job.status = "completed"
            ctx.db.commit()

        with (
            patch.object(
                backup_executor,
                "_run_agent_backup",
                new=AsyncMock(side_effect=agent_backup),
            ) as run_agent,
            patch(
                "app.services.backup_service.backup_service.execute_backup",
                new=AsyncMock(),
            ) as server_backup,
        ):
            outcome = await backup_executor.run_backup(ctx)

        run_agent.assert_awaited_once()
        server_backup.assert_not_awaited()
        assert outcome.status == "completed"
        test_db.expire_all()
        operation = test_db.get(Operation, job.id)
        assert operation.params["executor"] == "agent"
        assert operation.execution_mode == "agent"

    @pytest.mark.asyncio
    async def test_a_plan_backup_whose_agent_sources_no_longer_fit_fails(self, test_db):
        from app.services.operations.backup_facade import create_backup_operation
        from app.services.operations.executors import backup as backup_executor

        agent = _agent(test_db)
        repo = _repo(test_db, agent)
        job = create_backup_operation(
            test_db,
            repo,
            trigger="manual",
            executor="agent",
            params={
                "source_locations": [
                    {
                        "source_type": "agent",
                        "agent_machine_id": agent.id,
                        "paths": ["/srv/data"],
                    }
                ]
            },
        )
        # the repository moves back to the server while the backup waits
        repo.executor_type = "server"
        repo.execution_target = "local"
        repo.agent_machine_id = None
        test_db.commit()

        operation = test_db.get(Operation, job.id)
        ctx = SimpleNamespace(
            db=test_db,
            operation_id=operation.id,
            repository_id=repo.id,
            params=dict(operation.params),
            cancelled=lambda: False,
        )
        with (
            patch.object(
                backup_executor, "_run_agent_backup", new=AsyncMock()
            ) as run_agent,
            patch(
                "app.services.backup_service.backup_service.execute_backup",
                new=AsyncMock(),
            ) as server_backup,
        ):
            outcome = await backup_executor.run_backup(ctx)

        # an agent's path is no server path: nothing is backed up
        run_agent.assert_not_awaited()
        server_backup.assert_not_awaited()
        assert outcome.status == "failed"
        assert "agentSourceToServerRepoUnsupported" in outcome.error_message


# -- archives ------------------------------------------------------------------


@pytest.mark.unit
class TestArchiveRoutes:
    def test_v2_file_download_extracts_on_the_agent(
        self, test_client, admin_headers, test_db, server_borg
    ):
        _enable_borg_v2(test_db)
        repo = _repo(test_db, _agent(test_db))

        with (
            patch("app.api.archives.dispatch_agent_job_best_effort", new=AsyncMock()),
            patch(
                "app.api.archives.wait_for_agent_repository_operation_job",
                new=AsyncMock(
                    return_value={"success": True, "content_base64": "aGVsbG8="}
                ),
            ),
        ):
            response = test_client.get(
                "/api/v2/archives/download",
                params={
                    "repository": str(repo.id),
                    "archive": ARCHIVE_ID,
                    "file_path": "data/hello.txt",
                },
                headers=admin_headers,
            )

        assert server_borg == []
        assert response.status_code == 200, response.text
        assert response.content == b"hello"
        (job,) = _agent_jobs(test_db, "repository.extract_archive_file")
        assert job.payload["operation"]["archive"] == f"aid:{ARCHIVE_ID}"
        assert job.payload["operation"]["file_path"] == "data/hello.txt"

    def test_a_v2_download_the_wait_gave_up_on_is_taken_back(
        self, test_client, admin_headers, test_db, server_borg
    ):
        from fastapi import HTTPException

        _enable_borg_v2(test_db)
        repo = _repo(test_db, _agent(test_db))

        with (
            patch("app.api.archives.dispatch_agent_job_best_effort", new=AsyncMock()),
            patch(
                "app.api.archives.wait_for_agent_repository_operation_job",
                new=AsyncMock(
                    side_effect=HTTPException(
                        status_code=504,
                        detail={"key": "backend.errors.agents.jobTimeout"},
                    )
                ),
            ),
        ):
            response = test_client.get(
                "/api/v2/archives/download",
                params={
                    "repository": str(repo.id),
                    "archive": ARCHIVE_ID,
                    "file_path": "data/hello.txt",
                },
                headers=admin_headers,
            )

        assert server_borg == []
        assert response.status_code == 504, response.text
        (job,) = _agent_jobs(test_db, "repository.extract_archive_file")
        assert job.status == "canceled"

    def test_v2_delete_passes_the_archive_id_to_the_agent(
        self, test_client, admin_headers, test_db, server_borg
    ):
        _enable_borg_v2(test_db)
        repo = _repo(test_db, _agent(test_db))

        response = test_client.delete(
            f"/api/v2/archives/{ARCHIVE_ID}",
            params={"repository": str(repo.id)},
            headers=admin_headers,
        )

        assert server_borg == []
        assert response.status_code == 200, response.text
        operation = test_db.query(Operation).filter_by(kind="delete_archive").one()
        assert operation.params["archive_name"] == f"aid:{ARCHIVE_ID}"

    @pytest.mark.parametrize("verdict", ["completed", "completed_with_warnings"])
    def test_v2_prune_dry_run_runs_on_the_agent(
        self, test_client, admin_headers, test_db, server_borg, verdict
    ):
        _enable_borg_v2(test_db)
        repo = _repo(test_db, _agent(test_db))

        async def agent_prunes(self, **kwargs):
            # the agent's report closes the linked prune row
            operation = test_db.get(Operation, kwargs["maintenance_job_id"])
            # a Borg warning (exit 1) is a dry run that ran
            operation.status = verdict
            test_db.commit()

        with patch.object(
            BorgRouter,
            "_run_agent_maintenance",
            autospec=True,
            side_effect=agent_prunes,
        ) as agent_prune:
            response = test_client.post(
                "/api/v2/backup/prune",
                json={"repository_id": repo.id, "keep_daily": 3, "dry_run": True},
                headers=admin_headers,
            )

        assert server_borg == []
        assert response.status_code == 200, response.text
        assert response.json()["dry_run"] is True
        agent_prune.assert_awaited_once()
        kwargs = agent_prune.await_args.kwargs
        assert kwargs["job_kind"] == "repository.prune"
        assert kwargs["operation"]["dry_run"] is True
        assert kwargs["operation"]["keep_daily"] == 3

    @pytest.mark.parametrize(
        "route, job_kind, stdout",
        [
            ("list", "repository.list_archives", '{"archives": []}'),
            (
                f"{ARCHIVE_ID}/info",
                "repository.archive_info",
                json.dumps({"archives": [{"name": "a", "id": ARCHIVE_ID}]}),
            ),
            (
                f"{ARCHIVE_ID}/contents",
                "repository.list_archive_contents",
                '{"path": "data"}\n',
            ),
        ],
    )
    def test_deprecated_archive_routes_run_on_the_agent(
        self, test_client, admin_headers, test_db, server_borg, route, job_kind, stdout
    ):
        repo = _repo(test_db, _agent(test_db))

        with (
            patch("app.api.archives.dispatch_agent_job_best_effort", new=AsyncMock()),
            patch(
                "app.api.archives.wait_for_agent_repository_operation_job",
                new=AsyncMock(return_value=_completed(stdout)),
            ),
        ):
            response = test_client.get(
                f"/api/archives/{route}",
                params={"repository": repo.path},
                headers=admin_headers,
            )

        assert server_borg == []
        assert response.status_code == 200, response.text
        (job,) = _agent_jobs(test_db, job_kind)
        if job_kind != "repository.list_archives":
            assert job.payload["operation"]["archive"] == f"aid:{ARCHIVE_ID}"


# -- restore preview and keyfile -------------------------------------------------


@pytest.mark.unit
class TestRefusals:
    def test_restore_preview_is_refused(
        self, test_client, admin_headers, test_db, server_borg
    ):
        repo = _repo(test_db, _agent(test_db))

        response = test_client.post(
            "/api/restore/preview",
            json={
                "repository": repo.path,
                "repository_id": repo.id,
                "archive": "a",
                "paths": ["data"],
                "destination": "/restore",
            },
            headers=admin_headers,
        )

        assert server_borg == []
        assert response.status_code == 400, response.text
        assert response.json()["detail"]["key"] == (
            "backend.errors.restore.agentPreviewUnsupported"
        )

    def test_keyfile_export_is_refused(
        self, test_client, admin_headers, test_db, server_borg
    ):
        repo = _repo(test_db, _agent(test_db), has_keyfile=True)

        response = test_client.get(
            f"/api/repositories/{repo.id}/keyfile", headers=admin_headers
        )

        assert server_borg == []
        assert response.status_code == 400, response.text
        assert response.json()["detail"]["key"] == (
            "backend.errors.repo.agentKeyfileExportUnsupported"
        )


# -- repository wipe -------------------------------------------------------------


def _admin(db):
    user = User(username="wiper", password_hash="hash", is_active=True, role="admin")
    db.add(user)
    db.commit()
    return user


def _other_agent(db, agent):
    other = AgentMachine(
        name="Other",
        agent_id="agt_other",
        token_hash=get_password_hash("borgui_agent_other"),
        token_prefix="borgui_agent_other"[:20],
        status="online",
        capabilities=list(agent.capabilities),
        borg_versions=list(agent.borg_versions),
    )
    db.add(other)
    db.commit()
    return other


@pytest.mark.unit
class TestRepositoryWipe:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("borg_version", [1, 2])
    async def test_preview_lists_the_archives_on_the_agent(
        self, test_db, server_borg, borg_version
    ):
        from app.services.repository_wipe_service import RepositoryWipeService

        repo = _repo(test_db, _agent(test_db), borg_version=borg_version)
        user = _admin(test_db)
        listing = {
            "archives": [
                {"name": "first", "id": "1" * 64, "time": "2026-10-01T00:00:00"},
                {"name": "second", "id": "2" * 64, "time": "2026-10-02T00:00:00"},
            ]
        }

        with (
            patch(
                "app.services.repository_wipe_service.dispatch_agent_job_best_effort",
                new=AsyncMock(),
                create=True,
            ),
            patch(
                "app.services.repository_wipe_service"
                ".wait_for_agent_repository_operation_job",
                new=AsyncMock(return_value=_completed(json.dumps(listing))),
                create=True,
            ),
        ):
            preview = await RepositoryWipeService().create_preview(test_db, repo, user)

        assert server_borg == []
        assert preview["blocked"] is False
        assert preview["archive_count"] == 2
        assert "first" in preview["dry_run_output"]
        assert "second" in preview["dry_run_output"]
        # Borg 2's listing carries no tags; its info does, and a protected
        # archive has to block the wipe as on the server.
        expected = (
            "repository.info" if borg_version == 2 else "repository.list_archives"
        )
        assert [j.payload["job_kind"] for j in _agent_jobs(test_db)] == [expected]

    @pytest.mark.asyncio
    async def test_preview_blocks_a_protected_archive(self, test_db, server_borg):
        from app.services.repository_wipe_service import RepositoryWipeService

        repo = _repo(test_db, _agent(test_db))
        user = _admin(test_db)
        info = {
            "archives": [
                {
                    "name": "kept",
                    "id": "1" * 64,
                    "time": "2026-10-01T00:00:00",
                    "tags": ["@PROT"],
                },
            ]
        }

        with (
            patch(
                "app.services.repository_wipe_service.dispatch_agent_job_best_effort",
                new=AsyncMock(),
                create=True,
            ),
            patch(
                "app.services.repository_wipe_service"
                ".wait_for_agent_repository_operation_job",
                new=AsyncMock(return_value=_completed(json.dumps(info))),
                create=True,
            ),
        ):
            preview = await RepositoryWipeService().create_preview(test_db, repo, user)

        assert server_borg == []
        assert preview["blocked"] is True
        assert preview["blocking_reason"] == "protected_archives"
        assert preview["protected_archives"] == ["kept"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("borg_version", [1, 2])
    async def test_wipe_deletes_only_the_confirmed_archives_on_the_agent(
        self, test_db, server_borg, borg_version
    ):
        from app.services.operations.wipe_facade import resolve_wipe_job
        from app.services.repository_wipe_service import (
            RepositoryWipeService,
            compute_archive_fingerprint,
            normalize_archive_manifest,
        )

        agent = _agent(test_db)
        repo = _repo(test_db, agent, borg_version=borg_version)
        # Another repository of the same agent, with an archive of the same
        # name: the wipe must not reach it.
        other = _repo(test_db, agent, borg_version=borg_version, name="other")
        user = _admin(test_db)
        archives = [
            {"name": "first", "id": "1" * 64, "time": "2026-10-01T00:00:00"},
            {"name": "second", "id": "2" * 64, "time": "2026-10-02T00:00:00"},
        ]
        manifest = normalize_archive_manifest(
            borg_version=borg_version, archives=archives
        )
        preview = RepositoryWipeJob(
            repository_id=repo.id,
            repository_path=repo.path,
            repository_name=repo.name,
            borg_version=borg_version,
            status="previewed",
            phase="preview",
            archive_count=2,
            archive_fingerprint=compute_archive_fingerprint(manifest),
            archive_manifest_json=json.dumps(manifest),
            run_compact=True,
            requested_by_user_id=user.id,
        )
        test_db.add(preview)
        test_db.commit()
        wipe = seed_job_operation(
            test_db,
            "wipe",
            repository_id=repo.id,
            status="running",
            params={
                "preview_id": preview.id,
                "run_compact": True,
                "agent_machine_id": agent.id,
            },
            archive_count=2,
            archive_fingerprint=preview.archive_fingerprint,
            archive_manifest_json=preview.archive_manifest_json,
            run_compact=True,
            requested_by_user_id=user.id,
            confirmed_by_user_id=user.id,
        )

        with (
            patch(
                "app.services.repository_wipe_service.SessionLocal",
                return_value=test_db,
            ),
            patch(
                "app.services.repository_wipe_service.dispatch_agent_job_best_effort",
                new=AsyncMock(),
                create=True,
            ),
            patch(
                "app.services.repository_wipe_service"
                ".wait_for_agent_repository_operation_job",
                new=_agent_answers(test_db, _completed()),
                create=True,
            ),
        ):
            await RepositoryWipeService().execute_wipe(wipe.id, repo.id)

        assert server_borg == []
        jobs = _agent_jobs(test_db)
        expected = (
            [f"aid:{'1' * 64}", f"aid:{'2' * 64}"]
            if borg_version == 2
            else ["first", "second"]
        )
        assert [j.payload["job_kind"] for j in jobs] == [
            "repository.delete_archive",
            "repository.delete_archive",
            "repository.compact",
        ]
        assert [j.payload["operation"].get("archive") for j in jobs[:2]] == expected
        # every job is this repository's, on its own agent
        assert {j.payload["repository"]["id"] for j in jobs} == {repo.id}
        assert {j.payload["repository"]["path"] for j in jobs} == {repo.path}
        assert {j.agent_machine_id for j in jobs} == {agent.id}
        assert other.id not in {j.payload["repository"]["id"] for j in jobs}
        job = resolve_wipe_job(test_db, wipe.id)
        assert job.status == "completed"
        assert job.phase == "completed"

    @pytest.mark.asyncio
    async def test_a_failed_delete_after_one_archive_is_a_partial_wipe(
        self, test_db, server_borg
    ):
        from fastapi import HTTPException

        from app.services.operations.wipe_facade import resolve_wipe_job
        from app.services.repository_wipe_service import (
            RepositoryWipeService,
            compute_archive_fingerprint,
            normalize_archive_manifest,
        )

        agent = _agent(test_db)
        repo = _repo(test_db, agent)
        user = _admin(test_db)
        manifest = normalize_archive_manifest(
            borg_version=2,
            archives=[
                {"name": "first", "id": "1" * 64, "time": "2026-10-01T00:00:00"},
                {"name": "second", "id": "2" * 64, "time": "2026-10-02T00:00:00"},
            ],
        )
        wipe = seed_job_operation(
            test_db,
            "wipe",
            repository_id=repo.id,
            status="running",
            params={"preview_id": 1, "run_compact": True, "agent_machine_id": agent.id},
            archive_count=2,
            archive_fingerprint=compute_archive_fingerprint(manifest),
            archive_manifest_json=json.dumps(manifest),
            run_compact=True,
            requested_by_user_id=user.id,
            confirmed_by_user_id=user.id,
        )
        wait = _agent_answers(
            test_db,
            _completed(),
            HTTPException(
                status_code=502,
                detail={
                    "key": "backend.errors.agents.jobFailed",
                    "params": {"reason": "lock timeout"},
                },
            ),
        )

        with (
            patch(
                "app.services.repository_wipe_service.SessionLocal",
                return_value=test_db,
            ),
            patch(
                "app.services.repository_wipe_service.dispatch_agent_job_best_effort",
                new=AsyncMock(),
                create=True,
            ),
            patch(
                "app.services.repository_wipe_service"
                ".wait_for_agent_repository_operation_job",
                new=wait,
                create=True,
            ),
        ):
            await RepositoryWipeService().execute_wipe(wipe.id, repo.id)

        assert server_borg == []
        assert [j.payload["job_kind"] for j in _agent_jobs(test_db)] == [
            "repository.delete_archive",
            "repository.delete_archive",
        ]
        job = resolve_wipe_job(test_db, wipe.id)
        # the server-side wipe's partial failure, archive by archive
        assert job.status == "failed_partial"
        assert job.operation.status == "failed"
        assert job.phase == "delete_failed_partial"
        assert "lock timeout" in job.error_message


def _seed_agent_wipe(db, repo, user, *, archive_count=2):
    from app.services.repository_wipe_service import (
        compute_archive_fingerprint,
        normalize_archive_manifest,
    )

    manifest = normalize_archive_manifest(
        borg_version=2,
        archives=[
            {
                "name": f"archive-{n}",
                "id": str(n) * 64,
                "time": "2026-10-01T00:00:00",
            }
            for n in range(1, archive_count + 1)
        ],
    )
    preview = RepositoryWipeJob(
        repository_id=repo.id,
        repository_path=repo.path,
        repository_name=repo.name,
        borg_version=2,
        status="previewed",
        phase="preview",
        archive_count=len(manifest),
        archive_fingerprint=compute_archive_fingerprint(manifest),
        archive_manifest_json=json.dumps(manifest),
        run_compact=True,
        requested_by_user_id=user.id,
    )
    db.add(preview)
    db.commit()
    return seed_job_operation(
        db,
        "wipe",
        repository_id=repo.id,
        status="running",
        params={
            "preview_id": preview.id,
            "run_compact": True,
            "agent_machine_id": repo.agent_machine_id,
        },
        archive_count=len(manifest),
        archive_fingerprint=preview.archive_fingerprint,
        archive_manifest_json=preview.archive_manifest_json,
        run_compact=True,
        requested_by_user_id=user.id,
        confirmed_by_user_id=user.id,
    )


async def _run_agent_wipe(db, wipe, repo, wait):
    from app.services.repository_wipe_service import RepositoryWipeService

    with (
        patch("app.services.repository_wipe_service.SessionLocal", return_value=db),
        patch(
            "app.services.repository_wipe_service.dispatch_agent_job_best_effort",
            new=AsyncMock(),
        ),
        patch(
            "app.services.repository_wipe_service.dispatch_agent_cancel_if_connected",
            new=AsyncMock(),
        ),
        patch(
            "app.services.repository_wipe_service"
            ".wait_for_agent_repository_operation_job",
            new=wait,
        ),
    ):
        await RepositoryWipeService().execute_wipe(wipe.id, repo.id)


@pytest.mark.unit
class TestAgentWipeEdges:
    @pytest.mark.asyncio
    async def test_a_repository_moved_to_another_agent_stops_the_wipe(
        self, test_db, server_borg
    ):
        from app.services.operations.wipe_facade import resolve_wipe_job

        agent = _agent(test_db)
        other_agent = _other_agent(test_db, agent)
        repo = _repo(test_db, agent)
        wipe = _seed_agent_wipe(test_db, repo, _admin(test_db))

        def first_delete_then_move():
            repo.agent_machine_id = other_agent.id
            test_db.commit()
            return _completed()

        await _run_agent_wipe(
            test_db, wipe, repo, _agent_answers(test_db, first_delete_then_move)
        )

        assert server_borg == []
        jobs = _agent_jobs(test_db)
        assert [j.payload["job_kind"] for j in jobs] == ["repository.delete_archive"]
        assert {j.agent_machine_id for j in jobs} == {agent.id}
        job = resolve_wipe_job(test_db, wipe.id)
        assert job.status == "failed_partial"
        assert "changed since the wipe was confirmed" in job.error_message

    @pytest.mark.asyncio
    async def test_a_delete_the_wait_gave_up_on_is_taken_back(
        self, test_db, server_borg
    ):
        from fastapi import HTTPException

        from app.services.operations.wipe_facade import resolve_wipe_job

        repo = _repo(test_db, _agent(test_db))
        wipe = _seed_agent_wipe(test_db, repo, _admin(test_db))
        timeout = HTTPException(
            status_code=504, detail={"key": "backend.errors.agents.jobTimeout"}
        )

        await _run_agent_wipe(test_db, wipe, repo, _agent_answers(test_db, timeout))

        (job,) = _agent_jobs(test_db)
        # never claimed: cancelled, so a returning agent does not delete
        assert job.status == "canceled"
        wipe_job = resolve_wipe_job(test_db, wipe.id)
        assert wipe_job.status == "failed"
        assert wipe_job.phase == "delete_failed"

    @pytest.mark.asyncio
    async def test_a_wipe_confirmed_on_one_agent_deletes_nothing_on_another(
        self, test_db, server_borg
    ):
        from app.services.operations.wipe_facade import resolve_wipe_job

        agent = _agent(test_db)
        repo = _repo(test_db, agent, borg_version=1)
        wipe = _seed_agent_wipe(test_db, repo, _admin(test_db))
        other_agent = _other_agent(test_db, agent)
        # reassigned after the confirmation, same path
        repo.agent_machine_id = other_agent.id
        test_db.commit()

        await _run_agent_wipe(
            test_db, wipe, repo, _agent_answers(test_db, _completed())
        )

        assert server_borg == []
        assert _agent_jobs(test_db) == []
        job = resolve_wipe_job(test_db, wipe.id)
        assert job.operation.status == "failed"
        assert "changed since the wipe was confirmed" in job.error_message

    @pytest.mark.asyncio
    async def test_a_preview_of_one_agent_is_stale_on_another(
        self, test_db, server_borg
    ):
        from app.services.repository_wipe_service import (
            RepositoryWipeService,
            WipeArchiveSetChanged,
        )

        agent = _agent(test_db)
        repo = _repo(test_db, agent, borg_version=1)
        user = _admin(test_db)
        listing = _completed(
            json.dumps({"archives": [{"name": "first", "time": "2026-10-01T00:00:00"}]})
        )
        with (
            patch(
                "app.services.repository_wipe_service.dispatch_agent_job_best_effort",
                new=AsyncMock(),
            ),
            patch(
                "app.services.repository_wipe_service"
                ".wait_for_agent_repository_operation_job",
                new=_agent_answers(test_db, listing),
            ),
        ):
            service = RepositoryWipeService()
            preview = await service.create_preview(test_db, repo, user)
            # the same path and archive names on another agent
            repo.agent_machine_id = _other_agent(test_db, agent).id
            test_db.commit()
            with pytest.raises(WipeArchiveSetChanged):
                await service.start_execution(
                    test_db,
                    repo,
                    user,
                    preview_id=preview["id"],
                    preview_fingerprint=preview["archive_fingerprint"],
                    confirmation_phrase=f"WIPE {repo.name}",
                    understood=True,
                    run_compact=True,
                )

        assert test_db.query(Operation).filter_by(kind="wipe").count() == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("change", ["path", "agent"])
    async def test_a_preview_of_a_repository_moved_during_its_listing_is_refused(
        self, test_db, server_borg, change
    ):
        from fastapi import HTTPException

        from app.services.repository_wipe_service import RepositoryWipeService

        agent = _agent(test_db)
        other = _other_agent(test_db, agent)
        repo = _repo(test_db, agent, borg_version=1)
        user = _admin(test_db)

        def listed_while_moved():
            # the listing is of the old place; same names may be at the new
            if change == "path":
                repo.path = "/repos/elsewhere"
            else:
                repo.agent_machine_id = other.id
            test_db.commit()
            return _completed(json.dumps({"archives": [{"name": "first"}]}))

        with (
            patch(
                "app.services.repository_wipe_service.dispatch_agent_job_best_effort",
                new=AsyncMock(),
            ),
            patch(
                "app.services.repository_wipe_service"
                ".wait_for_agent_repository_operation_job",
                new=_agent_answers(test_db, listed_while_moved),
            ),
            pytest.raises(HTTPException) as refused,
        ):
            await RepositoryWipeService().create_preview(test_db, repo, user)

        assert refused.value.status_code == 409
        assert test_db.query(RepositoryWipeJob).count() == 0

    @pytest.mark.asyncio
    async def test_a_compact_warning_is_kept(self, test_db, server_borg):
        from app.services.operations.wipe_facade import resolve_wipe_job

        repo = _repo(test_db, _agent(test_db))
        wipe = _seed_agent_wipe(test_db, repo, _admin(test_db), archive_count=1)
        warning = {"success": True, "return_code": 1, "stderr": "segment warning"}

        await _run_agent_wipe(
            test_db, wipe, repo, _agent_answers(test_db, _completed(), warning)
        )

        job = resolve_wipe_job(test_db, wipe.id)
        assert job.status == "completed_with_warnings"
        assert job.phase == "completed"
        assert "segment warning" in job.error_message


def test_a_deprecated_read_the_wait_gave_up_on_is_taken_back(
    test_client, admin_headers, test_db, server_borg
):
    from fastapi import HTTPException

    repo = _repo(test_db, _agent(test_db))

    with (
        patch("app.api.archives.dispatch_agent_job_best_effort", new=AsyncMock()),
        patch(
            "app.api.archives.wait_for_agent_repository_operation_job",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=504,
                    detail={"key": "backend.errors.agents.jobTimeout"},
                )
            ),
        ),
    ):
        response = test_client.get(
            "/api/archives/list",
            params={"repository": repo.path},
            headers=admin_headers,
        )

    assert server_borg == []
    assert response.status_code == 504, response.text
    (job,) = _agent_jobs(test_db, "repository.list_archives")
    # unclaimed: cancelled, so it no longer counts as the repository's work
    assert job.status == "canceled"


def test_deprecated_info_stands_without_a_failed_agent_file_listing(
    test_client, admin_headers, test_db, server_borg
):
    from fastapi import HTTPException

    repo = _repo(test_db, _agent(test_db))
    info = _completed(json.dumps({"archives": [{"name": "a", "id": ARCHIVE_ID}]}))
    failed = HTTPException(
        status_code=502,
        detail={"key": "backend.errors.agents.jobFailed", "params": {}},
    )

    with (
        patch("app.api.archives.dispatch_agent_job_best_effort", new=AsyncMock()),
        patch(
            "app.api.archives.wait_for_agent_repository_operation_job",
            new=AsyncMock(side_effect=[info, failed]),
        ),
    ):
        response = test_client.get(
            f"/api/archives/{ARCHIVE_ID}/info",
            params={"repository": repo.path, "include_files": True},
            headers=admin_headers,
        )

    # the files are best effort, as on the server
    assert response.status_code == 200, response.text
    body = response.json()["info"]
    assert body["name"] == "a"
    assert body["files"] == []
    assert body["file_count"] == 0


def test_deprecated_info_cuts_an_agent_file_listing_at_the_limit(
    test_client, admin_headers, test_db, server_borg
):
    repo = _repo(test_db, _agent(test_db))
    info = _completed(json.dumps({"archives": [{"name": "a", "id": ARCHIVE_ID}]}))
    listing = _completed(
        '{"path": "data/one"}\n{"path": "data/two"}\n{"path": "data/3"}'
    )

    with (
        patch("app.api.archives.dispatch_agent_job_best_effort", new=AsyncMock()),
        patch(
            "app.api.archives.wait_for_agent_repository_operation_job",
            new=AsyncMock(side_effect=[info, listing]),
        ),
    ):
        response = test_client.get(
            f"/api/archives/{ARCHIVE_ID}/info",
            params={"repository": repo.path, "include_files": True, "file_limit": 2},
            headers=admin_headers,
        )

    assert server_borg == []
    assert response.status_code == 200, response.text
    body = response.json()["info"]
    assert [f["path"] for f in body["files"]] == ["data/one", "data/two"]
    (job,) = _agent_jobs(test_db, "repository.list_archive_contents")
    # no line cap on the agent: it would end the listing as a failure
    assert "max_lines" not in job.payload["operation"]


# -- the choke point -------------------------------------------------------------


def _argument(name: str):
    """A value for a BorgRouter method parameter."""
    return {
        "job_id": 1,
        "archive": "aid:" + ARCHIVE_ID,
        "archive_name": "aid:" + ARCHIVE_ID,
        "archive_a": "aid:" + ARCHIVE_ID,
        "archive_b": "aid:" + "b" * 64,
        "paths": ["data"],
        "destination": "/restore",
        "output_path": "/tmp/key",
        "dry_run": True,
    }.get(name, 0)


async def _drive(result):
    if inspect.isawaitable(result):
        return await result
    if hasattr(result, "__aiter__"):
        async for _ in result:
            pass
    return result


def _borg_methods():
    """Every public BorgRouter method that may start Borg: all of them but
    the command builders and the pure helpers."""
    pure = {
        "upload_ratelimit",
        "backup_environment",
        "remote_command_options",
        "prepare_env",
        "ssh_repository_url",
        "ssh_repository_directory",
        "remote_path_env",
    }
    return sorted(
        name
        for name, member in inspect.getmembers(BorgRouter, inspect.isfunction)
        if not name.startswith("_")
        and not name.startswith("build_")
        and name not in pure
    )


def test_the_guard_walks_every_method_that_runs_borg():
    # A new method that runs Borg joins the walk by default; one this list
    # drops is a deliberate decision, made here.
    assert _borg_methods() == [
        "break_lock",
        "check",
        "compact",
        "delete_archive",
        "diff_archives",
        "export_keyfile",
        "initialize_repository",
        "list_archive_contents",
        "list_archive_lines",
        "list_archives",
        "list_archives_checked",
        "preview_restore",
        "prune",
        "run_wipe_compact",
        "run_wipe_delete",
        "validate_local_repository_access",
        "verify_repository",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("borg_version", [1, 2])
@pytest.mark.parametrize("method", _borg_methods())
async def test_borg_router_never_runs_borg_on_the_server_for_an_agent_repository(
    server_borg, monkeypatch, method, borg_version
):
    from app.core import borg_router

    # The refusal of a method that has no agent path yet.
    refused = getattr(borg_router, "ServerBorgRefused", ())
    repo = SimpleNamespace(
        id=41,
        name="repo",
        path="/repos/repo",
        borg_version=borg_version,
        executor_type="agent",
        execution_target="agent",
        agent_machine_id=7,
        passphrase="secret",
        remote_path=None,
        bypass_lock=False,
        encryption="none",
        connection_id=None,
        repository_type="local",
    )
    delegated = []

    async def agent(self, **kwargs):
        delegated.append(kwargs.get("job_kind"))
        return {"success": True}

    for helper in (
        "_run_agent_maintenance",
        "_run_agent_break_lock",
        "_run_agent_repository_probe",
    ):
        monkeypatch.setattr(BorgRouter, helper, agent)

    router = BorgRouter(repo)
    bound = getattr(router, method)
    arguments = {
        name: _argument(name)
        for name, parameter in inspect.signature(bound).parameters.items()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    try:
        await _drive(bound(**arguments))
    except refused:
        pass
    except OSError:
        pass  # the recorder's: the command line is what this test reads
    assert server_borg == []
