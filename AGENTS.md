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

Reach for existing shared components before introducing new patterns. Adding a raw MUI `Dialog` or a hand-rolled step indicator is almost always wrong — these patterns already exist and are used by the rest of the app.

- **Modals / dialogs** — Always use `frontend/src/components/ResponsiveDialog.tsx` instead of raw `@mui/material` `Dialog`. It renders a normal centered dialog on desktop and a bottom-anchored `SwipeableDrawer` (with drag handle, close button, sticky footer, safe-area inset) on mobile (`< md`). Place action buttons in the `footer` prop so they stay sticky above the safe area on mobile rather than scrolling away with the body.
- **Multi-step wizards** — Use `frontend/src/components/wizard/WizardDialog.tsx`, which composes `ResponsiveDialog` + `WizardStepIndicator`. Pass `steps` (array of `{ key, label, icon }`), `currentStep`, optional `onStepClick` (gate it to completed steps if you want to prevent jumping forward), and the action bar via `footer`. Do not build a custom chip row or stepper — `WizardStepIndicator` already provides the desktop tab row and mobile compact circle row used by `RepositoryWizard`, `ScheduleWizard`, and `AddAgentDialog`.
- **Step color keys** — The `key` on each step picks a color from the palette in `WizardStepIndicator.tsx` (`location`, `source`, `security`, `config`, `review`, `basic`, `schedule`, `scripts`, `maintenance`). Reuse these keys for visual consistency with other wizards rather than introducing new color tokens.
- **SSH connection picker** — Use `frontend/src/components/SshConnectionSelect.tsx` for any dropdown that lets the user pick an SSH connection. Required props: `value`, `onChange(id)`, `connections`, `label`, `emptyMessage`. The component renders a `RichSelectRow` per option (Cloud icon, `user@host` primary, `Port X • mount_point | default_path` secondary, green status dot when connected) and shows a warning Alert in the empty state (or returns `null` when `hideEmptyAlert` is set). Used by the Repository wizard's Location and Data Source steps and by the Backup Plan source dialog. Do not inline another `Select` + `MenuItem` over `SSHConnection[]` — extend or fix this component instead.
- **Managed agent picker** — Use `frontend/src/components/ManagedAgentSelect.tsx` for any dropdown that picks an enrolled managed agent. Required props: `value`, `onChange(id)`, `agents`, `label`, `emptyMessage`. Renders a `RichSelectRow` per option (Laptop icon, hostname-or-name primary, hostname/status secondary, green status dot when `online`) and shows a warning Alert in the empty state (or returns `null` when `hideEmptyAlert` is set). Don't inline another `Select` + `MenuItem` over `AgentMachineResponse[]` — extend or fix this component instead.
- **Destination picker**: Use `frontend/src/components/DestinationSelect.tsx` for any dropdown that picks one of a small set of static rich-row options (icon + label + description), like the Repository wizard's "Where should backups be stored?" picker and the Backup Plan source dialog's source kind picker. Required props: `value`, `onChange(key)`, `destinations`, `label`. Each destination is `{ key, icon, label, description, disabled? }`; the component renders the same 56px outlined Select + `RichSelectRow` shape as the SSH and Managed Agent pickers. Don't inline another `Select` + `MenuItem` + `RichSelectRow` block for a static option list. Use this component instead.
- **Rich select rows** — Inside any rich MUI `Select` (icon + 2-line text + optional indicator), use `frontend/src/components/wizard/RichSelectRow.tsx` instead of hand-rolled `Box`/`Stack` compositions. It keeps the icon size, gap, line-height, and truncation behavior consistent with the rest of the app.
