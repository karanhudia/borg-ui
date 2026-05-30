# Managed Agent Reinstall Action Spec

## Problem

Managed Agents supports a first-time install flow that creates an enrollment
token and shows a one-line installer command. Existing enrolled agents do not
have a reinstall/update path in the fleet cards. Re-running the first-time
command is the wrong model because it requires a new token and registration.

## Desired Outcome

Each existing agent card exposes a reinstall action. The action opens a focused
dialog with a copyable reinstall command that can be run on that already
enrolled machine. The command updates the installed `borg-ui-agent` package and
restarts the systemd service while preserving `/etc/borg-ui-agent/config.toml`.

## Design

Use the existing public `/agent/install.sh` script and add an explicit
`--reinstall` mode. Initial installs continue to require `--server`, `--token`,
and `--name`. Reinstall mode requires an existing config file and skips
registration. It updates the virtualenv package from the configured Git ref,
validates the service setup, reloads systemd, enables the unit, and restarts the
agent service.

The Managed Agents page keeps the current Add Agent flow unchanged. Agent cards
gain a compact icon action labelled "Reinstall agent". Selecting it opens a
dialog with the target agent name, brief copy explaining that no enrollment
token is required, and a copyable command:

```bash
curl -fsSL https://borg-ui.example.com/agent/install.sh | sudo bash -s -- --reinstall
```

The reinstall command intentionally does not include token, name, or register
arguments. Reinstall mode defaults to preserving Borg binaries by skipping Borg
installation unless an operator manually adds an existing installer
`--borg-version` flag.

## Acceptance Criteria

- Existing managed agent cards expose a reinstall action.
- The reinstall action opens a copyable script/command for that agent.
- The reinstall command contains `--reinstall` and no enrollment token or
  registration arguments.
- `/agent/install.sh --reinstall` preserves existing agent registration and does
  not call `borg-ui-agent register`.
- First-time Add Agent install commands and token creation behavior remain
  unchanged.
- Storybook includes the changed agent-card reinstall state.
- Managed Agents user docs describe reinstalling/updating an existing agent.

## Validation

- Backend unit tests cover reinstall script mode and bash syntax.
- Frontend tests cover the agent card reinstall action, dialog, and copyable
  tokenless command.
- Required frontend checks, snapshots, backend checks, and a local walkthrough
  are run before Human Review.

## Notes

The UI follows the existing operational card pattern: icon button with tooltip,
plain dialog, no heavy accent borders, no new navigation.
