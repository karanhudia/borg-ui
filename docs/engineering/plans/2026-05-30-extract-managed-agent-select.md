# Plan: Extract `ManagedAgentSelect` shared component

## Why

We already extracted [`SshConnectionSelect`](../../../frontend/src/components/SshConnectionSelect.tsx)
from three duplicated SSH-picker implementations. The Managed Agent picker has
the same problem — multiple copies of nearly-identical JSX rendering a Select
over `AgentMachine[]` with icon + hostname/name + status dot.

The user wants the same extraction done. Same shape, same target directory,
same AGENTS.md treatment.

## Pattern to follow

`SshConnectionSelect` is the reference. Same conventions:

- Lives in `frontend/src/components/` (not under `wizard/`)
- Wraps `<FormControl>` + `<InputLabel>` + `<Select>` + `<MenuItem>` over
  `RichSelectRow` rows
- Required props: `value`, `onChange`, `agents`, `label`, `emptyMessage`
- Optional: `labelId`, `disabled`, `hideEmptyAlert`, `connectedTooltip`
- Fixed 56px trigger height via:
  ```tsx
  sx={{
    '& .MuiOutlinedInput-root': { height: 56 },
    '& .MuiSelect-select': {
      height: 56,
      boxSizing: 'border-box',
      display: 'flex',
      alignItems: 'center',
    },
  }}
  ```
- Renders compact row when collapsed, full 2-line row in MenuItems when opened
  (`RichSelectRow` already handles this via `secondary` prop)
- Status dot (green when `status === 'online'`, else `text.disabled`)
- Default icon: `Laptop` from `lucide-react`
- Empty state: `<Alert severity="warning">{emptyMessage}</Alert>` unless
  `hideEmptyAlert`

## Proposed API

```ts
export interface ManagedAgentSummary {
  id: number
  name: string
  hostname?: string | null
  status: string
}

interface ManagedAgentSelectProps {
  value: number | ''
  onChange: (id: number) => void
  agents: ManagedAgentSummary[]
  label: string
  emptyMessage: string
  labelId?: string
  disabled?: boolean
  hideEmptyAlert?: boolean
  connectedTooltip?: string
}
```

The `ManagedAgentSummary` type matches the canonical `AgentMachineResponse`
shape from `frontend/src/services/api.ts`. Like `SshConnectionSummary`, keep it
structurally compatible so callers don't have to map.

`renderAgentRow` logic to copy from current `WizardStepLocation.tsx`:

- `displayName = agent.hostname || agent.name`
- `secondary = [metaSecondary, agent.status].filter(Boolean).join(' · ')`
  where `metaSecondary = agent.hostname && agent.name !== agent.hostname ? agent.name : undefined`
- Status dot color: `agent.status === 'online' ? 'success.main' : 'text.disabled'`

## Callsites to migrate

Confirmed locations (scan run 2026-05-30):

1. **`frontend/src/components/wizard/WizardStepLocation.tsx`** — the cleanest
   implementation, already uses `RichSelectRow` via the local `renderAgentRow`
   helper. After extraction, delete `renderAgentRow` and the local
   `StatusDot` helper if `SshConnectionSelect`'s inline dot replaces it.
2. **`frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`**
   — the agent picker for the "Managed agent" source kind. Currently inline
   JSX (similar pattern to the SSH dropdown that was extracted).
3. **Check `frontend/src/components/RepositoryWizard.tsx`,
   `frontend/src/pages/ManagedAgents.tsx`,
   `frontend/src/pages/backup-plans/wizard-step/SourceStep.tsx`** — these
   reference agents/agentMachines but may not all be Select dropdowns. Audit
   each before migrating.

Filtering convention: callers should pre-filter `agents` before passing in
(matches `SshConnectionSelect`'s `availableConnections` pattern in
`WizardStepDataSource.tsx`). The component shouldn't know about
`status !== 'revoked' && status !== 'disabled'` rules — that's policy, not
presentation.

## Tests / stories impact

The agent-locked-repo path in `SourceSelectionDialog` still needs the static
"Locked to {agent}" chip when the constraint applies — that's NOT a dropdown,
keep that branch as-is. The shared component only replaces the actual
unrestricted picker.

Tests that interact with the agent Select via
`getByRole('combobox', { name: /Managed Agent/i })` already work since the
component's `label` prop will populate the same accessible name. Confirm with
a full `npx vitest run` after migration.

## AGENTS.md update

Add a bullet right after the `SshConnectionSelect` entry under "Shared UI
Components":

> - **Managed agent picker** — Use
>   `frontend/src/components/ManagedAgentSelect.tsx` for any dropdown that
>   picks an enrolled managed agent. Required props: `value`, `onChange(id)`,
>   `agents`, `label`, `emptyMessage`. Renders a `RichSelectRow` per option
>   (Laptop icon, hostname-or-name primary, hostname/status secondary, green
>   status dot when `online`) and shows a warning Alert in the empty state.
>   Don't inline another `Select` + `MenuItem` over `AgentMachineResponse[]`
>   — extend or fix this component instead.

## Verification gate (copy from SSH extraction)

1. `npx tsc --noEmit` clean
2. Full `npx vitest run` — no regressions (1998 tests baseline)
3. `npx prettier --check` clean on touched files
4. Manually open both the Repository wizard (Location step, Managed Agent
   selected) and the Backup Plan source dialog (Remote → no — there's no
   parallel for agent here; the agent path goes through the "Managed Agent"
   source kind) and confirm the agent dropdown renders at 56px in both
   filled and empty states.

## Open questions for the next session

- Does the `ManagedAgents.tsx` page list use a Select anywhere, or only cards?
  If only cards, exclude it from the migration scope.
- Should `RestoreWizard.tsx` and `WizardStepRestoreDestination.tsx` be audited
  in this pass? They likely use agent pickers too. Worth one grep before
  starting.
