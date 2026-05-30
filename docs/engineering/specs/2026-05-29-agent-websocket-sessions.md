# Agent WebSocket Sessions

## Problem

Managed-agent filesystem browsing currently creates a queued `AgentJob` and then
waits for the agent's next `/api/agents/jobs/poll` request. The default agent
poll interval is 15 seconds, so interactive path browsing can stall even when
the agent and Borg UI are on the same LAN. The same polling-first control path
also makes cancellation, logs, progress, and reconnect state harder to reason
about as managed agents grow beyond the initial beta.

The agent process also exits when Borg UI is temporarily unavailable. Under
systemd, expected server downtime is reported as a crash loop rather than a
normal reconnecting service state.

## Desired Outcome

Agents open one authenticated outbound WebSocket session to Borg UI. The server
uses that live session for immediate command dispatch and marks agents online
from active session presence. Interactive filesystem browsing is an ephemeral
RPC over the session and no longer creates an `AgentJob`. Durable operations
keep their database records and can be dispatched over the session when the
agent is connected.

Agents keep running when Borg UI is unavailable and reconnect with bounded
backoff. Operators can inspect useful agent logs from the Managed Agents page.

## Scope

- Add `/api/agents/session` as an authenticated WebSocket endpoint.
- Add an in-memory connection manager keyed by `agent_machine_id`.
- Add session protocol messages for hello, command, acknowledgement, logs,
  progress, result, error, cancellation, and disconnect state.
- Route `filesystem.browse` through the live session with timeout and item
  limits.
- Keep `/api/agents/jobs/poll` for compatibility and offline fallback, but stop
  using it for interactive browse.
- Dispatch newly queued durable agent jobs over the live session when one is
  available, while preserving DB job records and the existing polling fallback.
- Add an agent runtime mode that maintains a reconnecting WebSocket loop.
- Add an agent-card logs action that shows recent session and job logs.

## Non-Goals

- Agents will not host an HTTP server or require inbound connectivity.
- This change will not add a new persistent agent-log table unless the existing
  job-log table and in-memory session log buffer prove insufficient.
- This change will not remove existing poll endpoints, because older agents may
  still use them during rollout.

## Protocol

The agent sends a `hello` message immediately after connection:

```json
{
  "type": "hello",
  "agent_id": "agt_...",
  "hostname": "nas-01",
  "agent_version": "0.1.0",
  "borg_versions": [],
  "capabilities": ["session.commands", "filesystem.browse"],
  "running_job_ids": []
}
```

The server sends commands:

```json
{
  "type": "command",
  "command_id": "uuid",
  "command": "filesystem.browse",
  "job_id": null,
  "payload": { "path": "/home", "include_hidden": false, "max_items": 1000 }
}
```

Agents respond with `command_ack`, `log`, `progress`, `command_result`, or
`command_error`. Durable jobs include `job_id`; browse RPCs do not.

## Error Handling

- Invalid or missing WebSocket credentials close the socket with a policy error.
- An invalid hello message closes the socket and records an agent session log.
- Browse requests to disconnected agents return `409 agentOffline`.
- Browse requests that exceed the timeout return `504 filesystemBrowseTimeout`.
- Browse responses over the item limit return a deterministic `items_truncated`
  response with only the first `max_items` entries.
- Failed durable dispatch leaves the DB job queued so polling or reconnect can
  still pick it up.

## Validation

- Backend unit tests cover WebSocket authentication, hello registration, online
  status, disconnect behavior, browse RPC success, browse timeout, browse item
  limits, and durable job dispatch preservation.
- Agent runtime tests cover reconnect backoff and command execution over the
  session.
- Frontend tests and Storybook cover the agent-card logs action.
- Manual/runtime validation launches Borg UI and an agent, then verifies a
  managed-agent filesystem browse completes over `/api/agents/session` instead
  of waiting for the 15-second poll interval.
