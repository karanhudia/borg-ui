# Remote Machine Preset Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct Remote Machine deploy presets so provider colors, placeholders, defaults, modal sizing, docs, and Storybook match provider-specific setup details.

**Architecture:** Keep the work frontend/docs-only. Extend the existing typed preset metadata, render brand colors and placeholder values through `DeployKeyDialog`, keep the existing shared `ResponsiveDialog` and `RichSelectRow` composition, and update docs where the prior Hetzner path guidance conflated browsing and repository paths.

**Tech Stack:** React, TypeScript, MUI, react-icons, i18next JSON locales, Vitest, Testing Library, Storybook, Markdown docs.

---

### Task 1: Failing Preset Tests

**Files:**
- Modify: `frontend/src/pages/__tests__/SSHConnectionsSingleKey.test.tsx`

- [ ] **Step 1: Update the Hetzner payload expectation**

  Change the existing Hetzner deploy test to expect:

  ```typescript
  default_path: '/home',
  mount_point: 'hetzner-storage-box',
  ```

  Keep host `u123456.your-storagebox.de`, username `u123456`, port `23`,
  password `secret`, SFTP deployment enabled, and empty SSH path prefix.

- [ ] **Step 2: Add placeholder assertions**

  After selecting Hetzner, assert host and username placeholders:

  ```typescript
  expect(within(dialog).getByLabelText(/^host$/i)).toHaveAttribute(
    'placeholder',
    'u123456.your-storagebox.de'
  )
  expect(within(dialog).getByLabelText(/^username$/i)).toHaveAttribute(
    'placeholder',
    'u123456'
  )
  ```

- [ ] **Step 3: Update preset icon color expectations**

  Replace wizard-step color assertions with brand-color assertions:

  ```typescript
  expect(selectedIcon).toHaveStyle({ color: '#D50C2D' })
  ```

  Add loop expectations from a metadata map for custom, linux, borgbase,
  hetzner, and nas.

- [ ] **Step 4: Add compact dialog assertion**

  In `DeployDialogHarness`, assert the dialog paper class includes the MUI
  `sm` max-width class:

  ```typescript
  expect(dialog.closest('.MuiDialog-paper')).toHaveClass('MuiDialog-paperWidthSm')
  ```

- [ ] **Step 5: Run red test command**

  Run:

  ```bash
  cd frontend && npm test -- SSHConnectionsSingleKey.test.tsx -t "Hetzner|preset icons|compact"
  ```

  Expected before implementation: failures for the old Hetzner path, old icon
  color source, missing placeholders, and `md` modal width.

### Task 2: Preset Metadata And Dialog Rendering

**Files:**
- Modify: `frontend/src/pages/ssh-connections-single-key/connectionPresets.ts`
- Modify: `frontend/src/pages/ssh-connections-single-key/dialogs/DeployKeyDialog.tsx`

- [ ] **Step 1: Extend preset metadata**

  Add `brandColor`, `hostPlaceholder`, and `usernamePlaceholder` to
  `RemoteMachineSetupPreset`. Use the values from the spec table:

  ```typescript
  brandColor: '#D50C2D',
  hostPlaceholder: 'u123456.your-storagebox.de',
  usernamePlaceholder: 'u123456',
  ```

- [ ] **Step 2: Correct preset defaults**

  Update defaults:

  ```typescript
  linux: { username: '', default_path: '/home/backup', mount_point: 'linux-server' }
  hetzner: { default_path: '/home', mount_point: 'hetzner-storage-box' }
  nas: { default_path: '/backups' }
  ```

  Keep provider-specific values editable and keep password untouched.

- [ ] **Step 3: Render brand colors**

  In `renderPresetRow`, replace `getWizardStepColor(...)` with
  `preset.brandColor` and keep the icon inside the existing `RichSelectRow`
  icon slot.

- [ ] **Step 4: Render dynamic placeholders**

  Resolve the selected preset and pass its `hostPlaceholder` to `SshHostField`
  and its `usernamePlaceholder` to the username `TextField`.

- [ ] **Step 5: Reduce desktop dialog width**

  Change `ResponsiveDialog` from `maxWidth="md"` to `maxWidth="sm"`.

### Task 3: Locale And Storybook Updates

**Files:**
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`
- Modify: `frontend/src/pages/ssh-connections-single-key/dialogs/DeployKeyDialog.stories.tsx`

- [ ] **Step 1: Update English preset copy**

  Change English defaults strings to match corrected values:

  ```json
  "presetLinuxDefaults": "Port 22, default path /home/backup",
  "presetHetznerDefaults": "Port 23, SFTP deployment on, default path /home",
  "presetNasDefaults": "Port 22, default path /backups, SSH path prefix /volume1"
  ```

- [ ] **Step 2: Mirror copy in shipped locales**

  Update German, Spanish, and Italian JSON strings with equivalent corrected
  path values. Preserve existing wording style where possible.

- [ ] **Step 3: Update Storybook Hetzner args**

  Change `HetznerDefaults` and `PresetIconColors` initial form to:

  ```typescript
  default_path: '/home',
  mount_point: 'hetzner-storage-box',
  ```

### Task 4: Docs Updates

**Files:**
- Modify: `docs/ssh-keys.md`
- Modify: `docs/provider-guides.md`

- [ ] **Step 1: Update setup preset docs**

  Mention that presets prefill placeholders and editable defaults, not
  passwords or private account IDs.

- [ ] **Step 2: Fix Hetzner default path guidance**

  Change Hetzner Remote Machine examples to:

  ```text
  Default path: /home
  Repository path: /./borg-repository
  ```

  Add one sentence explaining that `/home` is the browsing/default path while
  `/./borg-repository` remains the Borg repository path syntax.

- [ ] **Step 3: Preserve BorgBase guidance**

  Leave BorgBase `/./repo` repository/default path guidance unchanged.

### Task 5: Validation And Handoff

**Files:**
- No additional source changes expected.

- [ ] **Step 1: Run targeted tests**

  ```bash
  cd frontend && npm test -- SSHConnectionsSingleKey.test.tsx -t "Hetzner|preset icons|compact"
  ```

- [ ] **Step 2: Run required frontend gates**

  ```bash
  cd frontend && npm run check:locales
  cd frontend && npm run typecheck
  cd frontend && npm run lint
  cd frontend && npm run build
  ```

- [ ] **Step 3: Run UI walkthrough**

  Launch the app or Storybook locally, open the Remote Machines deploy dialog,
  select Hetzner/BorgBase/NAS, and record the visible placeholders/defaults and
  compact modal width in the Linear workpad.

- [ ] **Step 4: Commit, push, and PR**

  Commit source/docs/spec/plan changes, push the branch, create/update the PR
  with `.github/PULL_REQUEST_TEMPLATE.md`, add the `symphony` GitHub label,
  sweep all PR comments/checks, update the workpad handoff note, and move the
  issue to Human Review only when checks are green.
