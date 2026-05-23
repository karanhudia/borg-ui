"""Agent timing constants.

AGENT_FILESYSTEM_BROWSE_TIMEOUT_SECONDS is intentionally twice
DEFAULT_AGENT_POLL_INTERVAL_SECONDS so browse requests queued just after a poll
can wait for the next poll to complete the job.
"""

DEFAULT_AGENT_POLL_INTERVAL_SECONDS = 15
AGENT_FILESYSTEM_BROWSE_TIMEOUT_SECONDS = DEFAULT_AGENT_POLL_INTERVAL_SECONDS * 2
