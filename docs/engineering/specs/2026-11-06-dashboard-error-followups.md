# Dashboard error follow-ups

The 6 November error review identified agent filesystem failures reported as HTTP 502, repository creation conflicts reported as 502, SSH fallback replacing an absolute-path failure with a misleading home-relative error, rclone authorization failures reported as generic 500, and Borg traceback summaries reduced to `Local Exception`.

## Required outcomes

- Map recognized agent filesystem error codes (`missing`, `unreadable`, `not_directory`) to existing localized 404/403/400 filesystem errors for both failed result and AgentCommandError payloads. Unknown or malformed failures remain 502; offline and timeout behavior remains unchanged. No arbitrary path rewriting.
- Recognize an existing repository during agent `repository.init` without misclassifying other commands or errors. Return 409 with the existing `backend.errors.borg.repositoryAlreadyExists` translation, preserve repository data, and document Import as the recovery. Do not convert generic init exit code 2 to conflict solely by code.
- Preserve SSH login-relative compatibility when a genuine missing-path retry succeeds. Do not retry auth, host-key, connection, timeout or permission failures as relative paths. A failed alternate-path retry must leave the original absolute-path error authoritative. Keep remote path validation, access controls and tempfile cleanup.
- Preserve actual Borg exception reasons after generic `Local Exception`/traceback wrappers, excluding platform/pid/command footers; retain meaningful pre-traceback reasons and lock classification. Both current stderr-tail and legacy log fallback must remain redacted and bounded. Do not turn raw command/environment/token data into user-facing errors.
- On rclone browse failures explicitly identifying `invalid_grant`, return a recoverable remote-authorization conflict (409), with translated guidance to edit the remote in Cloud Storage and authorize again. Do not log users out, clear saved credentials, auto-authorize, or classify unrelated provider/network/storage failures as expired authorization.
- OAuth code-exchange rejection diagnostics may expose only configured provider, HTTP status and allowlisted OAuth error codes; never raw token responses, descriptions, codes, credentials, headers or URLs. Failed callbacks must leave the existing authorization session observably failed and retryable.
- Preserve the existing plain-string OAuth session error for older clients while optionally supplying safe structured error detail for translated polling in current clients. Clear stale detail when authorization succeeds. Failed listings must not claim that a directory is empty.
- Reuse existing recovery UI, localized error renderer and shared components. New error strings must cover en/de/es/it; a story must demonstrate any changed visible error state. No redesign or new flow.

No version bumps, dependencies, schema migrations, production changes or automatic storage repair. The isolated render crash remains outside scope without reproduction. Release 2.4.7 publication monitoring is independent of this PR.

## Evidence limits

The four generic backup `unknownError` reports contain neither a process exit code nor a recognized Borg message ID. The existing formatter already exposes an exit code when supplied. Without the affected operation logs, there is no verified backup-specific root cause to repair; the PR improves the demonstrated agent traceback-summary bug rather than guessing at those backup failures. Host storage repair and the unreproduced render crash remain operational/investigation follow-ups.
