# Frontend I18n Hardcoded Strings Plan

## Goal

Remove the remaining user-facing English literals identified in issue #775 from
application components and pages, and make locale use regressions visible in
CI.

## Scope

- Replace user-facing literals in `frontend/src/components` and
  `frontend/src/pages` with translation keys.
- Add matching English, German, Italian, and Spanish messages with interpolation
  where values are dynamic.
- Centralize common action labels when they are reused.
- Add scoped linting that rejects new user-facing literal strings without
  applying it to tests, stories, data, command text, or non-UI code.

## Delivery

Keep this as one PR with logical commits by surface:

1. Managed Agents.
2. API tokens and authentication.
3. Shared wizard and layout components.
4. Remaining pages and components.
5. Locale guard and full verification.

## Verification

- Targeted Vitest coverage for changed components.
- `npm run check:locales`.
- Frontend lint, typecheck, and build.
- Run the literal-string guard and inspect its exceptions for false positives.
