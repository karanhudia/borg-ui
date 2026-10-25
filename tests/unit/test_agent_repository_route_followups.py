"""#1422, #1423, #1424: agent repository routes behave as their server paths.

- #1422: the v2 archive info lists an agent archive's files without the
  agent's line cap and stands without them when the listing fails.
- #1423: an unnamed manual Borg 2 backup on the agent path is the
  `manual-backup` series, as on the server.
- #1424: a streamed file download that ends without the file takes its
  agent job back; a running agent is told to stop (the streamed tar
  download too).
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.database.models import AgentJob, Operation
from app.services.operations.backup_facade import BackupJobFacade
from tests.unit.test_agent_repository_server_borg import (
    ARCHIVE_ID,
    _agent,
    _agent_jobs,
    _completed,
    _enable_borg_v2,
    _repo,
    server_borg,  # noqa: F401 - fixture
)

# -- #1422: v2 archive info with include_files -----------------------------------


@pytest.mark.unit
class TestV2ArchiveInfoFiles:
    def _info(self, test_client, admin_headers, repo, *answers, **params):
        info = _completed(json.dumps({"archives": [{"name": "a", "id": ARCHIVE_ID}]}))
        with (
            patch(
                "app.api.v2.archives.dispatch_agent_job_best_effort", new=AsyncMock()
            ),
            patch(
                "app.api.v2.archives.wait_for_agent_repository_operation_job",
                new=AsyncMock(side_effect=[info, *answers]),
            ),
        ):
            return test_client.get(
                f"/api/v2/archives/{ARCHIVE_ID}/info",
                params={"repository": str(repo.id), "include_files": True, **params},
                headers=admin_headers,
            )

    def test_files_are_cut_at_the_limit_on_the_server(
        self,
        test_client,
        admin_headers,
        test_db,
        server_borg,  # noqa: F811
    ):
        _enable_borg_v2(test_db)
        repo = _repo(test_db, _agent(test_db))
        listing = _completed(
            '{"path": "data/one"}\n{"path": "data/two"}\n{"path": "data/3"}'
        )

        response = self._info(test_client, admin_headers, repo, listing, file_limit=2)

        assert server_borg == []
        assert response.status_code == 200, response.text
        body = response.json()["info"]
        assert [f["path"] for f in body["files"]] == ["data/one", "data/two"]
        assert body["file_count"] == 2
        (job,) = _agent_jobs(test_db, "repository.list_archive_contents")
        assert job.payload["operation"]["archive"] == f"aid:{ARCHIVE_ID}"
        # no line cap on the agent: it ends a listing past its cap as a failure
        assert "max_lines" not in job.payload["operation"]

    def test_info_stands_without_a_failed_file_listing(
        self,
        test_client,
        admin_headers,
        test_db,
        server_borg,  # noqa: F811
    ):
        _enable_borg_v2(test_db)
        repo = _repo(test_db, _agent(test_db))
        failed = HTTPException(
            status_code=502,
            detail={"key": "backend.errors.agents.jobFailed", "params": {}},
        )

        response = self._info(test_client, admin_headers, repo, failed)

        assert server_borg == []
        assert response.status_code == 200, response.text
        body = response.json()["info"]
        assert body["name"] == "a"
        assert body["files"] == []
        assert body["file_count"] == 0


# -- #1423: manual Borg 2 backup archive name ------------------------------------


@pytest.mark.unit
class TestManualAgentBackupName:
    def _queue(self, test_client, admin_headers, test_db, repo):
        from app.services.repository_executor import queue_agent_backup_job

        response = test_client.post(
            "/api/backup/start",
            json={"repository": repo.path},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        operation = test_db.get(Operation, response.json()["job_id"])
        assert operation.params["executor"] == "agent"
        job = BackupJobFacade(test_db, operation)
        agent_job = queue_agent_backup_job(test_db, job, repo)
        test_db.commit()
        return job, agent_job

    def test_borg2_is_the_manual_backup_series(
        self, test_client, admin_headers, test_db
    ):
        repo = _repo(test_db, _agent(test_db), borg_version=2)

        job, agent_job = self._queue(test_client, admin_headers, test_db, repo)

        # one series, as on the server, so the prune rules apply to it
        assert job.archive_name == "manual-backup"
        assert agent_job.payload["backup"]["archive_name"] == "manual-backup"

    def test_borg1_keeps_timestamped_names(self, test_client, admin_headers, test_db):
        repo = _repo(test_db, _agent(test_db), borg_version=1)

        job, agent_job = self._queue(test_client, admin_headers, test_db, repo)

        # archive names are unique in a Borg 1 repository
        assert job.archive_name.startswith("manual-backup-")
        assert agent_job.payload["backup"]["archive_name"] == job.archive_name

    def test_a_given_name_is_kept(self, test_client, admin_headers, test_db):
        from app.services.repository_executor import queue_agent_backup_job

        repo = _repo(test_db, _agent(test_db), borg_version=2)
        job, _ = self._queue(test_client, admin_headers, test_db, repo)
        _agent_jobs(test_db)[0].status = "completed"
        test_db.commit()

        agent_job = queue_agent_backup_job(
            test_db, job, repo, archive_name="nightly-{now}"
        )

        assert agent_job.payload["backup"]["archive_name"] == "nightly-{now}"


# -- #1424: streamed agent file download -----------------------------------------


def _streaming_agent(db):
    agent = _agent(db)
    agent.capabilities = [*agent.capabilities, "artifact.upload"]
    db.commit()
    return agent


@pytest.mark.unit
@pytest.mark.asyncio
class TestStreamedAgentFileDownload:
    async def test_a_first_byte_timeout_takes_the_queued_job_back(self, test_db):
        from app.api.archives import _stream_agent_archive_file
        from app.services.agent_artifact_relay import agent_artifact_relay

        repo = _repo(test_db, _streaming_agent(test_db))

        with (
            patch("app.api.archives.dispatch_agent_job_best_effort", new=AsyncMock()),
            patch("app.api.archives.AGENT_ARTIFACT_FIRST_BYTE_TIMEOUT", 0.01),
            patch(
                "app.api.archives.dispatch_agent_cancel_if_connected", new=AsyncMock()
            ) as send_cancel,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await _stream_agent_archive_file(
                    test_db, repo, f"aid:{ARCHIVE_ID}", "data/hello.txt"
                )

        assert exc_info.value.status_code == 504
        (job,) = _agent_jobs(test_db, "repository.extract_archive_file")
        # unclaimed: cancelled, so it no longer counts as the repository's work
        assert job.status == "canceled"
        assert not agent_artifact_relay.is_registered(job.id)
        send_cancel.assert_not_awaited()

    async def test_a_producer_error_takes_the_running_job_back(self, test_db):
        from app.api.archives import _stream_agent_archive_file
        from app.services.agent_artifact_relay import agent_artifact_relay

        repo = _repo(test_db, _streaming_agent(test_db))

        async def agent_fails(db, agent_job, **_kwargs):
            agent_job.status = "running"
            db.commit()

            async def close_with_error():
                await agent_artifact_relay.close(agent_job.id, error="extract failed")

            asyncio.get_running_loop().create_task(close_with_error())

        with (
            patch(
                "app.api.archives.dispatch_agent_job_best_effort",
                new=AsyncMock(side_effect=agent_fails),
            ),
            patch(
                "app.api.archives.dispatch_agent_cancel_if_connected", new=AsyncMock()
            ) as send_cancel,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await _stream_agent_archive_file(
                    test_db, repo, f"aid:{ARCHIVE_ID}", "data/hello.txt"
                )

        assert exc_info.value.status_code == 502
        (job,) = _agent_jobs(test_db, "repository.extract_archive_file")
        # running: the agent is told to stop
        assert job.status == "cancel_requested"
        assert send_cancel.await_args.args[0].id == job.id

    async def test_a_client_that_goes_away_takes_the_job_back(self, test_db):
        from app.api.archives import _stream_agent_archive_file
        from app.services.agent_artifact_relay import agent_artifact_relay

        repo = _repo(test_db, _streaming_agent(test_db))

        async def agent_sends(db, agent_job, **_kwargs):
            agent_job.status = "running"
            db.commit()
            await agent_artifact_relay.push(agent_job.id, b"first")

        with (
            patch(
                "app.api.archives.dispatch_agent_job_best_effort",
                new=AsyncMock(side_effect=agent_sends),
            ),
            patch(
                "app.api.archives.dispatch_agent_cancel_if_connected", new=AsyncMock()
            ) as send_cancel,
        ):
            response = await _stream_agent_archive_file(
                test_db, repo, f"aid:{ARCHIVE_ID}", "data/hello.txt"
            )
            body = response.body_iterator
            assert await body.__anext__() == b"first"
            # the client disconnects before the rest of the file
            await body.aclose()

        (job,) = _agent_jobs(test_db, "repository.extract_archive_file")
        assert job.status == "cancel_requested"
        assert send_cancel.await_args.args[0].id == job.id
        assert not agent_artifact_relay.is_registered(job.id)
        assert test_db.query(AgentJob).count() == 1

    async def test_a_streamed_tar_tells_the_running_agent_to_stop(self, test_db):
        from app.api.archives import _stream_agent_archive_tar
        from app.services.agent_artifact_relay import agent_artifact_relay

        agent = _streaming_agent(test_db)
        agent.capabilities = [*agent.capabilities, "repository.export_archive_tar"]
        test_db.commit()
        repo = _repo(test_db, agent)

        async def agent_fails(db, agent_job, **_kwargs):
            agent_job.status = "running"
            db.commit()

            async def close_with_error():
                await agent_artifact_relay.close(agent_job.id, error="export failed")

            asyncio.get_running_loop().create_task(close_with_error())

        with (
            patch(
                "app.api.archives.dispatch_agent_job_best_effort",
                new=AsyncMock(side_effect=agent_fails),
            ),
            patch(
                "app.api.archives.dispatch_agent_cancel_if_connected", new=AsyncMock()
            ) as send_cancel,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await _stream_agent_archive_tar(
                    test_db, repo, f"aid:{ARCHIVE_ID}", "/data"
                )

        assert exc_info.value.status_code == 502
        (job,) = _agent_jobs(test_db, "repository.export_archive_tar")
        assert job.status == "cancel_requested"
        assert send_cancel.await_args.args[0].id == job.id

    async def test_a_delivered_file_leaves_the_job_to_its_completion(self, test_db):
        from app.api.archives import _stream_agent_archive_file
        from app.services.agent_artifact_relay import agent_artifact_relay

        repo = _repo(test_db, _streaming_agent(test_db))

        async def agent_sends_all(db, agent_job, **_kwargs):
            agent_job.status = "running"
            db.commit()
            await agent_artifact_relay.push(agent_job.id, b"whole file")

            async def end_of_stream():
                await agent_artifact_relay.close(agent_job.id)

            asyncio.get_running_loop().create_task(end_of_stream())

        with (
            patch(
                "app.api.archives.dispatch_agent_job_best_effort",
                new=AsyncMock(side_effect=agent_sends_all),
            ),
            patch(
                "app.api.archives.dispatch_agent_cancel_if_connected", new=AsyncMock()
            ) as send_cancel,
        ):
            response = await _stream_agent_archive_file(
                test_db, repo, f"aid:{ARCHIVE_ID}", "data/hello.txt"
            )
            chunks = [chunk async for chunk in response.body_iterator]

        assert chunks == [b"whole file"]
        (job,) = _agent_jobs(test_db, "repository.extract_archive_file")
        # the agent reports the completion after the end of the stream
        assert job.status == "running"
        send_cancel.assert_not_awaited()

    async def test_the_cancel_reaches_the_agent_from_a_cancelled_download(
        self, test_db
    ):
        from app.api.archives import _take_back_streamed_agent_job

        repo = _repo(test_db, _streaming_agent(test_db))
        job = AgentJob(
            agent_machine_id=repo.agent_machine_id,
            job_type="repository",
            status="running",
            payload={"job_kind": "repository.extract_archive_file"},
        )
        test_db.add(job)
        test_db.commit()
        sent = asyncio.Event()

        async def send_cancel(_job):
            await asyncio.sleep(0.05)  # the agent's send lock is busy
            sent.set()

        with patch(
            "app.api.archives.dispatch_agent_cancel_if_connected",
            new=AsyncMock(side_effect=send_cancel),
        ):
            # a client disconnect cancels the download while it sends
            take_back = asyncio.create_task(
                _take_back_streamed_agent_job(test_db, job.id)
            )
            await asyncio.sleep(0.01)
            take_back.cancel()
            await asyncio.wait_for(sent.wait(), timeout=1)

        assert sent.is_set()
        test_db.expire_all()
        assert test_db.get(AgentJob, job.id).status == "cancel_requested"

    async def test_a_stalled_cancel_send_does_not_hold_the_answer(self, test_db):
        from app.api.archives import _CANCEL_SEND_TASKS, _take_back_streamed_agent_job

        repo = _repo(test_db, _streaming_agent(test_db))
        job = AgentJob(
            agent_machine_id=repo.agent_machine_id,
            job_type="repository",
            status="running",
            payload={"job_kind": "repository.extract_archive_file"},
        )
        test_db.add(job)
        test_db.commit()
        sent = asyncio.Event()

        async def send_cancel(_job):
            await asyncio.sleep(0.2)  # queued behind a stalled send
            sent.set()

        with (
            patch(
                "app.api.archives.dispatch_agent_cancel_if_connected",
                new=AsyncMock(side_effect=send_cancel),
            ),
            patch("app.api.archives.AGENT_CANCEL_SEND_TIMEOUT", 0.01),
        ):
            await asyncio.wait_for(
                _take_back_streamed_agent_job(test_db, job.id), timeout=0.1
            )
            assert not sent.is_set()
            # the send goes on, held until it is done, and reaches the agent
            assert len(_CANCEL_SEND_TASKS) == 1
            await asyncio.wait_for(sent.wait(), timeout=1)
            await asyncio.sleep(0)
            assert not _CANCEL_SEND_TASKS

    @pytest.mark.parametrize("kind", ["file", "tar"])
    async def test_a_request_cancelled_before_the_first_byte_takes_the_job_back(
        self, test_db, kind
    ):
        from app.api import archives
        from app.services.agent_artifact_relay import agent_artifact_relay

        agent = _streaming_agent(test_db)
        agent.capabilities = [*agent.capabilities, "repository.export_archive_tar"]
        test_db.commit()
        repo = _repo(test_db, agent)
        stream, job_kind, path = {
            "file": (
                archives._stream_agent_archive_file,
                "repository.extract_archive_file",
                "data/hello.txt",
            ),
            "tar": (
                archives._stream_agent_archive_tar,
                "repository.export_archive_tar",
                "/data",
            ),
        }[kind]

        with patch("app.api.archives.dispatch_agent_job_best_effort", new=AsyncMock()):
            download = asyncio.create_task(
                stream(test_db, repo, f"aid:{ARCHIVE_ID}", path)
            )
            await asyncio.sleep(0.05)  # waiting for the first byte
            download.cancel()
            with pytest.raises(asyncio.CancelledError):
                await download

        (job,) = _agent_jobs(test_db, job_kind)
        assert job.status == "canceled"
        assert not agent_artifact_relay.is_registered(job.id)

    @pytest.mark.parametrize("kind", ["file", "tar"])
    async def test_a_request_cancelled_during_the_dispatch_takes_the_job_back(
        self, test_db, kind
    ):
        from app.api import archives
        from app.services.agent_artifact_relay import agent_artifact_relay

        agent = _streaming_agent(test_db)
        agent.capabilities = [*agent.capabilities, "repository.export_archive_tar"]
        test_db.commit()
        repo = _repo(test_db, agent)
        stream, job_kind, path = {
            "file": (
                archives._stream_agent_archive_file,
                "repository.extract_archive_file",
                "data/hello.txt",
            ),
            "tar": (
                archives._stream_agent_archive_tar,
                "repository.export_archive_tar",
                "/data",
            ),
        }[kind]

        async def slow_dispatch(*_args, **_kwargs):
            await asyncio.sleep(10)

        with patch(
            "app.api.archives.dispatch_agent_job_best_effort",
            new=AsyncMock(side_effect=slow_dispatch),
        ):
            download = asyncio.create_task(
                stream(test_db, repo, f"aid:{ARCHIVE_ID}", path)
            )
            await asyncio.sleep(0.05)  # handing the job over
            download.cancel()
            with pytest.raises(asyncio.CancelledError):
                await download

        (job,) = _agent_jobs(test_db, job_kind)
        assert job.status == "canceled"
        assert not agent_artifact_relay.is_registered(job.id)

    @pytest.mark.parametrize("kind", ["file", "tar"])
    async def test_a_client_disconnect_through_the_server_takes_the_job_back(
        self, test_db, kind
    ):
        from starlette.requests import ClientDisconnect

        from app.api import archives
        from app.services.agent_artifact_relay import agent_artifact_relay

        agent = _streaming_agent(test_db)
        agent.capabilities = [*agent.capabilities, "repository.export_archive_tar"]
        test_db.commit()
        repo = _repo(test_db, agent)
        stream, job_kind, path = {
            "file": (
                archives._stream_agent_archive_file,
                "repository.extract_archive_file",
                "data/hello.txt",
            ),
            "tar": (
                archives._stream_agent_archive_tar,
                "repository.export_archive_tar",
                "/data",
            ),
        }[kind]

        async def agent_sends(db, agent_job, **_kwargs):
            agent_job.status = "running"
            db.commit()
            await agent_artifact_relay.push(agent_job.id, b"first")

        sent = []

        async def send(message):
            # the client is gone once the first chunk is on its way
            if message["type"] == "http.response.body" and sent:
                raise OSError("connection reset")
            sent.append(message)

        async def receive():
            await asyncio.sleep(10)

        scope = {"type": "http", "asgi": {"spec_version": "2.4"}}
        with (
            patch(
                "app.api.archives.dispatch_agent_job_best_effort",
                new=AsyncMock(side_effect=agent_sends),
            ),
            patch(
                "app.api.archives.dispatch_agent_cancel_if_connected", new=AsyncMock()
            ) as send_cancel,
        ):
            response = await stream(test_db, repo, f"aid:{ARCHIVE_ID}", path)
            with pytest.raises(ClientDisconnect):
                await response(scope, receive, send)

        (job,) = _agent_jobs(test_db, job_kind)
        assert job.status == "cancel_requested"
        assert send_cancel.await_args.args[0].id == job.id
        assert not agent_artifact_relay.is_registered(job.id)
