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
    assert job.payload["operation"] == {
        "archive": "aid:b",
        "predecessor": "aid:a",
        "timeout_seconds": 3600.0,
    }
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
    assert job.payload["operation"] == {
        "archive": "aid:b",
        "predecessor": None,
        "timeout_seconds": 3600.0,
    }
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


@pytest.mark.unit
@pytest.mark.parametrize("pad_every", [0.2, 0.01])
async def test_a_listing_past_its_budget_is_ended_here_when_the_agent_does_not(
    db_session, dispatch, quick_polls, pad_every
):
    # The agent ends borg at the budget itself; this is the agent whose
    # report never comes: it pads on, so the idle bound never fires. Padding
    # slower than the reader's poll and faster than it: the deadline is
    # checked between arrivals and on them.
    repo = _agent_repository(db_session)
    stream = _stream(
        db_session,
        repo,
        first_byte_timeout=0.1,
        idle_timeout=30,
        verdict_timeout=0.1,
        max_seconds=0.3,
    )

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        assert await agent_artifact_relay.push(job_id, b'{"path": "a"}\n') is True
        while agent_artifact_relay.is_registered(job_id):
            if not await agent_artifact_relay.push(job_id, b"\n"):
                break
            await asyncio.sleep(pad_every)

    producer = asyncio.create_task(agent())
    lines = []
    with pytest.raises(RuntimeError, match="did not report the change listing ended"):
        async for line in stream:
            lines.append(line)
    await producer

    assert lines == ['{"path": "a"}']
    db_session.expire_all()
    assert db_session.get(AgentJob, stream.job_id).status == "cancel_requested"
    dispatch[1].assert_awaited_once()
    assert not agent_artifact_relay.is_registered(stream.job_id)


@pytest.mark.unit
async def test_the_buffer_ahead_of_the_parser_is_bounded_and_the_end_still_confirmed(
    db_session, dispatch
):
    repo = _agent_repository(db_session)
    line = b'{"path": "' + b"x" * 40 + b'"}\n'
    stream = _stream(db_session, repo, buffer_bytes=len(line) * 2)
    pushed = asyncio.Event()
    checked = asyncio.Event()

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        # twelve lines fit the relay's sixteen slots, so no push waits
        for _ in range(12):
            assert await agent_artifact_relay.push(job_id, line) is True
        pushed.set()
        # the upload stays open while the buffer is looked at: a closed
        # one lets the drain take the tail
        await checked.wait()
        assert await agent_artifact_relay.close(job_id, confirm_timeout=2) is True
        _set_status(
            db_session,
            job_id,
            "completed",
            result={"return_code": 0, "artifact": True},
        )

    producer = asyncio.create_task(agent())
    reader = stream.__aiter__()
    lines = [await reader.__anext__()]
    await pushed.wait()
    await _buffer_full(stream, len(line) * 2)
    # the parser holds two lines, the drain one it waits to place, the
    # relay the rest: the listing is not pulled into memory ahead of use
    assert stream._buffered == len(line) * 2
    assert agent_artifact_relay._channels[stream.job_id].queue.qsize() >= 8
    checked.set()
    async for text in reader:
        lines.append(text)
    await producer

    assert len(lines) == 12
    assert stream.return_code == 0


async def _buffer_full(stream, size, timeout=2.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while stream._buffered < size:
        assert loop.time() < deadline, "the drain never filled the buffer"
        await asyncio.sleep(0.01)


@pytest.mark.unit
async def test_the_end_marker_is_confirmed_however_far_the_parser_is_behind(
    db_session, dispatch
):
    repo = _agent_repository(db_session)
    line = b'{"path": "' + b"x" * 40 + b'"}\n'
    stream = _stream(db_session, repo, buffer_bytes=len(line) * 2)
    confirmed = asyncio.Event()

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        for _ in range(6):
            assert await agent_artifact_relay.push(job_id, line) is True
        # the parser has taken one line and holds two; the close is
        # confirmed before it takes anything more
        assert await agent_artifact_relay.close(job_id, confirm_timeout=2) is True
        confirmed.set()
        _set_status(
            db_session,
            job_id,
            "completed",
            result={"return_code": 0, "artifact": True},
        )

    producer = asyncio.create_task(agent())
    reader = stream.__aiter__()
    lines = [await reader.__anext__()]
    await _buffer_full(stream, len(line) * 2)
    await asyncio.wait_for(confirmed.wait(), 3)
    async for text in reader:
        lines.append(text)
    await producer

    assert len(lines) == 6
    assert stream.return_code == 0


@pytest.mark.unit
async def test_stopping_a_stream_with_a_full_buffer_frees_the_blocked_upload(
    db_session, dispatch
):
    repo = _agent_repository(db_session)
    line = b'{"path": "' + b"x" * 40 + b'"}\n'
    stream = _stream(db_session, repo, buffer_bytes=len(line) * 2)
    results: list = []

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        # one line is read, two are buffered, one is in the drain's hand,
        # sixteen fill the relay's queue: the twenty-first push blocks
        for _ in range(21):
            results.append(await agent_artifact_relay.push(job_id, line))

    producer = asyncio.create_task(agent())
    reader = stream.__aiter__()
    await reader.__anext__()
    await _buffer_full(stream, len(line) * 2)
    await asyncio.sleep(0.05)
    assert len(results) == 20 and all(results)

    await stream.close()

    # the blocked push returns at once, refused: the consumer is gone
    await asyncio.wait_for(producer, 2)
    assert results[-1] is False
    assert not agent_artifact_relay.is_registered(stream.job_id)
    db_session.expire_all()
    assert db_session.get(AgentJob, stream.job_id).status == "cancel_requested"


@pytest.mark.unit
async def test_the_tail_of_a_closed_upload_is_read_out_however_late(
    db_session, dispatch, quick_polls
):
    repo = _agent_repository(db_session)
    stream = _stream(
        db_session,
        repo,
        first_byte_timeout=0.1,
        idle_timeout=30,
        verdict_timeout=0.1,
        max_seconds=0.1,
    )
    closed = asyncio.Event()

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        for path in ("a", "b", "c"):
            assert await agent_artifact_relay.push(
                job_id, f'{{"path": "{path}"}}\n'.encode()
            )
        assert await agent_artifact_relay.close(job_id, confirm_timeout=2) is True
        _set_status(
            db_session,
            job_id,
            "completed",
            result={"return_code": 0, "artifact": True},
        )
        closed.set()

    producer = asyncio.create_task(agent())
    reader = stream.__aiter__()
    lines = [await reader.__anext__()]
    # the upload ended, the reader is slow: well past the budget now
    await asyncio.wait_for(closed.wait(), 3)
    await asyncio.sleep(0.5)
    async for text in reader:
        lines.append(text)
    await producer

    assert lines == ['{"path": "a"}', '{"path": "b"}', '{"path": "c"}']
    assert stream.return_code == 0


@pytest.mark.unit
async def test_a_cancellation_is_honoured_under_fast_padding(
    db_session, dispatch, quick_polls
):
    """Padding faster than the reader's poll: every read returns a chunk, so
    the check must run on arrivals too, not only when nothing came."""
    from app.services.operations.executors.agent_changes import OperationCancelled

    repo = _agent_repository(db_session)
    requested = {"cancel": False}
    stream = _stream(
        db_session, repo, idle_timeout=30, cancelled=lambda: requested["cancel"]
    )

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        for _ in range(10):
            assert await agent_artifact_relay.push(job_id, b"\n") is True
            await asyncio.sleep(0.01)
        requested["cancel"] = True
        while agent_artifact_relay.is_registered(job_id):
            if not await agent_artifact_relay.push(job_id, b"\n"):
                break
            await asyncio.sleep(0.01)

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
async def test_a_job_that_fails_under_fast_padding_ends_the_stream_early(
    db_session, dispatch, quick_polls
):
    """The job row turns failed while padding keeps arriving: the status is
    read on arrivals too, so the stream ends with the job's reason and does
    not read padding until the deadline."""
    repo = _agent_repository(db_session)
    stream = _stream(db_session, repo, idle_timeout=30)

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        for _ in range(5):
            assert await agent_artifact_relay.push(job_id, b"\n") is True
            await asyncio.sleep(0.01)
        _set_status(
            db_session,
            job_id,
            "failed",
            result={"return_code": 2},
            error_message="borg diff: Repository lock could not be acquired",
        )
        while agent_artifact_relay.is_registered(job_id):
            if not await agent_artifact_relay.push(job_id, b"\n"):
                break
            await asyncio.sleep(0.01)

    producer = asyncio.create_task(agent())
    loop = asyncio.get_running_loop()
    started = loop.time()
    assert [line async for line in stream] == []
    await producer

    assert loop.time() - started < 5
    assert stream.return_code == -1
    assert "lock could not be acquired" in stream.stderr
    assert not agent_artifact_relay.is_registered(stream.job_id)


@pytest.mark.unit
async def test_the_verdict_wait_ends_at_the_listings_absolute_deadline(
    db_session, dispatch, quick_polls
):
    """An upload that ends just before the absolute deadline does not buy
    the job a whole verdict window on top of it."""
    repo = _agent_repository(db_session)
    stream = _stream(
        db_session,
        repo,
        first_byte_timeout=0.1,
        idle_timeout=30,
        verdict_timeout=3,
        max_seconds=0.1,
    )

    async def agent():
        job_id = await _job_of(stream)
        _set_status(db_session, job_id, "running")
        assert await agent_artifact_relay.push(job_id, b'{"path": "a"}\n') is True
        await asyncio.sleep(2.5)
        assert await agent_artifact_relay.close(job_id, confirm_timeout=2) is True
        # no verdict ever

    producer = asyncio.create_task(agent())
    loop = asyncio.get_running_loop()
    started = loop.time()
    lines = [line async for line in stream]
    await producer

    # absolute deadline 3.2 s after queueing; a fresh window would run to ~5.5 s
    assert loop.time() - started < 4.5
    assert lines == ['{"path": "a"}']
    assert stream.return_code == -1
    assert "did not report" in stream.stderr
    db_session.expire_all()
    assert db_session.get(AgentJob, stream.job_id).status == "cancel_requested"
