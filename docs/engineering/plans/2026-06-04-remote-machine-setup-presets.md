# Remote Machine Setup Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add setup presets to the deploy SSH key Remote Machine dialog so documented provider and NAS defaults can be applied without removing manual editing.

**Architecture:** Keep the feature frontend-only. Add typed preset metadata beside the SSH connection form code, render it inside `DeployKeyDialog` using MUI plus lucide icons, update locale strings and Storybook, and prove behavior with Vitest page tests before implementation.

**Tech Stack:** React, TypeScript, MUI, lucide-react, i18next JSON locales, Vitest, Testing Library, Storybook.

---

## Task 1: Failing Preset Tests

**Files:**
- Modify: `frontend/src/pages/__tests__/SSHConnectionsSingleKey.test.tsx`

- [ ] **Step 1: Add Hetzner preset payload test**

  Add a test in the existing `SSHConnectionsSingleKey` suite:

  ```typescript
  it('applies Hetzner Storage Box defaults when deploying the system key', async () => {
    const user = userEvent.setup()
    const { sshKeysAPI } = await import('../../services/api')

    renderWithProviders(<SSHConnectionsSingleKey />)

    await screen.findByText('Remote Machines')
    await user.click(
      screen.getByRole('button', {
        name: /automatically deploy ssh key using password authentication/i,
      })
    )
    await user.click(screen.getByRole('button', { name: /Hetzner Storage Box/i }))
    await user.type(screen.getByLabelText(/^host$/i), 'u123456.your-storagebox.de')
    await user.type(screen.getByLabelText(/^username$/i), 'u123456')
    await user.type(screen.getByLabelText(/^password$/i), 'secret')
    await user.click(screen.getByRole('button', { name: /^deploy key$/i }))

    await waitFor(() => {
      expect(sshKeysAPI.deploySSHKey).toHaveBeenCalledWith(7, {
        host: 'u123456.your-storagebox.de',
        username: 'u123456',
        port: 23,
        password: 'secret',
        use_sftp_mode: true,
        default_path: '/./borg-repository',
        ssh_path_prefix: '',
        mount_point: 'hetzner',
      })
    })
  })
  ```

- [ ] **Step 2: Add NAS manual-edit preservation test**

  Add a second test that selects NAS, fills host/user/password, changes
  `Default Path (Optional)` to `/backups/repo`, deploys, and expects:

  ```typescript
  {
    host: 'nas.local',
    username: 'backup',
    port: 22,
    password: 'secret',
    use_sftp_mode: false,
    default_path: '/backups/repo',
    ssh_path_prefix: '/volume1',
    mount_point: 'nas',
  }
  ```

- [ ] **Step 3: Add custom reset test**

  Add a third test that selects BorgBase, then selects Custom setup. Assert the
  port is back to `22`, SFTP mode is checked, and default path and mount point
  fields are empty.

- [ ] **Step 4: Run red test command**

  Run:

  ```bash
  cd frontend && npm run test -- src/pages/__tests__/SSHConnectionsSingleKey.test.tsx --run -t "preset|Hetzner|NAS|Custom"
  ```

  Expected before implementation: tests fail because preset buttons and
  associated defaults do not exist.

## Task 2: Preset Metadata And Selector

**Files:**
- Create: `frontend/src/pages/ssh-connections-single-key/connectionPresets.ts`
- Modify: `frontend/src/pages/ssh-connections-single-key/dialogs/DeployKeyDialog.tsx`

- [ ] **Step 1: Add preset metadata**

  Create `connectionPresets.ts` with:

  ```typescript
  import type { LucideIcon } from 'lucide-react'
  import { Database, HardDrive, Server, Settings2, Warehouse } from 'lucide-react'
  import type { DeployConnectionPayload } from './types'

  export type RemoteMachineSetupPresetId = 'custom' | 'linux' | 'borgbase' | 'hetzner' | 'nas'

  export interface RemoteMachineSetupPreset {
    id: RemoteMachineSetupPresetId
    icon: LucideIcon
    defaults: Partial<DeployConnectionPayload>
  }

  export const remoteMachineSetupPresets: RemoteMachineSetupPreset[] = [
    { id: 'custom', icon: Settings2, defaults: {} },
    {
      id: 'linux',
      icon: Server,
      defaults: {
        username: 'root',
        port: 22,
        use_sftp_mode: true,
        default_path: '',
        ssh_path_prefix: '',
        mount_point: '',
      },
    },
    {
      id: 'borgbase',
      icon: Database,
      defaults: {
        port: 22,
        use_sftp_mode: false,
        default_path: '/./repo',
        ssh_path_prefix: '',
        mount_point: 'borgbase',
      },
    },
    {
      id: 'hetzner',
      icon: Warehouse,
      defaults: {
        port: 23,
        use_sftp_mode: true,
        default_path: '/./borg-repository',
        ssh_path_prefix: '',
        mount_point: 'hetzner',
      },
    },
    {
      id: 'nas',
      icon: HardDrive,
      defaults: {
        port: 22,
        use_sftp_mode: false,
        default_path: '',
        ssh_path_prefix: '/volume1',
        mount_point: 'nas',
      },
    },
  ]
  ```

- [ ] **Step 2: Render preset buttons**

  In `DeployKeyDialog`, keep local `selectedPreset` state. Render the presets
  above the host field as MUI `ButtonBase` or `CardActionArea` items in a
  responsive grid. Each item must have:

  - `aria-pressed={selectedPreset === preset.id}`;
  - icon in a 32px square;
  - localized title, description, and short defaults line;
  - full-outline selected state using `theme.palette.primary.main` and
    `alpha(theme.palette.primary.main, 0.08)`;
  - `cursor: 'pointer'` and visible focus styles.

- [ ] **Step 3: Apply defaults without locking fields**

  On selection:

  ```typescript
  const nextForm =
    preset.id === 'custom'
      ? createConnectionForm()
      : { ...connectionForm, ...preset.defaults }
  setConnectionForm(nextForm)
  setHostError(undefined)
  setSelectedPreset(preset.id)
  ```

  Do not overwrite password. Do not fill host for any preset.

- [ ] **Step 4: Replace raw Dialog with ResponsiveDialog**

  Import `ResponsiveDialog` from `../../../components/shared/ResponsiveDialog`
  and pass `DialogActions` through the `footer` prop. Keep desktop `maxWidth`
  and `fullWidth` behavior.

## Task 3: Path Prefix Field And Locale Strings

**Files:**
- Modify: `frontend/src/pages/ssh-connections-single-key/dialogs/DeployKeyDialog.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] **Step 1: Expose SSH path prefix in deploy form**

  Add a TextField after default path:

  ```tsx
  <TextField
    label={t('sshConnections.deployDialog.sshPathPrefix')}
    fullWidth
    value={connectionForm.ssh_path_prefix}
    onChange={(e) => setConnectionForm({ ...connectionForm, ssh_path_prefix: e.target.value })}
    placeholder="/volume1"
    helperText={t('sshConnections.deployDialog.sshPathPrefixHelper')}
    InputLabelProps={{ shrink: true }}
  />
  ```

- [ ] **Step 2: Add English locale keys**

  Under `sshConnections.deployDialog`, add:

  ```json
  "setupPreset": "Setup preset",
  "setupPresetHint": "Pick a documented setup to prefill defaults. You can edit every field before deploying.",
  "presetCustom": "Custom setup",
  "presetCustomDescription": "Start from the standard SSH defaults.",
  "presetCustomDefaults": "Port 22, SFTP deployment enabled",
  "presetLinux": "Linux server",
  "presetLinuxDescription": "Headless server or VM with normal SSH access.",
  "presetLinuxDefaults": "root user, port 22",
  "presetBorgBase": "BorgBase",
  "presetBorgBaseDescription": "Hosted Borg repository using the /./repo path shape.",
  "presetBorgBaseDefaults": "Port 22, SFTP deployment off, default path /./repo",
  "presetHetzner": "Hetzner Storage Box",
  "presetHetznerDescription": "Storage Box repository over Hetzner's extended SSH service.",
  "presetHetznerDefaults": "Port 23, SFTP deployment on, default path /./borg-repository",
  "presetNas": "NAS",
  "presetNasDescription": "Synology, Unraid, or similar NAS with SSH path mapping.",
  "presetNasDefaults": "Port 22, SFTP deployment off, SSH path prefix /volume1",
  "sshPathPrefix": "SSH Path Prefix (Optional)",
  "sshPathPrefixHelper": "Prefix added when Borg needs a different SSH path than the browsing path, for example /volume1 on Synology."
  ```

  Add equivalent keys to German, Spanish, and Italian using clear direct
  translations.

## Task 4: Storybook

**Files:**
- Create: `frontend/src/pages/ssh-connections-single-key/dialogs/DeployKeyDialog.stories.tsx`

- [ ] **Step 1: Add deploy dialog story**

  Add a story titled `Remote Machines/DeployKeyDialog` with a controlled wrapper
  that renders the dialog open and lets Storybook interactions select presets.
  Use English locale text through the component's `t` prop from `i18next`.

- [ ] **Step 2: Add selected preset variant**

  Add a story variant that starts with the Hetzner defaults applied in
  `connectionForm`, so Argos has a stable selected/defaults visual state.

## Task 5: Docs

**Files:**
- Modify: `docs/ssh-keys.md`

- [ ] **Step 1: Add setup presets note**

  Add a short section near the Remote Machine setup guidance:

  ```markdown
  ## Setup Presets

  The deploy dialog includes setup presets for Linux servers, BorgBase,
  Hetzner Storage Box, and NAS targets such as Synology and Unraid. Presets
  only prefill editable defaults like port, deployment mode, default path,
  SSH path prefix, and mount point. Review provider-specific path details in
  [Provider Guides](provider-guides) before saving.
  ```

## Task 6: Green Tests And Required Validation

**Files:**
- Inspect: `.github/PULL_REQUEST_TEMPLATE.md`

- [ ] **Step 1: Run targeted test green**

  Run:

  ```bash
  cd frontend && npm run test -- src/pages/__tests__/SSHConnectionsSingleKey.test.tsx --run -t "preset|Hetzner|NAS|Custom"
  ```

- [ ] **Step 2: Run frontend required checks**

  Run:

  ```bash
  cd frontend && npm run check:locales
  cd frontend && npm run typecheck
  cd frontend && npm run lint
  cd frontend && npm run build
  ```

- [ ] **Step 3: Run visual proof**

  Prefer:

  ```bash
  cd frontend && npm run snapshots
  ```

  If full snapshots are unavailable in-session, run Storybook or a focused
  local UI walkthrough against `DeployKeyDialog.stories.tsx` and record the
  exact evidence in the workpad.

- [ ] **Step 4: Publish**

  Commit the implementation, push the branch, create or update the PR using
  `.github/PULL_REQUEST_TEMPLATE.md`, attach the PR to Linear, ensure the PR
  has the `symphony` label, run the feedback sweep, and move the issue to
  Human Review only after checks are green.
