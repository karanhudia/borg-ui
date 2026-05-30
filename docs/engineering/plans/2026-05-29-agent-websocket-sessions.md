# Agent WebSocket Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace interactive managed-agent browsing with live WebSocket RPCs
and make the agent runtime reconnect instead of exiting on server downtime.

**Architecture:** FastAPI owns an authenticated `/api/agents/session` WebSocket
endpoint backed by an in-memory `AgentConnectionManager`. The manager tracks
active sessions by database `agent_machine_id`, sends command envelopes, waits
for ephemeral browse responses, stores a small session-log ring buffer, and
pushes queued durable jobs when a live session exists. The agent keeps the
existing HTTP client for registration and compatibility, but `run` uses a
WebSocket loop with exponential backoff and command handlers.

**Tech Stack:** FastAPI WebSocket support, SQLAlchemy, Pydantic models,
React/MUI, Storybook, pytest, Vitest.

---

## Files

- Create `app/services/agent_connection_manager.py` for active sessions,
  pending command futures, browse RPC, durable job dispatch, and in-memory
  session logs.
- Modify `app/api/agents.py` to add `/session`, share job status update helpers
  between HTTP and WebSocket messages, and keep polling as fallback.
- Modify `app/services/agent_filesystem_service.py` to call the connection
  manager for live browse instead of creating a `filesystem.browse` `AgentJob`.
- Modify `app/api/managed_machines.py` to expose per-agent logs and dispatch
  newly queued backup jobs over a live session when available.
- Modify `app/services/repository_executor.py` only where a queued durable agent
  job can be opportunistically dispatched without changing repository semantics.
- Create `agent/borg_ui_agent/session.py` for the reconnecting WebSocket client
  and session reporter.
- Modify `agent/borg_ui_agent/runtime.py` and `agent/borg_ui_agent/cli.py` so
  `borg-ui-agent run` uses WebSocket sessions and `once` keeps polling behavior.
- Modify `agent/borg_ui_agent/filesystem.py` only if needed to share direct
  browse execution for ephemeral commands.
- Modify `agent/pyproject.toml` and `requirements.txt` to include the WebSocket
  client dependency.
- Modify `frontend/src/services/api.ts` for the per-agent logs endpoint.
- Modify `frontend/src/pages/ManagedAgents.tsx` to add a compact logs action on
  agent cards and reuse the existing log dialog pattern.
- Modify `frontend/src/pages/ManagedAgents.stories.tsx` and
  `frontend/src/pages/__tests__/ManagedAgents.test.tsx` for the changed UI.
- Update `docs/managed-agents.md` if setup/runtime guidance changes.

## Task 1: Backend Session Manager Tests

- [ ] Add tests in `tests/unit/test_api_agents.py` that connect to
  `/api/agents/session` with a valid agent token, send `hello`, and assert the
  agent is registered online from the active session.
- [ ] Add a disconnect test that closes the WebSocket and asserts the in-memory
  manager no longer reports the agent connected.
- [ ] Add a browse RPC test in `tests/unit/test_api_managed_machines.py` that
  creates a connected session, calls the managed-machine browse endpoint, sends
  a `command_result`, and asserts no `AgentJob` with `job_kind=filesystem.browse`
  is created.
- [ ] Run the new tests and confirm they fail because `/api/agents/session` and
  live browse dispatch do not exist yet.

## Task 2: Backend Session Manager Implementation

- [ ] Implement `AgentConnectionManager` with `register`, `disconnect`,
  `is_connected`, `send_command`, `send_ephemeral_command`, `resolve_command`,
  `reject_command`, `append_log`, and `list_logs`.
- [ ] Add the `/api/agents/session` WebSocket endpoint. Authenticate with the
  existing agent bearer token, require a `hello` message, update agent metadata,
  mark the session connected, and dispatch queued durable jobs after hello.
- [ ] Handle incoming `command_ack`, `log`, `progress`, `command_result`,
  `command_error`, and `job_canceled` messages. For durable jobs, update the
  same DB fields as the existing HTTP report endpoints.
- [ ] Change `browse_agent_filesystem` to require a connected session and call
  `filesystem.browse` with `path`, `include_hidden`, and `max_items`.
- [ ] Enforce browse timeout and max-item limits in the server response path.
- [ ] Keep `/api/agents/jobs/poll` available for durable queued jobs and older
  agents.
- [ ] Run the backend session and browse tests and confirm they pass.

## Task 3: Durable Job Push Dispatch

- [ ] Add a test that queues a managed-machine backup job while a session is
  connected and asserts the server sends a `backup.create` command with the DB
  `job_id`.
- [ ] Add a test that failed dispatch leaves the job queued.
- [ ] Dispatch newly queued backup jobs from `create_agent_backup_job` when the
  target agent has a live session.
- [ ] Opportunistically dispatch repository operation jobs after queue creation
  when the current event loop is available; otherwise leave the queued fallback.
- [ ] Run the durable dispatch tests and existing job polling tests to verify
  compatibility.

## Task 4: Agent Session Runtime

- [ ] Add tests in `tests/unit/test_agent_runtime.py` for WebSocket URL
  construction, hello payload, command acknowledgement, ephemeral
  `filesystem.browse` result, durable job progress/log/result messages, and
  reconnect backoff after a connection failure.
- [ ] Add the WebSocket client dependency to `agent/pyproject.toml` and
  `requirements.txt`.
- [ ] Implement `agent/borg_ui_agent/session.py` with a synchronous
  `websocket-client` loop that sends hello, receives commands, invokes existing
  handlers, and sends session events through a reporter object.
- [ ] Update `AgentRuntime.run_forever` to use the session loop by default and
  keep `run_once` as the polling compatibility path.
- [ ] Update CLI help so `--poll-interval` becomes a compatibility option and
  add backoff options if needed.
- [ ] Run targeted agent runtime tests and verify they pass.

## Task 5: Agent Logs UI

- [ ] Run ui-ux-pro-max guidance for the managed-agent dashboard and apply the
  existing MUI/lucide visual language.
- [ ] Add an API type and `managedAgentsAPI.listAgentLogs(agentId)` method.
- [ ] Add a terminal icon button to each agent card with an accessible label
  like `View agent logs`.
- [ ] Add a dialog that displays recent session/job logs with timestamps,
  streams, and empty/loading states.
- [ ] Update `ManagedAgents.stories.tsx` to show the new agent-card logs action.
- [ ] Update `ManagedAgents.test.tsx` to cover opening agent logs through an
  accessible button query.
- [ ] Run relevant Vitest/Storybook checks.

## Task 6: Documentation and Validation

- [ ] Update `docs/managed-agents.md` and navigation docs if user-facing setup or
  navigation text changes.
- [ ] Run `ruff check app tests`.
- [ ] Run `ruff format --check app tests`.
- [ ] Run targeted backend pytest for agent sessions, managed-machine browse,
  and agent runtime.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run `cd frontend && npm run typecheck`.
- [ ] Run `cd frontend && npm run lint`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Run `cd frontend && npm run snapshots` and commit the changed PNGs.
- [ ] Launch Borg UI locally and capture runtime evidence that browse uses the
  live session and avoids the 15-second poll delay.
