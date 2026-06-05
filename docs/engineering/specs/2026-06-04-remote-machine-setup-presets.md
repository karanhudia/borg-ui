# Remote Machine Setup Presets Spec

## Problem

The Remote Machines setup flow asks users to manually enter SSH host, user,
port, path, and deployment-mode details even when they are following documented
setup patterns. Borg UI already documents common mappings for generic SSH
servers, BorgBase, Hetzner Storage Box, and NAS targets such as Synology and
Unraid, but the add/deploy dialog does not surface those choices.

That makes first-time setup slower and creates avoidable mistakes around
provider-specific defaults such as Hetzner's port 23 SFTP deployment mode,
BorgBase's `/./repo` path shape, and NAS SSH path prefixes.

## Desired Outcome

The deploy SSH key dialog should offer setup presets for common documented
Remote Machine targets. Selecting a preset applies safe defaults and concise
guidance while keeping every field editable. Users whose target does not match
a preset can keep using the custom/manual path.

## Preset Set

Use the repository docs as the source of truth:

- Linux server, for generic headless SSH hosts.
- BorgBase, for hosted Borg repositories with `/./repo` path syntax.
- Hetzner Storage Box, for Storage Box SSH access on port 23 with SFTP key
  deployment enabled.
- NAS, for Synology, Unraid, and similar devices where SSH/SFTP path mapping
  often differs.

## Design

Add a compact preset section to the top of `DeployKeyDialog`. This is the
"automatically deploy SSH key using password authentication" path, so it is the
best point to prefill host metadata before the user tests or saves a Remote
Machine.

The UI should be operational rather than decorative:

- Use small selectable cards or buttons in a two-column responsive grid.
- Use lucide icons, not emoji.
- Use balanced full-outline selected states and background tint. Do not use
  heavy side accent borders.
- Keep labels and descriptions specific: provider name, what changes, and what
  the user still needs to enter.
- Include a custom setup option that clears back to the normal defaults.
- Selecting a preset applies default `port`, `username`, `use_sftp_mode`,
  `default_path`, `ssh_path_prefix`, and `mount_point` values where the docs
  justify them. Empty string defaults remain empty when the value is user
  specific.
- Preserve manual edits after selection. The preset is a starting point, not a
  locked mode.

The existing raw deploy dialog should be moved to the shared
`ResponsiveDialog` primitive while this surface is being changed.

## Behavior

Selecting a preset updates the current deploy form:

- Linux server: port `22`, user `root`, SFTP deployment enabled, empty default
  path and mount point.
- BorgBase: port `22`, empty user and host, SFTP deployment disabled, default
  path `/./repo`, mount point `borgbase`.
- Hetzner Storage Box: port `23`, empty user and host, SFTP deployment enabled,
  default path `/./borg-repository`, mount point `hetzner`.
- NAS: port `22`, empty user and host, SFTP deployment disabled, empty default
  path, SSH path prefix `/volume1`, mount point `nas`.
- Custom: restore the existing deploy-form defaults.

Password is never filled by a preset. Host remains empty for provider presets
because Borg UI cannot infer private hostnames or provider account IDs.

## Testing

Use TDD for the behavior:

- Add a failing page test that opens the deploy dialog, selects Hetzner Storage
  Box, fills host/user/password, deploys, and verifies the payload includes
  port 23, SFTP mode, `/./borg-repository`, and `hetzner`.
- Add a failing page test that selects NAS, edits the default path manually,
  deploys, and verifies the manual edit is preserved while the preset defaults
  for port, path prefix, mount point, and SFTP mode apply.
- Add a failing page test that selects Custom after another preset and verifies
  the deploy defaults return to the existing blank/port 22/SFTP enabled state.
- Add or update Storybook coverage for the preset selector in the deploy
  dialog.

## Documentation

Update `docs/ssh-keys.md` to mention that Remote Machines provides setup
presets for documented provider and NAS patterns. Do not duplicate the full
provider guide; link the preset behavior back to the existing provider-guide
details.

## Out Of Scope

- Backend API changes.
- Parsing complete SSH URLs into host, user, port, and path.
- Locking fields based on preset selection.
- Adding presets to the edit dialog or manual test dialog.
- Changing repository wizard flow or provider-guide content beyond the short
  Remote Machines note.
