"""Shared subprocess cancellation for the services that track their own process.

Every service that keeps a `running_processes` map cancelled it the same way:
SIGTERM, wait up to five seconds, SIGKILL. `cancel_watcher` in the maintenance
executor reads a `False` as "nothing tracked yet, poll again", so an untracked
job is a warning and not an error.

`label` is what the logs call the process ("prune", "borg2 prune"), which is
the only thing that differed between the copies.
"""

import asyncio

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
