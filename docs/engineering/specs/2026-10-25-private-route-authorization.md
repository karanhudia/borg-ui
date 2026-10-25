# Private Route Authorization PR

## Purpose
Prepare Benjamin Stein's supplied authorization patch as a private reviewable PR against current upstream main, including the known failed-plan dashboard integration.

## Scope and acceptance
- Apply the supplied authorization checks, repository visibility filters, and route inventory without unrelated policy expansion.
- Preserve current imports, agent operations, and newer API routes.
- Declare the current repository agent-scripts route accurately and retain its runtime guard.
- Restrict unresolved dispatch failures in dashboard overview using the same complete-plan repository visibility rule as other plan rows. Administrators retain all rows; restricted users see only fully visible plans, including mixed-access regression coverage.
- Keep frontend and versions unchanged. Record operator discovery restrictions and pending product behavior review in the PR.
- Add focused regression tests and run required unit/lint checks. Credit Benjamin Stein.
- Do not push to a public repository, merge, release, or publish advisories.

## Landing reconciliation against current main

- The refreshed Benjamin Stein patch is behaviorally equivalent to the existing
  complete-plan dispatch failure filter. Preserve its typed `visible_plan_ids`
  helper API and the current imports and analytics consent cache invalidation.
- Preserve the stronger local discovery checks added after the original patch:
  resolve and authorize discovered directories, SQLite files, and database
  marker paths before any probe, including default discovery.
- Add the author's combined visible/hidden/mixed failed-dispatch regression
  alongside the existing parameterized tests. Restricted responses must omit
  hidden plan names and errors; administrators retain all three failures.
- Check the merged main route inventory before changing declarations. Registry
  declarations document access and do not replace runtime authorization.
- Document operator discovery limits, default discovery's possible `403`,
  admin-only monitoring/report actions, and dashboard visibility in
  `docs/access-control.md`. Distinguish reinforced existing administrator checks
  from newly restricted discovery behavior. No frontend or new policy work.
