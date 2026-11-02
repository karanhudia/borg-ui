# Announcement prerelease ordering review fix

- [x] Reproduce locale-sensitive ordering of uppercase/lowercase prerelease identifiers and an incorrectly excluded announcement with an uppercase installed version.
- [x] Compare nonnumeric prerelease identifiers with JavaScript string ordering, preserving numeric precedence and build-metadata handling.
- [x] Verify 49 announcement utility, service, hook and component tests; frontend locale parity, typecheck, lint, formatting, build and whitespace checks.

Three regressions failed before the fix. The change only affects version bounds; no component, locale string or navigation changed. Existing build chunk warnings remain.

## Follow-up: complete SemVer validation

- [x] Reproduce malformed core versions and leading-zero numeric identifiers being accepted, and repeated-hyphen prerelease/build identifiers being rejected. Twelve regression cases fail before the fix.
- [x] Require exactly three numeric core parts without leading zeroes and enforce SemVer prerelease/build identifier grammar. Preserve whitespace trimming, optional `v` prefixes and the unknown-input type guard.
- [x] Verify malformed min/max bounds are excluded and valid versions remain eligible. All 63 announcement tests pass, along with locale parity, typecheck, lint, formatting, production build and whitespace checks. The component test run emitted an example.com DNS warning; existing build warnings remain.
