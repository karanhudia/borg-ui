"""AgentChangeStream: an agent's `repository.diff` job read like the
server's own listing stream (#1052). The agent side is simulated by pushing
into the real artifact relay and writing the job's verdict."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.database.models import AgentJob, AgentMachine, Repository
from app.services.agent_artifact_relay import agent_artifact_relay
from app.services.operations.executors import agent_changes
from app.services.operations.executors.agent_changes import (
    AgentChangeStream,
    AgentUnavailable,
)
from app.services.operations.runner import REPOSITORY_BUSY_KEY, repository_busy


@pytest.fixture()
def dispatch():
    with (
        patch(
            "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
            AsyncMock(return_value=True),
        ) as queued,
        patch(
            "app.services.agent_job_dispatcher.dispatch_agent_cancel_if_connected",
            AsyncMock(return_value=True),
        ) as cancelled,
    ):
        yield queued, cancelled


def _agent_repository(db):
    machine = AgentMachine(
        name="agent",
        agent_id="agt_changes",
        token_hash="x",
        token_prefix="x",
        status="online",
        capabilities=["repository.diff"],
    )
    db.add(machine)
    db.flush()
    repo = Repository(
        name="agent-repo",
        path="/repos/agent",
        encryption="none",
        repository_type="local",
        executor_type="agent",
        execution_target="agent",
        agent_machine_id=machine.id,
    )
    db.add(repo)
    db.commit()
    return repo


def _stream(db, repo, predecessor="aid:a", **timeouts):
    bounds = {"first_byte_timeout": 2, "idle_timeout": 2, "verdict_timeout": 2}
    bounds.update(timeouts)
    return AgentChangeStream(db, repo, "aid:b", predecessor, **bounds)


async def _job_of(stream):
    while stream.job_id is None or not agent_artifact_relay.is_registered(
        stream.job_id
    ):
        await asyncio.sleep(0.01)
    return stream.job_id


def _set_status(db, job_id, status, result=None, error_message=None, started=None):
    from datetime import datetime, timezone

    job = db.get(AgentJob, job_id)
    job.status = status
    job.result = result
    job.error_message = error_message
    if started is None:
        # an agent worker reports its start before it runs or fails a job
        started = status in (
            "running",
            "completed",
            "completed_with_warnings",
            "failed",
        )
    if started and job.started_at is None:
        job.started_at = datetime.now(timezone.utc)
    db.commit()


@pytest.mark.unit
async def test_lines_arrive_whole_across_chunks_and_the_verdict_is_read(
    db_session, dispatch
):
    repo = _agent_repository(db_session)
    stream = _stream(db_session, repo)

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        # a record split across chunks, the padding line, a last line
        # without its newline
        for chunk in (b'{"path": "a"}\n{"pa', b'th": "b"}\n', b"\n", b'{"path": "c"}'):
            assert await agent_artifact_relay.push(job_id, chunk) is True
        assert await agent_artifact_relay.close(job_id, confirm_timeout=1) is True
        _set_status(
            db_session,
            job_id,
            "completed_with_warnings",
            result={"return_code": 1, "artifact": True},
        )

    producer = asyncio.create_task(agent())
    lines = [line async for line in stream]
    await producer

    assert lines == ['{"path": "a"}', '{"path": "b"}', '{"path": "c"}']
    assert stream.return_code == 1
    job = db_session.get(AgentJob, stream.job_id)
    assert job.payload["job_kind"] == "repository.diff"
    assert job.payload["operation"] == {"archive": "aid:b", "predecessor": "aid:a"}
    assert not agent_artifact_relay.is_registered(stream.job_id)
    dispatch[1].assert_not_awaited()


@pytest.mark.unit
async def test_a_warning_verdict_reads_as_rc_1_whatever_borg_exited_with(
    db_session, dispatch
):
    """The agent completes a listing on Borg's modern warning codes too; in
    the stream contract that is rc 1, the code the history index accepts."""
    repo = _agent_repository(db_session)
    stream = _stream(db_session, repo)

    async def agent():
        job_id = await _job_of(stream)
        assert await agent_artifact_relay.close(job_id, confirm_timeout=1) is True
        _set_status(
            db_session,
            job_id,
            "completed_with_warnings",
            result={"return_code": 105, "artifact": True},
        )

    producer = asyncio.create_task(agent())
    assert [line async for line in stream] == []
    await producer
    assert stream.return_code == 1


@pytest.mark.unit
async def test_the_first_archive_of_a_series_asks_for_the_full_listing(
    db_session, dispatch
):
    repo = _agent_repository(db_session)
    stream = _stream(db_session, repo, predecessor=None)

    async def agent():
        job_id = await _job_of(stream)
        assert await agent_artifact_relay.close(job_id, confirm_timeout=1) is True
        _set_status(db_session, job_id, "completed", result={"return_code": 0})

    producer = asyncio.create_task(agent())
    assert [line async for line in stream] == []
    await producer
    job = db_session.get(AgentJob, stream.job_id)
    # the key is sent: `null` is the full listing, a missing key is refused
    assert job.payload["operation"] == {"archive": "aid:b", "predecessor": None}
    assert stream.return_code == 0


@pytest.mark.unit
async def test_a_failed_job_reports_its_reason(db_session, dispatch):
    repo = _agent_repository(db_session)
    stream = _stream(db_session, repo)

    async def agent():
        job_id = await _job_of(stream)
        assert await agent_artifact_relay.close(job_id, confirm_timeout=1) is True
        _set_status(
            db_session,
            job_id,
            "failed",
            error_message="repository.diff exited with code 2",
        )

    producer = asyncio.create_task(agent())
    assert [line async for line in stream] == []
    await producer
    assert stream.return_code == -1
    assert "exited with code 2" in stream.stderr


@pytest.fixture()
def quick_polls(monkeypatch):
    monkeypatch.setattr(agent_changes, "CHUNK_POLL_SECONDS", 0.05)
    monkeypatch.setattr(agent_changes, "JOB_POLL_SECONDS", 0.05)


@pytest.mark.unit
async def test_a_cancellation_is_honoured_while_the_diff_is_silent(
    db_session, dispatch, quick_polls
):
    """A diff of unchanged paths sends only padding, which yields no line,
    so the caller's per-line cancellation check never runs: the stream asks
    itself, ends the read and stops the agent's job."""
    from app.services.operations.executors.agent_changes import OperationCancelled

    repo = _agent_repository(db_session)
    requested = {"cancel": False}
    stream = _stream(
        db_session, repo, idle_timeout=30, cancelled=lambda: requested["cancel"]
    )

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        for _ in range(3):
            assert await agent_artifact_relay.push(job_id, b"\n") is True
            await asyncio.sleep(0.05)
        requested["cancel"] = True

    producer = asyncio.create_task(agent())
    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(OperationCancelled):
        async for _ in stream:
            pass
    await producer

    assert loop.time() - started < 5
    assert not agent_artifact_relay.is_registered(stream.job_id)
    db_session.expire_all()
    assert db_session.get(AgentJob, stream.job_id).status == "cancel_requested"
    dispatch[1].assert_awaited_once()


@pytest.mark.unit
async def test_a_job_that_fails_before_its_upload_ends_the_stream_early(
    db_session, dispatch, quick_polls
):
    """The agent could not start borg and failed the job without uploading:
    nothing more will arrive, so the stream ends with the job's reason
    instead of waiting out the first-byte bound."""
    repo = _agent_repository(db_session)
    stream = _stream(db_session, repo, first_byte_timeout=30)

    async def agent():
        job_id = await _job_of(stream)
        _set_status(
            db_session,
            job_id,
            "failed",
            result={"return_code": 1},
            error_message="Failed to start repository.diff: No such file",
        )

    producer = asyncio.create_task(agent())
    loop = asyncio.get_running_loop()
    started = loop.time()
    assert [line async for line in stream] == []
    await producer

    assert loop.time() - started < 5
    # never a warning code for a failed job, whatever borg's rc was
    assert stream.return_code == -1
    assert "Failed to start" in stream.stderr
    assert not agent_artifact_relay.is_registered(stream.job_id)


@pytest.mark.unit
async def test_a_failed_job_with_a_warning_code_is_not_a_complete_listing(
    db_session, dispatch
):
    """A warning exit whose delivery was refused fails the job with rc 1;
    the stream must not hand that rc on, or the history run would take the
    output it got for a complete listing."""
    repo = _agent_repository(db_session)
    stream = _stream(db_session, repo)

    async def agent():
        job_id = await _job_of(stream)
        assert await agent_artifact_relay.close(job_id, confirm_timeout=1) is True
        _set_status(
            db_session,
            job_id,
            "failed",
            result={"return_code": 1},
            error_message="repository.diff artifact not delivered",
        )

    producer = asyncio.create_task(agent())
    assert [line async for line in stream] == []
    await producer
    assert stream.return_code == -1


@pytest.mark.unit
async def test_a_claimed_job_that_never_started_is_agent_unavailable(
    db_session, dispatch
):
    """The dispatcher marks a job `claimed` before it sends the command; a
    command lost on a broken connection leaves it claimed with no start. No
    agent works on it, so it must not spend the archive's retry."""
    repo = _agent_repository(db_session)
    stream = _stream(db_session, repo, first_byte_timeout=0.2)

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "claimed")

    producer = asyncio.create_task(agent())
    with pytest.raises(AgentUnavailable):
        async for _ in stream:
            pass
    await producer
    db_session.expire_all()
    assert db_session.get(AgentJob, stream.job_id).status == "cancel_requested"


@pytest.mark.unit
async def test_a_cancellation_is_honoured_while_the_verdict_is_awaited(
    db_session, dispatch
):
    """The output arrived but the agent's completion report did not: a cancel
    in that phase ends the read at once instead of after the verdict bound,
    which would record a failure."""
    from app.services.operations.executors.agent_changes import OperationCancelled

    repo = _agent_repository(db_session)
    requested = {"cancel": False}
    stream = _stream(
        db_session, repo, verdict_timeout=30, cancelled=lambda: requested["cancel"]
    )

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        assert await agent_artifact_relay.close(job_id, confirm_timeout=1) is True
        requested["cancel"] = True

    producer = asyncio.create_task(agent())
    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(OperationCancelled):
        async for _ in stream:
            pass
    await producer
    assert loop.time() - started < 5
    db_session.expire_all()
    assert db_session.get(AgentJob, stream.job_id).status == "cancel_requested"


@pytest.mark.unit
async def test_a_job_insert_failure_never_carries_the_secrets(db_session, dispatch):
    """A statement error renders its parameters, and the job's payload holds
    the repository passphrase: the history run logs the error it gets."""
    from sqlalchemy.exc import IntegrityError

    repo = _agent_repository(db_session)
    insert_failed = IntegrityError(
        "INSERT INTO agent_jobs (payload) VALUES (?)",
        {"payload": '{"secrets": {"BORG_PASSPHRASE": {"value": "hunter2"}}}'},
        Exception("database is locked"),
    )
    assert "hunter2" in str(insert_failed)
    with patch.object(
        agent_changes, "queue_agent_repository_operation_job", side_effect=insert_failed
    ):
        with pytest.raises(RuntimeError) as failed:
            async for _ in _stream(db_session, repo):
                pass
    assert "hunter2" not in str(failed.value)
    assert "database is locked" in str(failed.value)
    assert failed.value.__cause__ is None and failed.value.__suppress_context__


@pytest.mark.unit
async def test_a_line_without_end_is_bounded_like_the_server_stream(
    db_session, dispatch, monkeypatch
):
    """Output with no newline must not grow on the server unchecked: past the
    server stream's line limit the attempt fails and the job is stopped."""
    monkeypatch.setattr(agent_changes, "LINE_LIMIT", 16)
    repo = _agent_repository(db_session)
    stream = _stream(db_session, repo)

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        assert await agent_artifact_relay.push(job_id, b"x" * 40) is True

    producer = asyncio.create_task(agent())
    with pytest.raises(RuntimeError, match="longer than 16 bytes"):
        async for _ in stream:
            pass
    await producer
    assert not agent_artifact_relay.is_registered(stream.job_id)
    db_session.expire_all()
    assert db_session.get(AgentJob, stream.job_id).status == "cancel_requested"


@pytest.mark.unit
async def test_a_complete_line_past_the_limit_is_refused_too(
    db_session, dispatch, monkeypatch
):
    """The bound holds whether the newline arrives with the record or later."""
    monkeypatch.setattr(agent_changes, "LINE_LIMIT", 16)
    repo = _agent_repository(db_session)
    stream = _stream(db_session, repo)

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        assert await agent_artifact_relay.push(job_id, b"x" * 40 + b"\n") is True

    producer = asyncio.create_task(agent())
    seen = []
    with pytest.raises(RuntimeError, match="longer than 16 bytes"):
        async for line in stream:
            seen.append(line)
    await producer
    assert seen == []


@pytest.mark.unit
async def test_a_job_no_agent_takes_is_agent_unavailable(db_session, dispatch):
    """Not the archive's fault: the history run keeps the archive's retry
    budget. The job is cancelled so it does not block the repository."""
    repo = _agent_repository(db_session)
    stream = _stream(db_session, repo, first_byte_timeout=0.1)

    with pytest.raises(AgentUnavailable):
        async for _ in stream:
            pass

    assert db_session.get(AgentJob, stream.job_id).status == "canceled"
    assert not agent_artifact_relay.is_registered(stream.job_id)


@pytest.mark.unit
async def test_a_claimed_job_that_stalls_fails_and_is_asked_to_stop(
    db_session, dispatch
):
    repo = _agent_repository(db_session)
    stream = _stream(db_session, repo, first_byte_timeout=0.2)

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")

    producer = asyncio.create_task(agent())
    with pytest.raises(RuntimeError, match="stalled"):
        async for _ in stream:
            pass
    await producer

    db_session.expire_all()
    assert db_session.get(AgentJob, stream.job_id).status == "cancel_requested"
    dispatch[1].assert_awaited_once()


@pytest.mark.unit
async def test_an_upload_that_breaks_fails_the_stream(db_session, dispatch):
    repo = _agent_repository(db_session)
    stream = _stream(db_session, repo)

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        assert await agent_artifact_relay.push(job_id, b'{"path": "a"}\n') is True
        await agent_artifact_relay.close(job_id, error="connection reset")

    producer = asyncio.create_task(agent())
    seen = []
    with pytest.raises(RuntimeError, match="connection reset"):
        async for line in stream:
            seen.append(line)
    await producer
    assert seen == ['{"path": "a"}']
    db_session.expire_all()
    assert db_session.get(AgentJob, stream.job_id).status == "cancel_requested"


@pytest.mark.unit
async def test_close_stops_reading_and_cancels_the_job(db_session, dispatch):
    repo = _agent_repository(db_session)
    stream = _stream(db_session, repo)

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        await agent_artifact_relay.push(job_id, b'{"path": "a"}\n')

    producer = asyncio.create_task(agent())
    lines = stream.__aiter__()
    assert await lines.__anext__() == '{"path": "a"}'
    await producer
    await stream.close()
    await stream.close()  # safe twice
    await lines.aclose()

    assert stream.return_code == -1
    assert not agent_artifact_relay.is_registered(stream.job_id)
    db_session.expire_all()
    assert db_session.get(AgentJob, stream.job_id).status == "cancel_requested"
    dispatch[1].assert_awaited_once()
    # a consumer that left is refused, so the agent ends borg
    assert await agent_artifact_relay.push(stream.job_id, b"x") is False


@pytest.mark.unit
async def test_a_missing_verdict_fails_the_stream_and_stops_the_job(
    db_session, dispatch
):
    repo = _agent_repository(db_session)
    stream = _stream(db_session, repo, verdict_timeout=0.2)

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        assert await agent_artifact_relay.close(job_id, confirm_timeout=1) is True

    producer = asyncio.create_task(agent())
    assert [line async for line in stream] == []
    await producer
    assert stream.return_code == -1
    assert "did not report" in stream.stderr
    db_session.expire_all()
    assert db_session.get(AgentJob, stream.job_id).status == "cancel_requested"


@pytest.mark.unit
async def test_a_busy_repository_reaches_the_runner_and_other_refusals_do_not(
    db_session, dispatch
):
    """The admission's busy 409 is the runner's to defer; any other refusal
    (agent disabled, capability gone) is the agent being unavailable."""
    repo = _agent_repository(db_session)
    busy = HTTPException(status_code=409, detail={"key": REPOSITORY_BUSY_KEY})
    with patch.object(
        agent_changes, "queue_agent_repository_operation_job", side_effect=busy
    ):
        with pytest.raises(HTTPException) as refused:
            async for _ in _stream(db_session, repo):
                pass
    assert repository_busy(refused.value)

    disabled = HTTPException(
        status_code=409, detail={"key": "backend.errors.agents.agentNotQueueable"}
    )
    with patch.object(
        agent_changes, "queue_agent_repository_operation_job", side_effect=disabled
    ):
        with pytest.raises(AgentUnavailable):
            async for _ in _stream(db_session, repo):
                pass
