import pytest

from app.api.agents import STALE_AGENT_JOB_REQUEUE_AFTER
from app.services.agent_job_reaper import AGENT_JOB_REAP_AFTER


@pytest.mark.unit
def test_requeue_window_is_shorter_than_the_reap_window():
    # A job claimed just before an agent's socket drops is never delivered and
    # sits "claimed" with started_at NULL. _requeue_stale_agent_jobs runs on
    # the agent's hello and on every heartbeat and can recover it, but only
    # for rows older than the requeue window.
    #
    # While the two windows were equal the reaper always won: by the time a
    # reconnecting agent was allowed to reclaim its own work, the job had
    # already been failed. The requeue has to become eligible first.
    assert STALE_AGENT_JOB_REQUEUE_AFTER < AGENT_JOB_REAP_AFTER
