"""Archive and file tools (spec 5.5, plan Task 9)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.mcp import borg_routes, resolve
from app.mcp.levels import Level
from app.mcp.registry import tool
from app.mcp.render import (
    ToolResult,
    ago,
    clamp_limit,
    decode_cursor,
    duration,
    human_size,
    more_line,
    next_cursor,
    page,
    when,
)
from app.mcp.tools._common import plural

ARCHIVE_FIELDS = (
    "id",
    "borg_id",
    "name",
    "series",
    "start",
    "end",
    "duration_seconds",
    "nfiles",
    "original_size",
    "compressed_size",
    "deduplicated_size",
    "hostname",
    "comment",
    "history_state",
)
CHANGE_GLYPH = {"added": "+", "removed": "-", "modified": "~", "summary": "…"}

_REPO = Field(description="Repository name or id.", examples=["Photos"])
_ARCHIVE = Field(
    description='Archive name or id, or "latest" for the newest one.',
    examples=["latest", "photos-2026-11-14"],
)
_LIMIT = Field(None, description="How many to show (default 25, max 200).")
_CURSOR = Field(None, description="Page marker from the previous answer.")


def _fields(archive: dict) -> dict:
    return {key: archive.get(key) for key in ARCHIVE_FIELDS}


def _archive_line(archive: dict) -> str:
    size = archive.get("original_size")
    added = archive.get("deduplicated_size")
    bits = [ago(archive.get("start"))]
    if size is not None:
        bits.append(human_size(size))
    if added is not None:
        bits.append(f"{human_size(added)} new")
    if archive.get("nfiles") is not None:
        bits.append(plural(archive["nfiles"], "file"))
    return f"*{archive['name']}*: {', '.join(bits)}"


class ListArchivesArgs(BaseModel):
    repository: str = _REPO
    newest_first: bool = Field(
        True, description="Newest first (default) or oldest first."
    )
    limit: Optional[int] = _LIMIT
    cursor: Optional[str] = _CURSOR


@tool(
    name="list_archives",
    title="List archives",
    description=(
        "The archives (backups) in a repository with their time, size and how "
        "much new data each added. Paged. Use get_archive for one archive, "
        "browse_archive to look inside one."
    ),
    level=Level.READ,
    routes=(
        "GET /api/repositories/",
        "GET /api/repositories/{repo_id}/archives",
        "GET /api/repositories/{repo_id}/archives/live",
        "GET /api/v2/repositories/{repo_id}/archives/live",
    ),
)
async def list_archives(ctx, args: ListArchivesArgs) -> ToolResult:
    repo = await resolve.repository(ctx, args.repository)
    archives = await resolve.archives_of(ctx, repo)
    if not args.newest_first:
        archives = list(reversed(archives))
    if not archives:
        return ToolResult(f"*{repo['name']}* has no archives yet.", {"archives": []})
    shown, cursor = page(archives, clamp_limit(args.limit), args.cursor)
    lines = [f"*{repo['name']}* has {plural(len(archives), 'archive')}:", ""]
    lines += [_archive_line(a) for a in shown]
    more = more_line(len(shown), len(archives), "archives", cursor)
    if more:
        lines += ["", more]
    return ToolResult(
        "\n".join(lines),
        {
            "repository_id": repo["id"],
            "total": len(archives),
            "archives": [_fields(a) for a in shown],
            "next_cursor": cursor,
        },
    )


class ArchiveRef(BaseModel):
    repository: str = _REPO
    archive: str = _ARCHIVE


@tool(
    name="get_archive",
    title="Look at an archive",
    description=(
        "One archive in detail: when it ran, how long it took, how many files, "
        "its size and how much new data it added to the repository."
    ),
    level=Level.READ,
    routes=(
        "GET /api/repositories/",
        "GET /api/repositories/{repo_id}/archives",
        "GET /api/repositories/{repo_id}/archives/live",
        "GET /api/archives/{archive_id}/info",
        "GET /api/v2/archives/{archive_id}/info",
    ),
)
async def get_archive(ctx, args: ArchiveRef) -> ToolResult:
    repo = await resolve.repository(ctx, args.repository)
    archive = await resolve.archive(ctx, repo, args.archive)
    info = archive
    if "borg_id" not in archive:  # a live row: the index does not have it
        path, params = borg_routes.archive_info(repo, archive)
        info = {**archive, **((await ctx.api.get(path, **params)).get("info") or {})}
    took = info.get("duration_seconds")
    lines = [
        f"*{info['name']}* in *{repo['name']}*",
        "",
        f"Started: {when(info.get('start'))}",
        f"Took: {duration(took) if took is not None else 'unknown'}",
        f"Files: {info.get('nfiles') if info.get('nfiles') is not None else 'unknown'}",
        f"Size: {human_size(info.get('original_size'))} (compressed {human_size(info.get('compressed_size'))})",
        f"New data added: at least {human_size(info.get('deduplicated_size'))}",
    ]
    if info.get("hostname"):
        lines.append(f"Made on: {info['hostname']}")
    if info.get("comment"):
        lines.append(f"Comment: {info['comment']}")
    return ToolResult(
        "\n".join(lines), {"repository_id": repo["id"], "archive": _fields(info)}
    )


class BrowseArgs(BaseModel):
    repository: str = _REPO
    archive: str = _ARCHIVE
    path: str = Field(
        "",
        description="Folder inside the archive; empty for the top.",
        examples=["", "home/alex/Documents"],
    )
    limit: Optional[int] = _LIMIT
    cursor: Optional[str] = _CURSOR


@tool(
    name="browse_archive",
    title="Browse files in an archive",
    description=(
        "Lists one folder inside an archive: folders first, then files with "
        "size and modified time. Paged. Pass a path to go deeper. Use "
        "search_files to find a file by name across archives."
    ),
    level=Level.READ,
    routes=(
        "GET /api/repositories/",
        "GET /api/repositories/{repo_id}/archives",
        "GET /api/repositories/{repo_id}/archives/live",
        "GET /api/browse/{repository_id}/{archive_name}",
        "GET /api/v2/archives/{archive_id}/contents",
    ),
)
async def browse_archive(ctx, args: BrowseArgs) -> ToolResult:
    repo = await resolve.repository(ctx, args.repository)
    archive = await resolve.archive(ctx, repo, args.archive)
    folder = args.path.strip("/")
    path, params = borg_routes.archive_contents(repo, archive, folder)
    items = (await ctx.api.get(path, **params)).get("items") or []
    label = f"/{folder}" if folder else "the top"
    if not items:
        parent = folder.rsplit("/", 1)[0] if "/" in folder else ""
        hint = (
            f" Try its parent, {('/' + parent) if parent else 'the top'}."
            if folder
            else ""
        )
        return ToolResult(
            f"Nothing at {label} in *{archive['name']}*.{hint}",
            {"items": [], "path": folder},
        )
    items = sorted(
        items,
        key=lambda i: (i.get("type") != "directory", str(i.get("name") or "").lower()),
    )
    shown, cursor = page(items, clamp_limit(args.limit), args.cursor)
    lines = [
        f"{label.capitalize() if not folder else label} of *{archive['name']}* ({plural(len(items), 'entry', 'entries')}):",
        "",
    ]
    for item in shown:
        if item.get("type") == "directory":
            lines.append(f"📁 {item.get('name')}/")
        else:
            lines.append(
                f"{item.get('name')}  {human_size(item.get('size'))}, modified {ago(item.get('mtime'))}"
            )
    more = more_line(len(shown), len(items), "entries", cursor)
    if more:
        lines += ["", more]
    data = {
        "path": folder,
        "total": len(items),
        "items": [
            {k: i.get(k) for k in ("name", "type", "size", "mtime", "path")}
            for i in shown
        ],
        "next_cursor": cursor,
    }
    return ToolResult("\n".join(lines), data)


class SearchArgs(BaseModel):
    repository: str = _REPO
    query: str = Field(
        description="Part of a file or folder name.", examples=["invoice", ".psd"]
    )
    limit: Optional[int] = Field(
        None, description="How many paths to show (default 25, max 200)."
    )


@tool(
    name="search_files",
    title="Search backed-up files",
    description=(
        "Finds files and folders by name across all indexed archives of a "
        "repository, with when each was first and last seen. Use it for 'which "
        "backup has my file X?'. Then use get_file_history for one path."
    ),
    level=Level.READ,
    routes=("GET /api/repositories/", "GET /api/repositories/{repo_id}/search"),
)
async def search_files(ctx, args: SearchArgs) -> ToolResult:
    repo = await resolve.repository(ctx, args.repository)
    limit = clamp_limit(args.limit)
    found = await ctx.api.get(
        f"/api/repositories/{repo['id']}/search", q=args.query, limit=limit
    )
    results = found.get("results") or []
    if found.get("detail_locked"):
        count = found.get("match_count") or 0
        return ToolResult(
            f'{plural(count, "path")} in *{repo["name"]}* match "{args.query}". Seeing which ones, and where they are, is part of Borg UI Pro.',
            {"match_count": count, "detail_locked": True},
        )
    if not results:
        return ToolResult(
            f'Nothing in *{repo["name"]}* matches "{args.query}".', {"results": []}
        )
    lines = [
        f'{plural(len(results), "path")} in *{repo["name"]}* match "{args.query}":',
        "",
    ]
    for r in results:
        lines.append(
            f"{r['path']}: first seen {ago(r.get('first_seen'))}, last seen {ago(r.get('last_seen'))}"
        )
    if found.get("truncated"):
        lines += [
            "",
            f"There are more matches. Ask with a narrower name or a larger limit (max 200).",
        ]
    return ToolResult(
        "\n".join(lines), {"results": results, "truncated": found.get("truncated")}
    )


class HistoryArgs(BaseModel):
    repository: str = _REPO
    path: str = Field(
        description="The full path of a file or folder, as search_files shows it.",
        examples=["home/alex/notes.md"],
    )


@tool(
    name="get_file_history",
    title="Trace a file's history",
    description=(
        "Every recorded change of one file or folder across the archives of a "
        "repository: when it appeared, changed, or was removed, and whether the "
        "newest archive still has it. Use it before restoring an older version."
    ),
    level=Level.READ,
    routes=("GET /api/repositories/", "GET /api/repositories/{repo_id}/history"),
)
async def get_file_history(ctx, args: HistoryArgs) -> ToolResult:
    repo = await resolve.repository(ctx, args.repository)
    path = args.path.strip("/")
    history = await ctx.api.get(f"/api/repositories/{repo['id']}/history", path=path)
    if history.get("detail_locked"):
        return ToolResult(
            f"{path} has {plural(history.get('versions') or 0, 'recorded change')}. The details are part of Borg UI Pro.",
            {"versions": history.get("versions"), "detail_locked": True},
        )
    entries = history.get("entries") or []
    if not entries:
        return ToolResult(
            f"No recorded changes for {path} in *{repo['name']}*. Check the exact path with search_files.",
            {"entries": []},
        )
    state = (
        "is in the newest archive"
        if history.get("present_in_latest")
        else "is not in the newest archive"
    )
    lines = [
        f"{path} {state}. {plural(len(entries), 'change')} recorded, newest first:",
        "",
    ]
    for e in entries[:50]:
        size = ""
        if e.get("size_after") is not None:
            size = f", {human_size(e['size_after'])}"
        lines.append(
            f"{CHANGE_GLYPH.get(e.get('change'), '·')} {e.get('change')} in *{e.get('archive_name')}* ({ago(e.get('start'))}{size})"
        )
    if len(entries) > 50:
        lines += ["", f"Showing the newest 50 of {len(entries)} changes."]
    coverage = history.get("coverage") or {}
    if coverage and coverage.get("indexed", 0) < coverage.get("total", 0):
        lines += [
            "",
            f"⚠ Only {coverage['indexed']} of {coverage['total']} archives are indexed so far, so older changes may be missing.",
        ]
    return ToolResult(
        "\n".join(lines),
        {
            "path": path,
            "entries": entries[:200],
            "present_in_latest": history.get("present_in_latest"),
            "coverage": coverage,
        },
    )


class CompareArgs(BaseModel):
    repository: str = _REPO
    archive: str = _ARCHIVE
    compare_to: Optional[str] = Field(
        None, description="Older archive to compare with; default is the one before it."
    )
    path_prefix: Optional[str] = Field(
        None, description="Only show changes below this folder."
    )
    limit: Optional[int] = _LIMIT
    cursor: Optional[str] = _CURSOR


@tool(
    name="compare_archives",
    title="See what changed between archives",
    description=(
        "Files added, removed and modified in one archive compared with the "
        "previous one (or one you name). Paged. Use it for 'what changed in "
        "last night's backup?'."
    ),
    level=Level.READ,
    routes=(
        "GET /api/repositories/",
        "GET /api/repositories/{repo_id}/archives",
        "GET /api/repositories/{repo_id}/archives/{archive_id}/changes",
    ),
)
async def compare_archives(ctx, args: CompareArgs) -> ToolResult:
    repo = await resolve.repository(ctx, args.repository)
    target = await resolve.archive(ctx, repo, args.archive)
    other = (
        await resolve.archive(ctx, repo, args.compare_to) if args.compare_to else None
    )
    if "borg_id" not in target:
        return ToolResult(
            f"*{repo['name']}* is not indexed, so changes between archives are not available.",
            {"changes": []},
            is_error=True,
        )
    limit = clamp_limit(args.limit)
    offset = decode_cursor(args.cursor)
    found = await ctx.api.get(
        f"/api/repositories/{repo['id']}/archives/{target['id']}/changes",
        compare_to=other["id"] if other else None,
        path_prefix=args.path_prefix,
        limit=limit,
        cursor=offset,
    )
    totals = found.get("totals") or {}
    summary = ", ".join(
        f"{totals.get(k, 0)} {k}" for k in ("added", "removed", "modified")
    )
    if found.get("detail_locked"):
        return ToolResult(
            f"*{target['name']}*: {summary}. The file list is part of Borg UI Pro.",
            {"totals": totals, "detail_locked": True},
        )
    changes = found.get("changes") or []
    against = f"*{other['name']}*" if other else "the previous archive"
    lines = [f"*{target['name']}* compared with {against}: {summary}.", ""]
    lines += [
        f"{CHANGE_GLYPH.get(c.get('change'), '·')} {c.get('path')}"
        + (
            f" ({human_size(c['size_after'])})"
            if c.get("size_after") is not None
            else ""
        )
        for c in changes
    ]
    if not changes:
        lines.append("No file changes recorded.")
    cursor = next_cursor(found["next_cursor"]) if found.get("next_cursor") else None
    if cursor:
        lines += ["", "There are more changes. Ask for the next page to see them."]
    if found.get("incomplete"):
        lines += [
            "",
            "⚠ Some archives are not indexed yet, so this list may be incomplete.",
        ]
    return ToolResult(
        "\n".join(lines),
        {
            "totals": totals,
            "changes": changes,
            "next_cursor": cursor,
            "incomplete": found.get("incomplete"),
        },
    )
