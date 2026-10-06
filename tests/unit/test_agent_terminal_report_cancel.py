import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.api import agents


async def test_committed_report_is_notified_after_the_request_is_cancelled():
    """The agent drops a request after 30 s while the worker is still
    committing. Its retry finds the job final, so the notification of the
    first report must not depend on the request still awaiting."""
    notified = asyncio.Event()

    def slow_worker(job_id, payload, agent_id):
        time.sleep(0.2)
        return True, "completed"

    async def notify(db, job):
        notified.set()

    session = MagicMock()
    session.get.return_value = SimpleNamespace(id=7)

    with (
        patch("app.database.database.SessionLocal", return_value=session),
        patch.object(agents, "_notify_agent_job_outcome", notify),
    ):
        request = asyncio.ensure_future(
            agents._terminal_report(slow_worker, 7, None, 1)
        )
        await asyncio.sleep(0.05)
        request.cancel()
        try:
            await request
        except asyncio.CancelledError:
            pass

        await asyncio.wait_for(notified.wait(), timeout=2)

    session.close.assert_called_once()


async def test_report_that_did_not_transition_is_not_notified():
    notify_calls = []

    def worker(job_id, payload, agent_id):
        return False, "completed"

    async def notify(db, job):
        notify_calls.append(job)

    with patch.object(agents, "_notify_agent_job_outcome", notify):
        status = await agents._terminal_report(worker, 7, None, 1)

    assert status == "completed"
    assert notify_calls == []
