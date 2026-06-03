# Managed Agent Diagnostics Spec

## Problem

Managed Agents show online/offline state, last seen time, logs, and job
history, but operators do not have a focused action for proving that an
enrolled agent has a healthy outbound session or can reach a specific service
from the agent host. When an agent is flaky or a repository/service endpoint is
suspect, the current UI forces operators to infer state from logs and job
history.

## Desired Outcome

Each managed-agent card exposes a diagnostics action. The action opens a
focused dialog that can run a live outbound session health check and optionally
ask the agent to try a TCP connection to a user-provided host and port. Results
include clear pass/fail state, elapsed timing, normalized error details, and
the metadata operators need for troubleshooting.

## Design

Use the existing authenticated `/api/agents/session` WebSocket command path.
The backend adds a managed-machine endpoint that validates the optional target
payload, snapshots the selected agent metadata, and sends an ephemeral
`diagnostics.run` command through `agent_connection_manager.send_command`.
Diagnostics do not create `AgentJob` rows and do not require inbound access to
the agent host.

The request accepts an optional TCP target:

```json
{
  "target": {
    "host": "postgres.internal",
    "port": 5432,
    "timeout_seconds": 3
  }
}
```

If no target is provided, the agent performs only the session round trip. Host
input is trimmed, bounded, and rejected when empty or containing characters that
cannot be a hostname, IPv4 address, or IPv6 literal. Port is an integer from 1
through 65535. Timeout is bounded to a short range so a diagnostic cannot hold a
server request indefinitely.

The agent handles `diagnostics.run` directly in the session runtime. It uses
Python socket APIs with caller-supplied host, port, and timeout values. It does
not run shell commands. TCP failures are normalized into stable error codes and
short messages.

The response shape is:

```json
{
  "agent": {
    "id": 7,
    "name": "Production NAS",
    "agent_id": "agt_prod_nas_01",
    "status": "online",
    "last_seen_at": "2026-06-03T14:00:00+00:00",
    "agent_version": "0.4.0",
    "borg_versions": [],
    "capabilities": ["session.commands", "diagnostics.run"],
    "last_error": null
  },
  "session": {
    "status": "success",
    "elapsed_ms": 12
  },
  "tcp": {
    "target": { "host": "postgres.internal", "port": 5432, "timeout_seconds": 3 },
    "status": "failed",
    "elapsed_ms": 81,
    "error": "connection_refused",
    "message": "Connection refused"
  }
}
```

Offline agents return a diagnostic payload with `session.status` set to
`offline` rather than forcing the UI to decode a generic error. Session command
timeouts return `session.status` set to `timeout`. Agent command errors return
`session.status` set to `failed` with a normalized message.

The Managed Agents UI adds a compact "Run diagnostics" icon action on each
agent card. The dialog uses the shared `ResponsiveDialog`, a simple optional
host/port/timeout form, and status rows for metadata, session health, and TCP
target health. It shows loading, success, partial failure, offline, and timeout
states without disabling the existing logs, reinstall, revoke, or delete card
actions.

## Acceptance Criteria

- Managed Agents cards expose a diagnostics action for enrolled agents.
- Diagnostics include session round-trip health and metadata: online/offline
  state, last seen time, agent version, Borg versions, capabilities, and last
  error.
- Diagnostics support an optional TCP target check from the selected agent to a
  host and port with timeout, success/failure, elapsed time, and normalized
  error text.
- Backend validation rejects invalid host, port, and timeout input.
- Backend and agent implementation use structured socket/session APIs and do
  not run shell commands from user-provided strings.
- The flow reuses existing Managed Agents API/session infrastructure and avoids
  inbound agent connectivity.
- The UI represents loading, success, partial failure, offline, and timeout
  states without blocking existing card actions.
- Storybook and targeted tests cover diagnostics action and result states.

## Validation

- Backend targeted tests cover diagnostic success, offline agent, timeout,
  invalid target, and failed TCP connection result.
- Agent targeted tests cover the diagnostic command handler without performing
  network calls outside mocked sockets.
- Frontend targeted tests cover the diagnostics dialog/action states.
- Required frontend checks pass: `npm run check:locales`,
  `npm run typecheck`, `npm run lint`, and `npm run build`.
- Required backend checks pass: `ruff check app tests`,
  `ruff format --check app tests`, and relevant `pytest` tests.

## Notes

A broad synthetic bandwidth speed test stays out of scope. Borg UI already
reports real backup and restore transfer speeds, and a synthetic speed target
needs a clearer product contract.
