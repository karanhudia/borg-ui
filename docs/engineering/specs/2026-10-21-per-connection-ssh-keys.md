# Per-connection SSH keys

Issue: #1430. Requested in discussion #109.

## Why

Remote Machines manages one system SSH key for every connection. Users with
existing setups (a borgserver with one key per repository, BorgBase or
rsync.net restricted keys, borgmatic migrations) need a different key per
machine. One shared key also means one compromised key exposes every machine.

## What already works

Most of the plumbing exists, so this is mainly lifting the single-key limit:

- `SSHConnection.ssh_key_id` is a foreign key, and runtime SSH code resolves the
  key through the connection (`resolve_repo_ssh_key_file`,
  `write_ssh_key_to_tempfile` in `app/utils/ssh_utils.py`).
- `POST /api/ssh-keys` already stores an extra key from a pasted private key.
- `POST /api/ssh-keys/{key_id}/deploy` already creates a connection bound to any key.
- `DELETE /api/ssh-keys/{key_id}` already avoids touching the system key files
  when deleting an extra key.
- The UI has `SshKeyDialog` and `SshKeyDeleteDialog` (from #1226) for the
  Cloud Mirror SFTP key.

## Gaps

1. `POST /generate` and `POST /import` refuse once a system key exists
   (`systemKeyAlreadyExists`), so extra keys can only be pasted.
2. `POST /connections/{id}/redeploy` always deploys the system key and then
   rebinds the connection to it. With several keys this would silently switch a
   connection to the wrong key. This must be fixed before anything else ships.
3. `PUT /connections/{id}` cannot change `ssh_key_id`.
4. The Remote Machines page (`SSHConnectionsSingleKey`) and its text assume one key.
5. Deleting a key currently unlinks its connections and marks them failed.

## Behaviour

- Existing connections keep the system key. No migration, no behaviour change
  for anyone who does not add a second key.
- Add a key from Remote Machines in three ways: generate, import from a path
  (for mounted `.ssh` folders and borgmatic setups), or paste a private key.
  Extra keys are never the system key and are never written to `~/.ssh`.
- A connection has a key picker in its create and edit dialog, defaulting to the
  system key. Changing the key resets the connection status to untested, since
  the new key may not be authorised on the server yet, and offers redeploy.
- Redeploy, test connection, diagnostics and deploy all use the connection's
  own key. The system key is only a fallback for a connection with no key.
- Each connection card shows its key name.
- Deleting an extra key that connections use is refused with the list of
  connections. Deleting the system key keeps today's behaviour. (A call to
  confirm, see below.)

## Non-goals

- Per-repository key overrides. The connection is the unit.
- Keys with passphrases (unchanged from today).
- Key rotation tooling.
- Gating behind a plan. This stays in the free tier.

## Work

Backend (`app/api/ssh_keys.py`):
- Add an optional `system_key` flag (default true) to the generate and import
  bodies. When false, skip the system-key check and do not write files to `~/.ssh`.
- Fix redeploy to use `_resolve_connection_ssh_key`.
- Accept `ssh_key_id` on connection update, validate it, reset status.
- Refuse deleting an in-use extra key (409 with connection names).

Frontend:
- Key list and "Add key" on the Remote Machines page, reusing `SshKeyDialog`
  and `SshKeyDeleteDialog`, plus generate and import.
- Key picker in the connection dialog using the shared `RichSelect` (a new
  `SshKeySelect` wrapper next to `SshConnectionSelect`).
- Key chip on `RemoteMachineCard`.
- Stories for every changed state, en/de/es/it strings, `docs/ssh-keys.md` and
  `docs/provider-guides.md`.

Tests first (TDD): redeploy keeps the connection's key, extra key generate and
import, connection key change, refused delete, plus component tests and stories.

## Open calls

1. Refuse deleting an in-use extra key (proposed), or keep today's behaviour of
   unlinking and marking connections failed.
2. Include import from a path in the first version (proposed), or generate and
   paste only.
