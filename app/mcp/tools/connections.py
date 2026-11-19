"""Connections, scripts, notifications, settings and users (spec 5.5, plan Task 11).

Every tool here returns an explicit allowlist of fields: these routes carry
private keys' metadata, notification URLs with tokens and rclone OAuth
tokens, none of which may reach the AI.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.mcp import resolve
from app.mcp.levels import Level
from app.mcp.registry import tool
from app.mcp.render import (
    ToolResult,
    ago,
    clamp_limit,
    duration,
    human_size,
    more_line,
    page,
)
from app.mcp.tools._common import NoArgs, plural


class FolderArgs(BaseModel):
    path: str = Field(
        "/local",
        description="Folder to list. /local is where host folders are mounted.",
        examples=["/local"],
    )
    limit: Optional[int] = Field(
        None, description="How many entries (default 25, max 200)."
    )
    cursor: Optional[str] = Field(
        None, description="Page marker from the previous answer."
    )


def _folder_text(
    where: str, path: str, items: list[dict], limit, cursor_in
) -> ToolResult:
    if not items:
        return ToolResult(
            f"{path} on {where} is empty or does not exist.",
            {"path": path, "items": []},
        )
    items = sorted(
        items,
        key=lambda i: (
            not (i.get("is_directory") or i.get("type") == "directory"),
            str(i.get("name")).lower(),
        ),
    )
    shown, cursor = page(items, clamp_limit(limit), cursor_in)
    lines = [f"{path} on {where} ({plural(len(items), 'entry', 'entries')}):", ""]
    for item in shown:
        if item.get("is_directory") or item.get("type") == "directory":
            mark = " (a Borg repository)" if item.get("is_borg_repo") else ""
            lines.append(f"📁 {item.get('name')}/{mark}")
        else:
            lines.append(f"{item.get('name')}  {human_size(item.get('size'))}")
    more = more_line(len(shown), len(items), "entries", cursor)
    if more:
        lines += ["", more]
    keep = ("name", "path", "is_directory", "type", "size", "is_borg_repo")
    return ToolResult(
        "\n".join(lines),
        {
            "path": path,
            "items": [{k: i.get(k) for k in keep if k in i} for i in shown],
            "next_cursor": cursor,
        },
    )


@tool(
    name="browse_server_folders",
    title="Browse folders on the server",
    description=(
        "Lists a folder on the Borg UI server, to find what to back up or where "
        "a repository lives. Host folders are usually under /local. Admins only."
    ),
    level=Level.READ,
    routes=("GET /api/filesystem/browse",),
)
async def browse_server_folders(ctx, args: FolderArgs) -> ToolResult:
    found = await ctx.api.get("/api/filesystem/browse", path=args.path)
    return _folder_text(
        "the server",
        found.get("current_path") or args.path,
        found.get("items") or [],
        args.limit,
        args.cursor,
    )


class AgentFolderArgs(FolderArgs):
    agent: str = Field(description="Agent machine name or id.", examples=["laptop"])
    path: str = Field(
        "/", description="Folder to list on that machine.", examples=["/home"]
    )


@tool(
    name="browse_agent_folders",
    title="Browse folders on an agent machine",
    description="Lists a folder on a machine running the Borg UI agent, to find what to back up there.",
    level=Level.READ,
    routes=(
        "GET /api/managed-machines/agents",
        "GET /api/managed-machines/agents/{agent_machine_id}/filesystem/browse",
    ),
)
async def browse_agent_folders(ctx, args: AgentFolderArgs) -> ToolResult:
    agent = await resolve.agent(ctx, args.agent)
    found = await ctx.api.get(
        f"/api/managed-machines/agents/{agent['id']}/filesystem/browse", path=args.path
    )
    return _folder_text(
        f"*{agent['name']}*",
        found.get("path") or args.path,
        found.get("items") or [],
        args.limit,
        args.cursor,
    )


@tool(
    name="list_ssh_connections",
    title="List SSH connections",
    description="SSH connections to remote servers: user and host, which key they use, whether the last test worked, and free space.",
    level=Level.READ,
    routes=("GET /api/ssh-keys/connections",),
)
async def list_ssh_connections(ctx, args: NoArgs) -> ToolResult:
    connections = (await ctx.api.get("/api/ssh-keys/connections"))["connections"]
    if not connections:
        return ToolResult("No SSH connections yet.", {"connections": []})
    lines = [f"{plural(len(connections), 'SSH connection')}:", ""]
    # Free space lives under `storage`, absent until it was measured.
    connections = [{**c, **(c.get("storage") or {})} for c in connections]
    for c in connections:
        ok = {"connected": "✓", "failed": "✗"}.get(c.get("status"), "·")
        space = (
            f", {c['available_formatted']} free" if c.get("available_formatted") else ""
        )
        lines.append(
            f"{ok} {resolve.ssh_label(c)} with key *{c.get('ssh_key_name') or 'none'}*, tested {ago(c.get('last_test'))}{space}"
        )
    keep = (
        "id",
        "host",
        "username",
        "port",
        "ssh_key_id",
        "ssh_key_name",
        "status",
        "last_test",
        "last_success",
        "default_path",
        "host_key_verified",
        "available",
        "total",
    )
    return ToolResult(
        "\n".join(lines),
        {"connections": [{k: c.get(k) for k in keep} for c in connections]},
    )


@tool(
    name="list_ssh_keys",
    title="List SSH keys",
    description="The SSH keys Borg UI holds: name, type, fingerprint and how many connections use each. Never the keys themselves.",
    level=Level.READ,
    routes=("GET /api/ssh-keys/",),
)
async def list_ssh_keys(ctx, args: NoArgs) -> ToolResult:
    keys = (await ctx.api.get("/api/ssh-keys/"))["ssh_keys"]
    if not keys:
        return ToolResult("No SSH keys yet.", {"ssh_keys": []})
    lines = [f"{plural(len(keys), 'SSH key')}:", ""]
    for k in keys:
        system = " (system key)" if k.get("is_system_key") else ""
        lines.append(
            f"*{k.get('name')}*{system}: {k.get('key_type')}, {k.get('fingerprint')}, used by {plural(k.get('connection_count') or 0, 'connection')}"
        )
    keep = (
        "id",
        "name",
        "key_type",
        "fingerprint",
        "is_system_key",
        "connection_count",
        "created_at",
    )
    return ToolResult(
        "\n".join(lines), {"ssh_keys": [{f: k.get(f) for f in keep} for k in keys]}
    )


@tool(
    name="list_agents",
    title="List agent machines",
    description="Machines running the Borg UI agent: name, host, OS, agent version and whether they are online.",
    level=Level.READ,
    routes=("GET /api/managed-machines/agents",),
)
async def list_agents(ctx, args: NoArgs) -> ToolResult:
    agents = await ctx.api.get("/api/managed-machines/agents")
    if not agents:
        return ToolResult("No agent machines yet.", {"agents": []})
    lines = [f"{plural(len(agents), 'agent machine')}:", ""]
    for a in agents:
        online = "✓" if a.get("status") == "online" else "⚠"
        lines.append(
            f"{online} *{a.get('name')}*: {a.get('hostname') or 'unknown host'}, {a.get('os') or '?'} {a.get('arch') or ''}, agent {a.get('agent_version') or '?'}, last seen {ago(a.get('last_seen_at'))}"
        )
    keep = (
        "id",
        "name",
        "hostname",
        "os",
        "arch",
        "agent_version",
        "status",
        "last_seen_at",
    )
    return ToolResult(
        "\n".join(lines), {"agents": [{k: a.get(k) for k in keep} for a in agents]}
    )


@tool(
    name="list_rclone_remotes",
    title="List cloud remotes",
    description="Cloud storage remotes (rclone) used for cloud repositories: name, provider and the last connection test. Admins only.",
    level=Level.READ,
    routes=("GET /api/rclone/remotes",),
)
async def list_rclone_remotes(ctx, args: NoArgs) -> ToolResult:
    remotes = (await ctx.api.get("/api/rclone/remotes"))["remotes"]
    if not remotes:
        return ToolResult("No cloud remotes yet.", {"remotes": []})
    lines = [f"{plural(len(remotes), 'cloud remote')}:", ""]
    for r in remotes:
        ok = {"success": "✓", "failed": "✗"}.get(r.get("last_test_status"), "·")
        lines.append(
            f"{ok} *{r.get('name')}*: {r.get('provider')}, tested {ago(r.get('last_tested_at'))}, used by {plural(r.get('usage_count') or 0, 'repository', 'repositories')}"
        )
    keep = (
        "id",
        "name",
        "provider",
        "usage_count",
        "last_tested_at",
        "last_test_status",
    )
    return ToolResult(
        "\n".join(lines), {"remotes": [{k: r.get(k) for k in keep} for r in remotes]}
    )


@tool(
    name="list_scripts",
    title="List scripts",
    description="Scripts in the script library: name, description, when they run and how many repositories use them. Script bodies are not shown.",
    level=Level.READ,
    routes=("GET /api/scripts",),
)
async def list_scripts(ctx, args: NoArgs) -> ToolResult:
    scripts = await ctx.api.get("/api/scripts")
    if not scripts:
        return ToolResult("No scripts yet.", {"scripts": []})
    lines = [f"{plural(len(scripts), 'script')}:", ""]
    for s in scripts:
        about = f": {s['description']}" if s.get("description") else ""
        lines.append(
            f"*{s.get('name')}*{about} (runs {s.get('run_on') or 'on the server'}, used {plural(s.get('usage_count') or 0, 'time')})"
        )
    keep = (
        "id",
        "name",
        "description",
        "category",
        "run_on",
        "timeout",
        "usage_count",
        "is_template",
    )
    return ToolResult(
        "\n".join(lines), {"scripts": [{k: s.get(k) for k in keep} for s in scripts]}
    )


def _service(url: Optional[str]) -> str:
    return (url or "").split("://", 1)[0] or "unknown"


@tool(
    name="list_notification_channels",
    title="List notification channels",
    description="Where Borg UI sends notifications: each channel's name, service and which events it gets. Never the address itself.",
    level=Level.READ,
    routes=("GET /api/notifications",),
)
async def list_notification_channels(ctx, args: NoArgs) -> ToolResult:
    channels = await ctx.api.get("/api/notifications")
    if not channels:
        return ToolResult("No notification channels yet.", {"channels": []})
    lines = [f"{plural(len(channels), 'notification channel')}:", ""]
    data = []
    for c in channels:
        events = sorted(
            k[len("notify_on_") :].replace("_", " ")
            for k, v in c.items()
            if k.startswith("notify_on_") and v
        )
        state = "" if c.get("enabled") else " (off)"
        lines.append(
            f"*{c.get('name')}*{state} via {_service(c.get('service_url'))}: {', '.join(events) or 'no events'}"
        )
        data.append(
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "service": _service(c.get("service_url")),
                "enabled": c.get("enabled"),
                "events": events,
                "last_used_at": c.get("last_used_at"),
            }
        )
    return ToolResult("\n".join(lines), {"channels": data})


SETTINGS_SHOWN = (
    ("backup_timeout", "Backup timeout (s)"),
    ("max_concurrent_backups", "Backups at once"),
    ("max_concurrent_scheduled_backups", "Scheduled backups at once"),
    ("max_concurrent_scheduled_checks", "Scheduled checks at once"),
    ("max_concurrent_maintenance", "Maintenance at once (0 is no cap)"),
    ("log_retention_days", "Keep logs (days)"),
    ("log_save_policy", "Which logs are kept"),
    ("stale_backup_hours", "Backup counts as stale after (hours)"),
)


@tool(
    name="get_settings",
    title="Look at settings",
    description="The main Borg UI settings: timeouts, how many jobs run at once and log retention. Secrets are never shown.",
    level=Level.READ,
    routes=("GET /api/settings/system",),
)
async def get_settings(ctx, args: NoArgs) -> ToolResult:
    settings = (await ctx.api.get("/api/settings/system"))["settings"]
    lines = ["Borg UI settings:", ""]
    data = {}
    for key, label in SETTINGS_SHOWN:
        if key in settings:
            lines.append(f"{label}: {settings[key]}")
            data[key] = settings[key]
    return ToolResult("\n".join(lines), {"settings": data})


@tool(
    name="list_users",
    title="List users",
    description="Borg UI users with their role and when they last signed in. Admins only.",
    level=Level.READ,
    routes=("GET /api/settings/users",),
)
async def list_users(ctx, args: NoArgs) -> ToolResult:
    users = (await ctx.api.get("/api/settings/users"))["users"]
    lines = [f"{plural(len(users), 'user')}:", ""]
    for u in users:
        state = "" if u.get("is_active") else " (deactivated)"
        lines.append(
            f"*{u.get('username')}*{state}: {u.get('role')}, signs in with {u.get('auth_source') or 'password'}, last sign-in {ago(u.get('last_login'))}"
        )
    keep = (
        "id",
        "username",
        "full_name",
        "role",
        "is_active",
        "auth_source",
        "last_login",
        "created_at",
    )
    return ToolResult(
        "\n".join(lines), {"users": [{k: u.get(k) for k in keep} for u in users]}
    )


# Phase 3: tests (operate)

SCRIPT_TAIL = 50


class ConnectionArg(BaseModel):
    connection: str = Field(
        description="SSH connection as user@host, or its id.",
        examples=["borg@nas.example.com"],
    )


@tool(
    name="test_ssh_connection",
    title="Test an SSH connection",
    description="Checks that Borg UI can still log in to a server over SSH, and records the result on the connection.",
    level=Level.OPERATE,
    routes=(
        "GET /api/ssh-keys/connections",
        "POST /api/ssh-keys/connections/{connection_id}/test",
    ),
    read_only=False,
)
async def test_ssh_connection(ctx, args: ConnectionArg) -> ToolResult:
    connection = await resolve.ssh_connection(ctx, args.connection)
    label = resolve.ssh_label(connection)
    answer = await ctx.api.post(f"/api/ssh-keys/connections/{connection['id']}/test")
    data = {"connection_id": connection["id"], "success": bool(answer.get("success"))}
    if answer.get("success"):
        return ToolResult(f"✓ {label} answered. The connection works.", data)
    reason = answer.get("error") or "the test failed"
    return ToolResult(f"✗ Could not connect to {label}: {reason}", data, is_error=True)


class ChannelArg(BaseModel):
    channel: str = Field(
        description="Notification channel name or id.", examples=["Phone"]
    )


@tool(
    name="test_notification",
    title="Send a test notification",
    description="Sends a test message through one of the saved notification channels, to check it still arrives.",
    level=Level.OPERATE,
    routes=("GET /api/notifications", "POST /api/notifications/test"),
    read_only=False,
    idempotent=False,
)
async def test_notification(ctx, args: ChannelArg) -> ToolResult:
    channels = await ctx.api.get("/api/notifications")
    channel = resolve.pick("notification channel", args.channel, channels)
    ctx.target = f"notification channel {channel['name']}"[:200]
    # The stored URL holds the service's token: it goes from one route to the
    # other inside the server and never into the answer (spec 5.9).
    answer = await ctx.api.post(
        "/api/notifications/test", json={"service_url": channel["service_url"]}
    )
    data = {"channel_id": channel["id"], "success": bool(answer.get("success"))}
    if answer.get("success"):
        return ToolResult(f"✓ Sent a test message to *{channel['name']}*.", data)
    return ToolResult(
        f"✗ The test message to *{channel['name']}* did not go through. Check the "
        "channel's settings in Borg UI under Settings > Notifications.",
        data,
        is_error=True,
    )


class ScriptArgs(BaseModel):
    script: str = Field(description="Script name or id.", examples=["notify"])
    repository: Optional[str] = Field(
        None, description="Run it with this repository's context, as a hook would."
    )


@tool(
    name="test_script",
    title="Test a script",
    description=(
        "Runs a saved script once on the server and shows its exit code and the "
        "end of its output. Nothing is recorded in the script's history. Admins only."
    ),
    level=Level.OPERATE,
    routes=(
        "GET /api/scripts",
        "GET /api/repositories/",
        "POST /api/scripts/{script_id}/test",
    ),
    read_only=False,
    idempotent=False,
)
async def test_script(ctx, args: ScriptArgs) -> ToolResult:
    script = resolve.pick("script", args.script, await ctx.api.get("/api/scripts"))
    body = {}
    if args.repository:
        repo = await resolve.repository(ctx, args.repository)
        body["repository_id"] = repo["id"]
    ctx.target = f"script {script['name']}"[:200]
    answer = await ctx.api.post(f"/api/scripts/{script['id']}/test", json=body)
    took = duration(answer.get("execution_time"))
    output = [
        line
        for line in (
            (answer.get("stdout") or "") + "\n" + (answer.get("stderr") or "")
        ).splitlines()
        if line.strip()
    ]
    code = answer.get("exit_code")
    ok = bool(answer.get("success"))
    head = (
        f"✓ *{script['name']}* ran in {took} and exited with {code}."
        if ok
        else f"✗ *{script['name']}* exited with {code} after {took}."
    )
    lines = [head]
    if output:
        tail = output[-SCRIPT_TAIL:]
        lines += [
            "",
            f"Last {len(tail)} lines of output:"
            if len(output) > SCRIPT_TAIL
            else "Output:",
            "```",
            *tail,
            "```",
        ]
    return ToolResult(
        "\n".join(lines),
        {
            "script_id": script["id"],
            "exit_code": code,
            "success": ok,
            "output": output[-SCRIPT_TAIL:],
        },
        is_error=not ok,
    )
