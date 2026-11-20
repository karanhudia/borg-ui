"""Manage: create, connect and change repositories (spec 5.5 Manage, 5.9; phase 4)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.mcp import borg_routes, links, passphrase, resolve
from app.mcp.levels import Level
from app.mcp.registry import tool
from app.mcp.render import ToolResult, when
from app.mcp.tools.plans import ScheduleInvalid, validate_schedule

# The app's own default encryption for each Borg version.
DEFAULT_ENCRYPTION = {1: "repokey", 2: "repokey-aes-ocb"}
WHY_SAVE = "Without it the backups cannot be restored if Borg UI's database is lost."


class CreateRepositoryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Name shown in Borg UI.", examples=["Photos"])
    path: str = Field(
        description="Where the repository lives: a folder on the server, or a path on the SSH server when ssh_connection is given.",
        examples=["/data/example/photos"],
    )
    ssh_connection: Optional[str] = Field(
        None,
        description="SSH connection to store it on, as user@host or its id. Leave out for a folder on this server.",
        examples=["borg@backups.example.com"],
    )
    borg_version: Literal[1, 2] = Field(1, description="Borg major version.")
    encryption: Optional[str] = Field(
        None,
        description="Encryption mode. Leave out for the app's default (repokey, or repokey-aes-ocb on Borg 2). `none` stores data unencrypted.",
        examples=["repokey"],
    )
    compression: str = Field("lz4", description="Compression, for example lz4 or zstd.")


async def _connection_id(ctx, ref: Optional[str]) -> Optional[int]:
    if not ref:
        return None
    return (await resolve.ssh_connection(ctx, ref))["id"]


@tool(
    name="create_repository",
    title="Create a repository",
    description=(
        "Creates a new Borg repository on this server or over SSH. For an "
        "encrypted repository Borg UI generates a strong passphrase itself and "
        "never shows it here: the user saves it once in the web UI. Agent and "
        "cloud repositories are set up in the web UI."
    ),
    level=Level.MANAGE,
    routes=(
        "GET /api/ssh-keys/connections",
        "POST /api/repositories/",
        "POST /api/v2/repositories/",
    ),
    read_only=False,
    idempotent=False,
)
async def create_repository(ctx, args: CreateRepositoryArgs) -> ToolResult:
    encryption = args.encryption or DEFAULT_ENCRYPTION[args.borg_version]
    body = {
        "name": args.name,
        "path": args.path,
        "borg_version": args.borg_version,
        "encryption": encryption,
        "compression": args.compression,
        "connection_id": await _connection_id(ctx, args.ssh_connection),
    }
    body = {k: v for k, v in body.items() if v is not None}
    encrypted = encryption != "none"
    if encrypted:
        body["passphrase"] = passphrase.generate()
    answer = await ctx.api.post(borg_routes.repository_create(body), json=body)
    repo = answer.get("repository") or answer
    repo_id = repo["id"]
    ctx.target = f"repository {args.name}"[:200]
    data = {"repository_id": repo_id, "name": args.name, "encryption": encryption}
    if answer.get("already_existed"):
        # The route adds an existing repository with whatever passphrase it was
        # sent and does not check it, so the generated one opens nothing: do not
        # ask the user to save it.
        link = links.web(ctx, "repositories", q=args.name)
        lines = [
            f"⚠ A Borg repository already exists at {args.path}, so Borg UI added it "
            f"as *{args.name}* instead of creating a new one.",
        ]
        if encrypted:
            lines += [
                "",
                "It was added with a passphrase Borg UI generated, which cannot "
                "open it. Open the repository at "
                f"{link} and enter its real passphrase in its settings before "
                "backing up to it.",
            ]
        return ToolResult(
            "\n".join(lines), {**data, "already_existed": True}, is_error=encrypted
        )
    if not encrypted:
        return ToolResult(
            f"✓ Created *{args.name}* at {args.path}, unencrypted.\n\nWant me to set up a backup plan for it?",
            data,
        )
    try:
        passphrase.mark_unsaved(ctx.api.app, repo_id)
    except Exception:
        return ToolResult(
            f"⚠ Created *{args.name}*, but Borg UI could not remind you to save its "
            "passphrase. Open the repository in the web UI and save the passphrase "
            f"from its settings. {WHY_SAVE}",
            data,
            is_error=True,
        )
    link = links.repository(ctx, repo_id)
    return ToolResult(
        "\n".join(
            [
                f"✓ Created *{args.name}* at {args.path} ({encryption}).",
                "",
                "Borg UI generated its passphrase and stored it. It is not shown here, "
                f"so it never passes through the AI. Save it now: {WHY_SAVE}",
                "",
                f"Open {link} to reveal it once and mark it saved.",
                "",
                "Want me to set up a backup plan for it?",
            ]
        ),
        {**data, "save_passphrase_url": link},
    )


class ImportRepositoryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Name shown in Borg UI.", examples=["Old photos"])
    path: str = Field(description="Where the existing repository lives.")
    ssh_connection: Optional[str] = Field(
        None, description="SSH connection it lives on, as user@host or its id."
    )
    borg_version: Literal[1, 2] = Field(1, description="Borg major version.")
    encrypted: bool = Field(
        True,
        description="Whether the repository is encrypted. Encrypted ones are connected in the web UI, where the user types the passphrase.",
    )


@tool(
    name="import_repository",
    title="Connect an existing repository",
    description=(
        "Connects a Borg repository that already exists. An encrypted one needs "
        "its passphrase, which never goes through the AI: the answer is a link "
        "to the web UI's import dialog with everything else filled in."
    ),
    level=Level.MANAGE,
    routes=(
        "GET /api/ssh-keys/connections",
        "POST /api/repositories/import",
        "POST /api/v2/repositories/import",
    ),
    read_only=False,
    idempotent=False,
)
async def import_repository(ctx, args: ImportRepositoryArgs) -> ToolResult:
    connection_id = await _connection_id(ctx, args.ssh_connection)
    ctx.target = f"repository {args.name}"[:200]
    if args.encrypted:
        link = links.import_repository(
            ctx,
            name=args.name,
            path=args.path,
            borg_version=args.borg_version,
            connection_id=connection_id,
        )
        return ToolResult(
            f"To connect *{args.name}*, open {link}\n\nEverything is filled in. "
            "Enter the passphrase there; it stays out of this chat.",
            {"import_url": link},
        )
    body = {
        "name": args.name,
        "path": args.path,
        "borg_version": args.borg_version,
        "encryption": "none",
        "connection_id": connection_id,
    }
    body = {k: v for k, v in body.items() if v is not None}
    answer = await ctx.api.post(borg_routes.repository_import(body), json=body)
    repo = answer.get("repository") or answer
    return ToolResult(
        f"✓ Connected *{args.name}* at {args.path}.\n\nWant me to refresh its archive list?",
        {"repository_id": repo.get("id"), "name": args.name},
    )


# Spec 5.9 and 5.2: never the passphrase, the location or the encryption.
UPDATE_REPOSITORY_FIELDS = frozenset(
    {
        "name",
        "compression",
        "source_directories",
        "exclude_patterns",
        "custom_flags",
        "upload_ratelimit_kib",
        "pre_hook_timeout",
        "post_hook_timeout",
        "continue_on_hook_failure",
        "skip_on_hook_failure",
    }
)


class UpdateRepositoryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str = Field(description="Repository name or id.", examples=["Photos"])
    name: Optional[str] = Field(None, description="New name.")
    compression: Optional[str] = Field(None, description="Compression, e.g. zstd.")
    source_directories: Optional[list[str]] = Field(
        None, description="Folders this repository's own backups read."
    )
    exclude_patterns: Optional[list[str]] = Field(
        None, description="Borg exclude patterns, e.g. *.tmp."
    )
    custom_flags: Optional[str] = Field(
        None, description="Extra flags for borg create."
    )
    upload_ratelimit_kib: Optional[int] = Field(
        None, description="Upload limit in KiB/s; 0 for none."
    )
    pre_hook_timeout: Optional[int] = Field(None, description="Seconds.")
    post_hook_timeout: Optional[int] = Field(None, description="Seconds.")
    continue_on_hook_failure: Optional[bool] = Field(
        None, description="Back up even when the pre-backup script fails."
    )
    skip_on_hook_failure: Optional[bool] = Field(
        None, description="Skip the backup quietly when the pre-backup script fails."
    )


@tool(
    name="update_repository",
    title="Change repository settings",
    description=(
        "Changes a repository's name, compression, folders, exclusions, flags, "
        "upload limit or script timeouts. Its location, encryption and "
        "passphrase stay as they are. Answers with what changed."
    ),
    level=Level.MANAGE,
    routes=("GET /api/repositories/", "PUT /api/repositories/{repo_id}"),
    read_only=False,
)
async def update_repository(ctx, args: UpdateRepositoryArgs) -> ToolResult:
    changes = {
        k: v
        for k, v in args.model_dump(exclude={"repository"}).items()
        if v is not None and k in UPDATE_REPOSITORY_FIELDS
    }
    if not changes:
        return ToolResult(
            "Tell me what to change: a name, compression, folders, exclusions, flags, upload limit or script timeouts.",
            is_error=True,
        )
    repo = await resolve.repository(ctx, args.repository)
    await ctx.api.put(f"/api/repositories/{repo['id']}", json=changes)
    lines = [f"✓ Updated *{changes.get('name', repo['name'])}*.", ""]
    for key, value in changes.items():
        before = repo.get(key)
        shown = f"{before} → {value}" if before not in (None, "", []) else str(value)
        lines.append(f"- {key.replace('_', ' ')}: {shown}")
    return ToolResult(
        "\n".join(lines), {"repository_id": repo["id"], "changed": changes}
    )


class CheckScheduleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str = Field(description="Repository name or id.", examples=["Photos"])
    schedule: str = Field(
        description="Five-field cron expression, or `off` to stop the schedule.",
        examples=["0 3 * * 0"],
    )
    timezone: Optional[str] = Field(
        None, description="IANA timezone; default UTC.", examples=["Europe/Berlin"]
    )


class RepositoryCheckScheduleArgs(CheckScheduleArgs):
    max_duration: Optional[int] = Field(
        None,
        description="Minutes before a check stops and resumes next time (a partial check). Leave out for the current setting.",
    )


async def _set_schedule(ctx, args, route: str, what: str, extra: dict) -> ToolResult:
    repo = await resolve.repository(ctx, args.repository)
    path = route.format(repo_id=repo["id"])
    if args.schedule.strip().lower() == "off":
        await ctx.api.put(path, json={"cron_expression": ""})
        return ToolResult(
            f"✓ {what} of *{repo['name']}* is off.", {"repository_id": repo["id"]}
        )
    try:
        checked = await validate_schedule(ctx, args.schedule, args.timezone)
    except ScheduleInvalid as invalid:
        return ToolResult(invalid.text, is_error=True)
    body = {"cron_expression": checked["cron_expression"]}
    if args.timezone:
        body["timezone"] = checked.get("timezone") or args.timezone
    await ctx.api.put(path, json={**body, **extra})
    runs = checked.get("next_runs") or []
    lines = [
        f"✓ {what} of *{repo['name']}* runs on `{checked['cron_expression']}` ({checked.get('timezone') or 'UTC'})."
    ]
    if runs:
        lines.append(f"Next: {when(runs[0])}.")
    return ToolResult(
        "\n".join(lines), {"repository_id": repo["id"], **body, "next_runs": runs[:3]}
    )


@tool(
    name="set_check_schedule",
    title="Schedule checks",
    description=(
        "Sets when Borg UI checks a repository's integrity, as a cron "
        "expression in a timezone, or turns the schedule off. Optionally limits "
        "each check to a number of minutes."
    ),
    level=Level.MANAGE,
    routes=(
        "GET /api/repositories/",
        "POST /api/schedule/validate-cron",
        "PUT /api/repositories/{repo_id}/check-schedule",
    ),
    read_only=False,
)
async def set_check_schedule(ctx, args: RepositoryCheckScheduleArgs) -> ToolResult:
    extra = {"max_duration": args.max_duration * 60} if args.max_duration else {}
    return await _set_schedule(
        ctx, args, "/api/repositories/{repo_id}/check-schedule", "Checking", extra
    )


@tool(
    name="set_restore_check_schedule",
    title="Schedule restore checks",
    description=(
        "Sets when Borg UI test-restores from a repository to prove backups can "
        "come back, as a cron expression in a timezone, or turns it off. The "
        "paths it restores stay as configured in the web UI."
    ),
    level=Level.MANAGE,
    routes=(
        "GET /api/repositories/",
        "POST /api/schedule/validate-cron",
        "PUT /api/repositories/{repo_id}/restore-check-schedule",
    ),
    read_only=False,
)
async def set_restore_check_schedule(ctx, args: CheckScheduleArgs) -> ToolResult:
    return await _set_schedule(
        ctx,
        args,
        "/api/repositories/{repo_id}/restore-check-schedule",
        "Restore checking",
        {},
    )
