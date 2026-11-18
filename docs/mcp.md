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

This version has tools for **Read** only. The other levels arrive in later
updates, and you cannot create a connection at a level that has no tools yet.
That way, a connection never gains new powers just because Borg UI was
upgraded.

Your own permissions still apply. A viewer's connection can only do what a
viewer can do in the web UI, whatever its level.

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

**VS Code**, in `.mcp.json` at the workspace root:

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

## Activity

Each connection's row has an **Activity** button. It lists every tool call with
its outcome, its target (such as "repository Photos"), how long it took and
when. The arguments the AI sent are never stored. Activity is kept for 30 days
or 20,000 rows, whichever comes first, and survives revoking the connection.

The list also shows the client each connection last used, such as
`claude-code 2.1.0`, and how many calls it made today.

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
  settings, licensing or passwords.
- Calls are rate limited per connection.
- To cut a client off, revoke its connection. It stops working on its next
  call.
