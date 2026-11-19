"""Restore tools (spec 5.5, phase 3): preview, and restore to a new place.

At operate the destination must be empty or not exist yet, checked once
before the restore starts (Borg 2 also refuses existing files while it
extracts; Borg 1 does not). Overwriting is the full-level tool of phase 5.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.mcp import borg_routes, resolve
from app.mcp.client import LONG_TIMEOUT, ApiError
from app.mcp.levels import Level
from app.mcp.registry import tool
from app.mcp.render import ToolResult
from app.mcp.tools.jobs import estimate
from app.mcp.tools.operate import started

PREVIEW_SHOWN = 50
SERVER_BROWSE = "/api/filesystem/browse"


class RestoreTarget(BaseModel):
    repository: str = Field(description="Repository name or id.", examples=["Photos"])
    archive: str = Field(
        description='Archive name or id, or "latest".', examples=["latest"]
    )
    paths: list[str] = Field(
        min_length=1,
        description="Paths inside the archive to restore, as browse_archive shows them.",
        examples=[["home/alex/notes"]],
    )


async def _target(ctx, args: RestoreTarget) -> tuple[dict, dict]:
    repo = await resolve.repository(ctx, args.repository)
    archive = await resolve.archive(ctx, repo, args.archive)
    return repo, archive


@tool(
    name="preview_restore",
    title="Preview a restore",
    description=(
        "Shows which files restoring these paths from an archive would write, "
        "from Borg's own dry run. Nothing is written."
    ),
    level=Level.OPERATE,
    routes=(
        "GET /api/repositories/",
        "GET /api/repositories/{repo_id}/archives",
        "POST /api/restore/preview",
    ),
    read_only=False,
)
async def preview_restore(ctx, args: RestoreTarget) -> ToolResult:
    repo, archive = await _target(ctx, args)
    answer = await ctx.api.post(
        "/api/restore/preview",
        json={
            "repository": repo["path"],
            "repository_id": repo["id"],
            "archive": borg_routes.restore_archive(repo, archive),
            "paths": args.paths,
            "destination": "",
        },
        timeout=LONG_TIMEOUT,
    )
    lines = [
        line for line in (answer.get("preview") or "").splitlines() if line.strip()
    ]
    what = ", ".join(args.paths)
    text = [
        f"Restoring {what} from *{archive['name']}* would write {len(lines)} "
        f"{'entry' if len(lines) == 1 else 'entries'}."
    ]
    if lines:
        text += ["", "```", *lines[:PREVIEW_SHOWN], "```"]
        if len(lines) > PREVIEW_SHOWN:
            text.append(f"and {len(lines) - PREVIEW_SHOWN} more.")
    text += ["", "Nothing was written."]
    return ToolResult(
        "\n".join(text),
        {"archive": archive["name"], "count": len(lines), "entries": lines[:200]},
    )


class RestoreArgs(RestoreTarget):
    destination: str = Field(
        description="Folder to restore into. It must be empty or not exist yet.",
        examples=["/local/restore/notes"],
    )
    destination_connection: Optional[str] = Field(
        None,
        description="SSH connection (user@host or name) when the folder is on another server.",
    )
    layout: Literal["preserve_path", "contents_only"] = Field(
        "preserve_path",
        description="preserve_path keeps the full path under the folder; contents_only puts the selected folder's contents straight in.",
    )


async def _path_metadata(
    ctx, repo: dict, archive: dict, paths: list[str]
) -> list[dict]:
    """Which selected paths are folders, read from the archive, as the web
    UI's browser sends it: contents_only strips a folder itself only when the
    route knows it is one."""
    from app.mcp.tools.archives import _contents

    meta, listed = [], {}
    for selected in paths:
        parent, _, name = selected.strip("/").rpartition("/")
        if parent not in listed:
            path, params = borg_routes.archive_contents(repo, archive, parent)
            listed[parent] = (await _contents(ctx, path, params)).get("items") or []
        item = next((i for i in listed[parent] if i.get("name") == name), None)
        if item and item.get("type") in ("file", "directory"):
            meta.append({"path": selected, "type": item["type"]})
    return meta


class _Refused(Exception):
    pass


async def _listing(ctx, repo: dict, destination: str, ssh: Optional[dict]):
    """The destination's entries, or None when it does not exist yet."""
    if repo.get("execution_target") == "agent":
        route = f"/api/managed-machines/agents/{repo.get('agent_machine_id')}/filesystem/browse"
        # The agent hides dotfiles unless asked; they count as contents here.
        params = {"path": destination, "include_hidden": True}
    elif ssh is not None:
        route = SERVER_BROWSE
        params = {
            "path": destination,
            "connection_type": "ssh",
            "ssh_key_id": ssh.get("ssh_key_id"),
            "host": ssh.get("host"),
            "username": ssh.get("username"),
            "port": ssh.get("port") or 22,
        }
    else:
        route, params = SERVER_BROWSE, {"path": destination}
    try:
        found = await ctx.api.get(route, **params)
    except ApiError as exc:
        if exc.status == 404:
            return None
        raise _Refused() from exc
    return found.get("items") or []


@tool(
    name="restore_files",
    title="Restore files (new location)",
    description=(
        "Restores paths from an archive into a folder that is empty or does not "
        "exist yet, and answers at once with the job id. A folder that holds "
        "anything is refused. Use preview_restore first to see what it would write."
    ),
    level=Level.OPERATE,
    routes=(
        "GET /api/repositories/",
        "GET /api/repositories/{repo_id}/archives",
        "GET /api/ssh-keys/connections",
        "GET /api/filesystem/browse",
        "GET /api/managed-machines/agents/{agent_machine_id}/filesystem/browse",
        "GET /api/browse/{repository_id}/{archive_name}",
        "GET /api/v2/archives/{archive_id}/contents",
        "GET /api/activity/recent",
        "POST /api/restore/start",
    ),
    read_only=False,
    idempotent=False,
)
async def restore_files(ctx, args: RestoreArgs) -> ToolResult:
    repo, archive = await _target(ctx, args)
    if args.destination_connection and repo.get("execution_target") == "agent":
        return ToolResult(
            f"*{repo['name']}* restores on its agent machine, so the folder must be "
            "on that machine. Leave destination_connection empty and pick a folder "
            "there (browse_agent_folders shows them).",
            is_error=True,
        )
    if args.destination_connection and (args.destination.rstrip("/") or "/") in (
        "/",
        "/local",
    ):
        # The SSH browse route lists the connection's default folder for these,
        # while the restore writes the literal path: the check would look elsewhere.
        return ToolResult(
            f"Restore stopped. Pick a folder inside {args.destination} on the other "
            "server, such as /srv/restore, not the top level.",
            is_error=True,
        )
    ssh = (
        await resolve.ssh_connection(ctx, args.destination_connection)
        if args.destination_connection
        else None
    )
    ctx.target = f"restore from {repo['name']}"[:200]
    # ponytail: listed once, then started; something writing into the folder
    # in between is not caught. The route's existing_files=refuse still
    # stops Borg 2 from writing into a folder that filled up meanwhile.
    try:
        items = await _listing(ctx, repo, args.destination, ssh)
    except _Refused:
        return ToolResult(
            f"Restore stopped. I could not look inside {args.destination} to make "
            "sure it is empty, so I did not start the restore. Pick a folder you "
            "can browse with browse_server_folders.",
            is_error=True,
        )
    if items:
        return ToolResult(
            f"Restore stopped. {args.destination} already has files in it, and "
            "restoring at operate only goes into an empty or new folder. Pick one, "
            "or ask an admin for a connection with full access to overwrite.",
            is_error=True,
        )
    metadata = (
        await _path_metadata(ctx, repo, archive, args.paths)
        if args.layout == "contents_only"
        else []
    )
    answer = await ctx.api.post(
        "/api/restore/start",
        json={
            "repository": repo["path"],
            "repository_id": repo["id"],
            "archive": borg_routes.restore_archive(repo, archive),
            "paths": args.paths,
            "destination": args.destination,
            "destination_type": "ssh" if ssh else "local",
            "destination_connection_id": ssh["id"] if ssh else None,
            "restore_layout": args.layout,
            "path_metadata": metadata,
            "existing_files": "refuse",
        },
    )
    took = await estimate(ctx, "restore", repository_id=repo["id"])
    return started(
        f"Restore of *{repo['name']}*", "restore", answer.get("job_id"), took
    )
