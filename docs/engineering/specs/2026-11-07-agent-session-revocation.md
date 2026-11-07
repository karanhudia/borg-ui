# Preserve managed-agent revocation across live sessions

Prepare a private advisory PR for GHSA-99jv-rr5j-fhj7 from Benjamin Stein's
November 2 patch, against current main 959150e48a191b9ff5840c07b49cc5074b53ad0f.
A revoked, disabled or deleted agent must not be marked online by an existing
session, a request authenticated earlier, or the connected-agent list refresh.

Use one guarded SQL update for online transitions, re-read the agent status
before applying session messages, and guard the disconnect transition from
online to offline. Refuse inactive sessions with WebSocket code 1008 and stale
REST heartbeats with the existing agentDisabled 403 response.

Retain the supplied minimal scope: silent sessions close on their next message;
revocation does not cancel queued jobs, and the narrow interval between the
heartbeat guard and job delivery remains. Administrator-initiated commands are
unchanged. Agents whose earlier revocation was undone must be revoked again.
No frontend, agent package, schema or version changes. Credit Benjamin Stein.
This request authorizes a private PR; merging, advisory publication and release
are separate actions.

Acceptance: demonstrate supplied regressions against current main, pass all
12 supplied tests with the patch, run backend unit/lint/format checks, review
the exact diff, and verify that the PR targets the private advisory fork.
