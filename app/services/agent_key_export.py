"""The key of an agent repository, exported on its agent (#1425).

`borg key export` runs where the repository is reached: on the agent. The
key comes back as the job's artifact upload, which the relay hands to this
reader from memory. It is never written to the server's disk, a log line or
the job row: the agent reports no output for this kind, and the bytes live
only in the download's answer.
"""

from __future__ import annotations

import asyncio

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.database.models import Repository
from app.services.agent_artifact_relay import agent_artifact_relay
from app.services.agent_job_dispatcher import (
    dispatch_agent_cancel_if_connected,
    dispatch_agent_job_best_effort,
)
from app.services.repository_executor import (
    AGENT_KEY_EXPORT_JOB_KIND,
    abandon_agent_repository_operation_job,
    agent_operation_failed_detail,
    queue_agent_repository_operation_job,
    wait_for_agent_repository_operation_job,
)

# A key export is a few hundred bytes; an upload past this is not a key, and
# the reader stops holding it in memory.
MAX_KEY_EXPORT_BYTES = 64 * 1024


def _failed(reason: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=agent_operation_failed_detail(reason),
    )


async def _read_key(job_id: int, timeout_seconds: float) -> bytes:
    """The bytes of the job's upload, from the relay."""
    content = bytearray()
    try:
        # The stream unregisters the channel however it ends.
        async for chunk in agent_artifact_relay.stream(
            job_id,
            first_byte_timeout=timeout_seconds,
            idle_timeout=timeout_seconds,
        ):
            content.extend(chunk)
            if len(content) > MAX_KEY_EXPORT_BYTES:
                raise _failed("the key export is larger than a key")
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"key": "backend.errors.agents.repositoryOperationTimeout"},
        ) from exc
    except RuntimeError as exc:
        raise _failed(str(exc)) from exc
    return bytes(content)


async def export_agent_repository_key(db: Session, repository: Repository) -> bytes:
    """Run `repository.key_export` on the repository's agent and return the
    key as Borg wrote it.

    The upload ends the same way whether Borg finished or failed, so the key
    is returned only once the job itself completed. The job's verdict is
    watched while the upload is awaited: a job that fails before it uploads
    anything (Borg could not be started) answers with its reason at once.
    Both take the operation's info timeout: the export opens the repository
    as an info does. A wait that ends without the job's verdict (a timeout,
    a client that left) takes the job back."""
    from app.api.repositories import get_operation_timeouts

    timeout_seconds = get_operation_timeouts(db)["info_timeout"]
    agent_job = queue_agent_repository_operation_job(
        db, repository, job_kind=AGENT_KEY_EXPORT_JOB_KIND
    )
    agent_artifact_relay.register(agent_job.id)
    reader: asyncio.Task | None = None
    verdict: asyncio.Task | None = None
    try:
        await dispatch_agent_job_best_effort(db, agent_job, repository_id=repository.id)
        reader = asyncio.ensure_future(_read_key(agent_job.id, timeout_seconds))
        verdict = asyncio.ensure_future(
            wait_for_agent_repository_operation_job(
                db, agent_job.id, timeout_seconds=timeout_seconds
            )
        )
        done, _ = await asyncio.wait(
            {reader, verdict}, return_when=asyncio.FIRST_COMPLETED
        )
        if verdict in done and verdict.exception() is not None:
            # failed (or gave up) before the upload ended
            raise verdict.exception()
        content = await reader
        await verdict
        if not content:
            raise _failed("the agent exported no key")
        return content
    except BaseException:
        for task in (reader, verdict):
            if task is not None and not task.done():
                task.cancel()
        agent_artifact_relay.unregister(agent_job.id)
        # Nobody takes this key any more: a live job is taken back (one that
        # is over already is left as it is).
        abandoned = abandon_agent_repository_operation_job(db, agent_job.id)
        if abandoned is not None and abandoned.status == "cancel_requested":
            await dispatch_agent_cancel_if_connected(abandoned)
        raise
