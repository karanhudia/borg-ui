# Borg Installer Management Spec

## Goal

Make managed-agent installation install and verify Borg 1 by default, expose
advanced Borg install choices in the Add Agent flow, and keep agent capability
reporting clear enough for Borg UI to warn when an agent cannot run Borg.

## User Model

An admin enrolls a Linux or Raspberry Pi managed agent from Borg UI. Most users
want the one-command installer to make the agent usable for Borg 1 repositories
without extra package work. Advanced users can choose Borg 2 or self-managed
Borg, but Borg UI must not silently upgrade or replace an existing system
`borg` binary.

## Product Direction

The ticket text is the approved product direction for this unattended run. The
installer should keep Borg 1 as the default and treat Borg 2 as advanced,
beta/experimental behavior. The setup UI should use radio-style choices in the
existing Add Agent wizard rather than a separate installer page.

UI/UX Pro Max guidance for this change: keep the form quiet and operational,
use progressive disclosure, high-contrast labels, balanced outlines, visible
focus states, Lucide icons, and existing MUI components. Avoid heavy left accent
borders and avoid marketing-style treatment in the setup dialog.

## Scope

In scope:

- `GET /agent/install.sh` usage and shell logic for `--borg-version 1`,
  `--borg-version 2`, `--borg-version both`, and `--skip-borg-install`;
- preserving `--version` as the Borg UI agent source ref while preventing
  `/etc/os-release` from overwriting it;
- Borg 1 install/verify as `borg`, without replacing an existing `borg`;
- Borg 2 install/verify as `borg2`, with an isolated install path and no
  replacement of an existing `borg2`;
- agent binary detection payloads that include path, version, major, and
  install source;
- Managed Agents UI warning when an agent reports no usable Borg binary;
- Add Agent radio choices and generated command flags;
- Storybook coverage and snapshots for the changed setup state.

Out of scope:

- macOS or Windows installer support;
- automatic Borg upgrades;
- changing Borg 2 repository feature licensing;
- broad repository creation redesign. Existing repository creation already pins
  `repositories.borg_version`; this change must avoid weakening that behavior.

## Acceptance Criteria

- The generated installer command defaults to Borg 1 and can generate Borg 2,
  both, or skip-install modes.
- The installer accepts the requested Borg mode, installs only missing selected
  binaries, verifies selected binaries before registration, and exits before
  registration if verification fails.
- `borg` is reserved for Borg 1 and `borg2` is reserved for Borg 2.
- Existing `borg` or `borg2` binaries are verified and reused; the installer does
  not overwrite them.
- The agent source ref remains `main` by default after sourcing
  `/etc/os-release`.
- Agent registration/heartbeat reports detected Borg binary path, version,
  major version, and install source.
- Managed Agents shows a clear warning on agent cards with no usable Borg
  binary.
- Borg 2 setup options are labelled beta/experimental and are not the default.

## Validation

- Backend targeted tests for installer script content, shell syntax, the
  `/etc/os-release` regression, and Borg detection payloads.
- Frontend targeted tests for Add Agent default command generation, Borg 2
  advanced selection, and no-Borg warning rendering.
- Storybook story and snapshot for the Borg install selection UI.
- Repository policy checks: `ruff check app tests`,
  `ruff format --check app tests`, relevant `pytest`, frontend locales,
  typecheck, lint, build, snapshots, runtime/script validation, and
  `git diff --check`.
