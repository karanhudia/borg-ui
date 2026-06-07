# Docker Mount Size Scan

## Problem

Docker container scanning now returns bind mounts and named-volume source paths, but it does not report whether Borg UI can estimate the amount of data behind those paths. `docker inspect` does not include mount sizes, so the scan needs a separate bounded host-filesystem probe that can fail per mount without failing the whole container scan.

## Desired Outcome

When a user scans Docker containers from the Backup Plans source chooser, each detected mount can include best-effort size metadata. Available sizes are shown next to the mount source path. Permission, missing-path, timeout, and unavailable states are explicit so users understand that an unknown size is not the same as an empty mount.

## Scope

- Extend `ContainerMount` with optional `size_bytes` and a `size_status` value.
- Use bounded `du` execution to collect sizes for local Docker mount source paths.
- Use bounded remote `du` execution for SSH Docker source scans, using the same SSH connection and key material as the scan.
- Keep the Docker container scan response successful when one or more mount size probes fail.
- Display available sizes and unavailable states in the Docker source UI.
- Update Storybook states for available and unavailable mount sizes.
- Cover available, unavailable, permission, and timeout paths in backend tests.
- Cover available and unavailable display states in frontend tests.

## Out Of Scope

- Exact volume accounting beyond host filesystem `du` output.
- Starting containers or inspecting inside container filesystems.
- Managed-agent Docker size scanning in this server-side scan flow.
- Making size metadata required for clients; older clients can ignore it.

## Contract

Each `ContainerMount` keeps its existing fields and gains:

```json
{
  "size_bytes": 1073741824,
  "size_status": "available"
}
```

`size_bytes` is `null` unless `size_status` is `available`.

Allowed `size_status` values:

- `available`: `size_bytes` is populated from a bounded filesystem traversal.
- `unavailable`: no source path exists for the mount, the path is missing, or the host cannot provide a usable size.
- `permission_denied`: the filesystem traversal reported a permission/access failure.
- `timeout`: the per-mount size probe exceeded its bounded runtime.

The timeout budget is small and per mount. The scan endpoint timeout remains bounded by the existing container scan timeout, and size probing must not raise out of the container scan response.

## UI Notes

The mount row should stay dense and match the existing source chooser. Show the formatted size as a compact caption/chip near the mount source path. For unavailable states, show muted status copy such as "Size unavailable", "Permission denied", or "Size timed out". The checkbox behavior and path selection flow must remain unchanged.

## Acceptance Criteria

- Container scan responses optionally include mount size metadata for bind mounts and named volumes when collected safely.
- Container scan runtime is bounded; per-mount unavailable, permission, or timeout states do not fail the whole scan.
- Docker source UI displays available mount sizes near each mount path.
- Docker source UI handles unavailable/permission/timeout size states clearly.
- Backend tests cover available size, unavailable size, permission failure, and timeout behavior.
- Frontend tests cover mount-size display and unavailable states.
- Storybook demonstrates the changed Docker mount-size states.

## Validation

- `pytest tests/unit/test_source_discovery.py -k "container_scan" -q`
- `ruff check app tests`
- `ruff format --check app tests`
- `cd frontend && npm test -- src/pages/backup-plans/__tests__/SourceStep.test.tsx -t "Docker|container|mount" --run`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- Local UI/runtime proof for the Docker source scan path, with fallback evidence recorded when browser dependencies are unavailable.
