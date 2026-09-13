"""Shared process cancellation for the Borg 2 maintenance services.

Every v2 service that tracks its subprocess cancels it the same way: SIGTERM,
wait, SIGKILL. `cancel_watcher` in the maintenance executor reads a `False`
as "nothing tracked yet, poll again", so an untracked job is a warning and
not an error.
"""

import asyncio

import structlog

logger = structlog.get_logger()


async def terminate_tracked_process(
    running_processes: dict, job_id: int, kind: str
) -> bool:
    """Terminate the tracked borg2 process for `job_id`, if there is one."""
    process = running_processes.get(job_id)
    if process is None:
        logger.warning(
            "No running borg2 process found for job", job_id=job_id, kind=kind
        )
        return False

    try:
        process.terminate()
        logger.info(
            "Sent SIGTERM to borg2 process", job_id=job_id, kind=kind, pid=process.pid
        )
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        return True
    except Exception as e:
        logger.error(
            "Failed to cancel borg2 process", job_id=job_id, kind=kind, error=str(e)
        )
        return False
