# Remote sudo repository access

## Problem

Remote-direct backups run `borg create` on the SSH source host. When that
connection uses sudo, Borg writes repository data as root. Repository
maintenance later runs from Borg UI through SSH as the normal SSH user, so it
cannot read the data it created.

## User outcome

When a remote SSH repository uses a connection with **Use sudo** enabled,
every Borg operation reaches its remote Borg server as root. Users can create,
list, browse, check, prune, compact, restore, extract, delete, and unlock the
same repository consistently.

## Execution contract

- The connection associated with an SSH repository is the authority for its
  remote Borg command.
- With `use_sudo` disabled, Borg UI preserves the configured remote Borg path.
- With `use_sudo` enabled, Borg UI invokes the remote Borg command through
  `sudo -n -H`. `-n` never prompts in a background process and `-H` keeps
  Borg's root configuration and cache under `/root`.
- Only the required Borg environment variables are preserved for a
  remote-direct `create`; the server-side Borg commands keep credentials in
  their local process environment and use Borg's remote protocol.

## Scope

- Add a shared resolver for the effective remote Borg command.
- Use it in Borg 1 and Borg 2 repository operations.
- Use `sudo -n -H` for remote-direct create commands.
- Add regression tests for normal and sudo repository command resolution.

## Non-goals

- Do not change the managed-agent executor.
- Do not repair ownership automatically on already affected hosts.
- Do not enable the hidden `is_backup_source` setting. That is handled by the
  remote-source routing work.

## Recovery

Existing affected installations need an administrator to repair repository and
user Borg configuration ownership before changing configuration. Borg UI must
not run a broad recursive ownership change automatically.
