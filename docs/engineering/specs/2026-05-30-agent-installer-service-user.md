# Agent Installer Service User

## Goal

Make managed-agent installs run as the user who installs the agent by default,
so agent filesystem access matches the operator's expectation from SSH-based
remote machines. The agent should be able to read and write the same paths the
installing user can access, without requiring Borg UI users to reason about a
separate `borg-ui-agent` service account for common installs.

## Current Behavior

The Linux installer is run with `sudo`, but it creates and runs the systemd
service as a dedicated `borg-ui-agent` user. That is safer by default, but it
surprises users who install as `karanhudia` and then choose repository paths
under `/home/karanhudia`. Those paths are often not writable by
`borg-ui-agent`, so `borg init` fails with permission errors.

## Desired Behavior

The default installer behavior should be:

- Resolve the service user from `SUDO_USER` when the installer is run through
  `sudo`.
- Fail with a clear message when the installer is run directly as root without
  `SUDO_USER`; the operator should pass `--service-user root` or
  `--service-user USERNAME` intentionally.
- Use the resolved user's primary group.
- Run the systemd service as that user and group.
- Use the resolved user's home directory as the service working directory when
  available.
- Keep the agent virtualenv in `/opt/borg-ui-agent/.venv`.
- Keep the service config in `/etc/borg-ui-agent/config.toml`.
- Own `/etc/borg-ui-agent` by the selected service user and group so the agent
  can read its config and perform local unregister/repair operations.

The installer should support explicit overrides:

- `--service-user current`: run as the installing sudo user. This is the
  default.
- `--service-user borg-ui-agent`: preserve the previous dedicated service-user
  behavior.
- `--service-user root`: run the agent as root. This is an advanced option.
- `--service-user USERNAME`: run as an existing local user.

The installer should not create arbitrary non-default users from a free-form
username. It may continue creating the dedicated `borg-ui-agent` user only when
`--service-user borg-ui-agent` is selected.

## UI Behavior

The Add Agent wizard should keep this simple:

- Add a service-user option in the details step.
- Default label: "Installing user".
- Supporting copy: "The agent can access the same files as the user running the
  installer."
- Advanced options: "Dedicated borg-ui-agent user", "Root".
- Root mode must have clear warning copy because the enrolled agent can perform
  root-level Borg operations on that machine.

The generated install command should include the chosen service-user mode only
when it differs from the default, unless including `--service-user current`
improves clarity in stories and docs.

## Installer Behavior

For `current`:

- Require that the installer is run with `sudo` from a non-root user, or produce
  a clear error telling the operator to pass an explicit `--service-user`.
- Resolve UID, primary group, and home directory via system tools such as `id`
  and `getent passwd`.
- Do not create `/var/lib/borg-ui-agent` as the service home for this mode.
- Create `/etc/borg-ui-agent` owned by the resolved user and primary group.
- Write the systemd unit with `User=<resolved user>`,
  `Group=<resolved group>`, and `WorkingDirectory=<resolved home>`.

For `borg-ui-agent`:

- Keep current behavior: create the system user if missing, create
  `/var/lib/borg-ui-agent`, create `/etc/borg-ui-agent` owned by
  `borg-ui-agent`, and run the service as `borg-ui-agent`.

For `root`:

- Write the systemd unit with `User=root`, `Group=root`, and `WorkingDirectory=/root`
  when available.
- Do not relax filesystem permissions through `chmod` or `chown`.

For explicit existing users:

- Validate the user exists.
- Resolve the primary group and home directory.
- Create `/etc/borg-ui-agent` owned by that user and primary group.
- Use that user and group in the systemd unit.

## Systemd Hardening

The installer-generated unit currently includes:

- `NoNewPrivileges=true`
- `PrivateTmp=true`
- `ReadWritePaths=/etc/borg-ui-agent /var/lib/borg-ui-agent /tmp`

Service-user mode should not depend on broad `chmod` changes. The agent's
filesystem access should come from the chosen OS user. If a systemd sandboxing
directive blocks the chosen user's normal filesystem access, the installer unit
should be adjusted consistently for this feature rather than silently failing.
The installer-generated unit should not add `ProtectHome=read-only` for the
default current-user mode, because that would block the primary behavior this
feature enables.

## Documentation

Update managed-agent docs to explain:

- Default installs run as the sudo-invoking user.
- Agent repositories should be placed somewhere that user can write.
- Dedicated service-user mode is still available for stricter isolation.
- Root mode should be reserved for machines where the agent must back up
  root-owned paths.

## Testing

Backend and agent installer tests should cover:

- Default generated installer script resolves `SUDO_USER`.
- `--service-user current` writes the systemd unit with the resolved user/group.
- `--service-user borg-ui-agent` preserves dedicated-user behavior.
- `--service-user root` writes a root service unit and warning text is present
  in UI/docs.
- Unknown explicit users fail with a clear installer error.
- The Add Agent command builder emits the selected service-user argument.

Frontend tests and Storybook should cover the new Add Agent service-user option,
including the root warning state.
