# SSH-key decryption failures

**Goal:** Replace the archive-sync `InvalidToken` crash with a failed operation that explains how to recover an unreadable saved SSH key.

**Evidence:** Dashboard fingerprint `3463483cec131121` reports four archive-sync failures on one 2.4.1 installation. Its traceback reaches `write_ssh_key_to_tempfile`; both normal and compatibility decryption fail. Existing disaster-recovery documentation explains that changing the app secret makes saved credentials unreadable. The report cannot establish whether the stored token is malformed or its encryption key changed.

**Scope:** Keep decryption strict. Do not accept plaintext, change encryption, replace credentials, or retry using no SSH key. Preserve normal and legacy decryption behavior. Keep failure output free of private-key contents and ciphertext.

## Plan

- [x] Reproduce malformed, empty, and wrong-key failures using real decryption and verify no temporary private-key file is created.
- [x] Raise a specific decryption exception with recovery guidance after supported decryption attempts fail.
- [x] Reproduce the archive-sync path using a real saved SSH key. Return a failed outcome for this specific configuration failure, preserving existing archive records and metadata; do not run Borg.
- [x] Add recovery documentation and run SSH, Borg-env, index-executor, security, and nearest maintenance tests, backend lint/format, and the docs build.

This improves failure handling and recovery guidance; the affected installation still needs the original app secret restored or its SSH key re-imported.

## Verification

- Baseline: 104 SSH utility, Borg-environment, and index-executor tests passed.
- All four new decryption and archive-sync regressions failed before implementation and passed after it.
- 343 tests passed across SSH utility, Borg-environment, index-executor, SSH maintenance, security, SSH API, error reporter, and runner suites; existing warnings remain.
- Full backend Ruff lint and format checks passed (803 files); the documentation build and diff whitespace checks passed.
