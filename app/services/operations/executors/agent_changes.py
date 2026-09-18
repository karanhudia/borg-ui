"""The change listing of a repository a managed agent executes (#1052).

`history_index` reads an archive's changes from a stream with the contract
of `CommandLineStream`: iterate the lines, `close()` to end early, and read
`return_code` and `stderr` once iteration is over. For an agent's
repository the agent runs the listing (`repository.diff`) on its machine
and uploads stdout through the artifact relay; `AgentChangeStream` is that
stream, so the parser, the excludes, size resolution, the cap and the fold
stay the server's and identical for both executors.
"""

import asyncio
from types import SimpleNamespace
from typing import AsyncIterator, Callable, Optional

import structlog
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.borg_stream import LINE_LIMIT
from app.database.models import AgentJob, Repository
from app.services.agent_artifact_relay import agent_artifact_relay
from app.services.operations.maintenance_start import detail_text, failure_text
from app.services.operations.runner import repository_busy
from app.services.repository_executor import (
    AGENT_DIFF_JOB_KIND,
    SUCCESSFUL_AGENT_STATUSES,
    TERMINAL_AGENT_STATUSES,
    _agent_job_failure_message,
    abandon_agent_repository_operation_job,
    queue_agent_repository_operation_job,
)

logger = structlog.get_logger()

# From queueing the job to its first byte: the agent has to take the job,
# borg may wait out a held lock (BORG_LOCK_WAIT), and the agent pads a
# silent listing with a blank line only after 30 s.
AGENT_DIFF_FIRST_BYTE_TIMEOUT = 600.0
# Between two chunks, against the agent's 30 s padding. An agent that
# cannot pad (not posix) and compares unchanged paths for longer than this
# fails the attempt.
AGENT_DIFF_IDLE_TIMEOUT = 300.0
# From the end of the stream to the job's verdict: the agent reports it
# once its upload request has returned.
AGENT_DIFF_VERDICT_TIMEOUT = 60.0
# The listing's absolute budget, sent to the agent in the payload
# (`timeout_seconds`) and held at this end too. Stdout silence says
# nothing about a diff (a line per changed path, nothing while it compares
# unchanged ones) and the agent pads the silence, so a wedged borg and a
# healthy one look the same at both ends; the deadline alone tells them
# apart, and it bounds how long a listing that never ends can hold the
# repository. The agent ends borg at the budget and fails the job with the
# reason; this end stops waiting once the agent has also had its first-byte
# bound to start borg and its verdict bound to report the end. The
# server's own listings run under `borg_stream.MAX_DURATION` (24 h): their
# silence is watched by an idle bound a padded stream cannot have.
AGENT_DIFF_MAX_SECONDS = 3600.0
VERDICT_POLL_SECONDS = 0.25
# While no line arrives (a diff comparing unchanged paths sends only
# padding, which is dropped), how often the stream asks whether the run was
# cancelled, and how often it reads the job's status, so a job that ended
# without its output is noticed long before the idle bound.
CHUNK_POLL_SECONDS = 1.0
JOB_POLL_SECONDS = 5.0
# How much of the listing the server holds ahead of the parser. The relay's
# own queue is 16 chunks; past this the drain waits for the parser and the
# agent's upload blocks, which is the backpressure the relay is built for.
# Small enough that the parser clears it well inside the relay's 5 s
# confirmation of the end marker, which the agent otherwise records as a
# listing not delivered.
AGENT_DIFF_BUFFER_BYTES = 8 * 1024 * 1024

_END = object()
_MISSING = object()


class OperationCancelled(Exception):
    """The history run was cancelled while its listing was being read."""


class AgentUnavailable(Exception):
    """No agent took the job: offline, disabled, or no longer able to run
    it. A fact about the agent, not about the archive, so the history run
    stops without spending the archive's retry budget."""


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").rstrip("\r")


class AgentChangeStream:
    def __init__(
        self,
        db: Session,
        repository: Repository,
        archive: str,
        predecessor: Optional[str],
        *,
        first_byte_timeout: float = AGENT_DIFF_FIRST_BYTE_TIMEOUT,
        idle_timeout: float = AGENT_DIFF_IDLE_TIMEOUT,
        verdict_timeout: float = AGENT_DIFF_VERDICT_TIMEOUT,
        max_seconds: float = AGENT_DIFF_MAX_SECONDS,
        buffer_bytes: int = AGENT_DIFF_BUFFER_BYTES,
        cancelled: Optional[Callable[[], bool]] = None,
    ):
        self._db = db
        self._cancelled = cancelled
        self._last_job_check = float("-inf")
        self._repository = repository
        self._archive = archive
        self._predecessor = predecessor
        self._first_byte_timeout = first_byte_timeout
        self._idle_timeout = idle_timeout
        self._verdict_timeout = verdict_timeout
        self._max_seconds = max_seconds
        self._queued_at: Optional[float] = None
        self.return_code: Optional[int] = None
        self.stderr: str = ""
        self.job_id: Optional[int] = None
        self._relay_stream = None
        self._drain_task: Optional[asyncio.Task] = None
        self._chunks: asyncio.Queue = asyncio.Queue()
        self._buffer_bytes = buffer_bytes
        self._buffered = 0
        self._space_freed = asyncio.Event()
        self._received = False
        self._drained = False
        self._finished = False

    async def _start(self) -> None:
        from app.services.agent_job_dispatcher import dispatch_agent_job_best_effort

        try:
            job = queue_agent_repository_operation_job(
                self._db,
                self._repository,
                job_kind=AGENT_DIFF_JOB_KIND,
                # The key is always sent: `null` asks for the full listing of
                # a series' first archive, a missing key is refused. The budget
                # is the server's: without it the agent falls back to its own.
                operation={
                    "archive": self._archive,
                    "predecessor": self._predecessor,
                    "timeout_seconds": self._max_seconds,
                },
            )
        except HTTPException as exc:
            if repository_busy(exc):
                # The runner defers the operation and retries later.
                raise
            raise AgentUnavailable(detail_text(exc.detail)) from exc
        except Exception as exc:
            # The job insert carries the repository's secrets, and a statement
            # error renders its parameters: only the sanitized line may reach
            # the operation log, and the original is not chained.
            self._db.rollback()
            raise RuntimeError(
                f"could not queue the change listing job: {failure_text(exc)}"
            ) from None
        self.job_id = job.id
        self._queued_at = asyncio.get_running_loop().time()
        agent_artifact_relay.register(job.id)
        try:
            await dispatch_agent_job_best_effort(
                self._db, job, repository_id=self._repository.id
            )
        except BaseException:
            agent_artifact_relay.unregister(job.id)
            raise
        self._relay_stream = agent_artifact_relay.stream(
            job.id,
            first_byte_timeout=self._first_byte_timeout,
            idle_timeout=self._idle_timeout,
        )
        self._drain_task = asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        # Moves the chunks out of the relay's small queue into a buffer the
        # parser reads at its own pace, bounded in bytes: past the bound the
        # drain waits, the relay's queue fills and the agent's upload blocks.
        # Once the agent has closed the upload, the tail (at most the relay's
        # queue) is taken whatever the buffer holds, so the end marker is
        # confirmed within the relay's bound however far the parser is
        # behind; late, the agent records a complete listing as not
        # delivered.
        try:
            async for chunk in self._relay_stream:
                await self._wait_for_space()
                self._buffered += len(chunk)
                self._received = True
                self._chunks.put_nowait(chunk)
            self._drained = True
            self._chunks.put_nowait(_END)
        except asyncio.CancelledError:
            # Cancelled in the wait for buffer space, the relay's generator
            # is parked at its yield: closing it runs the generator's exit,
            # which marks the consumer gone and wakes an upload blocked on
            # the full queue. Cancelled inside the generator, it has run.
            await self._relay_stream.aclose()
            raise
        except BaseException as exc:  # noqa: BLE001 - handed to the reader
            self._chunks.put_nowait(exc)

    async def _wait_for_space(self) -> None:
        while self._buffered >= self._buffer_bytes:
            if agent_artifact_relay.is_closing(self.job_id):
                return
            self._space_freed.clear()
            try:
                await asyncio.wait_for(self._space_freed.wait(), CHUNK_POLL_SECONDS)
            except asyncio.TimeoutError:
                pass  # look at the producer's state again

    async def __aiter__(self) -> AsyncIterator[str]:
        await self._start()
        partial = b""
        while True:
            item = await self._next_item()
            if item is None:
                # the job ended without its output; the verdict is set
                return
            if item is _END:
                break
            if isinstance(item, BaseException):
                await self._fail(item)
            self._buffered -= len(item)
            self._space_freed.set()
            partial += item
            *lines, partial = partial.split(b"\n")
            if len(partial) > LINE_LIMIT or any(len(raw) > LINE_LIMIT for raw in lines):
                # The server's own stream refuses such a line too; without the
                # bound, output with no newline would grow here unchecked.
                await self._stop_reading()
                await self._abandon_job()
                self._finished = True
                raise RuntimeError(
                    f"the agent's change listing has a line longer than {LINE_LIMIT} bytes"
                )
            for raw in lines:
                # blank lines are the agent's padding against idle proxies
                if raw.strip():
                    yield _decode(raw)
        if partial.strip():
            yield _decode(partial)
        await self._read_verdict()
        self._finished = True

    async def _next_item(self):
        """The next chunk, end marker or failure from the drain. While none
        arrives, honour a cancellation and notice a job that already ended:
        neither may wait for the idle bound. A listing past its budget is
        ended from here when the agent's own report of that end has not
        arrived: an agent that pads and keeps its job alive would otherwise
        hold the repository for as long as the relay's idle bound is reset.
        Every check runs on an arrival as well as on a poll, so a producer
        that sends faster than the poll (padding, say) cannot starve any of
        them; the tail of an upload the agent has closed is read out however
        late, end marker included."""
        loop = asyncio.get_running_loop()
        overdue = self._first_byte_timeout + self._max_seconds + self._verdict_timeout
        while True:
            try:
                item = await asyncio.wait_for(
                    self._chunks.get(), timeout=CHUNK_POLL_SECONDS
                )
            except asyncio.TimeoutError:
                item = _MISSING
            if self._cancelled is not None and self._cancelled():
                await self.close()
                raise OperationCancelled()
            if item is not _MISSING and (
                not isinstance(item, bytes)
                or self._drained
                or agent_artifact_relay.is_closing(self.job_id)
            ):
                return item
            now = loop.time()
            if now - self._queued_at >= overdue:
                await self._stop_reading()
                await self._abandon_job()
                self._finished = True
                raise RuntimeError(
                    "the agent did not report the change listing ended "
                    f"{overdue:g}s after it was queued (budget {self._max_seconds:g}s "
                    "plus its start and report bounds)"
                )
            if now - self._last_job_check >= JOB_POLL_SECONDS:
                self._last_job_check = now
                row = self._job_row()
                if (
                    row is not None
                    and row.status in TERMINAL_AGENT_STATUSES
                    and row.status not in SUCCESSFUL_AGENT_STATUSES
                ):
                    # A job that failed before its upload (no borg binary, a
                    # bad payload) sends nothing more; its output never comes.
                    await self._stop_reading()
                    self._record_failure(row)
                    self._finished = True
                    return None
            if item is not _MISSING:
                return item

    def _record_failure(self, row) -> None:
        # Always an error code: a job the agent reports as failed is not a
        # complete listing, whatever exit code borg had (a warning exit whose
        # upload was refused fails the job with rc 1).
        self.return_code = -1
        self.stderr = (
            _agent_job_failure_message(
                self._db,
                SimpleNamespace(id=self.job_id, error_message=row.error_message),
            )
            or f"the change listing job ended {row.status}"
        )

    async def _stop_reading(self) -> None:
        try:
            if self._drain_task is not None and not self._drain_task.done():
                self._drain_task.cancel()
                try:
                    await self._drain_task
                except asyncio.CancelledError:
                    # the drain's own end; a cancellation of this task that
                    # lands in the same await is not swallowed with it
                    if asyncio.current_task().cancelling():
                        raise
                except Exception:  # noqa: BLE001 - the drain's failure is not this call's
                    pass
        finally:
            # also on the way out of a cancellation: the channel must not
            # stay registered with an upload blocked on its queue
            if self._relay_stream is not None:
                # the drain closes the generator when it is cancelled; this
                # covers a drain that ended another way, a finished
                # generator ignores it
                try:
                    await self._relay_stream.aclose()
                except Exception:  # noqa: BLE001 - the generator's exit, not this call's
                    pass
            if self.job_id is not None:
                agent_artifact_relay.unregister(self.job_id)

    def _job_row(self):
        # Column query: read fresh from the database, not from the
        # session's identity map, which still holds the job as queued.
        return (
            self._db.query(
                AgentJob.status,
                AgentJob.error_message,
                AgentJob.started_at,
            )
            .filter(AgentJob.id == self.job_id)
            .one_or_none()
        )

    async def _fail(self, exc: BaseException) -> None:
        row = self._job_row()
        # A job the dispatcher marked `claimed` whose command never arrived
        # has not started either: no agent is working on it.
        unclaimed = row is not None and (
            row.status == "queued"
            or (row.status == "claimed" and row.started_at is None)
        )
        await self._abandon_job()
        self._finished = True
        if isinstance(exc, TimeoutError):
            if unclaimed and not self._received:
                raise AgentUnavailable(
                    "no agent picked up the change listing job"
                ) from exc
            raise RuntimeError("the agent's change listing stalled") from exc
        raise RuntimeError(f"the agent's change listing failed: {exc}") from exc

    async def _read_verdict(self) -> None:
        loop = asyncio.get_running_loop()
        # The report follows the upload's return within the verdict bound,
        # but never past the listing's absolute one: a stream that ended
        # near it does not buy the job a second window.
        absolute = (
            self._queued_at
            + self._first_byte_timeout
            + self._max_seconds
            + self._verdict_timeout
        )
        deadline = min(loop.time() + self._verdict_timeout, absolute)
        while True:
            row = self._job_row()
            if row is None:
                self.return_code = -1
                self.stderr = "the change listing job no longer exists"
                return
            if row.status in SUCCESSFUL_AGENT_STATUSES:
                # In the stream contract a warning is rc 1, the code the
                # history index accepts besides 0. The agent also completes a
                # listing on Borg's modern warning codes (100-127), which the
                # index's check does not know, so the verdict is translated
                # here rather than widening that check.
                self.return_code = 0 if row.status == "completed" else 1
                return
            if row.status in TERMINAL_AGENT_STATUSES:
                self._record_failure(row)
                return
            if loop.time() >= deadline:
                await self._abandon_job()
                self.return_code = -1
                self.stderr = "the agent did not report the change listing's result"
                return
            if self._cancelled is not None and self._cancelled():
                await self._abandon_job()
                self._finished = True
                raise OperationCancelled()
            await asyncio.sleep(VERDICT_POLL_SECONDS)

    async def _abandon_job(self) -> None:
        """Take the job out of the admission's way: a queued one is
        cancelled, a claimed or running one is asked to stop."""
        from app.services.agent_job_dispatcher import dispatch_agent_cancel_if_connected

        if self.job_id is None:
            return
        try:
            job = abandon_agent_repository_operation_job(self._db, self.job_id)
            if job is not None and job.status == "cancel_requested":
                await dispatch_agent_cancel_if_connected(job)
        except Exception as exc:  # noqa: BLE001 - the reaper is the fallback
            self._db.rollback()
            logger.warning(
                "could not cancel the agent's change listing job",
                job_id=self.job_id,
                error=str(exc),
            )

    async def close(self) -> None:
        """End early: stop reading and cancel the agent's job. Safe to call
        more than once, and after the stream finished."""
        await self._stop_reading()
        if not self._finished:
            self._finished = True
            await self._abandon_job()
        if self.return_code is None:
            self.return_code = -1
