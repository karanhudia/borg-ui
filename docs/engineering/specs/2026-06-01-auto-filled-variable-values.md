# Auto-Filled Variable Value Disclosure

## Status

Drafted for BOR-111 on June 1, 2026.

## Context

The backup-plan Scripts step shows database source scripts separately from
plan-level scripts. When a database source supplies script parameters, the row
currently shows only the `Auto-filled from source` chip. That tells the user
the values came from the selected source, but it does not let the user verify
which value will be passed to the script.

The affected UI is
`frontend/src/pages/backup-plans/wizard-step/ScriptsStep.tsx`. Existing tests
and stories already cover the database source script summary state.

## Design Inputs

- Keep the Borg UI product surface quiet and operational: no decorative cards,
  no heavy left accents, no marketing-style treatment.
- Use a discoverable value affordance that works with hover and keyboard focus.
- Preserve the existing `Auto-filled from source` chip so users still understand
  the parameter source.
- Show only non-empty parameter values. Empty parameter maps should keep the
  existing chip with no misleading value list.

## Goals

- Users can verify auto-filled pre/post script parameter names and values from
  the Scripts step before continuing.
- The value disclosure is compact and visually subordinate to the selected
  database and script names.
- Keyboard users can focus the affordance and read the same value information
  exposed to pointer users.
- The changed state is covered by a focused component test and Storybook story.

## Non-Goals

- Editing auto-filled values in the Scripts step.
- Changing backend script parameter generation.
- Redesigning the full backup-plan wizard scripts flow.

## Approach

Add a small tooltip affordance next to the `Auto-filled from source` chip when a
database source row has non-empty `pre_backup_script_parameters` or
`post_backup_script_parameters`.

The tooltip title will list `KEY=value` pairs, grouped by pre and post script
when both exist. The trigger will be a focusable, icon-only MUI `IconButton`
with an accessible label. The icon appears only when there are values to verify;
rows with empty parameter maps continue to render only the existing chip.

The visible row copy remains unchanged except for the small verification icon.
This avoids implying that values are editable or user-entered.

## Acceptance Criteria

- Auto-filled database source script rows expose non-empty resolved parameter
  values through a hover and keyboard-focus tooltip.
- The existing `Auto-filled from source` chip remains visible.
- Rows with empty or missing auto-filled parameter maps do not show an empty
  value tooltip.
- The focused component test proves values are discoverable and empty values
  are not exposed.
- The Storybook story includes auto-filled values so Argos can capture the
  changed state in CI.

## Validation

- `cd frontend && npm test -- --run src/pages/backup-plans/__tests__/ScriptsStep.test.tsx`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- Local UI walkthrough of the Scripts step Storybook state.
