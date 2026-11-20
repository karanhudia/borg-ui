---
title: AI assistants (MCP)
nav_order: 7
description: "Use Borg UI from Claude Code, Claude Desktop, Cursor, VS Code or any MCP client"
---

# AI assistants (MCP)

Borg UI includes a [Model Context Protocol](https://modelcontextprotocol.io)
server. Connect an AI assistant such as Claude Code, Claude Desktop, Cursor or
VS Code, and ask it about your backups in plain language: "What failed last
night?", "Where is my space going?", "When did Photos last back up?".

MCP is part of Borg UI Pro, Lite and Enterprise, and works during a trial.

## Access levels

Every connection has an access level. Levels add up: each one can do
everything the levels above it can.

| Level | What the AI can do |
| --- | --- |
| Read | Look only: status, problems, repositories, archives, files, jobs, logs, plans, schedules, connections and settings. |
| Operate | Also run what exists: backups, checks, compacts, restores to a new place, mounts. |
| Manage | Also create and edit configuration: repositories, plans, schedules, scripts and connections. |
| Full | Also destructive actions, always through a preview you confirm first. |

This version has tools for **Read**, **Operate** and **Manage**. Full arrives
in a later update, and you cannot create a connection at a level that has no tools yet.
That way, a connection never gains new powers just because Borg UI was
upgraded.

Your own permissions still apply. A viewer's connection can only do what a
viewer can do in the web UI, whatever its level.

## Turning MCP on

MCP is a beta feature and is off on a new or upgraded install. An admin turns
it on under **Settings > Advanced > Beta** with **Enable MCP**. Until then the
AI assistants (MCP) tab and the MCP section of System settings are hidden,
and no new connection can be created. Existing connections still connect and
list tools, but every tool call is refused with a note pointing at this
switch. Turning the beta off again keeps those connections: their tool calls
work again once it is back on.

## Creating a connection

1. Open **Settings > Personal > AI assistants (MCP)**.
2. Select **New connection**, give it a name ("Claude on my laptop") and pick a level.
3. Copy the token. It is shown once and never again. If you lose it, revoke
   the connection and create a new one.

The dialog that shows the token also has the setup for each client, with your
address and token already filled in.

## Connecting your client

Replace `https://your-borg-ui` with the address you open Borg UI on (including
any base path, such as `/borg`) and `borgui_...` with your token.

**Claude Code**, in a terminal:

```bash
claude mcp add --transport http borg-ui https://your-borg-ui/mcp --header "Authorization: Bearer borgui_..."
```

**Claude Desktop**, in `claude_desktop_config.json` (needs Node.js for
`mcp-remote`):

```json
{
  "mcpServers": {
    "borg-ui": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://your-borg-ui/mcp", "--header", "Authorization:${AUTH_HEADER}"],
      "env": { "AUTH_HEADER": "Bearer borgui_..." }
    }
  }
}
```

**Cursor**, in `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "borg-ui": {
      "url": "https://your-borg-ui/mcp",
      "headers": { "Authorization": "Bearer borgui_..." }
    }
  }
}
```

**VS Code**, in your own `~/.copilot/mcp-config.json`. Do not put a live token
in the workspace `.mcp.json`: that file is meant to be committed, and a token
committed to Git stays in its history until you revoke the connection. See the
VS Code docs on authentication and secrets in MCP configuration.

```json
{
  "mcpServers": {
    "borg-ui": {
      "type": "http",
      "url": "https://your-borg-ui/mcp",
      "headers": { "Authorization": "Bearer borgui_..." }
    }
  }
}
```

**Other clients**: any client that supports Streamable HTTP with a custom
header. Use the URL `https://your-borg-ui/mcp` and the header
`Authorization: Bearer borgui_...`.

## What the AI can do at Read

- **Overview**: how your backups are doing, what needs attention, what runs
  next, and details about this Borg UI.
- **Repositories**: list them, look at one, see where the space goes, compare
  retention policies.
- **Archives and files**: list and inspect archives, browse files, search
  backed-up files, trace a file's history, and see what changed between two
  archives.
- **Jobs**: recent activity, what is running, a job's status and log, why it
  failed, and waiting for it to finish.
- **Plans and schedules**: backup plans and their runs, schedules, and checking
  a schedule expression.
- **Connections and settings**: SSH keys and connections, agents, cloud
  remotes, notification channels, scripts, users (for admins), settings, and
  folders on the server or an agent.

Large answers are trimmed and paged, so a big file listing or a long log does
not flood the conversation.

## What the AI can do at Operate

Everything at Read, plus running what already exists:

- **Backups**: back up a repository now, run a backup plan, run a schedule now,
  cancel a job, and retry a failed backup or plan run.
- **Maintenance**: check a repository (fully, or for a set number of minutes),
  compact it, run a restore check, refresh its archive list and stats, and
  preview what a prune would delete. The preview deletes nothing; pruning
  itself needs Full.
- **Restores**: preview a restore, and restore files into a folder that is
  empty or does not exist yet, on the server, over SSH or on an agent. At
  Operate a folder that already has anything in it is refused. The check runs
  once, just before the restore starts: Borg 2 repositories also refuse
  existing files while extracting, Borg 1 repositories do not, so a file put
  into the folder after the check could be replaced.
- **Mounts**: mount an archive or a whole repository read-only, and unmount
  it. Borg UI picks the mount point.
- **Tests**: test an SSH connection, send a test notification, and run a
  script once (admins).
- **Sources and background work**: find databases and Docker containers to
  back up, and pause or resume background work (admins).

Starting something answers at once with the job, and usually an estimate from
earlier runs. Ask the AI to wait for it: clients that show progress get live
updates while it runs.

## What the AI can do at Manage

Everything at Operate, plus setting things up and changing them:

- **Repositories**: create a repository on the server or over SSH, connect an
  existing one, change its name, compression, folders, exclusions and limits,
  and schedule checks and restore checks.
- **Backup plans**: create a plan from what to back up (server, SSH or agent
  paths), which repositories, when and how long to keep archives. When
  something is missing the AI asks instead of guessing, and it tells you which
  defaults it used. Plans can also be changed and turned on or off.
- **Schedules**: create, change, copy, and turn schedules on or off.
- **SSH**: create a key, add a connection, change one, and trust a server's
  host key. Trusting takes two steps: the AI shows the fingerprint, you compare
  it with the server's own, and only then is it trusted.
- **Scripts, notifications, cloud remotes and agents** (admins): add and change
  scripts and attach them to repositories, choose which events a notification
  channel sends, change a cloud remote's non-secret settings, and upgrade agent
  machines.
- **Settings and users** (admins): change system settings such as timeouts,
  log retention, dashboard thresholds and backup reports, and change other
  users' roles. Integrations, metrics, MQTT and the lock-breaking switch stay
  in the web UI, and so does your own account.

When a step needs a secret, such as the server's password to deploy a key,
the passphrase of an encrypted repository you are connecting, a cloud key or
a new user's password, the AI prepares everything else and gives you a link
to the right dialog in Borg UI. You type the secret there, so it never reaches
the AI.

## Saving a generated passphrase

When the AI creates an encrypted repository, Borg UI generates a strong
passphrase and stores it. The AI never sees it. Until you save it:

- The **Repositories** page shows a **Save the passphrase** notice for that
  repository, and the dashboard lists the repository as needing attention.
- Select **Reveal** and confirm it is you: type your password, or, if you sign
  in through single sign-on or a proxy, the repository's name.
- Copy the passphrase into a password manager or somewhere safe outside Borg
  UI. For keyfile repositories, also download the keyfile.
- Select **I've saved it**. Borg UI then never shows the passphrase again.

Without the passphrase the backups cannot be restored if Borg UI's database is
lost, so do not skip this. Revealing works only in the browser: personal API
tokens and AI connections cannot reveal a passphrase.

## Activity

Each connection's row has an **Activity** button. It lists each tool call that
runs, or is refused for an unknown tool or an access level the connection
lacks, with its outcome, its target (such as "repository Photos"), how long it
took and when. Calls refused because the plan does not include MCP or MCP is
turned off, calls over the per-minute limit, and calls with invalid arguments
are not listed. The arguments the AI sent are never stored. Activity is kept for 30 days
or 20,000 rows, whichever comes first, and survives revoking the connection.

The list also shows the client each connection last used, such as
`claude-code 2.1.0`, and how many calls it made today. "Today" is the UTC
day, so the count resets at midnight UTC.

## Admin controls

Admins find these under **Settings > System > System**, in the
**AI assistants (MCP)** section:

- **Allow MCP connections**: when off, every MCP call is refused with a
  friendly message. Connections are kept and work again when you switch it
  back on.
- **Highest access level**: the most any user may grant. Lowering it never
  rewrites a connection. A Full connection under a Read cap keeps its Full
  setting, works at Read, and gets Full back when you raise the cap.

Admins can also turn on **Everyone's connections** on the MCP tab to see and
revoke every user's connections.

## Security

- An MCP token works only on the `/mcp` endpoint. The REST API refuses it, and
  `/mcp` refuses personal API tokens and browser sessions.
- Each call runs as the connection's user, with that user's permissions,
  capped by the connection's level and the admin's cap.
- Secrets never pass through the AI. No tool returns a passphrase, private key,
  password or notification URL token, and no tool can manage tokens, MCP
  settings, licensing or passwords. Where a secret is needed, the AI hands you
  a link to the Borg UI dialog where you enter it.
- Calls are rate limited per connection.
- To cut a client off, revoke its connection. It stops working on its next
  call.
