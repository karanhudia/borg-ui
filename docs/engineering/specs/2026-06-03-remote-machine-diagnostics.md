# Remote Machine Diagnostics Spec

## Problem

GitHub issue #252 asks for a speed test with ping and remote port testing.
Borg UI already lets operators test an SSH Remote Machine connection, but that
basic action only records connected or failed state. It does not provide a
focused diagnostic result with round-trip timing, a remote port reachability
check from the selected host, or a bounded throughput signal for the configured
SSH path.

## Desired Outcome

Each configured Remote Machine card exposes a diagnostics action. The action
opens a focused dialog that can run a live SSH health check, show a latency
style round-trip timing result, optionally test a TCP host and port from the
remote machine, and run a bounded throughput probe over the same SSH transport.
Results should be clear enough to distinguish full success, partial failure,
connection failure, command timeout, and validation errors.

## Design

Add a new authenticated FastAPI endpoint:

```text
POST /api/ssh-keys/connections/{connection_id}/diagnostics
```

The request accepts:

- `target`, optional object with `host`, `port`, and `timeout_seconds`.
- `timeout_seconds`, the SSH command timeout used for the session and speed
  probes.
- `speed_probe_bytes`, a bounded byte count for the throughput probe.

The backend resolves the selected `SSHConnection` and its SSH key using the
same system-key fallback used by the existing connection test and storage
refresh paths. It writes the private key to a temporary file, then runs a small
sequence of `ssh` subprocesses with explicit argument lists:

- session/latency probe: remote `pwd`, measured with `time.monotonic()`;
- optional TCP probe: OpenSSH `-W <validated-host>:<validated-port>` through
  the remote SSH server, measured independently;
- speed probe: a constant remote `dd if=/dev/zero bs=65536 count=N` command
  with validated `N` derived from `speed_probe_bytes`.

User-provided host, port, timeout, and probe-size values are validated and
converted before use. The implementation must not interpolate unvalidated input
into shell commands. The TCP probe validates the target host with the existing
bare DNS/IP host validator and uses only validated primitive values in the SSH
arguments. The speed command uses only a bounded integer block count derived
from validated bytes.

The response returns normalized result sections:

- `connection`: Remote Machine metadata for troubleshooting.
- `session`: SSH connection health and elapsed milliseconds.
- `latency`: the same measured round-trip signal shown as a ping-style result.
- `tcp`: optional remote port result.
- `throughput`: bounded SSH transport speed result with bytes, elapsed time,
  and MB/s when successful.

Failure in the optional TCP or speed probe should not turn the entire HTTP
request into an error. It should return HTTP 200 with the relevant section
marked `failed` or `timeout`. Request validation failures should return 422, and
missing connections or missing SSH keys should return the existing 404-style
backend error contracts.

## Frontend

Extend the Remote Machines page rather than adding a new route. Add a compact
diagnostics icon action to `RemoteMachineCard`. The page owns dialog state and
mutation state, following the existing `SSHConnectionsSingleKey.tsx` pattern.
The dialog lives under `frontend/src/pages/ssh-connections-single-key/dialogs/`
and uses `ResponsiveDialog`.

The dialog should be quiet and operational:

- header with selected machine identity and existing status;
- optional TCP target controls for host, port, and timeout;
- speed probe size control with bounded values;
- result rows for SSH session, latency, remote TCP, and throughput;
- clear loading, success, partial failure, connection failure, timeout, and
  validation-error states;
- existing card actions remain available while diagnostics run.

Use MUI and Lucide icons consistently with the current page. Avoid heavy left
accent borders; use balanced outlines, chips, and status icons.

## Testing

Use TDD for backend and frontend changes.

Backend targeted tests belong in `tests/unit/test_api_ssh_keys.py` and cover:

- successful diagnostics response with session, latency, TCP, and throughput;
- diagnostics do not create or mutate unrelated Remote Machine rows;
- missing connection returns 404;
- invalid target host, port, timeout, and probe-size return 422;
- failed remote TCP result stays HTTP 200 with `tcp.status == "failed"`;
- SSH command timeout maps to normalized timeout state;
- throughput result normalization calculates bytes, elapsed time, and MB/s.

Frontend targeted tests cover:

- Remote Machine cards expose a diagnostics action;
- clicking the action opens the dialog and runs diagnostics;
- loading state disables only the dialog run button;
- client-side target validation prevents invalid submissions;
- success result shows latency, TCP, and throughput values;
- partial failure shows successful session plus failed TCP or speed details;
- connection failure and timeout states show clear status copy.

Storybook should demonstrate the diagnostics dialog in success, partial failure,
and timeout/failure states.

## Documentation

Update `docs/ssh-keys.md` because the Remote Machines action list changes. Add
a short diagnostics section describing what the session, remote port, and speed
checks prove, and note that the speed probe is a bounded SSH transport probe,
not a broad internet benchmark.

## Out Of Scope

- ICMP ping, because many targets block it and containers may lack the needed
  privileges.
- External speed-test services.
- Persisted diagnostics history.
- Managed Agent diagnostics, which is covered by BOR-133.
