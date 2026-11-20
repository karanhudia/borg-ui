"""Manage: backup plans and schedules (spec 5.5 Manage and the create_backup_plan
paragraph; phase 4, Task 6)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.api.backup_plans import BackupPlanPayload, BackupPlanRepositoryPayload
from app.mcp import resolve
from app.mcp.client import ApiError
from app.mcp.levels import Level
from app.mcp.registry import tool
from app.mcp.render import ToolResult, when
from app.mcp.tools.plans import ScheduleInvalid, validate_schedule

# BackupPlanPayload's own defaults, named back to the user when applied.
DEFAULT_RETENTION = {"daily": 7, "weekly": 4, "monthly": 6, "yearly": 1}
DEFAULT_COMPRESSION = "lz4"
DEFAULT_ARCHIVE_TEMPLATE = "{plan_name}-{now}"
MISSING_SENTENCES = {
    "name": "a name for the plan",
    "sources": "what to back up",
    "repositories": "which repository to back up to",
    "schedule": "how often (a cron expression, or `manual`)",
}
AFTER_STEPS = {
    "prune": "run_prune_after",
    "compact": "run_compact_after",
    "check": "run_check_after",
    "restore_check": "run_restore_check_after",
}


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        description="Folder or file to back up.", examples=["/data/example/photos"]
    )
    ssh_connection: Optional[str] = Field(
        None, description="Read it over this SSH connection (user@host or id)."
    )
    agent: Optional[str] = Field(
        None, description="Read it on this agent machine (name or id)."
    )


class Retention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hourly: Optional[int] = Field(None, description="Hourly archives to keep.")
    daily: Optional[int] = Field(None, description="Daily archives to keep.")
    weekly: Optional[int] = Field(None, description="Weekly archives to keep.")
    monthly: Optional[int] = Field(None, description="Monthly archives to keep.")
    quarterly: Optional[int] = Field(None, description="Quarterly archives to keep.")
    yearly: Optional[int] = Field(None, description="Yearly archives to keep.")
    within: Optional[str] = Field(
        None, description="Keep everything within this span, e.g. 2d."
    )


RETENTION_UNITS = ("hourly", "daily", "weekly", "monthly", "quarterly", "yearly")


def _retention_fields(
    retention: Optional[Retention], *, complete: bool = False
) -> dict:
    """The route's prune_keep_* fields for the units given. With complete=True
    (creating), units not given are 0, so "keep 14 daily" keeps only that
    instead of silently taking the route's weekly, monthly and yearly defaults."""
    if retention is None:
        return {}
    fields = {
        ("prune_keep_within" if k == "within" else f"prune_keep_{k}"): v
        for k, v in retention.model_dump().items()
        if v is not None
    }
    if complete:
        for unit in RETENTION_UNITS:
            fields.setdefault(f"prune_keep_{unit}", 0)
    return fields


def _keeps_something(fields: dict) -> bool:
    """Borg refuses a prune with no keep rule; an all-zero policy has none."""
    return any(fields.get(f"prune_keep_{unit}") for unit in RETENTION_UNITS) or bool(
        fields.get("prune_keep_within")
    )


EMPTY_POLICY = (
    "That retention keeps nothing, and pruning with it would delete every "
    "archive. Give at least one rule, for example 7 daily."
)


def _retention_text(fields: dict) -> str:
    parts = [
        f"{fields[f'prune_keep_{unit}']} {unit}"
        for unit in ("hourly", "daily", "weekly", "monthly", "quarterly", "yearly")
        if fields.get(f"prune_keep_{unit}")
    ]
    if fields.get("prune_keep_within"):
        parts.append(f"everything within {fields['prune_keep_within']}")
    return ", ".join(parts) or "nothing"


async def _source_locations(ctx, sources: list[Source]) -> list[dict]:
    """One location per endpoint, in the order the user named them."""
    groups: dict[tuple, dict] = {}
    for source in sources:
        if source.ssh_connection and source.agent:
            raise ScheduleInvalid(
                f"{source.path} names both an SSH connection and an agent. Pick one."
            )
        if source.ssh_connection:
            conn = await resolve.ssh_connection(ctx, source.ssh_connection)
            key = ("remote", conn["id"])
            fresh = {
                "source_type": "remote",
                "source_ssh_connection_id": conn["id"],
                "paths": [],
            }
        elif source.agent:
            agent = await resolve.agent(ctx, source.agent)
            key = ("agent", agent["id"])
            fresh = {
                "source_type": "agent",
                "agent_machine_id": agent["id"],
                "paths": [],
            }
        else:
            key = ("local", None)
            fresh = {"source_type": "local", "paths": []}
        groups.setdefault(key, fresh)["paths"].append(source.path)
    return list(groups.values())


async def _script_id(ctx, ref: Optional[str]) -> Optional[int]:
    if not ref:
        return None
    scripts = await ctx.api.get("/api/scripts")
    return resolve.pick("script", ref, scripts)["id"]


class CreatePlanArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(
        None, description="Plan name.", examples=["Nightly photos"]
    )
    sources: Optional[list[Source]] = Field(None, description="What to back up.")
    repositories: Optional[list[str]] = Field(
        None, description="Repositories to write to, by name or id, in order."
    )
    schedule: Optional[str] = Field(
        None,
        description="Five-field cron expression, or `manual` to run only on demand.",
        examples=["0 2 * * *"],
    )
    timezone: Optional[str] = Field(None, description="IANA timezone; default UTC.")
    retention: Optional[Retention] = Field(
        None, description="How many archives to keep."
    )
    compression: Optional[str] = Field(
        None, description="Compression, e.g. lz4 or zstd."
    )
    exclude_patterns: Optional[list[str]] = Field(
        None, description="Borg exclude patterns."
    )
    pre_backup_script: Optional[str] = Field(
        None, description="Script to run before, by name."
    )
    post_backup_script: Optional[str] = Field(
        None, description="Script to run after, by name."
    )
    after: Optional[list[Literal["prune", "compact", "check", "restore_check"]]] = (
        Field(None, description="Maintenance to run after each backup.")
    )


@tool(
    name="create_backup_plan",
    title="Create a backup plan",
    description=(
        "Creates a backup plan: what to back up (local, SSH or agent paths), "
        "which repositories, when (cron with timezone, or manual), how long to "
        "keep archives, and scripts and maintenance around it. When something "
        "is missing it asks instead of guessing, and it lists any defaults it used."
    ),
    level=Level.MANAGE,
    routes=(
        "GET /api/repositories/",
        "GET /api/ssh-keys/connections",
        "GET /api/managed-machines/agents",
        "GET /api/scripts",
        "POST /api/schedule/validate-cron",
        "POST /api/backup-plans/",
    ),
    read_only=False,
    idempotent=False,
)
async def create_backup_plan(ctx, args: CreatePlanArgs) -> ToolResult:
    missing = [field for field in MISSING_SENTENCES if not getattr(args, field)]
    if missing:
        return ToolResult(
            "To make the plan I still need: "
            + "; ".join(MISSING_SENTENCES[field] for field in missing)
            + ".",
            {"missing": missing},
        )
    try:
        locations = await _source_locations(ctx, args.sources)
        manual = args.schedule.strip().lower() == "manual"
        checked = (
            None
            if manual
            else await validate_schedule(ctx, args.schedule, args.timezone)
        )
    except ScheduleInvalid as invalid:
        return ToolResult(invalid.text, is_error=True)
    repos = [await resolve.repository(ctx, ref) for ref in args.repositories]
    defaults = []
    retention = _retention_fields(args.retention, complete=True)
    if not retention:
        retention = {f"prune_keep_{k}": v for k, v in DEFAULT_RETENTION.items()}
        defaults.append(f"keep {_retention_text(retention)}")
    if not args.compression:
        defaults.append(f"{DEFAULT_COMPRESSION} compression")
    if len(repos) > 1:
        defaults.append("repositories run one after another")
    defaults.append(f"archive names `{DEFAULT_ARCHIVE_TEMPLATE}`")
    prune_after = "prune" in (args.after or [])
    if prune_after and not _keeps_something(retention):
        return ToolResult(EMPTY_POLICY, is_error=True)
    body = {
        "name": args.name,
        "source_type": locations[0]["source_type"] if len(locations) == 1 else "mixed",
        "source_locations": locations,
        "source_directories": [p for loc in locations for p in loc["paths"]],
        "repositories": [
            {"repository_id": repo["id"], "execution_order": i}
            for i, repo in enumerate(repos, start=1)
        ],
        "compression": args.compression or DEFAULT_COMPRESSION,
        "schedule_enabled": not manual,
        **retention,
    }
    if checked:
        body["cron_expression"] = checked["cron_expression"]
        body["timezone"] = checked.get("timezone") or args.timezone or "UTC"
    if args.exclude_patterns:
        body["exclude_patterns"] = args.exclude_patterns
    for field, ref in (
        ("pre_backup_script_id", args.pre_backup_script),
        ("post_backup_script_id", args.post_backup_script),
    ):
        script_id = await _script_id(ctx, ref)
        if script_id:
            body[field] = script_id
    for step, field in AFTER_STEPS.items():
        body[field] = step in (args.after or [])
    plan = await ctx.api.post("/api/backup-plans/", json=body)
    ctx.target = f"backup plan {args.name}"[:200]
    lines = [
        f"✓ Created the backup plan *{args.name}*.",
        "",
        "- Backs up: " + ", ".join(p for loc in locations for p in loc["paths"]),
        "- To: " + ", ".join(f"*{r['name']}*" for r in repos),
        "- When: "
        + (
            "only when run by hand"
            if manual
            else f"`{body['cron_expression']}` ({body['timezone']})"
        ),
        f"- Keeps: {_retention_text(retention)}"
        + ("" if prune_after else " (saved; pruning after backups is off)"),
    ]
    if any(body[f] for f in AFTER_STEPS.values()):
        lines.append("- After each backup: " + ", ".join(args.after))
    if defaults:
        lines += ["", "Defaults I used: " + "; ".join(defaults) + "."]
    # The run the saved plan will make, not the earlier preview's first one.
    next_run = plan.get("next_run")
    if next_run:
        lines += ["", f"Next run: {when(next_run)}."]
    lines += ["", "Want me to run it now?"]
    return ToolResult(
        "\n".join(lines), {"plan_id": plan.get("id"), "next_run": next_run}
    )


def _payload_from(detail: dict) -> dict:
    """The PUT body the web UI would send: the plan as stored, in the route's
    own payload shape."""
    body = {
        k: detail[k]
        for k in BackupPlanPayload.model_fields
        if k in detail and k != "script_hooks"
    }
    body["repositories"] = [
        {k: link[k] for k in BackupPlanRepositoryPayload.model_fields if k in link}
        for link in detail.get("repositories") or []
    ]
    # No script_hooks: the route then keeps the stored hooks as they are. The
    # GET masks password parameters as "***", and sending that back would
    # store "***" as the password.
    return {k: v for k, v in body.items() if v is not None}


class UpdatePlanArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backup_plan: str = Field(
        description="Backup plan name or id.", examples=["Nightly photos"]
    )
    name: Optional[str] = Field(None, description="New name.")
    description: Optional[str] = Field(None, description="New description.")
    sources: Optional[list[Source]] = Field(
        None, description="Replaces what it backs up."
    )
    repositories: Optional[list[str]] = Field(
        None, description="Replaces where it writes."
    )
    schedule: Optional[str] = Field(None, description="Cron expression, or `manual`.")
    timezone: Optional[str] = Field(None, description="IANA timezone.")
    retention: Optional[Retention] = Field(
        None, description="Changes only the units given."
    )
    compression: Optional[str] = Field(None, description="Compression.")
    exclude_patterns: Optional[list[str]] = Field(
        None, description="Replaces exclusions."
    )
    after: Optional[list[Literal["prune", "compact", "check", "restore_check"]]] = (
        Field(None, description="Replaces the maintenance run after each backup.")
    )


@tool(
    name="update_backup_plan",
    title="Change a backup plan",
    description=(
        "Changes a backup plan's name, sources, repositories, schedule, "
        "retention, compression, exclusions or follow-up maintenance. Anything "
        "not mentioned stays as it is. Answers with what changed."
    ),
    level=Level.MANAGE,
    routes=(
        "GET /api/backup-plans/",
        "GET /api/backup-plans/{plan_id}",
        "GET /api/repositories/",
        "GET /api/ssh-keys/connections",
        "GET /api/managed-machines/agents",
        "POST /api/schedule/validate-cron",
        "PUT /api/backup-plans/{plan_id}",
    ),
    read_only=False,
)
async def update_backup_plan(ctx, args: UpdatePlanArgs) -> ToolResult:
    if not args.model_dump(exclude={"backup_plan"}, exclude_none=True):
        return ToolResult(
            "Tell me what to change: name, sources, repositories, schedule, retention, compression, exclusions or follow-up maintenance.",
            is_error=True,
        )
    for field in ("sources", "repositories"):
        if getattr(args, field) == []:
            return ToolResult(
                f"A plan needs at least one of its {field}; leave {field} out to keep them.",
                is_error=True,
            )
    found = await resolve.backup_plan(ctx, args.backup_plan)
    detail = await ctx.api.get(f"/api/backup-plans/{found['id']}")
    body = _payload_from(detail)
    changes: dict = {}
    try:
        if args.sources:
            locations = await _source_locations(ctx, args.sources)
            changes["source_locations"] = locations
            changes["source_directories"] = [
                p for loc in locations for p in loc["paths"]
            ]
            changes["source_type"] = (
                locations[0]["source_type"] if len(locations) == 1 else "mixed"
            )
        if args.schedule:
            if args.schedule.strip().lower() == "manual":
                changes["schedule_enabled"] = False
                if args.timezone:
                    changes["timezone"] = args.timezone
            else:
                checked = await validate_schedule(
                    ctx, args.schedule, args.timezone or detail.get("timezone")
                )
                changes["cron_expression"] = checked["cron_expression"]
                changes["timezone"] = checked.get("timezone") or detail.get("timezone")
                changes["schedule_enabled"] = True
                # An availability plan ignores the cron; an explicit cron
                # means the user wants it to run on that cron.
                changes["schedule_mode"] = "cron"
        elif args.timezone:
            # A new timezone alone: the stored cron, checked in that zone; the
            # plan stays on or off as it was.
            if detail.get("cron_expression"):
                checked = await validate_schedule(
                    ctx, detail["cron_expression"], args.timezone
                )
                changes["timezone"] = checked.get("timezone") or args.timezone
            else:
                changes["timezone"] = args.timezone
    except ScheduleInvalid as invalid:
        return ToolResult(invalid.text, is_error=True)
    if args.repositories:
        repos = [await resolve.repository(ctx, ref) for ref in args.repositories]
        # Links that stay keep their overrides and on/off state; only their
        # order changes. New links take the defaults.
        kept = {link["repository_id"]: link for link in body.get("repositories", [])}
        changes["repositories"] = [
            {**kept[r["id"]], "execution_order": i}
            if r["id"] in kept
            else {"repository_id": r["id"], "execution_order": i, "enabled": True}
            for i, r in enumerate(repos, start=1)
        ]
    for field in ("name", "description", "compression", "exclude_patterns"):
        if getattr(args, field) is not None:
            changes[field] = getattr(args, field)
    changes.update(_retention_fields(args.retention))
    if args.after is not None:
        changes.update(
            {field: step in args.after for step, field in AFTER_STEPS.items()}
        )
    if not changes:
        return ToolResult(
            f"Nothing changed: *{found['name']}* already has those settings.",
            {"plan_id": found["id"], "changed": []},
        )
    await ctx.api.put(f"/api/backup-plans/{found['id']}", json={**body, **changes})
    lines = [f"✓ Updated the backup plan *{changes.get('name', found['name'])}*.", ""]
    for key, value in changes.items():
        if key in ("source_type", "source_locations"):
            continue
        before = detail.get(key)
        if key == "repositories":
            before = [
                link.get("repository", {}).get("name")
                for link in detail.get("repositories") or []
            ]
            value = [r["name"] for r in repos]
        shown = f"{before} → {value}" if before not in (None, "", []) else str(value)
        lines.append(f"- {key.replace('_', ' ')}: {shown}")
    return ToolResult(
        "\n".join(lines), {"plan_id": found["id"], "changed": sorted(changes)}
    )


class PlanEnabledArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backup_plan: str = Field(description="Backup plan name or id.")
    enabled: bool = Field(description="True to turn it on, false to turn it off.")


@tool(
    name="set_backup_plan_enabled",
    title="Turn a backup plan on or off",
    description=(
        "Turns a backup plan on or off. An off plan keeps its settings and "
        "history but does not run on its schedule."
    ),
    level=Level.MANAGE,
    routes=("GET /api/backup-plans/", "POST /api/backup-plans/{plan_id}/toggle"),
    read_only=False,
)
async def set_backup_plan_enabled(ctx, args: PlanEnabledArgs) -> ToolResult:
    plan = await resolve.backup_plan(ctx, args.backup_plan)
    state = "on" if args.enabled else "off"
    if bool(plan.get("enabled")) == args.enabled:
        return ToolResult(
            f"*{plan['name']}* is already {state}.",
            {"plan_id": plan["id"], "enabled": args.enabled},
        )
    await ctx.api.post(f"/api/backup-plans/{plan['id']}/toggle")
    return ToolResult(
        f"✓ *{plan['name']}* is now {state}.",
        {"plan_id": plan["id"], "enabled": args.enabled},
    )


# Schedules (the older way to run backups; plans are preferred for new work)

SCHEDULE_MISSING = {
    "repositories": "which repositories it backs up",
    "schedule": "when it runs (a cron expression)",
}


class CreateScheduleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Schedule name.", examples=["Hourly"])
    repositories: Optional[list[str]] = Field(
        None, description="Repositories, by name or id."
    )
    schedule: Optional[str] = Field(None, description="Five-field cron expression.")
    timezone: Optional[str] = Field(None, description="IANA timezone; default UTC.")
    retention: Optional[Retention] = Field(
        None, description="Prune after each run with this retention."
    )
    compact_after: bool = Field(False, description="Compact after pruning.")


@tool(
    name="create_schedule",
    title="Create a schedule",
    description=(
        "Creates a schedule that backs up repositories with their own settings "
        "on a cron expression. For anything new, a backup plan is usually the "
        "better fit: it owns its sources, retention and scripts."
    ),
    level=Level.MANAGE,
    routes=(
        "GET /api/repositories/",
        "POST /api/schedule/validate-cron",
        "POST /api/schedule/",
    ),
    read_only=False,
    idempotent=False,
)
async def create_schedule(ctx, args: CreateScheduleArgs) -> ToolResult:
    missing = [field for field in SCHEDULE_MISSING if not getattr(args, field)]
    if missing:
        return ToolResult(
            "To make the schedule I still need: "
            + "; ".join(SCHEDULE_MISSING[f] for f in missing)
            + ".",
            {"missing": missing},
        )
    try:
        checked = await validate_schedule(ctx, args.schedule, args.timezone)
    except ScheduleInvalid as invalid:
        return ToolResult(invalid.text, is_error=True)
    repos = [await resolve.repository(ctx, ref) for ref in args.repositories]
    retention = _retention_fields(args.retention, complete=True)
    if args.retention is not None and not _keeps_something(retention):
        return ToolResult(EMPTY_POLICY, is_error=True)
    body = {
        "name": args.name,
        "repository_ids": [r["id"] for r in repos],
        "cron_expression": checked["cron_expression"],
        "timezone": checked.get("timezone") or args.timezone or "UTC",
        "run_prune_after": bool(retention),
        "run_compact_after": args.compact_after,
        **retention,
    }
    answer = await ctx.api.post("/api/schedule/", json=body)
    job = answer.get("job") or {}
    ctx.target = f"schedule {args.name}"[:200]
    next_run = job.get("next_run")
    lines = [
        f"✓ Created the schedule *{args.name}* for "
        + ", ".join(f"*{r['name']}*" for r in repos)
        + ".",
        f"Runs on `{body['cron_expression']}` ({body['timezone']}).",
    ]
    if retention:
        lines.append(f"Prunes after each run, keeping {_retention_text(retention)}.")
    if next_run:
        lines.append(f"Next run: {when(next_run)}.")
    lines += [
        "",
        "Tip: a backup plan keeps sources, retention and scripts together, if you want to move this later.",
    ]
    return ToolResult(
        "\n".join(lines), {"schedule_id": job.get("id"), "next_run": next_run}
    )


class UpdateScheduleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule: str = Field(description="Schedule name or id.", examples=["Nightly"])
    name: Optional[str] = Field(None, description="New name.")
    cron: Optional[str] = Field(None, description="New five-field cron expression.")
    timezone: Optional[str] = Field(None, description="IANA timezone.")
    repositories: Optional[list[str]] = Field(
        None, description="Replaces its repositories."
    )
    retention: Optional[Retention] = Field(
        None, description="Changes only the units given."
    )


@tool(
    name="update_schedule",
    title="Change a schedule",
    description=(
        "Changes a schedule's name, cron expression, timezone, repositories or "
        "retention. Anything not mentioned stays as it is."
    ),
    level=Level.MANAGE,
    routes=(
        "GET /api/schedule/",
        "GET /api/repositories/",
        "POST /api/schedule/validate-cron",
        "PUT /api/schedule/{job_id}",
    ),
    read_only=False,
)
async def update_schedule(ctx, args: UpdateScheduleArgs) -> ToolResult:
    if not args.model_dump(exclude={"schedule"}, exclude_none=True):
        return ToolResult(
            "Tell me what to change: name, cron expression, timezone, repositories or retention.",
            is_error=True,
        )
    if args.repositories == []:
        return ToolResult(
            "A schedule needs at least one repository; leave repositories out to keep them.",
            is_error=True,
        )
    job = await resolve.schedule(ctx, args.schedule)
    changes: dict = {}
    # Timing is checked only when the caller changes it; a rename or a
    # repository change leaves the stored cron and zone alone.
    cron = (args.cron or args.timezone) and (
        args.cron
        or (
            job.get("cron_expression")
            if job.get("schedule_mode") != "availability"
            else None
        )
    )
    if cron:
        try:
            checked = await validate_schedule(
                ctx, cron, args.timezone or job.get("timezone")
            )
        except ScheduleInvalid as invalid:
            return ToolResult(invalid.text, is_error=True)
        if args.cron:
            changes["cron_expression"] = checked["cron_expression"]
            # Availability schedules drop the cron; an explicit one means cron.
            changes["schedule_mode"] = "cron"
        if checked.get("timezone"):
            changes["timezone"] = checked["timezone"]
    elif args.timezone:
        # No cron to check (availability mode): the route checks the zone.
        changes["timezone"] = args.timezone
    if args.name:
        changes["name"] = args.name
    if args.repositories:
        changes["repository_ids"] = [
            (await resolve.repository(ctx, r))["id"] for r in args.repositories
        ]
    retention = _retention_fields(args.retention)
    if retention:
        changes.update(retention)
        changes["run_prune_after"] = True
    await ctx.api.put(f"/api/schedule/{job['id']}", json=changes)
    lines = [f"✓ Updated the schedule *{changes.get('name', job['name'])}*.", ""]
    for key, value in changes.items():
        before = job.get(key)
        shown = f"{before} → {value}" if before not in (None, "", []) else str(value)
        lines.append(f"- {key.replace('_', ' ')}: {shown}")
    return ToolResult("\n".join(lines), {"schedule_id": job["id"], "changed": changes})


class ScheduleEnabledArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule: str = Field(description="Schedule name or id.")
    enabled: bool = Field(description="True to turn it on, false to turn it off.")


@tool(
    name="set_schedule_enabled",
    title="Turn a schedule on or off",
    description="Turns a schedule on or off. Its settings stay as they are.",
    level=Level.MANAGE,
    routes=("GET /api/schedule/", "POST /api/schedule/{job_id}/toggle"),
    read_only=False,
)
async def set_schedule_enabled(ctx, args: ScheduleEnabledArgs) -> ToolResult:
    job = await resolve.schedule(ctx, args.schedule)
    state = "on" if args.enabled else "off"
    if bool(job.get("enabled")) == args.enabled:
        return ToolResult(
            f"*{job['name']}* is already {state}.",
            {"schedule_id": job["id"], "enabled": args.enabled},
        )
    await ctx.api.post(f"/api/schedule/{job['id']}/toggle")
    return ToolResult(
        f"✓ *{job['name']}* is now {state}.",
        {"schedule_id": job["id"], "enabled": args.enabled},
    )


class DuplicateScheduleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule: str = Field(description="Schedule to copy, by name or id.")
    new_name: Optional[str] = Field(None, description="Name for the copy.")


@tool(
    name="duplicate_schedule",
    title="Copy a schedule",
    description=(
        "Copies a schedule with all its settings, optionally under a new name. "
        "The copy starts turned off so it does not run twice."
    ),
    level=Level.MANAGE,
    routes=(
        "GET /api/schedule/",
        "POST /api/schedule/{job_id}/duplicate",
        "PUT /api/schedule/{job_id}",
    ),
    read_only=False,
    idempotent=False,
)
async def duplicate_schedule(ctx, args: DuplicateScheduleArgs) -> ToolResult:
    job = await resolve.schedule(ctx, args.schedule)
    answer = await ctx.api.post(f"/api/schedule/{job['id']}/duplicate")
    copy = answer.get("job") or {}
    name = copy.get("name")
    data = {"schedule_id": copy.get("id"), "name": name}
    if args.new_name and copy.get("id"):
        try:
            await ctx.api.put(
                f"/api/schedule/{copy['id']}", json={"name": args.new_name}
            )
        except ApiError:
            # The copy is committed; name it so a retry does not make another.
            return ToolResult(
                f"Copied *{job['name']}* to *{name}*, but could not rename it to "
                f"*{args.new_name}* (that name may be taken). Rename *{name}* "
                "instead of copying again.",
                data,
                is_error=True,
            )
        name = args.new_name
        data["name"] = name
    lines = [f"✓ Copied *{job['name']}* to *{name}*."]
    if copy.get("enabled") is False:
        lines.append("It is off; turn it on when ready.")
    if job.get("pre_backup_script_id") or job.get("post_backup_script_id"):
        lines.append(
            "Its scripts are attached, but their script parameters are not "
            "copied: set them in the web UI before turning it on."
        )
    return ToolResult(" ".join(lines), data)
