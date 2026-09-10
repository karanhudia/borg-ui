"""Agent timing constants.

AGENT_FILESYSTEM_BROWSE_TIMEOUT_SECONDS is intentionally twice
DEFAULT_AGENT_POLL_INTERVAL_SECONDS so browse requests queued just after a poll
can wait for the next poll to complete the job.
"""

DEFAULT_AGENT_POLL_INTERVAL_SECONDS = 15
AGENT_FILESYSTEM_BROWSE_TIMEOUT_SECONDS = DEFAULT_AGENT_POLL_INTERVAL_SECONDS * 2
AGENT_FILESYSTEM_BROWSE_MAX_ITEMS = 1000

# How long the server waits for an endpoint to acknowledge agent.upgrade. The
# agent only creates a file, so this bounds the round trip, not the reinstall.
AGENT_UPGRADE_COMMAND_TIMEOUT_SECONDS = 15.0

# How long an endpoint has to come back on its target version before the
# upgrade is called failed. Generous on purpose: an endpoint that hits this is
# far more likely broken than slow.
AGENT_UPGRADE_TIMEOUT_SECONDS = 600

# How many endpoints may be upgrading at once. Every upgrading endpoint is
# briefly offline, so a fleet-wide request is released in waves rather than
# taking the whole fleet down together. The cap bounds upgrades in flight, not
# endpoints offline: a timeout frees its slot while that endpoint may still be
# mid-reinstall (spec section 8).
AGENT_UPGRADE_CONCURRENCY = 5
