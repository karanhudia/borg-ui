# Analytics error recovery

The 3 November analytics investigation found 2.4.6 migration failures (missing `users`, already-existing `agent_machines`, and full storage), activity requests timing out at the database pool limit, and SSH key temporary-file cleanup masking disk-full failures. Archive sync also reported actual OS I/O and capacity failures. One isolated frontend DOM crash and network failures lack a reproducible product cause.

## Required behavior

- Legacy database transfers must tolerate dangling source foreign-key metadata while enforcing the target schema and retaining the existing orphan policy: optional pointers cleared, required-orphan rows and dependent rows reported/dropped. The original source remains available for rollback.
- A database left by an interrupted schema build must never be silently stamped or destructively rebuilt. Reproduce the already-existing-table failure and implement only a data-preserving recovery or actionable refusal justified by the evidence.
- Failed SQLite snapshots must close both connections, remove disposable incomplete copies, preserve the original exception, and leave the original database untouched. Document capacity requirements and safe recovery.
- Long-running operations must release idle read transactions across external work where safe. Preserve operation status, cancellation, retries, and follow-ups. Do not increase the connection pool to conceal exhaustion.
- Failed SSH key writes must preserve their root exception, close owned descriptors exactly once and remove partial secret files.
- Existing storage recovery guidance must remain accurate. Investigate the isolated DOM crash; do not claim it fixed without reproduction.

No app or agent version bumps, dependency changes, telemetry data disclosure, or production changes. UI changes require the UI skill, stories, and applicable checks; prefer no UI changes for unproven render causes.

## Render-crash investigation

The one 2.4.6 render report occurred on `/repositories` in Chrome/Linux. Resolving all ten stack frames with the published `sourcemaps-2.4.6.json.gz` maps them to React DOM placement/reconciliation internals; the captured component location maps to Emotion's `useContext` wrapper. There is no application source frame or captured reproduction sequence. Browser DOM modification is a hypothesis, not an established cause. No frontend behavior change is justified by this evidence. A reproduction, full component stack and browser translation/extension context are needed before a product fix can be verified.

## Operational limits

The pool fix proves a connection-retention mechanism in the agent repository poller; it does not identify the exact workload behind every Activity timeout. OS I/O errors and exhausted capacity require host/storage repair; application changes cannot restore that hardware or capacity. Existing troubleshooting documents storage checks and automatic archive-sync cooldowns. Interrupted durable schemas are preserved and refused with recovery guidance, not automatically rebuilt or stamped as verified.
