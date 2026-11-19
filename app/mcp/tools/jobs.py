"""Jobs and activity tools (spec 5.5, plan Task 10).

Jobs are named the way /api/activity/recent names them: a type and an id
("backup 412"). Almost every job is an operation, read from
/api/operations/{id}.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from app.mcp import resolve
from app.mcp.client import ApiError
from app.mcp.levels import Level
from app.mcp.registry import tool
from app.mcp.render import (
    LOG_DEFAULT,
    LOG_MAX,
    ToolResult,
    _as_utc,
    ago,
    clamp_limit,
    decode_cursor,
    decode_stamp,
    duration,
    more_line,
    next_cursor,
    stamp_cursor,
    when,
)
from app.mcp.tools._common import STATUS_GLYPH, NoArgs, job_label, plural

# Activity rows that are not operations, read from the activity list itself.
ACTIVITY_ONLY = {"backup_plan_run", "script_execution", "availability_check"}
# Activity names whose operation kind differs.
KIND_OF = {"package": "package_install", "rclone_hydrate": "rclone_sync"}
TERMINAL = {"completed", "completed_with_warnings", "failed", "cancelled", "skipped"}
WAIT_SECONDS, POLL_SECONDS = 45.0, 3.0
ACTIVITY_FETCH = 200
FEED_PAGES = 50
EXPLAIN_LOG_LINES = 40
JOB_FIELDS = (
    "id",
    "type",
    "status",
    "repository",
    "repository_id",
    "started_at",
    "completed_at",
    "created_at",
    "error_message",
    "skip_reason",
    "trigger",
    "triggered_by",
    "schedule_name",
    "backup_plan_name",
    "archive_name",
    "progress_percent",
    "progress_message",
    "has_logs",
)

# A job type goes into route paths, so it is a plain name, never a path.
JOB_TYPE_PATTERN = r"^[a-z][a-z0-9_]{0,39}$"
_JOB_TYPE = Field(
    pattern=JOB_TYPE_PATTERN,
    description="Job type as listed by list_activity, such as backup, check, prune.",
    examples=["backup"],
)
_JOB_ID = Field(description="Job id as listed by list_activity.", examples=[412])


def _stamp(job: dict) -> Optional[str]:
    """The moment the feed sorts by (plan runs sort by when they finished)."""
    return job.get("sort_at") or job.get("started_at") or job.get("created_at")


def _fields(job: dict) -> dict:
    return {key: job.get(key) for key in JOB_FIELDS}


def _took(job: dict) -> Optional[float]:
    if job.get("started_at") and job.get("completed_at"):
        return (
            _as_utc(job["completed_at"]) - _as_utc(job["started_at"])
        ).total_seconds()
    return None


async def estimate(
    ctx,
    job_type: str,
    *,
    repository_id: Optional[int] = None,
    backup_plan_id: Optional[int] = None,
) -> Optional[float]:
    """Median seconds of the last five completed runs like this one, or None
    with fewer than two to go on (spec 5.7: an estimate, never a guess)."""
    try:
        rows = await ctx.api.get(
            "/api/activity/recent",
            job_type=job_type,
            status="completed",
            repository_id=repository_id,
            limit=50,
        )
    except (ApiError, httpx.HTTPError):
        # Callers ask after starting work; a failed lookup is "no estimate",
        # never an error that hides a job which did start.
        return None
    if backup_plan_id is not None:
        rows = [row for row in rows if row.get("backup_plan_id") == backup_plan_id]
    took = [t for t in map(_took, rows) if t is not None][:5]
    return statistics.median(took) if len(took) >= 2 else None


def _job_line(job: dict) -> str:
    glyph = STATUS_GLYPH.get(job.get("status"), "·")
    stamp = job.get("completed_at") or job.get("started_at") or job.get("created_at")
    where = f" of *{job['repository']}*" if job.get("repository") else ""
    line = f"{glyph} {job_label(job.get('type'))}{where} {job.get('status')}, {ago(stamp)} ({job.get('type')} {job.get('id')})"
    if job.get("status") == "running" and job.get("progress_percent") is not None:
        line += f", {round(job['progress_percent'])}% done"
    if job.get("status") == "failed" and job.get("error_message"):
        line += f": {job['error_message']}"
    return line


class ActivityArgs(BaseModel):
    repository: Optional[str] = Field(
        None, description="Only this repository (name or id)."
    )
    status: Optional[str] = Field(
        None, description="running, completed, failed or cancelled."
    )
    job_type: Optional[str] = Field(
        None, description="backup, check, prune, compact, restore, ..."
    )
    since: Optional[str] = Field(
        None, description='Only since then: "24h", "7d" or a date like 2026-11-01.'
    )
    limit: Optional[int] = Field(
        None, description="How many to show (default 25, max 200)."
    )
    cursor: Optional[str] = Field(
        None, description="Page marker from the previous answer."
    )


@tool(
    name="list_activity",
    title="Show recent activity",
    description=(
        "Recent jobs (backups, checks, prunes, restores and more), newest first, "
        "with their outcome. Filter by repository, status, type or time. Each "
        "job shows its type and id, which get_job, get_job_log and "
        "explain_failure take."
    ),
    level=Level.READ,
    routes=("GET /api/repositories/", "GET /api/activity/recent"),
)
async def list_activity(ctx, args: ActivityArgs) -> ToolResult:
    repo = await resolve.repository(ctx, args.repository) if args.repository else None
    limit = clamp_limit(args.limit)
    # New jobs land at the top while someone pages, so the cursor is a
    # moment ("before this job"), not an offset into a moving list.
    jobs = await ctx.api.get(
        "/api/activity/recent",
        limit=limit + 1,
        before=decode_stamp(args.cursor),
        status=args.status,
        job_type=args.job_type,
        repository_id=repo["id"] if repo else None,
    )
    since = resolve.parse_since(args.since)
    if since:
        jobs = [j for j in jobs if (s := _stamp(j)) and _as_utc(s) >= since]
    if not jobs:
        empty = "No more activity." if args.cursor else "No matching activity."
        return ToolResult(empty, {"jobs": []})
    # Never end a page inside rows that share a moment: the next page starts
    # strictly before it and would skip the rest of the group.
    shown = jobs[:limit]
    shown += [j for j in jobs[limit:] if _stamp(j) == _stamp(shown[-1])]
    # A tie group can swallow the extra row, so more may exist whenever the
    # feed sent more than a page; the worst case is one empty last page.
    cursor = stamp_cursor(_stamp(shown[-1])) if len(jobs) > limit else None
    lines = [_job_line(j) for j in shown]
    more = more_line(len(shown), None, "jobs", cursor)
    if more:
        lines += ["", more]
    return ToolResult(
        "\n".join(lines), {"jobs": [_fields(j) for j in shown], "next_cursor": cursor}
    )


@tool(
    name="list_running_jobs",
    title="See what's running",
    description=(
        "Jobs running right now with their progress, plus what is waiting in "
        "the queue and whether background work is paused."
    ),
    level=Level.READ,
    routes=("GET /api/activity/recent", "GET /api/operations/queue"),
)
async def list_running_jobs(ctx, args: NoArgs) -> ToolResult:
    running = await ctx.api.get(
        "/api/activity/recent", status="running", limit=ACTIVITY_FETCH
    )
    queue = await ctx.api.get("/api/operations/queue")
    lines = [_job_line(j) for j in running] or ["Nothing is running right now."]
    waiting = sum(
        1
        for r in queue.get("repositories") or []
        for op in r.get("operations") or []
        if op.get("status") == "queued"
    )
    if waiting:
        lines += ["", f"{plural(waiting, 'job')} waiting in the queue."]
    if queue.get("paused"):
        lines += ["", "⚠ Background work is paused."]
    elif queue.get("paused_stages"):
        lines += ["", f"⚠ Paused: {', '.join(queue['paused_stages'])}."]
    return ToolResult(
        "\n".join(lines), {"running": [_fields(j) for j in running], "queue": queue}
    )


class JobRef(BaseModel):
    job_type: str = _JOB_TYPE
    job_id: int = _JOB_ID


async def _find_in_feed(ctx, job_type: str, job_id: int) -> Optional[dict]:
    """Walk the activity feed for one row that has no detail route."""
    before = None
    # ponytail: at most FEED_PAGES pages (10,000 rows); a detail route for
    # plan runs and script runs would make this one call.
    for _ in range(FEED_PAGES):
        rows = await ctx.api.get(
            "/api/activity/recent",
            job_type=job_type,
            limit=ACTIVITY_FETCH,
            before=before,
        )
        found = next((row for row in rows if row.get("id") == job_id), None)
        if found or len(rows) < ACTIVITY_FETCH:
            return found
        before = _stamp(rows[-1])
    raise resolve.NotFound(
        f"I searched the newest {FEED_PAGES * ACTIVITY_FETCH} {job_type} rows "
        f"and {job_id} is not among them, so it is older than that or gone."
    )


async def _job(ctx, job_type: str, job_id: int) -> dict:
    missing = resolve.NotFound(
        f"I could not find {job_type} {job_id}. list_activity shows the recent ones."
    )
    if job_type == "availability_check":
        # A skip record, written by plan runs and by schedules under ids
        # that overlap, so an id alone cannot name one; it has no more to it.
        raise resolve.NotFound(
            "An availability check is a record of a skipped run, with nothing "
            "more to show than its line in list_activity."
        )
    if job_type in ACTIVITY_ONLY:
        job = await _find_in_feed(ctx, job_type, job_id)
        if job is None:
            raise missing
        ctx.target = f"{job_type} {job_id}"
        return job
    try:
        job = await ctx.api.get(f"/api/operations/{job_id}")
    except ApiError as exc:
        if exc.status == 404:
            raise missing from None
        raise
    if job.get("type") != KIND_OF.get(job_type, job_type):
        raise resolve.NotFound(
            f"Job {job_id} is a {job.get('type')}, not a {job_type}. Ask for {job.get('type')} {job_id}."
        )
    ctx.target = f"{job_type} {job_id}"
    return job


def _job_text(job: dict) -> str:
    glyph = STATUS_GLYPH.get(job.get("status"), "·")
    where = f" of *{job['repository']}*" if job.get("repository") else ""
    lines = [f"{glyph} {job_label(job.get('type'))}{where}: {job.get('status')}", ""]
    lines.append(f"Started: {when(job.get('started_at') or job.get('created_at'))}")
    if job.get("completed_at"):
        lines.append(
            f"Finished: {when(job['completed_at'])}, took {duration(_took(job))}"
        )
    if job.get("status") == "running":
        progress = job.get("progress_percent")
        lines.append(
            f"Progress: {round(progress)}%"
            if progress is not None
            else "Progress: unknown"
        )
        if job.get("progress_message"):
            lines.append(f"Now: {job['progress_message']}")
    if job.get("archive_name"):
        lines.append(f"Archive: *{job['archive_name']}*")
    if job.get("schedule_name") or job.get("backup_plan_name"):
        lines.append(
            f"Started by: {job.get('backup_plan_name') or job.get('schedule_name')}"
        )
    if job.get("error_message"):
        lines.append(f"Error: {job['error_message']}")
    if job.get("skip_reason"):
        lines.append(f"Skipped: {job['skip_reason']}")
    return "\n".join(lines)


@tool(
    name="get_job",
    title="Check on a job",
    description="The status, timing, progress and error of one job, by type and id.",
    level=Level.READ,
    routes=("GET /api/operations/{operation_id}", "GET /api/activity/recent"),
)
async def get_job(ctx, args: JobRef) -> ToolResult:
    job = await _job(ctx, args.job_type, args.job_id)
    return ToolResult(_job_text(job), {"job": _fields(job)})


class LogArgs(JobRef):
    lines: Optional[int] = Field(
        None, description="How many lines from the end (default 200, max 1000)."
    )
    cursor: Optional[str] = Field(
        None, description="Page marker for earlier lines, from the previous answer."
    )


async def _tail(
    ctx, job_type: str, job_id: int, count: int, end: Optional[int] = None
) -> tuple[list[str], int, int]:
    """The `count` lines before line `end` (0-based, exclusive), or the last
    `count` lines. `end` is absolute, so a growing log does not shift pages."""
    route = f"/api/activity/{job_type}/{job_id}/logs"
    total = (await ctx.api.get(route, offset=0, limit=1)).get("total_lines") or 0
    end = total if end is None else min(end, total)
    start = max(0, end - count)
    if end == 0:
        return [], total, 0
    chunk = await ctx.api.get(route, offset=start, limit=end - start)
    # A running backup's live buffer ignores offset and limit and sends the
    # whole tail, so keep only this page's line numbers (1-based).
    lines = [
        line.get("content", "")
        for line in chunk.get("lines") or []
        if start < (line.get("line_number") or start + 1) <= end
    ]
    return lines, total, start


@tool(
    name="get_job_log",
    title="Read a job's log",
    description=(
        "The end of one job's log (last 200 lines by default). The answer says "
        "how to read earlier lines when there are more."
    ),
    level=Level.READ,
    routes=(
        "GET /api/operations/{operation_id}",
        "GET /api/activity/recent",
        "GET /api/activity/{job_type}/{job_id}/logs",
    ),
)
async def get_job_log(ctx, args: LogArgs) -> ToolResult:
    await _job(ctx, args.job_type, args.job_id)
    count = clamp_limit(args.lines, default=LOG_DEFAULT, max_=LOG_MAX)
    end = decode_cursor(args.cursor) if args.cursor else None
    try:
        lines, total, start = await _tail(ctx, args.job_type, args.job_id, count, end)
    except ApiError as exc:
        if exc.key == "backend.errors.activity.noLogsAvailableForJob":
            return ToolResult(
                f"{args.job_type} {args.job_id} kept no log (the log policy only keeps some).",
                {"lines": []},
            )
        raise
    if not lines:
        return ToolResult(
            f"The log of {args.job_type} {args.job_id} is empty.", {"lines": []}
        )
    head = f"Lines {start + 1} to {start + len(lines)} of {total} from {args.job_type} {args.job_id}:"
    cursor = next_cursor(start) if start > 0 else None
    tail = (
        ["", f'There are {start} earlier lines. For them, pass cursor "{cursor}".']
        if cursor
        else []
    )
    return ToolResult(
        "\n".join([head, "```", *lines, "```", *tail]),
        {
            "total_lines": total,
            "first_line": start + 1,
            "lines": lines,
            "next_cursor": cursor,
        },
    )


@tool(
    name="wait_for_job",
    title="Wait for a job to finish",
    description=(
        "Waits up to 45 seconds for a job to finish and returns its result. If "
        "it is still running after that, says how far it got; ask again to keep "
        "waiting."
    ),
    level=Level.READ,
    routes=("GET /api/operations/{operation_id}", "GET /api/activity/recent"),
)
async def wait_for_job(ctx, args: JobRef) -> ToolResult:
    deadline = time.monotonic() + WAIT_SECONDS
    job = await _job(ctx, args.job_type, args.job_id)
    reported = -1.0
    while (
        job.get("status") not in TERMINAL
        and time.monotonic() + POLL_SECONDS <= deadline
    ):
        percent = job.get("progress_percent")
        if percent is not None and percent > reported:
            # MCP: progress must increase with each notification.
            reported = percent
            await ctx.progress(percent, job.get("progress_message"))
        await asyncio.sleep(POLL_SECONDS)
        job = await _job(ctx, args.job_type, args.job_id)
    if job.get("status") in TERMINAL:
        return ToolResult(_job_text(job), {"job": _fields(job), "finished": True})
    progress = job.get("progress_percent")
    done = f"{round(progress)}% done" if progress is not None else "progress unknown"
    return ToolResult(
        f"⏳ Still running after 45 seconds ({done}). Ask me again to keep waiting.",
        {"job": _fields(job), "finished": False},
    )


class ExplainArgs(BaseModel):
    job_type: Optional[str] = Field(
        None,
        pattern=JOB_TYPE_PATTERN,
        description="Job type; leave both empty for the most recent failure.",
    )
    job_id: Optional[int] = Field(
        None, description="Job id; leave both empty for the most recent failure."
    )


@tool(
    name="explain_failure",
    title="Explain why a job failed",
    description=(
        "Gathers what is needed to explain a failed job: what failed, the error, "
        "the last 40 log lines and similar recent failures on the same "
        "repository. With no job given it takes the most recent failure. It "
        "states facts; you reason about the cause."
    ),
    level=Level.READ,
    routes=(
        "GET /api/activity/recent",
        "GET /api/operations/{operation_id}",
        "GET /api/activity/{job_type}/{job_id}/logs",
    ),
)
async def explain_failure(ctx, args: ExplainArgs) -> ToolResult:
    if args.job_id is None:
        failed = await ctx.api.get("/api/activity/recent", status="failed", limit=1)
        if not failed:
            return ToolResult("✓ Nothing has failed recently.", {"job": None})
        job_type, job_id = failed[0]["type"], failed[0]["id"]
    else:
        job_type, job_id = args.job_type or "backup", args.job_id
    job = await _job(ctx, job_type, job_id)
    took = _took(job)
    stamp = job.get("completed_at") or job.get("started_at")
    where = f" of *{job['repository']}*" if job.get("repository") else ""
    lines = [
        f"✗ {job_label(job_type)}{where} {job.get('status')} {ago(stamp)}"
        + (f" after {duration(took)}." if took is not None else "."),
        "",
    ]
    lines += [
        "**What failed**",
        f"{job_type} {job_id}, started by {job.get('backup_plan_name') or job.get('schedule_name') or job.get('triggered_by') or 'unknown'}.",
        "",
    ]
    lines += [
        "**Error**",
        job.get("error_message") or "No error message was recorded.",
        "",
    ]
    try:
        log, _, _ = await _tail(ctx, job_type, job_id, EXPLAIN_LOG_LINES)
    except ApiError:
        log = []
    lines += [
        "**Last log lines**",
        *(["```", *log, "```"] if log else ["No log was kept for this job."]),
        "",
    ]
    similar = []
    if job.get("repository_id"):
        recent = await ctx.api.get(
            "/api/activity/recent",
            status="failed",
            limit=6,
            repository_id=job["repository_id"],
        )
        similar = [j for j in recent if j.get("id") != job_id][:5]
    lines.append("**Similar recent failures**")
    lines += [_job_line(j) for j in similar] or ["None on this repository recently."]
    return ToolResult(
        "\n".join(lines),
        {
            "job": _fields(job),
            "log_tail": log,
            "similar": [_fields(j) for j in similar],
        },
    )
