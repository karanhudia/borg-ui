"""Shared subprocess cancellation for the services that track their own process.

Every service that keeps a `running_processes` map cancelled it the same way:
SIGTERM, wait up to five seconds, SIGKILL. `cancel_watcher` in the maintenance
executor reads a `False` as "nothing tracked yet, poll again", so an untracked
job is a warning and not an error.

`label` is what the logs call the process ("prune", "borg2 prune"), which is
the only thing that differed between the copies.
"""

import asyncio
from typing import Optional, Tuple

import structlog

logger = structlog.get_logger()

_GRACE_SECONDS = 5.0


async def terminate_tracked_process(
    running_processes: dict, job_id: int, label: str
) -> bool:
    """Terminate the tracked process for `job_id`, if there is one."""
    process = running_processes.get(job_id)
    if process is None:
        logger.warning("No running process found for job", job_id=job_id, kind=label)
        return False
    return await terminate_process(process, job_id, label)


async def terminate_process(process, job_id: int, label: str) -> bool:
    """Terminate a process a caller already holds.

    The services call this from inside their own run, where the process is a
    local; `terminate_tracked_process` is the same thing reached through the
    `running_processes` map, which is what an outside canceller has.
    """
    try:
        process.terminate()
        logger.info(
            "Sent SIGTERM to process", job_id=job_id, kind=label, pid=process.pid
        )
        try:
            await asyncio.wait_for(process.wait(), timeout=_GRACE_SECONDS)
        except asyncio.TimeoutError:
            logger.warning(
                "Process did not terminate, sending SIGKILL",
                job_id=job_id,
                kind=label,
                pid=process.pid,
            )
            process.kill()
            await process.wait()
        return True
    except Exception as e:
        logger.error(
            "Failed to cancel process", job_id=job_id, kind=label, error=str(e)
        )
        return False


async def communicate_or_kill(
    process: asyncio.subprocess.Process,
    *,
    timeout: Optional[float],
    input: Optional[bytes] = None,
) -> Tuple[bytes, bytes]:
    """`communicate` with a deadline that also ends the child.

    `wait_for` only cancels the wait: a timed-out or cancelled Borg would
    otherwise keep running, and keep its repository lock, after the caller
    has given up on it (#1259).
    """
    try:
        return await asyncio.wait_for(process.communicate(input=input), timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        try:
            process.kill()
        except ProcessLookupError:
            # Already gone; raising here would replace the timeout or the
            # cancellation with an OSError.
            pass
        await asyncio.shield(process.wait())
        raise
