"""Operate tools: start backups, plans and schedules (spec 5.5, phase 3)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.mcp import borg_routes, resolve
from app.mcp.levels import Level
from app.mcp.registry import tool
from app.mcp.render import ToolResult, duration
from app.mcp.tools.jobs import estimate

WAIT_OFFER = "Want me to wait for it?"


def started(
    what: str, job_type: Optional[str], job_id: Optional[int], took: Optional[float]
) -> ToolResult:
    """The answer every start gives: at once, with the job and an estimate (5.8)."""
    ref = f" ({job_type} {job_id})" if job_id is not None else ""
    lines = [f"⏳ {what} started{ref}."]
    if took is not None:
        lines.append(f"Usually takes ~{duration(took)}.")
    if job_id is not None:
        lines += ["", WAIT_OFFER]
    else:
        lines += ["", "list_running_jobs shows what it started."]
    return ToolResult(
        "\n".join(lines),
        {"job_type": job_type, "job_id": job_id, "estimate_seconds": took},
    )


class RepositoryArg(BaseModel):
    repository: str = Field(
        description="Repository name or id. Partial names work when they are unique.",
        examples=["Photos"],
    )


@tool(
    name="start_backup",
    title="Back up now",
    description=(
        "Starts a one-off backup of a repository with its saved settings and "
        "answers at once with the job id. Use wait_for_job to follow it. For "
        "anything recurring, a backup plan is the better fit."
    ),
    level=Level.OPERATE,
    routes=(
        "GET /api/repositories/",
        "GET /api/activity/recent",
        "POST /api/backup/start",
        "POST /api/v2/backup/run",
    ),
    read_only=False,
    idempotent=False,
)
async def start_backup(ctx, args: RepositoryArg) -> ToolResult:
    repo = await resolve.repository(ctx, args.repository)
    path, body = borg_routes.backup_run(repo)
    answer = await ctx.api.post(path, json=body)
    took = await estimate(ctx, "backup", repository_id=repo["id"])
    return started(f"Backup of *{repo['name']}*", "backup", answer.get("job_id"), took)


class PlanArg(BaseModel):
    backup_plan: str = Field(
        description="Backup plan name or id. Partial names work when they are unique.",
        examples=["Nightly"],
    )


@tool(
    name="run_backup_plan",
    title="Run a backup plan",
    description=(
        "Runs a backup plan now, to every repository it writes to, and answers "
        "at once with the run id. Use wait_for_job with job_type backup_plan_run "
        "to follow it."
    ),
    level=Level.OPERATE,
    routes=(
        "GET /api/backup-plans/",
        "GET /api/activity/recent",
        "POST /api/backup-plans/{plan_id}/run",
    ),
    read_only=False,
    idempotent=False,
)
async def run_backup_plan(ctx, args: PlanArg) -> ToolResult:
    plan = await resolve.backup_plan(ctx, args.backup_plan)
    answer = await ctx.api.post(f"/api/backup-plans/{plan['id']}/run")
    took = await estimate(ctx, "backup_plan_run", backup_plan_id=plan["id"])
    return started(f"*{plan['name']}*", "backup_plan_run", answer.get("id"), took)


class ScheduleArg(BaseModel):
    schedule: str = Field(
        description="Schedule name or id. Partial names work when they are unique.",
        examples=["Photos nightly"],
    )


@tool(
    name="run_schedule_now",
    title="Run a schedule now",
    description=(
        "Runs a schedule's backup now instead of waiting for its next time. A "
        "schedule for one repository answers with the backup's job id."
    ),
    level=Level.OPERATE,
    routes=("GET /api/schedule/", "POST /api/schedule/{job_id}/run-now"),
    read_only=False,
    idempotent=False,
)
async def run_schedule_now(ctx, args: ScheduleArg) -> ToolResult:
    job = await resolve.schedule(ctx, args.schedule)
    answer = await ctx.api.post(f"/api/schedule/{job['id']}/run-now") or {}
    job_id = answer.get("job_id")
    return started(
        f"*{job['name']}*", "backup" if job_id is not None else None, job_id, None
    )


class JobArgs(BaseModel):
    job_type: str = Field(
        description="Job type as listed by list_activity, such as backup, check, backup_plan_run.",
        examples=["backup"],
    )
    job_id: int = Field(
        description="Job id as listed by list_activity.", examples=[412]
    )


PLAN_RUN = "backup_plan_run"
# What to use instead of a retry, for the kinds the app cannot retry.
RERUN_WITH = {
    "check": "check_repository",
    "compact": "compact_repository",
    "restore_check": "run_restore_check",
    "restore": "restore_files",
}


@tool(
    name="cancel_job",
    title="Cancel a job",
    description=(
        "Stops a queued or running job, such as a backup, check, compact or plan "
        "run. A finished job cannot be cancelled, and some kinds cannot be "
        "stopped once they are running; the answer says so."
    ),
    level=Level.OPERATE,
    routes=(
        "POST /api/activity/{job_type}/{job_id}/cancel",
        "POST /api/backup-plans/runs/{run_id}/cancel",
    ),
    read_only=False,
)
async def cancel_job(ctx, args: JobArgs) -> ToolResult:
    ctx.target = f"{args.job_type} {args.job_id}"
    if args.job_type == PLAN_RUN:
        await ctx.api.post(f"/api/backup-plans/runs/{args.job_id}/cancel")
    else:
        await ctx.api.post(f"/api/activity/{args.job_type}/{args.job_id}/cancel")
    return ToolResult(
        f"✓ Asked {args.job_type} {args.job_id} to stop. It shows as cancelled "
        "once it has.",
        {"job_type": args.job_type, "job_id": args.job_id},
    )


@tool(
    name="retry_job",
    title="Retry a job",
    description=(
        "Runs a failed or cancelled backup or plan run again with the same "
        "settings, as a new job. Other kinds are started again with their own "
        "tool, such as check_repository."
    ),
    level=Level.OPERATE,
    routes=(
        "POST /api/backup/jobs/{job_id}/retry",
        "POST /api/backup-plans/runs/{run_id}/retry",
    ),
    read_only=False,
    idempotent=False,
)
async def retry_job(ctx, args: JobArgs) -> ToolResult:
    ctx.target = f"{args.job_type} {args.job_id}"
    if args.job_type == "backup":
        answer = await ctx.api.post(f"/api/backup/jobs/{args.job_id}/retry")
        new_id = answer.get("job_id")
    elif args.job_type == PLAN_RUN:
        answer = await ctx.api.post(f"/api/backup-plans/runs/{args.job_id}/retry")
        new_id = answer.get("id")
    else:
        instead = RERUN_WITH.get(args.job_type)
        hint = (
            f" To run a {args.job_type.replace('_', ' ')} again, use {instead}."
            if instead
            else ""
        )
        return ToolResult(
            f"Only backups and plan runs can be retried.{hint}", is_error=True
        )
    return started(
        f"Retry of {args.job_type} {args.job_id}", args.job_type, new_id, None
    )
