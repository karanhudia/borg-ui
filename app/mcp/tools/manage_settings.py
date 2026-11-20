"""Manage: settings and users (spec 5.5 Manage, 5.2 rule 5, 5.9; phase 4, Task 8)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, create_model

from app.api.settings import SystemSettingsUpdate
from app.mcp import links, resolve
from app.mcp.levels import Level
from app.mcp.registry import tool
from app.mcp.render import ToolResult

# An allowlist, not a denylist: a field a later release adds stays out until
# someone decides it belongs here. MCP, metrics, MQTT, webhook and e-mail
# delivery and the lock-breaking switch are never changed over MCP.
UPDATE_SETTINGS_FIELDS = frozenset(
    {
        "backup_timeout",
        "mount_timeout",
        "info_timeout",
        "list_timeout",
        "init_timeout",
        "source_size_timeout",
        "max_concurrent_backups",
        "max_concurrent_scheduled_backups",
        "max_concurrent_scheduled_checks",
        "max_concurrent_maintenance",
        "maintenance_counts_toward_backup_limit",
        "log_retention_days",
        "log_save_policy",
        "log_max_total_size_mb",
        "log_cleanup_on_startup",
        "auto_cleanup",
        "cleanup_retention_days",
        "bypass_lock_on_info",
        "bypass_lock_on_list",
        "stats_refresh_interval_minutes",
        "auto_prune_preview",
        "dashboard_backup_warning_days",
        "dashboard_backup_critical_days",
        "dashboard_check_warning_days",
        "dashboard_check_critical_days",
        "dashboard_compact_warning_days",
        "dashboard_compact_critical_days",
        "dashboard_restore_check_warning_days",
        "dashboard_restore_check_critical_days",
        "dashboard_observe_freshness_warning_days",
        "dashboard_observe_freshness_critical_days",
        "backup_monitoring_enabled",
        "backup_monitoring_stale_after_days",
        "backup_monitoring_interval_hours",
        "backup_monitoring_alert_cooldown_hours",
        "backup_monitoring_include_observe_repos",
        "backup_reports_enabled",
        "backup_reports_frequency",
        "backup_reports_cron_expression",
        "backup_reports_timezone",
        "backup_reports_hour_utc",
        "backup_reports_weekday",
        "backup_reports_monthday",
        "backup_reports_include_summary",
        "backup_reports_include_stale_repositories",
        "backup_reports_include_recent_activity",
    }
)


class _SettingsBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# The route's own field types, so validation matches what the web UI sends.
SettingsArgs = create_model(
    "SettingsArgs",
    __base__=_SettingsBase,
    **{
        name: (
            SystemSettingsUpdate.model_fields[name].annotation,
            Field(None, description=name.replace("_", " ").capitalize() + "."),
        )
        for name in sorted(UPDATE_SETTINGS_FIELDS)
    },
)


@tool(
    name="update_settings",
    title="Change settings",
    description=(
        "Changes Borg UI's system settings: timeouts, how many jobs run at "
        "once, log retention and cleanup, dashboard health thresholds, stale "
        "backup monitoring and backup reports. Admins only. Integrations, "
        "metrics and security switches stay in the web UI."
    ),
    level=Level.MANAGE,
    routes=("GET /api/settings/system", "PUT /api/settings/system"),
    read_only=False,
)
async def update_settings(ctx, args: SettingsArgs) -> ToolResult:
    changes = {
        k: v
        for k, v in args.model_dump(exclude_none=True).items()
        if k in UPDATE_SETTINGS_FIELDS
    }
    if not changes:
        return ToolResult("Tell me which setting to change and to what.", is_error=True)
    current = (await ctx.api.get("/api/settings/system")).get("settings") or {}
    await ctx.api.put("/api/settings/system", json=changes)
    ctx.target = "system settings"
    lines = ["✓ Updated the settings.", ""]
    for key, value in changes.items():
        before = current.get(key)
        shown = f"{before} → {value}" if before is not None else str(value)
        lines.append(f"- {key.replace('_', ' ')}: {shown}")
    return ToolResult("\n".join(lines), {"changed": changes})


Role = Literal["viewer", "operator", "admin"]


async def _users(ctx) -> list[dict]:
    return (await ctx.api.get("/api/settings/users"))["users"]


class UpdateUserArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: str = Field(description="Username or id.", examples=["sam"])
    full_name: Optional[str] = Field(None, description="Display name.")
    email: Optional[str] = Field(None, description="E-mail address.")
    role: Optional[Role] = Field(None, description="viewer, operator or admin.")
    is_active: Optional[bool] = Field(
        None, description="False switches the account off."
    )


@tool(
    name="update_user",
    title="Change a user",
    description=(
        "Changes another user's display name, e-mail, role or whether the "
        "account is active. Admins only. Your own account, usernames, sign-in "
        "method and passwords are changed in the web UI."
    ),
    level=Level.MANAGE,
    routes=("GET /api/settings/users", "PUT /api/settings/users/{user_id}"),
    read_only=False,
)
async def update_user(ctx, args: UpdateUserArgs) -> ToolResult:
    changes = args.model_dump(exclude={"user"}, exclude_none=True)
    if not changes:
        return ToolResult(
            "Tell me what to change: display name, e-mail, role or whether the account is active.",
            is_error=True,
        )
    user = resolve.pick(
        "user",
        args.user,
        await _users(ctx),
        name_of=lambda u: str(u.get("username") or ""),
    )
    ctx.target = f"user {user['username']}"[:200]
    if user["id"] == ctx.conn.user_id:
        return ToolResult(
            "That is the account this connection runs as. Change your own account in the web UI.",
            is_error=True,
        )
    await ctx.api.put(f"/api/settings/users/{user['id']}", json=changes)
    lines = [f"✓ Updated *{user['username']}*.", ""]
    for key, value in changes.items():
        before = user.get(key)
        shown = f"{before} → {value}" if before not in (None, "") else str(value)
        lines.append(f"- {key.replace('_', ' ')}: {shown}")
    return ToolResult("\n".join(lines), {"user_id": user["id"], "changed": changes})


class CreateUserArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(
        description="Username for the new account.", examples=["robin"]
    )
    email: Optional[str] = Field(None, description="E-mail address.")
    full_name: Optional[str] = Field(None, description="Display name.")
    role: Role = Field("viewer", description="viewer, operator or admin.")


@tool(
    name="create_user",
    title="Add a user",
    description=(
        "Prepares a new user account. A new account needs a password, which "
        "never goes through the AI, so the answer is a link to the web UI's "
        "add-user dialog with everything else filled in. Admins only."
    ),
    level=Level.MANAGE,
    routes=("GET /api/settings/users",),
    read_only=False,
    idempotent=False,
)
async def create_user(ctx, args: CreateUserArgs) -> ToolResult:
    taken = {str(u.get("username") or "").lower() for u in await _users(ctx)}
    if args.username.lower() in taken:
        return ToolResult(
            f"There is already a user called *{args.username}*. Want me to change that account instead?",
            is_error=True,
        )
    link = links.new_user(
        ctx,
        username=args.username,
        email=args.email,
        full_name=args.full_name,
        role=args.role,
    )
    return ToolResult(
        f"To add *{args.username}* as {args.role}, open {link}\n\n"
        "Everything is filled in. Set their password there; it stays out of this chat.",
        {"create_url": link},
    )
