"""Manage: scripts, notification events, cloud remotes, agent upgrades
(spec 5.5 Manage, 5.9; phase 4, Task 7)."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, create_model

from app.api.rclone import _is_sensitive_config_key
from app.mcp import links, resolve
from app.mcp.levels import Level
from app.mcp.registry import tool
from app.mcp.render import ToolResult

SCRIPT_ECHO_LINES = 20
RunOn = Literal["always", "success", "failure", "warning"]


def _echo(content: str) -> str:
    lines = content.splitlines()
    shown = "\n".join(lines[:SCRIPT_ECHO_LINES])
    more = (
        f"\n... {len(lines) - SCRIPT_ECHO_LINES} more lines"
        if len(lines) > SCRIPT_ECHO_LINES
        else ""
    )
    return f"```sh\n{shown}{more}\n```"


class CreateScriptArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Script name.", examples=["pg dump"])
    content: str = Field(description="The script body (shell).")
    description: Optional[str] = Field(None, description="What it does, one line.")
    timeout: Optional[int] = Field(
        None, description="Seconds before it is stopped; default 300."
    )
    run_on: Optional[RunOn] = Field(None, description="When a post-backup script runs.")


@tool(
    name="create_script",
    title="Create a script",
    description=(
        "Adds a shell script to the script library, to run before or after "
        "backups. Write no secrets into it: scripts are shown in the web UI. "
        "Admins only."
    ),
    level=Level.MANAGE,
    routes=("POST /api/scripts",),
    read_only=False,
    idempotent=False,
)
async def create_script(ctx, args: CreateScriptArgs) -> ToolResult:
    body = args.model_dump(exclude_none=True)
    answer = await ctx.api.post("/api/scripts", json=body)
    ctx.target = f"script {args.name}"[:200]
    return ToolResult(
        f"✓ Added the script *{args.name}*.\n\n{_echo(args.content)}\n\n"
        "Want me to attach it to a repository or a backup plan?",
        {"script_id": (answer or {}).get("id")},
    )


class UpdateScriptArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    script: str = Field(description="Script name or id.")
    name: Optional[str] = Field(None, description="New name.")
    content: Optional[str] = Field(None, description="New body.")
    description: Optional[str] = Field(None, description="New description.")
    timeout: Optional[int] = Field(None, description="Seconds.")
    run_on: Optional[RunOn] = Field(None, description="When a post-backup script runs.")


@tool(
    name="update_script",
    title="Change a script",
    description=(
        "Changes a library script's name, body, description, timeout or when it "
        "runs. Every repository and plan using it picks up the change. Admins only."
    ),
    level=Level.MANAGE,
    routes=("GET /api/scripts", "PUT /api/scripts/{script_id}"),
    read_only=False,
)
async def update_script(ctx, args: UpdateScriptArgs) -> ToolResult:
    changes = args.model_dump(exclude={"script"}, exclude_none=True)
    if not changes:
        return ToolResult(
            "Tell me what to change: name, body, description, timeout or when it runs.",
            is_error=True,
        )
    script = resolve.pick("script", args.script, await ctx.api.get("/api/scripts"))
    ctx.target = f"script {script['name']}"[:200]
    await ctx.api.put(f"/api/scripts/{script['id']}", json=changes)
    lines = [f"✓ Updated the script *{changes.get('name', script['name'])}*."]
    if "content" in changes:
        lines += ["", _echo(changes["content"])]
    return ToolResult(
        "\n".join(lines), {"script_id": script["id"], "changed": sorted(changes)}
    )


class AssignScriptArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str = Field(description="Repository name or id.")
    script: str = Field(
        description="Library script name or id; for an agent repository, the name of a script the agent publishes."
    )
    hook: Literal["pre-backup", "post-backup"] = Field(description="When it runs.")


@tool(
    name="assign_script",
    title="Attach a script to a repository",
    description=(
        "Runs a script before or after a repository's own backups. Server "
        "repositories use library scripts; agent repositories use scripts the "
        "agent publishes."
    ),
    level=Level.MANAGE,
    routes=(
        "GET /api/repositories/",
        "GET /api/scripts",
        "POST /api/repositories/{repository_id}/scripts",
    ),
    read_only=False,
    idempotent=False,
)
async def assign_script(ctx, args: AssignScriptArgs) -> ToolResult:
    repo = await resolve.repository(ctx, args.repository)
    if repo.get("execution_target") == "agent":
        body = {"agent_script_name": args.script, "hook_type": args.hook}
        name = args.script
    else:
        script = resolve.pick("script", args.script, await ctx.api.get("/api/scripts"))
        body = {"script_id": script["id"], "hook_type": args.hook}
        name = script["name"]
    await ctx.api.post(f"/api/repositories/{repo['id']}/scripts", json=body)
    when = "before" if args.hook == "pre-backup" else "after"
    return ToolResult(
        f"✓ *{name}* now runs {when} each backup of *{repo['name']}*.",
        {"repository_id": repo["id"], "hook_type": args.hook},
    )


# Events only. The URL holds the provider's token and stays in the web UI (5.9).
NOTIFY_EVENTS = (
    "backup_start",
    "backup_success",
    "backup_warning",
    "backup_failure",
    "restore_success",
    "restore_failure",
    "check_success",
    "check_failure",
    "restore_check_success",
    "restore_check_failure",
    "schedule_failure",
    "stale_backup",
    "backup_report",
)


class _NotificationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: str = Field(
        description="Notification channel name or id.", examples=["Phone"]
    )
    enabled: Optional[bool] = Field(None, description="Turn the channel on or off.")
    title_prefix: Optional[str] = Field(None, description="Text before every title.")
    include_job_name_in_title: Optional[bool] = Field(
        None, description="Name the job in titles."
    )
    monitor_all_repositories: Optional[bool] = Field(
        None, description="Cover every repository."
    )
    repositories: Optional[list[str]] = Field(
        None, description="Only these repositories (sets monitor all off)."
    )


NotificationArgs = create_model(
    "NotificationArgs",
    __base__=_NotificationBase,
    **{
        f"notify_on_{event}": (
            Optional[bool],
            Field(None, description=f"Notify on {event.replace('_', ' ')}."),
        )
        for event in NOTIFY_EVENTS
    },
)


@tool(
    name="update_notification_channel",
    title="Change a notification channel's events",
    description=(
        "Chooses which events a notification channel sends (backup failures, "
        "successes, checks, restores, stale backups, reports), its title and "
        "which repositories it covers. Its address stays in the web UI, under "
        "Settings > Notifications. Admins only."
    ),
    level=Level.MANAGE,
    routes=(
        "GET /api/notifications",
        "GET /api/repositories/",
        "PUT /api/notifications/{setting_id}",
    ),
    read_only=False,
)
async def update_notification_channel(ctx, args: NotificationArgs) -> ToolResult:
    changes = args.model_dump(exclude={"channel", "repositories"}, exclude_none=True)
    if args.repositories is not None:
        changes["repository_ids"] = [
            (await resolve.repository(ctx, ref))["id"] for ref in args.repositories
        ]
        changes["monitor_all_repositories"] = False
    if not changes:
        return ToolResult(
            "Tell me what to change: which events it sends, its title, or which repositories it covers.",
            is_error=True,
        )
    channel = resolve.pick(
        "notification channel", args.channel, await ctx.api.get("/api/notifications")
    )
    ctx.target = f"notification channel {channel['name']}"[:200]
    await ctx.api.put(f"/api/notifications/{channel['id']}", json=changes)
    lines = [f"✓ Updated *{channel['name']}*.", ""]
    for key, value in changes.items():
        label = key.removeprefix("notify_on_").replace("_", " ")
        if isinstance(value, bool) and key.startswith("notify_on_"):
            lines.append(f"- {label}: {'on' if value else 'off'}")
        else:
            lines.append(f"- {label}: {value}")
    return ToolResult(
        "\n".join(lines), {"channel_id": channel["id"], "changed": sorted(changes)}
    )


class RcloneArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remote: str = Field(description="Cloud remote name or id.", examples=["b2"])
    name: Optional[str] = Field(None, description="New name.")
    settings: Optional[dict[str, Any]] = Field(
        None,
        description='rclone settings to change, e.g. {"hard_delete": "true"}. Keys, passwords and tokens are changed in the web UI.',
    )


@tool(
    name="update_rclone_remote",
    title="Change a cloud remote",
    description=(
        "Renames a cloud remote or changes its non-secret rclone settings. "
        "Secret settings (keys, passwords, tokens, accounts) are changed in the "
        "web UI: the answer links there. Admins only."
    ),
    level=Level.MANAGE,
    routes=("GET /api/rclone/remotes", "PUT /api/rclone/remotes/{remote_id}"),
    read_only=False,
)
async def update_rclone_remote(ctx, args: RcloneArgs) -> ToolResult:
    if not args.name and not args.settings:
        return ToolResult(
            "Tell me what to change: the name, or a setting.", is_error=True
        )
    remotes = (await ctx.api.get("/api/rclone/remotes"))["remotes"]
    remote = resolve.pick("cloud remote", args.remote, remotes)
    ctx.target = f"cloud remote {remote['name']}"[:200]
    secret = sorted(
        k for k in (args.settings or {}) if _is_sensitive_config_key(str(k))
    )
    if secret:
        link = links.rclone_remote(ctx, remote["id"])
        return ToolResult(
            f"{', '.join(secret)} {'is a secret' if len(secret) == 1 else 'are secrets'}, "
            f"so it stays out of this chat. Change it at {link}",
            {"edit_url": link},
        )
    if args.name and remote.get("config_source") != "managed":
        # The route renames only the database row of a remote whose config
        # Borg UI does not manage; rclone would then not find it by name.
        link = links.rclone_remote(ctx, remote["id"])
        return ToolResult(
            f"*{remote['name']}* uses an rclone config Borg UI does not manage, so "
            f"renaming it here would break it. Rename it in that config, then at {link}",
            {"edit_url": link},
            is_error=True,
        )
    body: dict = {}
    if args.name:
        body["name"] = args.name
    if args.settings:
        # The route replaces the whole config and keeps values still marked
        # redacted, so send what it listed plus the change.
        body["redacted_config"] = {
            **(remote.get("redacted_config") or {}),
            **args.settings,
        }
    await ctx.api.put(f"/api/rclone/remotes/{remote['id']}", json=body)
    changed = ([f"name → {args.name}"] if args.name else []) + [
        f"{k} → {v}" for k, v in (args.settings or {}).items()
    ]
    return ToolResult(
        f"✓ Updated *{remote['name']}*: " + "; ".join(changed) + ".",
        {"remote_id": remote["id"]},
    )


class UpgradeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agents: list[str] = Field(
        description='Agent names or ids, or ["outdated"] for every agent with an upgrade waiting.',
        examples=[["outdated"]],
    )


@tool(
    name="upgrade_agents",
    title="Upgrade agent machines",
    description=(
        "Asks agent machines to upgrade themselves to the version this Borg UI "
        'ships. Pass names, or "outdated" for every agent that is behind. '
        "Upgrades finish on the agents a little later. Admins only."
    ),
    level=Level.MANAGE,
    routes=(
        "GET /api/managed-machines/agents",
        "POST /api/managed-machines/agents/upgrade",
    ),
    read_only=False,
    idempotent=False,
)
async def upgrade_agents(ctx, args: UpgradeArgs) -> ToolResult:
    agents = await ctx.api.get("/api/managed-machines/agents")

    # The route refuses the whole batch when one agent cannot upgrade itself,
    # so those are left out and named instead. None means not reported yet.
    def upgradable(agent: dict) -> bool:
        return (
            agent.get("upgrade_status") == "outdated"
            and agent.get("self_upgrade_supported") is not False
        )

    if [a.strip().lower() for a in args.agents] == ["outdated"]:
        outdated = [a for a in agents if a.get("upgrade_status") == "outdated"]
    else:
        outdated = [resolve.pick("agent machine", ref, agents) for ref in args.agents]
    wanted = [a for a in outdated if upgradable(a)]
    current = [a for a in outdated if not upgradable(a)]
    names = ", ".join(f"*{a['name']}*" for a in current)
    current_text = (
        f"{names} {'is' if len(current) == 1 else 'are'} already current or cannot be upgraded from here."
        if current
        else ""
    )
    if not wanted:
        return ToolResult(
            ("Nothing to upgrade. " + current_text).strip()
            if current
            else "Nothing to upgrade: every agent is already current.",
            {"requested": []},
        )
    await ctx.api.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [a["id"] for a in wanted]},
    )
    lines = [
        "⏳ Upgrade requested for " + ", ".join(f"*{a['name']}*" for a in wanted) + ".",
        "They reinstall themselves within a few minutes; list_agents shows the new versions.",
    ]
    if current_text:
        lines += ["", current_text]
    return ToolResult("\n".join(lines), {"requested": [a["id"] for a in wanted]})
