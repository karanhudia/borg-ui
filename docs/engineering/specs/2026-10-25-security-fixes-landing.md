# Security Fixes Landing

## Approved objective
The maintainer requested complete ownership of reconciling, validating, and merging all three supplied security fixes. Prior recommendations and this execution are authorized; no extra merge confirmation is required.

## Design
Use the three existing advisory-specific private forks. Reconcile the refreshed author patches against current upstream main 59fe26261c2ad714b8a7e3f96051fa4e7fa3225e. Keep each fix independently reviewable. Preserve server-to-agent operand validation, mounted SSH /-data compatibility, and discovery candidate/marker symlink authorization from the earlier drafts. Incorporate the refreshed mount and archive-delete boundaries. Accept the third patch's deliberate operator restrictions with clear access-control and upgrade/audit guidance; preserve stored-plan compatibility and document residual selection-time-only checks. Do not add an agent roots policy or runtime plan migration.

## Acceptance
- All three intended fixes are merged into upstream main through their security advisories, verified remotely.
- Benjamin Stein attribution is retained. Versions are assigned by release tooling, never manually bumped.
- No unrelated fixes, deployed data changes, release publication, CVE requests, or advisory publication.
- Full Linux unit validation and lint/format run on exact final combined source; investigate failures rather than report partial runs as success.
- Independently exercise representative real Borg 1.4.5/Borg 2.0.0b25 operations and role restrictions in a fresh disposable app stack; preserve existing installations and containers.
- Current-main analytics work remains intact. Security PRs stay private until the authorized merge makes their code public.
- Operator docs describe new paths, agent restores, mount confinement, preserved old plans, admin review, and known limits. No UI change is necessary for this backend permissions patch; verify existing HTTP error handling and document restrictions.
