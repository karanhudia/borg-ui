"""Backup plan and schedule tools (spec 5.5, plan Task 11)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.mcp import resolve
from app.mcp.levels import Level
from app.mcp.registry import tool
from app.mcp.render import ToolResult, ago, clamp_limit, duration, more_line, page, when
from app.mcp.tools._common import STATUS_GLYPH, plural
from app.mcp.tools.repositories import _retention

PLAN_FIELDS = (
    "id",
    "name",
    "description",
    "enabled",
    "source_type",
    "source_directories",
    "exclude_patterns",
    "compression",
    "cron_expression",
    "timezone",
    "schedule_enabled",
    "next_run",
    "last_run",
    "repository_count",
    "repository_run_mode",
    "run_prune_after",
    "run_compact_after",
    "run_check_after",
    "run_restore_check_after",
    "prune_keep_hourly",
    "prune_keep_daily",
    "prune_keep_weekly",
    "prune_keep_monthly",
    "prune_keep_quarterly",
    "prune_keep_yearly",
    "prune_keep_within",
)
SCHEDULE_FIELDS = (
    "id",
    "name",
    "description",
    "enabled",
    "cron_expression",
    "timezone",
    "next_run",
    "last_run",
    "repository",
    "repository_id",
    "repository_ids",
    "backup_plan_id",
    "run_prune_after",
    "run_compact_after",
    "archive_name_template",
)

_PLAN = Field(description="Backup plan name or id.", examples=["Nightly photos"])
_SCHEDULE = Field(description="Schedule name or id.", examples=["Nightly"])


class NoArgsList(BaseModel):
    limit: Optional[int] = Field(
        None, description="How many to show (default 25, max 200)."
    )
    cursor: Optional[str] = Field(
        None, description="Page marker from the previous answer."
    )


def _sources(plan: dict) -> str:
    paths = plan.get("source_directories") or []
    if not paths:
        return plan.get("source_type") or "no sources"
    shown = ", ".join(paths[:5])
    return shown + (f" and {len(paths) - 5} more" if len(paths) > 5 else "")


def _schedule_words(item: dict) -> str:
    cron = item.get("cron_expression")
    if not cron or item.get("schedule_enabled") is False:
        return "not scheduled"
    return (
        f"`{cron}` ({item.get('timezone') or 'UTC'}), next {when(item.get('next_run'))}"
    )


@tool(
    name="list_backup_plans",
    title="List backup plans",
    description=(
        "Every backup plan: what it backs up, how many repositories it writes "
        "to, its schedule and when it last ran. Use get_backup_plan for one plan "
        "in full."
    ),
    level=Level.READ,
    routes=("GET /api/backup-plans/",),
)
async def list_backup_plans(ctx, args: NoArgsList) -> ToolResult:
    plans = (await ctx.api.get("/api/backup-plans/"))["backup_plans"]
    if not plans:
        return ToolResult("No backup plans yet.", {"backup_plans": []})
    shown, cursor = page(plans, clamp_limit(args.limit), args.cursor)
    lines = [f"{plural(len(plans), 'backup plan')}:", ""]
    for plan in shown:
        state = "" if plan.get("enabled", True) else " (off)"
        lines.append(
            f"*{plan['name']}*{state}: {_sources(plan)} to "
            f"{plural(plan.get('repository_count') or len(plan.get('repositories') or []), 'repository', 'repositories')}, "
            f"{_schedule_words(plan)}"
        )
    more = more_line(len(shown), len(plans), "plans", cursor)
    if more:
        lines += ["", more]
    return ToolResult(
        "\n".join(lines),
        {
            "backup_plans": [{k: p.get(k) for k in PLAN_FIELDS} for p in shown],
            "next_cursor": cursor,
        },
    )


class PlanRef(BaseModel):
    plan: str = _PLAN


@tool(
    name="get_backup_plan",
    title="Look at a backup plan",
    description=(
        "One backup plan in full: sources and exclusions, the repositories it "
        "writes to, schedule, retention, what runs after the backup, scripts, "
        "and the next run."
    ),
    level=Level.READ,
    routes=("GET /api/backup-plans/", "GET /api/backup-plans/{plan_id}"),
)
async def get_backup_plan(ctx, args: PlanRef) -> ToolResult:
    found = await resolve.backup_plan(ctx, args.plan)
    plan = await ctx.api.get(f"/api/backup-plans/{found['id']}")
    plan = plan.get("backup_plan", plan)
    repos = [r.get("repository") or r for r in plan.get("repositories") or []]
    after = [
        label
        for key, label in (
            ("run_prune_after", "prune"),
            ("run_compact_after", "compact"),
            ("run_check_after", "check"),
            ("run_restore_check_after", "restore check"),
        )
        if plan.get(key)
    ]
    lines = [
        f"*{plan['name']}*{'' if plan.get('enabled', True) else ' (turned off)'}",
        "",
        f"Backs up: {_sources(plan)}",
    ]
    if plan.get("exclude_patterns"):
        lines.append(f"Skips: {', '.join(plan['exclude_patterns'][:10])}")
    lines.append(
        "To: " + (", ".join(f"*{r.get('name')}*" for r in repos) or "no repositories")
    )
    lines.append(f"When: {_schedule_words(plan)}")
    rules = {
        key[len("prune_") :]: plan.get(key)
        for key in PLAN_FIELDS
        if key.startswith("prune_keep_")
    }
    lines.append(f"Keeps: {_retention(rules)}")
    lines.append(f"After the backup: {', '.join(after) if after else 'nothing'}")
    hooks = plan.get("script_hooks") or []
    if hooks:
        lines.append(
            "Scripts: "
            + ", ".join(str(h.get("script_name") or h.get("name")) for h in hooks)
        )
    lines.append(f"Last run: {when(plan.get('last_run'))}")
    data = {k: plan.get(k) for k in PLAN_FIELDS}
    data["repositories"] = [{"id": r.get("id"), "name": r.get("name")} for r in repos]
    data["scripts"] = [str(h.get("script_name") or h.get("name")) for h in hooks]
    return ToolResult("\n".join(lines), {"backup_plan": data})


class PlanRunsArgs(PlanRef):
    limit: Optional[int] = Field(
        None, description="How many runs (default 25, max 200)."
    )
    cursor: Optional[str] = Field(
        None, description="Page marker from the previous answer."
    )


@tool(
    name="list_plan_runs",
    title="Show a plan's runs",
    description="The recent runs of one backup plan with their outcome and duration, newest first.",
    level=Level.READ,
    routes=("GET /api/backup-plans/", "GET /api/backup-plans/{plan_id}/runs"),
)
async def list_plan_runs(ctx, args: PlanRunsArgs) -> ToolResult:
    plan = await resolve.backup_plan(ctx, args.plan)
    runs = (await ctx.api.get(f"/api/backup-plans/{plan['id']}/runs")).get("runs") or []
    if not runs:
        return ToolResult(f"*{plan['name']}* has not run yet.", {"runs": []})
    shown, cursor = page(runs, clamp_limit(args.limit), args.cursor)
    lines = [f"Runs of *{plan['name']}*:", ""]
    for run in shown:
        took = ""
        if run.get("started_at") and run.get("completed_at"):
            from app.mcp.render import _as_utc

            took = f", took {duration((_as_utc(run['completed_at']) - _as_utc(run['started_at'])).total_seconds())}"
        lines.append(
            f"{STATUS_GLYPH.get(run.get('status'), '·')} {run.get('status')} {ago(run.get('started_at') or run.get('created_at'))}{took}"
            + (f": {run['error_message']}" if run.get("error_message") else "")
        )
    more = more_line(len(shown), len(runs), "runs", cursor)
    if more:
        lines += ["", more]
    keep = (
        "id",
        "status",
        "trigger",
        "started_at",
        "completed_at",
        "error_message",
        "skip_reason",
    )
    return ToolResult(
        "\n".join(lines),
        {"runs": [{k: r.get(k) for k in keep} for r in shown], "next_cursor": cursor},
    )


@tool(
    name="list_schedules",
    title="List schedules",
    description="Every schedule with what it runs, its cron expression and timezone, and the next run.",
    level=Level.READ,
    routes=("GET /api/schedule/",),
)
async def list_schedules(ctx, args: NoArgsList) -> ToolResult:
    jobs = (await ctx.api.get("/api/schedule/"))["jobs"]
    if not jobs:
        return ToolResult("No schedules yet.", {"schedules": []})
    shown, cursor = page(jobs, clamp_limit(args.limit), args.cursor)
    lines = [f"{plural(len(jobs), 'schedule')}:", ""]
    for job in shown:
        state = "" if job.get("enabled", True) else " (off)"
        target = f" for *{job['repository']}*" if job.get("repository") else ""
        lines.append(
            f"*{job['name']}*{state}{target}: `{job.get('cron_expression')}` ({job.get('timezone') or 'UTC'}), next {when(job.get('next_run'))}"
        )
    more = more_line(len(shown), len(jobs), "schedules", cursor)
    if more:
        lines += ["", more]
    return ToolResult(
        "\n".join(lines),
        {
            "schedules": [{k: j.get(k) for k in SCHEDULE_FIELDS} for j in shown],
            "next_cursor": cursor,
        },
    )


class ScheduleRef(BaseModel):
    schedule: str = _SCHEDULE


@tool(
    name="get_schedule",
    title="Look at a schedule",
    description="One schedule in full: what it runs, when, what follows the backup, and its last and next run.",
    level=Level.READ,
    routes=("GET /api/schedule/", "GET /api/schedule/{job_id}"),
)
async def get_schedule(ctx, args: ScheduleRef) -> ToolResult:
    found = await resolve.schedule(ctx, args.schedule)
    job = await ctx.api.get(f"/api/schedule/{found['id']}")
    job = job.get("job", job)
    lines = [
        f"*{job['name']}*{'' if job.get('enabled', True) else ' (turned off)'}",
        "",
        f"When: `{job.get('cron_expression')}` ({job.get('timezone') or 'UTC'})",
        f"Next run: {when(job.get('next_run'))}",
        f"Last run: {when(job.get('last_run'))}",
    ]
    if job.get("repository"):
        lines.append(f"Repository: *{job['repository']}*")
    after = [
        label
        for key, label in (
            ("run_prune_after", "prune"),
            ("run_compact_after", "compact"),
        )
        if job.get(key)
    ]
    lines.append(f"After the backup: {', '.join(after) if after else 'nothing'}")
    return ToolResult(
        "\n".join(lines), {"schedule": {k: job.get(k) for k in SCHEDULE_FIELDS}}
    )


class CronArgs(BaseModel):
    expression: str = Field(
        description="A five-field cron expression.", examples=["0 2 * * *"]
    )
    timezone: Optional[str] = Field(
        None, description="IANA timezone; default UTC.", examples=["Europe/Berlin"]
    )


@tool(
    name="check_cron",
    title="Check a schedule expression",
    description=(
        "Checks a cron expression and shows its next five run times in the given "
        "timezone. Use it before suggesting a schedule to the user. Changes nothing."
    ),
    level=Level.READ,
    routes=("POST /api/schedule/validate-cron",),
)
async def check_cron(ctx, args: CronArgs) -> ToolResult:
    fields = args.expression.split()
    if len(fields) != 5:
        return ToolResult(
            "A cron expression has five fields: minute, hour, day of month, month, day of week. For example `0 2 * * *` is every day at 02:00.",
            is_error=True,
        )
    names = ("minute", "hour", "day_of_month", "month", "day_of_week")
    result = await ctx.api.request(
        "POST",
        "/api/schedule/validate-cron",
        json={**dict(zip(names, fields)), "timezone": args.timezone},
    )
    if not result.get("success"):
        return ToolResult(
            f"`{args.expression}` does not work: {result.get('error')}",
            {"valid": False},
            is_error=True,
        )
    runs = result.get("next_runs") or []
    lines = [
        f"✓ `{result['cron_expression']}` is valid ({result.get('timezone')}). Next runs:",
        "",
    ]
    lines += [f"- {when(run)}" for run in runs[:5]]
    return ToolResult(
        "\n".join(lines),
        {
            "valid": True,
            "cron_expression": result["cron_expression"],
            "timezone": result.get("timezone"),
            "next_runs": runs[:5],
        },
    )
