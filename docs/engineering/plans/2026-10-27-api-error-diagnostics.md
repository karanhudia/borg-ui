# API error diagnostics implementation plan

**Goal:** Make failed API requests actionable while suppressing intentional cancellation and retaining expected refusals without bug alerts.

**Architecture:** Extend the existing Axios reporting path with allowlisted endpoint templates, transport codes, failure classes and elapsed time. Version API fingerprints to distinguish endpoint and cause. Keep raw request configuration, headers, bodies, query values and backend detail params out of reports. The analytics consumer remains compatible with old reports and groups API failures under one parent without merging child fingerprints.

**Approved design:** User approved the API request failures umbrella, selective reporting policy and richer allowlisted diagnostics in chat on 2026-10-27. No version bump. Existing consent, deduplication of global Axios rejections and flood controls remain in effect.

- [x] Add regression tests for endpoint redaction, transport/configuration classification, duration, distinct fingerprints, 5xx capture and cancellation suppression.
- [x] Run those tests and observe failures before implementation.
- [x] Implement diagnostics in a focused helper, capture request start in both Axios clients and extend ErrorContext/report payload. Keep expected refusals countable and plan gates in their existing product event.
- [x] Update trust documentation with the additional allowlisted fields and reporting policy.
- [x] Run targeted reporter, analytics and client tests, frontend typecheck, lint and build. Review the diff; publish from the isolated branch as a Borg UI PR.
- [x] Analytics: test and implement backward-compatible extraction/classification, API umbrella, readable child labels and report context. Network/timeout alerts use spike-only policy; expected HTTP refusals never alert. Preserve historical identities and overrides.
Companion rollout in borg-ui-analytics: its unit/SQL integration tests, typechecks, builds and visual check precede pushing main, applying the error view, and deploying/verifying the dashboard and alert job.

Historical reports cannot recover endpoint, duration or transport code that was never captured. Network failures do not establish whether DNS, TLS, CORS, proxy or server availability caused the failure. A frontend 5xx symptom remains separate from backend exceptions unless an actual shared request identifier exists; no synthetic correlation is claimed.

Validation: 172 targeted frontend tests passed across reporter, analytics and both Axios clients. Frontend typecheck, lint and production build passed. CodeRabbit CLI is signed out; the diff was reviewed directly. No user-facing Borg UI component changed, so no Storybook change is required.
