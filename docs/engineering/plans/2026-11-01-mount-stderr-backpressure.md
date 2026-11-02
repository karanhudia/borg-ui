# Mount stderr backpressure recovery plan

**Goal:** Prevent foreground Borg mount stderr from blocking readiness without increasing the mount timeout.

**Evidence:** A child writing 2 MB to an unread stderr pipe blocks before publishing readiness. Pipe drainage required lifetime tasks, process groups and cancellation handling. The requested revision replaces that machinery with a regular temporary file.

**Design:** Create a private `borg_mount_` temporary directory per mount and pass its stderr file directly to the child. Close the parent's file handle after spawn. Record the directory in the existing `MountInfo.temp_root` field so normal unmount and startup orphan cleanup remove it. On early exit or readiness timeout, read at most the last 8 KB, discard an initial partial line, and apply the shared `redact_secrets` function. Unmount retains the existing PID termination path. Failed or cancelled startup kills and reaps its direct child and removes temporary resources.

The file can grow while the mount lives; Borg is normally quiet after readiness. No truncation policy, private-key filter, reader task, process registry, new session or process-group signalling is introduced. Preserve readiness timing, FUSE classification, mount-path confinement, host-key settings and versions.

- [x] Replace the pipe-specific lifecycle tests with a compact real-child regression covering readiness, early exit and timeout after 2 MB of stderr; verify regular-file output, redaction and temporary-resource cleanup.
- [x] Run the new regression against the pipe design and confirm all three cases fail because stderr is a pipe.
- [x] Replace process ownership with the temporary file and bounded diagnostic reader; remove obsolete test-fixture accommodations.
- [x] Run all mount unit suites, lint/format, whitespace and personal-path checks; independently review the final diff.

**Verification:** All six affected mount unit suites pass 128 tests, with two existing planned-feature skips. Ruff lint/format, personal-path and whitespace checks pass. Independent review found no issues. Existing dependency warnings remain.
