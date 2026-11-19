"""Repository and space tools (spec 5.5, plan Task 9)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.mcp import resolve
from app.mcp.client import LONG_TIMEOUT
from app.mcp.levels import Level
from app.mcp.registry import tool
from app.mcp.render import (
    ToolResult,
    ago,
    clamp_limit,
    human_size,
    more_line,
    page,
    when,
)
from app.mcp.tools._common import plural

REPO_FIELDS = (
    "id",
    "name",
    "path",
    "repository_type",
    "execution_target",
    "agent_machine_name",
    "host",
    "borg_version",
    "encryption",
    "compression",
    "mode",
    "last_backup",
    "last_check",
    "last_compact",
    "last_prune",
    "total_size",
    "archive_count",
    "has_schedule",
    "schedule_name",
    "next_run",
    "index_mode",
    "has_running_maintenance",
)


class RepositoryRef(BaseModel):
    repository: str = Field(
        description="Repository name or id. Partial names work when they are unique.",
        examples=["Photos"],
    )


class ListArgs(BaseModel):
    limit: Optional[int] = Field(
        None, description="How many to show (default 25, max 200)."
    )
    cursor: Optional[str] = Field(
        None, description="Page marker from the previous answer."
    )


def _where(repo: dict) -> str:
    if repo.get("execution_target") == "agent":
        return f"on agent *{repo.get('agent_machine_name') or 'unknown'}*"
    if repo.get("repository_type") == "ssh" or repo.get("host"):
        return f"over SSH on {repo.get('host')}"
    return "on this server"


def _fields(repo: dict) -> dict:
    return {key: repo.get(key) for key in REPO_FIELDS}


@tool(
    name="list_repositories",
    title="List repositories",
    description=(
        "Every repository this user can see, with where it lives, Borg version, "
        "size, archive count and last backup. For health use get_overview; for "
        "one repository in detail use get_repository."
    ),
    level=Level.READ,
    routes=("GET /api/repositories/",),
)
async def list_repositories(ctx, args: ListArgs) -> ToolResult:
    repos = sorted(
        (await ctx.api.get("/api/repositories/"))["repositories"],
        key=lambda r: r["name"].lower(),
    )
    if not repos:
        return ToolResult("No repositories yet.", {"repositories": []})
    shown, cursor = page(repos, clamp_limit(args.limit), args.cursor)
    lines = [f"{plural(len(repos), 'repository', 'repositories')}:", ""]
    for repo in shown:
        lines.append(
            f"*{repo['name']}*: Borg {repo.get('borg_version') or 1}, {_where(repo)}, "
            f"{repo.get('total_size') or 'size unknown'}, "
            f"{plural(repo.get('archive_count') or 0, 'archive')}, "
            f"last backup {ago(repo.get('last_backup'))}"
        )
    more = more_line(len(shown), len(repos), "repositories", cursor)
    if more:
        lines += ["", more]
    return ToolResult(
        "\n".join(lines),
        {"repositories": [_fields(r) for r in shown], "next_cursor": cursor},
    )


@tool(
    name="get_repository",
    title="Look at a repository",
    description=(
        "Everything about one repository: where it lives, encryption, Borg "
        "version, size, archives, last backup, check and compact, the check "
        "schedule, and anything running on it now."
    ),
    level=Level.READ,
    routes=(
        "GET /api/repositories/",
        "GET /api/repositories/{repo_id}",
        "GET /api/repositories/{repo_id}/check-schedule",
        "GET /api/repositories/{repo_id}/running-jobs",
    ),
)
async def get_repository(ctx, args: RepositoryRef) -> ToolResult:
    repo = await resolve.repository(ctx, args.repository)
    detail = (await ctx.api.get(f"/api/repositories/{repo['id']}"))["repository"]
    check = await ctx.api.get(f"/api/repositories/{repo['id']}/check-schedule")
    running = await ctx.api.get(f"/api/repositories/{repo['id']}/running-jobs")
    stats = detail.get("stats") or {}
    lines = [
        f"*{repo['name']}* is a Borg {repo.get('borg_version') or 1} repository {_where(repo)}.",
        "",
        f"Location: {repo.get('path')}",
        f"Encryption: {repo.get('encryption') or 'none'}, compression {repo.get('compression') or 'default'}",
        f"Size: {repo.get('total_size') or 'unknown'}, {plural(repo.get('archive_count') or 0, 'archive')}",
        f"Last backup: {when(repo.get('last_backup'))}",
        f"Last check: {when(repo.get('last_check'))}",
        f"Last compact: {when(repo.get('last_compact'))}",
    ]
    if check.get("enabled") and check.get("check_cron_expression"):
        lines.append(
            f"Checks run on `{check['check_cron_expression']}` ({check.get('timezone') or 'UTC'}), next {when(check.get('next_scheduled_check'))}"
        )
    else:
        lines.append("Checks are not scheduled.")
    if repo.get("has_schedule"):
        lines.append(
            f"Backups: schedule *{repo.get('schedule_name')}*, next {when(repo.get('next_run'))}"
        )
    busy = [
        kind.replace("_job", "")
        for kind, job in running.items()
        if kind.endswith("_job") and job
    ]
    if busy:
        lines.append(f"⏳ Running now: {', '.join(busy)}")
    if stats.get("error"):
        lines.append(
            "Live statistics are not available right now (Borg could not read the repository)."
        )
    data = {
        "repository": _fields(repo),
        "stats": {k: v for k, v in stats.items() if k not in ("details",)},
        "check_schedule": {
            k: check.get(k)
            for k in (
                "enabled",
                "check_cron_expression",
                "timezone",
                "next_scheduled_check",
                "last_scheduled_check",
            )
        },
        "running": {k: bool(v) for k, v in running.items() if k.endswith("_job")},
    }
    return ToolResult("\n".join(lines), data)


@tool(
    name="get_repository_space",
    title="See where the space goes",
    description=(
        "How much space a repository takes and how it grew archive by archive, "
        "with the archives that added the most. Use it for 'why is this "
        "repository so big?' or 'how fast is it growing?'."
    ),
    level=Level.READ,
    routes=(
        "GET /api/repositories/",
        "GET /api/repositories/{repo_id}/storage",
        "GET /api/repositories/{repo_id}/archives/growth",
    ),
)
async def get_repository_space(ctx, args: RepositoryRef) -> ToolResult:
    repo = await resolve.repository(ctx, args.repository)
    storage = (await ctx.api.get(f"/api/repositories/{repo['id']}/storage")).get(
        "storage"
    ) or {}
    growth = await ctx.api.get(f"/api/repositories/{repo['id']}/archives/growth")
    points = growth.get("points") or []
    lines = [f"*{repo['name']}* takes {human_size(storage.get('size_bytes'))} on disk."]
    if storage.get("original_size"):
        lines.append(
            f"The data it protects is {human_size(storage['original_size'])} before deduplication and compression."
        )
    if points:
        total = points[-1].get("running_total")
        lines += [
            "",
            f"Across {plural(len(points), 'archive')}, new data added up to at least {human_size(total)}.",
        ]
        biggest = sorted(
            points, key=lambda p: p.get("deduplicated_size") or 0, reverse=True
        )[:5]
        lines += ["", "Archives that added the most:"]
        lines += [
            f"- *{p['name']}*: at least {human_size(p.get('deduplicated_size'))} new ({ago(p.get('start'))})"
            for p in biggest
        ]
    else:
        lines += [
            "",
            "No archive sizes are known yet. They appear after the next archive listing.",
        ]
    if growth.get("stale_count"):
        stale = growth["stale_count"]
        verb = "has" if stale == 1 else "have"
        lines.append(
            f"{plural(stale, 'archive')} {verb} sizes from an older measurement."
        )
    data = {
        "repository_id": repo["id"],
        "storage": storage,
        "points": points[-200:],
        "series": growth.get("series"),
        "stale_count": growth.get("stale_count"),
        "unmeasured_count": growth.get("unmeasured_count"),
    }
    return ToolResult("\n".join(lines), data)


def _retention(rules: dict) -> str:
    parts = []
    for key, unit in (
        ("keep_within", "within"),
        ("keep_hourly", "h"),
        ("keep_daily", "d"),
        ("keep_weekly", "w"),
        ("keep_monthly", "m"),
        ("keep_quarterly", "q"),
        ("keep_yearly", "y"),
    ):
        value = (rules or {}).get(key)
        if value:
            parts.append(
                f"within {value}" if key == "keep_within" else f"{value}{unit}"
            )
    return " ".join(parts) or "keep everything"


@tool(
    name="compare_retention",
    title="Compare retention policies",
    description=(
        "Compares the current retention policy with a few common ones for a "
        "repository: how many archives each keeps and deletes and at least how "
        "much space each frees. Read only; nothing is pruned."
    ),
    level=Level.READ,
    routes=(
        "GET /api/repositories/",
        "GET /api/repositories/{repo_id}/prune/comparison",
        "GET /api/repositories/{repo_id}/prune/retention-defaults",
    ),
)
async def compare_retention(ctx, args: RepositoryRef) -> ToolResult:
    repo = await resolve.repository(ctx, args.repository)
    comparison = await ctx.api.get(f"/api/repositories/{repo['id']}/prune/comparison")
    current = await ctx.api.get(
        f"/api/repositories/{repo['id']}/prune/retention-defaults"
    )
    source = {
        "plan": f"from plan *{current.get('plan_name')}*",
        "last_prune": "from the last prune",
        "default": "Borg UI's default",
    }.get(current.get("source"), current.get("source"))
    lines = [f"Current policy for *{repo['name']}*: {_retention(current)} ({source})."]
    candidates = comparison.get("candidates") or []
    if not candidates:
        lines += [
            "",
            "No comparison has been computed yet. Borg UI computes one after the next archive listing; an operator can also start one from the Prune Preview page.",
        ]
    else:
        lines += ["", f"Compared {ago(comparison.get('computed_at'))}:"]
        for row in candidates:
            freed = (
                human_size(row.get("freed_at_least"))
                if row.get("freed_at_least") is not None
                else "unknown"
            )
            lines.append(
                f"- *{row.get('label')}* ({_retention(row.get('retention') or {})}): keeps {row.get('kept_count')}, deletes {row.get('deleted_count')}, frees at least {freed}"
            )
        if comparison.get("stale"):
            lines += [
                "",
                "⚠ New archives arrived since; the numbers may be out of date.",
            ]
    return ToolResult("\n".join(lines), {"current": current, "comparison": comparison})


# Phase 3: maintenance (operate)


async def _start(ctx, repo: dict, what: str, job_type: str, path: str, body=None):
    from app.mcp.tools.jobs import estimate
    from app.mcp.tools.operate import started

    answer = await ctx.api.post(path, json=body)
    took = await estimate(ctx, job_type, repository_id=repo["id"])
    return started(f"{what} of *{repo['name']}*", job_type, answer.get("job_id"), took)


class CheckArgs(RepositoryRef):
    max_duration: Optional[int] = Field(
        None,
        description="Stop after this many minutes for a partial check. Leave empty for a full check.",
        ge=1,
    )


@tool(
    name="check_repository",
    title="Check a repository",
    description=(
        "Starts Borg's consistency check of a repository and answers at once with "
        "the job id. A full check reads everything and can take hours on big "
        "repositories; max_duration makes it a partial check."
    ),
    level=Level.OPERATE,
    routes=(
        "GET /api/repositories/",
        "GET /api/activity/recent",
        "POST /api/repositories/{repo_id}/check",
        "POST /api/v2/backup/check",
    ),
    read_only=False,
    idempotent=False,
)
async def check_repository(ctx, args: CheckArgs) -> ToolResult:
    from app.mcp import borg_routes

    repo = await resolve.repository(ctx, args.repository)
    path, body = borg_routes.repository_check(repo, args.max_duration)
    return await _start(ctx, repo, "Check", "check", path, body)


@tool(
    name="compact_repository",
    title="Compact a repository",
    description=(
        "Starts a compact, which gives back the space that prunes and archive "
        "deletes left behind. Nothing is deleted by compacting."
    ),
    level=Level.OPERATE,
    routes=(
        "GET /api/repositories/",
        "GET /api/activity/recent",
        "POST /api/repositories/{repo_id}/compact",
        "POST /api/v2/backup/compact",
    ),
    read_only=False,
    idempotent=False,
)
async def compact_repository(ctx, args: RepositoryRef) -> ToolResult:
    from app.mcp import borg_routes

    repo = await resolve.repository(ctx, args.repository)
    path, body = borg_routes.repository_compact(repo)
    return await _start(ctx, repo, "Compact", "compact", path, body)


@tool(
    name="run_restore_check",
    title="Run a restore check",
    description=(
        "Proves files can be restored from a repository's latest archive, using "
        "the restore check settings saved for that repository. Nothing is "
        "written anywhere the user would see."
    ),
    level=Level.OPERATE,
    routes=(
        "GET /api/repositories/",
        "GET /api/activity/recent",
        "POST /api/repositories/{repo_id}/restore-check",
    ),
    read_only=False,
    idempotent=False,
)
async def run_restore_check(ctx, args: RepositoryRef) -> ToolResult:
    repo = await resolve.repository(ctx, args.repository)
    path = f"/api/repositories/{repo['id']}/restore-check"
    return await _start(ctx, repo, "Restore check", "restore_check", path)


@tool(
    name="refresh_repository",
    title="Refresh repository info",
    description=(
        "Brings Borg UI's archive list and stats for a repository back in line "
        "with the repository itself, for example after work done outside Borg UI."
    ),
    level=Level.OPERATE,
    routes=("GET /api/repositories/", "POST /api/repositories/{repo_id}/resync"),
    read_only=False,
)
async def refresh_repository(ctx, args: RepositoryRef) -> ToolResult:
    repo = await resolve.repository(ctx, args.repository)
    answer = await ctx.api.post(f"/api/repositories/{repo['id']}/resync") or {}
    return ToolResult(
        f"⏳ Refreshing the archive list and stats of *{repo['name']}*. "
        "list_running_jobs shows it while it runs.",
        {"repository_id": repo["id"], "operations": answer.get("operations") or []},
    )


RETENTION_FIELDS = (
    "keep_within",
    "keep_hourly",
    "keep_daily",
    "keep_weekly",
    "keep_monthly",
    "keep_quarterly",
    "keep_yearly",
)
PRUNE_LISTED = 10


class PruneArgs(RepositoryRef):
    keep_within: Optional[str] = Field(
        None, description="Keep everything newer than this, such as 2d or 1w."
    )
    keep_hourly: Optional[int] = Field(
        None, ge=0, description="Hourly archives to keep."
    )
    keep_daily: Optional[int] = Field(None, ge=0, description="Daily archives to keep.")
    keep_weekly: Optional[int] = Field(
        None, ge=0, description="Weekly archives to keep."
    )
    keep_monthly: Optional[int] = Field(
        None, ge=0, description="Monthly archives to keep."
    )
    keep_quarterly: Optional[int] = Field(
        None, ge=0, description="Quarterly archives to keep."
    )
    keep_yearly: Optional[int] = Field(
        None, ge=0, description="Yearly archives to keep."
    )


@tool(
    name="preview_prune",
    title="Preview a prune",
    description=(
        "Shows what pruning a repository with a retention policy would delete "
        "and at least how much space it would free, from Borg's own dry run. "
        "Nothing is deleted. compare_retention compares common policies."
    ),
    level=Level.OPERATE,
    routes=("GET /api/repositories/", "POST /api/repositories/{repo_id}/prune/preview"),
    read_only=False,
)
async def preview_prune(ctx, args: PruneArgs) -> ToolResult:
    rules = {
        key: getattr(args, key)
        for key in RETENTION_FIELDS
        if getattr(args, key) not in (None, 0, "")
    }
    if not rules:
        return ToolResult(
            "A prune preview needs at least one rule, such as keep_daily 7 or "
            "keep_within 2w. compare_retention shows the current policy.",
            is_error=True,
        )
    repo = await resolve.repository(ctx, args.repository)
    preview = await ctx.api.post(
        f"/api/repositories/{repo['id']}/prune/preview",
        json=rules,
        timeout=LONG_TIMEOUT,
    )
    gone = [a for a in preview.get("archives") or [] if a.get("verdict") == "deleted"]
    gone.sort(key=lambda a: str(a.get("start") or ""))
    deleted, kept = preview.get("deleted_count") or 0, preview.get("kept_count") or 0
    lines = [
        f"Pruning *{repo['name']}* with {_retention(rules)} would delete "
        f"{plural(deleted, 'archive')} and keep {kept}."
    ]
    if preview.get("sizes_available"):
        partial = (
            " Some of them are not measured yet, so it may be more."
            if preview.get("partial_measure")
            else ""
        )
        lines.append(
            f"It would free at least {human_size(preview.get('freed_at_least'))}.{partial}"
        )
    else:
        lines.append("How much space it frees is not known for this repository.")
    if gone:
        lines += ["", "Would delete, oldest first:"]
        lines += [
            f"- *{a['name']}* ({when(a.get('start'))})" for a in gone[:PRUNE_LISTED]
        ]
        if len(gone) > PRUNE_LISTED:
            lines.append(f"- and {len(gone) - PRUNE_LISTED} more")
    lost = preview.get("lost_files") or {}
    if lost.get("total_count"):
        lines += [
            "",
            f"⚠ {plural(lost['total_count'], 'file')} ({human_size(lost.get('total_size'))}) "
            "exist only in archives this would delete.",
        ]
    lines += ["", "Nothing was deleted."]
    data = {k: v for k, v in preview.items() if k != "log"}
    return ToolResult("\n".join(lines), {"repository_id": repo["id"], "preview": data})
