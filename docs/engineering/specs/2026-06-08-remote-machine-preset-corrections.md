# Remote Machine Preset Corrections Spec

## Problem

The Remote Machines deploy dialog presets added on June 4 are too generic in a
few provider-specific places. Icons inherit wizard step colors instead of
recognizable provider colors, Hetzner Storage Box treats the Borg repository
path as the Remote Machine default browsing path, and the desktop dialog feels
larger than the form needs.

Docs also repeat the same Hetzner default-path conflation, which can mislead
users configuring a Storage Box connection before they create or import a Borg
repository.

## Desired Outcome

The deploy dialog should remain an operational form, but each preset should
carry provider-aware examples and visual identity:

- provider icons use stable brand colors;
- selecting a preset updates host and username placeholders as well as editable
  defaults;
- Hetzner uses `/home` as the Remote Machine default path while docs keep
  `/./borg-repository` as the repository path example;
- the desktop modal uses a smaller width that matches the field count;
- docs and Storybook show the corrected preset state.

## Preset Details

Provider source checks:

- Hetzner Storage Box docs show extended SSH/Borg access on port `23`, host
  shape `uXXXXX.your-storagebox.de`, sub-account username/host variants, SFTP
  operations under `/home`, and Borg repository examples using
  `/./borg-repository`.
- BorgBase docs show repository URL shape
  `ssh://mmvz9gp4@mmvz9gp4.repo.borgbase.com/./repo`.
- Simple Icons brand data gives icon colors for the current icon set:
  Hetzner `#D50C2D`, BorgBackup `#00DD00`, Linux `#FCC624`, and Synology
  `#B5B5B6`.

Corrected presets:

| Preset | Host placeholder | Username placeholder | Port | Default path | SSH path prefix | Mount point | Notes |
| --- | --- | --- | ---: | --- | --- | --- | --- |
| Custom | `backup.example.com` | `backup` | 22 | blank | blank | blank | Standard editable defaults. |
| Linux server | `backup.example.com` | `backup` | 22 | `/home/backup` | blank | `linux-server` | A non-root dedicated backup user is safer than preselecting `root`. |
| BorgBase | `mmvz9gp4.repo.borgbase.com` | `mmvz9gp4` | 22 | `/./repo` | blank | `borgbase` | Keeps the hosted repo path shape. |
| Hetzner Storage Box | `u123456.your-storagebox.de` | `u123456` | 23 | `/home` | blank | `hetzner-storage-box` | Remote Machine browsing starts at writable Storage Box home; repository docs keep `/./borg-repository`. |
| NAS | `diskstation.local` | `backup` | 22 | `/backups` | `/volume1` | `nas` | Keeps Synology-style SSH prefix mapping visible but editable. |

Host, username, and password values remain user-entered. Preset selection only
changes placeholders and safe editable defaults.

## UI Design

Keep `DeployKeyDialog` composed from `ResponsiveDialog` and
`RichSelectRow`. Use a `maxWidth="sm"` desktop dialog with full width so the
modal is narrower while the mobile drawer behavior remains unchanged. Keep the
preset control as a single rich select instead of returning to card grids,
because it is compact and consistent with shared Borg UI select patterns.

Render provider icons as single-color brand marks in a subtle icon square. Do
not use heavy side borders, large decorative cards, or extra explanatory text
inside the dialog.

## Acceptance Criteria

- Preset icon colors use the provider brand values above, including Hetzner
  red.
- Selecting each preset updates the preset-specific placeholders and editable
  default fields.
- Hetzner deploy payload uses port `23`, SFTP deployment on, default path
  `/home`, no SSH path prefix, and mount point `hetzner-storage-box`.
- The dialog desktop width is `sm` and remains full-width within that limit.
- Storybook includes a corrected Hetzner preset state.
- Docs distinguish Remote Machine default browsing path from repository path
  for Hetzner and keep BorgBase `/./repo` guidance intact.

## Validation

- Add or update failing Vitest expectations first for preset values, icon
  colors, placeholders, and dialog sizing.
- Run the targeted Vitest file after implementation.
- Run locale, typecheck, lint, and build commands from `frontend/`.
- Run a local UI walkthrough for the Remote Machines deploy dialog.

## Out Of Scope

- Parsing provider SSH URLs into fields.
- Adding new presets beyond the current set.
- Backend API changes.
- Redesigning the Remote Machines page outside the deploy dialog.
