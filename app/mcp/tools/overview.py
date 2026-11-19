"""Overview and health tools (spec 5.5, plan Task 8)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.mcp.levels import Level
from app.mcp.registry import tool
from app.mcp.render import ToolResult, _as_utc, ago, when
from app.mcp.tools._common import GLYPH, NoArgs, job_label, plural

_RANK = {"critical": 0, "warning": 1, "healthy": 2}
FAILURE_DAYS = 7
FAILURES_SHOWN = 10


def _repo_line(repo: dict) -> str:
    glyph = GLYPH.get(repo.get("health_status"), "·")
    line = (
        f"{glyph} *{repo['name']}*: backed up {ago(repo.get('last_backup'))}, "
        f"{repo.get('total_size') or 'size unknown'}, "
        f"{plural(repo.get('archive_count') or 0, 'archive')}"
    )
    warnings = repo.get("warnings") or []
    return f"{line} ({'; '.join(warnings)})" if warnings else line


def _worst_first(repos: list[dict]) -> list[dict]:
    return sorted(
        repos, key=lambda r: (_RANK.get(r.get("health_status"), 1), r["name"])
    )


@tool(
    name="get_overview",
    title="See how my backups are doing",
    description=(
        "A one-glance summary of every repository this user can see: health, "
        "last backup, size and archive count, worst first, plus recent failures. "
        "Start here when the user asks how their backups are doing. For a list "
        "of only what is wrong use list_problems; for one repository in detail "
        "use get_repository."
    ),
    level=Level.READ,
    routes=("GET /api/dashboard/overview",),
)
async def get_overview(ctx, args: NoArgs) -> ToolResult:
    overview = await ctx.api.get("/api/dashboard/overview")
    repos = _worst_first(overview.get("repository_health") or [])
    summary = overview.get("summary") or {}
    if not repos:
        return ToolResult(
            "No repositories yet. Want to set one up? That needs Manage access.",
            {"summary": summary, "repositories": []},
        )
    unhealthy = [r for r in repos if r.get("health_status") != "healthy"]
    if unhealthy:
        verb = "needs" if len(unhealthy) == 1 else "need"
        head = f"⚠ {len(unhealthy)} of {plural(len(repos), 'repository', 'repositories')} {verb} a look."
    else:
        latest = max((r.get("last_backup") or "" for r in repos), default="")
        head = (
            f"✓ All {plural(len(repos), 'repository', 'repositories')} are healthy. "
            f"Last backup finished {ago(latest)}."
        )
    lines = [head, "", *(_repo_line(r) for r in repos)]
    failed = summary.get("failed_jobs_30d") or 0
    if failed:
        lines += ["", f"{plural(failed, 'job')} failed in the last 30 days."]
    if unhealthy:
        lines += ["", f"Want me to look into *{unhealthy[0]['name']}*?"]
    data = {
        "summary": summary,
        "storage": {
            k: (overview.get("storage") or {}).get(k)
            for k in ("total_size", "total_size_bytes", "total_archives")
        },
        "repositories": [
            {
                k: r.get(k)
                for k in (
                    "id",
                    "name",
                    "health_status",
                    "last_backup",
                    "last_check",
                    "total_size",
                    "size_bytes",
                    "archive_count",
                    "warnings",
                    "dimension_health",
                    "next_run",
                )
            }
            for r in repos
        ],
    }
    return ToolResult("\n".join(lines), data)


def _recent(item: dict, days: int) -> bool:
    stamp = item.get("completed_at") or item.get("started_at") or item.get("created_at")
    if not stamp:
        return False
    return _as_utc(stamp) >= datetime.now(timezone.utc) - timedelta(days=days)


@tool(
    name="list_problems",
    title="Find what needs attention",
    description=(
        "Lists only what is wrong right now: repositories whose health is not "
        "fine (stale backups, overdue checks, failing restore checks) and jobs "
        "that failed in the last 7 days. Use it when the user asks what is wrong, "
        "what failed, or whether anything needs attention."
    ),
    level=Level.READ,
    routes=("GET /api/dashboard/overview", "GET /api/activity/recent"),
)
async def list_problems(ctx, args: NoArgs) -> ToolResult:
    overview = await ctx.api.get("/api/dashboard/overview")
    failed = await ctx.api.get(
        "/api/activity/recent", status="failed", limit=FAILURES_SHOWN + 1
    )
    cut = len(failed or []) > FAILURES_SHOWN
    failed = (failed or [])[:FAILURES_SHOWN]
    repos = overview.get("repository_health") or []
    problems: list[dict] = []
    lines: list[str] = []
    for repo in _worst_first(repos):
        if repo.get("health_status") == "healthy":
            continue
        reasons = repo.get("warnings") or [f"health is {repo.get('health_status')}"]
        lines.append(
            f"{GLYPH.get(repo.get('health_status'), '⚠')} *{repo['name']}*: {'; '.join(reasons)}"
        )
        problems.append(
            {
                "kind": "repository",
                "id": repo["id"],
                "name": repo["name"],
                "health_status": repo.get("health_status"),
                "warnings": reasons,
            }
        )
        if repo.get("latest_restore_check_status") == "failed":
            error = repo.get("latest_restore_check_error") or "no details"
            lines.append(f"✗ Restore check of *{repo['name']}* failed: {error}")
    for job in failed or []:
        if not _recent(job, FAILURE_DAYS):
            continue
        stamp = job.get("completed_at") or job.get("started_at")
        error = job.get("error_message") or "no error message"
        lines.append(
            f"✗ {job_label(job.get('type'))} of *{job.get('repository') or 'unknown'}* "
            f"failed {ago(stamp)}: {error}"
        )
        problems.append(
            {
                "kind": "failed_job",
                "job_type": job.get("type"),
                "job_id": job.get("id"),
                "repository": job.get("repository"),
                "at": stamp,
                "error": error,
            }
        )
    # The feed is ordered by start time, so a long job that failed today
    # can sit past the cut whatever the shown rows' ages.
    more = (
        f"Only the {FAILURES_SHOWN} most recent failures were checked. For the "
        'rest, use list_activity with status "failed".'
    )
    if not lines and cut:
        return ToolResult(
            "No repository needs attention, and none of the "
            f"{FAILURES_SHOWN} most recent failures is from the last "
            f"{FAILURE_DAYS} days. A long job that failed recently may still be "
            f"further back.\n\n{more}",
            {"problems": []},
        )
    if not lines:
        return ToolResult(
            f"✓ Nothing needs attention. {plural(len(repos), 'repository', 'repositories')}, "
            "all backed up recently.",
            {"problems": []},
        )
    count = len(lines)
    head = f"⚠ {plural(count, 'thing')} {'needs' if count == 1 else 'need'} attention."
    tail = (
        ["", "Ask me to explain a failure and I will pull its log."]
        if any(p["kind"] == "failed_job" for p in problems)
        else []
    )
    if cut:
        tail += ["", more]
    return ToolResult("\n".join([head, "", *lines, *tail]), {"problems": problems})


@tool(
    name="get_upcoming_runs",
    title="See what runs next",
    description=(
        "Scheduled backups and maintenance due in the next 24 hours, soonest "
        "first, with the time in UTC. Use it for questions like 'what runs "
        "tonight?' or 'when is the next backup?'."
    ),
    level=Level.READ,
    routes=("GET /api/schedule/upcoming-jobs",),
)
async def get_upcoming_runs(ctx, args: NoArgs) -> ToolResult:
    data = await ctx.api.get("/api/schedule/upcoming-jobs")
    jobs = sorted(
        data.get("upcoming_jobs") or [], key=lambda j: str(j.get("next_run") or "")
    )
    hours = data.get("hours_ahead", 24)
    if not jobs:
        return ToolResult(
            f"Nothing is scheduled in the next {hours} hours.", {"upcoming": []}
        )
    lines = [f"{plural(len(jobs), 'run')} in the next {hours} hours:", ""]
    for job in jobs:
        where = f" on *{job['repository']}*" if job.get("repository") else ""
        lines.append(f"⏳ *{job.get('name')}*{where}: {when(job.get('next_run'))}")
    return ToolResult("\n".join(lines), {"upcoming": jobs})


@tool(
    name="get_system_info",
    title="About this Borg UI",
    description=(
        "The Borg UI version, the plan this install is on, and the Borg versions "
        "installed. Use it when the user asks which version they run or whether "
        "a feature is available on their plan."
    ),
    level=Level.READ,
    routes=("GET /api/system/info",),
)
async def get_system_info(ctx, args: NoArgs) -> ToolResult:
    info = await ctx.api.get("/api/system/info")
    entitlement = info.get("entitlement") or {}
    plan = (
        entitlement.get("license_plan") or info.get("plan") or "community"
    ).capitalize()
    borg1 = info.get("borg_version") or "not installed"
    borg2 = info.get("borg2_version") or "not installed"
    text = (
        f"Borg UI {info.get('app_version')} on the {plan} plan.\n\n"
        f"Borg 1: {borg1}\nBorg 2: {borg2}"
    )
    data = {
        "app_version": info.get("app_version"),
        "plan": info.get("plan"),
        "license_plan": entitlement.get("license_plan"),
        "borg_version": info.get("borg_version"),
        "borg2_version": info.get("borg2_version"),
        "feature_access": info.get("feature_access"),
    }
    return ToolResult(text, data)
