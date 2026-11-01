# Operation error recovery implementation plan

**Goal:** Preserve actionable, bounded, redacted failure reasons and classify evidenced user-correctable refusals without guessing unknown causes.

**Architecture:** Add a small diagnostic/status helper shared by repository API error boundaries and prune exceptions. Extend existing SFTP and mount capability classifications in place. Preserve unknown failures as server errors; never retry mutations, delete repositories, repair data, bypass host keys, or break locks.

**Evidence:** Five-day production groups supplied by the coordinating task: generic repository verification failures (15 events, six installs), permission/occupied create-update targets, prune DryRunFailed losing diagnostic (two events), unavailable SFTP and duplicate-home browsing, missing FUSE device and mount readiness timeout. Existing main already retries login-relative SFTP paths; retain that behavior and cover current gaps only. A timeout alone does not establish a new root cause.

## Tasks

- [x] Add failing regression tests for redacted/bounded diagnostics, known permission/occupied statuses, import response preservation, prune exception reason, unavailable SFTP, and FUSE missing-device classification.
- [x] Run those tests and confirm they fail for the missing behaviors.
- [x] Implement diagnostic/status helper and wire repository import/create/update refusal paths without changing initialization or transaction semantics.
- [x] Preserve prune failure diagnostic in exception text and API output with the same bound/redaction.
- [x] Classify unavailable SFTP and missing device at existing error boundaries; preserve unknown 500s and host-key enforcement. Keep existing timeout cleanup and login-relative normalization unless a failing regression proves another fix.
- [x] Run focused tests and adjacent repository/filesystem/prune/mount gates; run ruff on changed Python files, inspect diff, and commit without pushing.

**Validation command:** `PYTHONPATH=. .venv/bin/python -m pytest tests/unit/test_operation_error_recovery.py tests/unit/test_api_filesystem.py tests/unit/test_prune_preview.py tests/unit/test_mount_service.py tests/unit/test_api_repositories.py`

**Excluded:** Unknown import root causes, automatic host/device changes, timeout inflation without evidence, changes to archive-sync backoff or storage/disk-full recovery owned by the coordinator.

## Evidence and implementation outcome

- Repository errors now keep at most 2,000 characters after secret redaction, retaining both the beginning and final cause. Existing translated import/verification copy interpolates the diagnostic in all four locales.
- Recognized permission failures return 403; occupied paths return 409 from modern code 19, FileExistsError, or Borg 1's exact `There is already something at <path>.` line. Unknown failures remain 500. Existing lock refusal behavior and rollback semantics remain covered.
- A disposable-directory probe with installed Borg 1.4.3 reproduced the occupied-target line with exit 2 and verified the existing file was preserved.
- Prune dry-run exceptions now carry the bounded diagnostic in exception text and their existing API log field, preserving telemetry reason and preview diagnostics.
- SFTP servers without a subsystem/server receive an actionable 422 without a shell fallback. Existing login-relative/home normalization remains intact.
- Missing FUSE devices use the existing unavailable-capability response. Readiness timeout configuration and cleanup are preserved: a 120-second timeout alone does not prove a different root cause or justify changing its budget.

## Verification

Regression tests were observed failing before their corresponding fixes. Final focused recovery gate: 19 passed. Repository plus recovery gate: 254 passed. API mount, Borg error, and archive-index boundary gate: 173 passed. Ruff and diff whitespace checks pass. Existing dependency deprecation warnings remain; mount capability tests include existing planned-feature skips.

## Review correction: mounted-cache rclone import

Independent review found that mounted-cache rclone import still returned blanket HTTP 400 for generic verification failures. The regression now exercises unknown failure (500), permission denial (403), occupied target (409), passphrase refusal (400), and invalid repository (400), asserting diagnostic preservation and removal of uncommitted repository/storage records. Before the fix, the first three status assertions failed while the user-correctable 400 cases passed. Mounted-cache Borg 2 rejection remains at the existing validation boundary. The generic verification branch now uses `repository_failure_status` after preserving the explicit 400 refusals.

Review correction verification: `test_api_rclone.py` plus `test_operation_error_recovery.py`: **148 passed**. Ruff and diff whitespace checks passed.

## Review corrections: classify raw failures and retain Borg 1 exit codes

Validate the review findings as local issue reports. Add regressions that place passphrase/invalid-repository markers in the omitted middle of long diagnostics across ordinary, direct-rclone, cached-rclone, and update verification paths. Preserve existing 400 refusal keys and update rollback/no-initialization behavior; keep displayed diagnostics bounded and redacted. Exercise numeric exit codes 21/19 and unknown 2 through the actual Borg 1 verification producer and import/update consumers, then retain `return_code` in producer failures. Run the affected API/service suites plus Ruff, and make one consolidated commit without pushing or posting comments.

Portable focused command: `PYTHONPATH=. python -m pytest tests/unit/test_operation_error_recovery.py tests/unit/test_repository_service.py tests/unit/test_api_rclone.py tests/unit/test_api_repositories.py`.

Local validation confirmed the two mechanisms: numeric Borg 1 codes 21/19 were lost before real import/update consumers, while truncation removed passphrase and invalid-repository markers from long import failures. The fix retains the producer's `return_code` and explicitly requests full diagnostic text only for import classification; the default helper still redacts/bounds displayed diagnostics. Existing update verification already inspected raw text and required no production change. Fourteen regression cases pass across real producer/consumer numeric failures and long-diagnostic refusal cases, including unchanged unknown-500, 400 keys, rclone cleanup, and update rollback semantics.

Final correction gate: **402 passed** across recovery, Borg 1 repository service, rclone API, and repository API suites. The strengthened 14-case regression gate also passed independently. Ruff and diff whitespace checks passed; only existing dependency deprecation warnings remain. No version bump, locale change, additional HTTP status policy, or external review comment/push was included.
