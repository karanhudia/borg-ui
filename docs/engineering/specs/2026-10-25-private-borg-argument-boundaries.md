# Private Borg argument-boundary patch preparation

Reconcile the private security PR for GHSA-6r73-qghm-mmj4 with Benjamin Stein's refreshed October 25 patch and current main. The maintainer has authorized the controller to validate and merge the security fixes. Implementation workers prepare scoped commits only; advisory publication and releases remain outside this work.

Preserve the supplied option/operand separation and input validation across server and agent builders. Adapt the moved agent archive-deletion code to current main, including its shared single/batch delete helper. Reject option-shaped stored source paths and archive names before constructing agent backup jobs so older agents do not receive newly dispatched unsafe operands.

Keep normal archive selectors, supported paths, and permitted Borg flags working. Do not add path-confinement policies or redesign permissions. Retain the current app and agent versions; release tooling assigns versions. Describe agent upgrade, queued-job handling, and Borg 2 runtime validation as merge/release review requirements rather than claiming they are solved.

All commits and PRs stay in the temporary private advisory fork. Credit Benjamin Stein for the supplied patch. Implementation workers do not push, merge, publish advisories, or deploy. The controller owns the authorized advisory merge after combined validation.

## Refreshed landing scope (2026-10-25)

Mount command builders put `-o allow_other -f` and Borg 1's optional
`--bypass-lock` before the operand boundary. Borg 1's repository/archive target
and mount point follow `--`; Borg 2's mount point follows `--`, with its `-a`
archive filter remaining an option. The shared router rejects option-shaped
mount archive selectors for either major. Borg 1's progress-reporting delete
service closes options before its repository/archive target, and the agent's
direct delete helper validates its selector in addition to existing job checks.

Preserve the earlier server-to-agent dispatch checks, mounted SSH `/-data`
compatibility, single/batch deletion checks, and the accurate restore-preview
validation comment. Import refreshed mount and delete regression tests without
replacing these safeguards from the author-only comparison tree.

Scoped unit, lint, format, and diff checks are required for this commit. The
controller owns the exact combined Linux suite and real Borg 1/2 runtime checks
before landing. Full landing requirements are in
[Security Fixes Landing](2026-10-25-security-fixes-landing.md).
