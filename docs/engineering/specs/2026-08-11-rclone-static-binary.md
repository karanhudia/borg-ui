# rclone from the Official Static Binary

Status: implemented. Concerns where the runtime base image gets its `rclone`
binary, why the version is what it is, and what was verified before crossing a
large version jump. Companion to `2026-07-27-version-single-source-of-truth.md`,
which rclone now joins as another single-sourced version.

## Problem

The runtime base installed `rclone` from the Debian package (`apt-get install
rclone`). That build lags upstream by years and ships as a `-DEV` build —
bookworm carries **v1.60.1-DEV**. It predates rclone's fix for the OneDrive
chunked-upload bug, where the backend wrongly sent an `Authorization` header on
the upload-session PUT that Microsoft Graph rejects, so cloud-mirror sync to
OneDrive failed with `unauthenticated` on every file (issue #798):

```
ERROR : data/0/257: Failed to copy: unauthenticated: Unauthenticated
NOTICE: data/0/69: Failed to cancel multipart upload: unauthenticated: Unauthenticated
```

The relevant upstream fixes are rclone **v1.65.1** (the auth header on chunked
upload) and **v1.73.0** (`Fix cancelling multipart upload` — the second error
line above), so nothing in the distro's v1.60.x lineage can carry them.

## Decision

Fetch the **official static binary** from `downloads.rclone.org` instead of the
distro package:

- Downloaded and checksum-verified in the `builder` stage, per target arch
  (`amd64`/`arm64` via BuildKit's `TARGETARCH`); only the verified binary is
  copied into the runtime image, so the download/unzip tooling never ships.
- The version is single-sourced in `docker/runtime-base.env` as `RCLONE_VERSION`
  and passed through as a build `ARG`, matching the Borg/borgstore/Python
  discipline; a unit test asserts the env value and the `ARG` default agree.
- CI smoke-tests the result with `rclone version` on both arches, so a broken
  download, wrong arch, or raised glibc floor fails the build before publish.

A future rclone bump is: edit `RCLONE_VERSION` and the two `RCLONE_SHA256_*`
checksums in `Dockerfile.runtime-base`, and bump `RUNTIME_BASE_REVISION` (a
recipe-only change). A version bump without matching checksums fails the build
at the `sha256sum -c` step — a safe failure, not a silent wrong binary.

## Version choice: v1.75.0

The minimal fix for #798 is v1.65.1, but the current stable at time of writing
is **v1.75.0**, and it is the better target: v1.73.0 adds `Fix cancelling
multipart upload`, which addresses the exact second error line in the report.
Pinning current stable also picks up the v1.69.1 follow-up the issue mentions.

## Backward-compatibility assessment (v1.60 → v1.75)

rclone keeps CLI flags and config format stable across releases; the concern
with a jump this size is whether *our* invocation surface changed. That surface
is small and entirely core commands:

- Subcommands: `version`, `listremotes`, `config providers`, `config create`,
  `lsjson`, `about`, `authorize <provider>`, `sync`, `check`.
- Flags: `--config`, `--auth-no-open-browser`, `--transfers`, `--checkers`, plus
  the OAuth/provider flags (`--client-id`, `--client-secret`, `--token`, …)
  passed to `config create` / `authorize`.

Breaking changes in that window, checked against the changelog and weighed
against the surface above:

| Change | Version | Affects us? |
| --- | --- | --- |
| Usage-error exit code `1` → `2` | 1.69.0 | **No** — the service treats any non-zero return as failure; it never branches on a specific code. |
| `bisync` exit `2` → `7`; RC endpoints require auth; unix-socket auth; `--links` made global | 1.69.0 / 1.74.0 | **No** — none of these commands/flags are used. |
| OneDrive Personal: `Fix require sign in`, `Fix cancelling multipart upload`, permission/description fixes | 1.73.0 | **Positive** — all fixes; the multipart-cancel one is exactly the reported error. |
| S3 backend migrated to AWS SDK v2 | 1.68.0 | **Watch** — the one real backend rewrite; rclone-S3 remotes are exercised the same way, and SDK v2 is broadly settled by 1.75, but this is the area to sanity-check on a live S3 remote. |

No signature change to any subcommand we call.

## Test coverage and residual risk

- `tests/unit/test_rclone_service.py` and `test_rclone_repository_service.py`
  lock the argv we build (subcommands, flags, secret redaction). They are unit
  tests with a mocked subprocess: they keep our invocation surface stable but do
  not exercise the binary.
- The new `rclone version` CI smoke test proves the static binary loads and runs
  on both arches — nothing functional beyond that.
- Live cloud behaviour (OneDrive OAuth, S3) is not CI-testable and was not before
  this change either. The natural validation is one real cloud-mirror sync
  against a OneDrive remote (the fix's target) and, given the SDK v2 note, one
  against an S3 remote.
