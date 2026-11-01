# Announcement prerelease ordering review fix

- [x] Reproduce locale-sensitive ordering of uppercase/lowercase prerelease identifiers and an incorrectly excluded announcement with an uppercase installed version.
- [x] Compare nonnumeric prerelease identifiers with JavaScript string ordering, preserving numeric precedence and build-metadata handling.
- [x] Verify 49 announcement utility, service, hook and component tests; frontend locale parity, typecheck, lint, formatting, build and whitespace checks.

Three regressions failed before the fix. The change only affects version bounds; no component, locale string or navigation changed. Existing build chunk warnings remain.
