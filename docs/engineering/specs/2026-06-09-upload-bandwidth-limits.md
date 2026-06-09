# Upload Bandwidth Limits Spec

## Goal

Let users cap Borg backup upload bandwidth without hand-editing Borg command
flags, while keeping existing unlimited backup behavior unchanged by default.

## Context

GitHub issue #663 asks for upload caps such as 0.1 MB/s or 1.0 MB/s so backups
do not consume all daytime bandwidth. The Linear ticket also asks whether the
setting belongs on a repository, a backup plan, or both.

Borg exposes upload limiting as a create-time option. Borg 1.4 documents
`--upload-ratelimit RATE` as a common option in KiB/s and marks the older
`--remote-ratelimit` alias as deprecated. Borg 2 removes the deprecated alias
and keeps `--upload-ratelimit`. Because the knob is applied per command, Borg UI
should resolve the effective rate when starting each backup instead of trying to
write Borg repository configuration.

Borg UI already has a backup-plan upload cap and a per-plan-repository numeric
override in the API, persistence, command builders, and backup plan UI. The
remaining product gap is a repository-level default that manual backups,
repository schedules, and backup plans can inherit.

## Design

Add `upload_ratelimit_kib` to repositories as an optional default upload cap in
KiB/s. `NULL` means unlimited and preserves current behavior.

Effective backup rate:

1. Per-plan repository override, when present.
2. Backup plan upload cap, when present.
3. Repository default upload cap, when present.
4. Unlimited.

Manual repository backups and legacy repository schedules use the repository
default directly. Backup plans resolve the effective value per target repository
before dispatching to server, remote SSH, Borg 2, or managed-agent execution.

This deliberately does not add a system-wide/global setting in this slice. Borg
UI repositories represent target storage and network paths more accurately than
global Settings for this feature, and existing backup plans already provide the
user-facing per-workflow override.

## UI

Repository create/edit gets one optional numeric field in advanced backup
settings:

- label: Upload speed limit
- unit: MB/s
- helper: leave empty to inherit unlimited/default behavior

The existing backup-plan Settings step remains the workflow-level override. The
review step and repository detail surfaces should show configured values without
heavy accent borders or new visual patterns.

## Validation

Backend coverage must prove:

- repository create/import/update accept, validate, persist, and serialize
  `upload_ratelimit_kib`;
- invalid non-positive repository limits are rejected;
- manual and scheduled repository backups inherit the repository default;
- backup plans use link override, then plan value, then repository default;
- Borg 1 and Borg 2 command builders receive the same effective value.

Frontend coverage must prove:

- repository wizard edit state hydrates the limit from repository data;
- create/edit payloads convert MB/s to KiB/s and send `null` for empty values;
- backup plan controls still send explicit plan-level overrides;
- Storybook demonstrates the changed repository advanced state.

## Self-review

- No placeholders remain.
- Scope is intentionally constant upload caps only. Time-window throttling is
  larger than the current Borg command option and would need a scheduler-aware
  follow-up.
- The default remains `NULL`, so existing repositories and plans keep unlimited
  uploads until users opt in.
