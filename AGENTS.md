# Agent Instructions

These instructions apply to the entire repository.

## Feature Planning

- For non-trivial features, meaningful behavior changes, and UI changes, use the relevant Superpowers workflow before implementation.
- Use `superpowers:brainstorming` when requirements, product behavior, or UX need shaping; use `superpowers:writing-plans` for multi-step implementation plans.
- Use `superpowers:test-driven-development` for feature and bug-fix implementation, and `superpowers:verification-before-completion` before claiming completion, committing, or pushing.
- Save durable specs and implementation plans under `docs/engineering/specs/` and `docs/engineering/plans/` with dated, slugged filenames such as `YYYY-MM-DD-feature-name.md`.
- Keep process proportional: small mechanical fixes can use a concise inline plan plus targeted tests or verification instead of a full written spec.
- Do not create generic `design.md` files by default; use feature-specific specs only when a written spec is warranted.
- When sidebar tabs, navigation groups, or the main user flow change, update the relevant user docs in the same change so navigation guidance stays current.

## UI Workflow

- All UI-related decisions, design changes, reviews, and implementations must use the `ui-ux-pro-max` skill before proceeding.
- New or changed UI features must add or update a Storybook story that demonstrates the changed state.
- After adding or changing a UI story, run `cd frontend && npm run snapshots` and commit the resulting screenshot files under `frontend/storybook-snapshots/`.
- UI components should stay small and composed from smaller components. When a UI component is added or changed, add or update the component story and snapshot that cover it.
- Schedule-related UI must use the shared schedule controls (`SchedulePicker`,
  `CronExpressionInput`, `CronBuilderDialog`, and the timezone selector rendered
  by `SchedulePicker`) instead of ad hoc cron or timezone text fields.

## UI Preferences

- Do not use heavy left accent borders for cards, panels, alerts, list items, or status surfaces.
- Prefer balanced borders, subtle full-outline treatments, background tinting, icons, chips, or typography for emphasis instead.

## Shared UI Components

Reach for existing shared components before introducing new patterns. The source
of truth is `frontend/src/components/shared/`: if a reusable Borg UI product
primitive already exists there, use it instead of inlining a new dialog, wizard
shell, schedule control, picker, gate, or rich select row.

`shared/` is for Borg UI product primitives that are used across features or are
canonical controls named by project guidance. They may know product concepts
like plans, agents, SSH, schedules, repositories, or paths, but they should not
know a specific page, wizard step, or business flow. Feature components and
wizard-step components stay outside `shared/`.

Current shared inventory:

- `ResponsiveDialog` — required replacement for raw MUI `Dialog`.
- `WizardDialog` and `WizardStepIndicator` — required shell for multi-step wizards.
- `SchedulePicker`, `CronExpressionInput`, and `CronBuilderDialog` — required schedule controls.
- `SshConnectionSelect`, `ManagedAgentSelect`, `DestinationSelect`, and `RichSelectRow` — canonical rich-row select primitives.
- `PathSelectorField`, `PlanGate`, and `CodeEditor` — canonical path picker, plan gate, and code editor primitives.

Use the existing component APIs and extend these files when a shared primitive
needs new behavior. Do not add ad hoc replacements in pages, wizard steps, or
feature components.

Step color keys still come from `WizardStepIndicator.tsx`
(`location`, `source`, `security`, `config`, `review`, `basic`, `schedule`,
`scripts`, `maintenance`). Reuse those keys for visual consistency rather than
introducing new step color tokens.
