"""Turn the names a person types into Borg UI objects (spec 5.4).

Order: id, exact name, case-insensitive exact, unique prefix, unique
substring. More than one hit at a step asks which one; it never guesses.
"""

from __future__ import annotations

import difflib
from datetime import datetime, timezone
from typing import Callable, Optional, Union

from app.mcp.context import ToolContext

Ref = Union[str, int]
MAX_NAMED = 8
MAX_SUGGESTED = 5


class NotFound(Exception):
    def __init__(self, text: str):
        super().__init__(text)
        self.text = text


class Ambiguous(Exception):
    def __init__(self, text: str):
        super().__init__(text)
        self.text = text


def _plural(kind: str) -> str:
    if kind.endswith("y") and kind[-2:-1] not in "aeiou":
        return kind[:-1] + "ies"
    return kind + "s"


def _article(kind: str) -> str:
    return "an" if kind[:1].lower() in "aeiou" else "a"


def _names(names: list[str]) -> str:
    shown = [f"*{name}*" for name in names[:MAX_NAMED]]
    if len(names) > MAX_NAMED:
        return f"{', '.join(shown)} and {len(names) - MAX_NAMED} more"
    if len(shown) == 1:
        return shown[0]
    return f"{', '.join(shown[:-1])} and {shown[-1]}"


def pick(
    kind: str,
    ref: Ref,
    items: list[dict],
    *,
    name_of: Callable[[dict], str] = lambda item: str(item.get("name") or ""),
) -> dict:
    text = str(ref).strip()
    if text.isdigit():
        for item in items:
            if str(item.get("id")) == text:
                return item
    lowered = text.lower()
    steps = (
        lambda name: name == text,
        lambda name: name.lower() == lowered,
        lambda name: name.lower().startswith(lowered),
        lambda name: lowered in name.lower(),
    )
    for matches in steps:
        hits = [item for item in items if lowered and matches(name_of(item))]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise Ambiguous(
                f'I found {len(hits)} {_plural(kind)} matching "{text}": '
                f"{_names([name_of(h) for h in hits])}. Which one?"
            )
    message = f'I could not find {_article(kind)} {kind} called "{text}".'
    all_names = [name_of(item) for item in items]
    if not all_names:
        raise NotFound(f"{message} There are no {_plural(kind)} yet.")
    if len(all_names) <= MAX_SUGGESTED:
        raise NotFound(f"{message} The {_plural(kind)} are {_names(all_names)}.")
    close = difflib.get_close_matches(text, all_names, n=MAX_SUGGESTED, cutoff=0.4)
    if close:
        raise NotFound(f"{message} Did you mean {_names(close)}?")
    raise NotFound(message)


def ssh_label(connection: dict) -> str:
    label = f"{connection.get('username')}@{connection.get('host')}"
    port = connection.get("port")
    return label if port in (None, 22) else f"{label}:{port}"


def _target(ctx: ToolContext, kind: str, name: str) -> None:
    ctx.target = f"{kind} {name}"[:200]


async def repository(ctx: ToolContext, ref: Ref) -> dict:
    items = (await ctx.api.get("/api/repositories/"))["repositories"]
    repo = pick("repository", ref, items)
    _target(ctx, "repository", repo["name"])
    return repo


async def archives_of(ctx: ToolContext, repo: dict) -> list[dict]:
    """Newest first: the index when it has rows, otherwise Borg's live list."""
    from app.mcp import borg_routes

    indexed = (await ctx.api.get(f"/api/repositories/{repo['id']}/archives"))[
        "archives"
    ]
    if indexed:
        return indexed
    path, params = borg_routes.archives_list(repo)
    live = (await ctx.api.get(path, **params)).get("archives", [])
    return sorted(live, key=lambda a: str(a.get("start") or ""), reverse=True)


async def archive(ctx: ToolContext, repo: dict, ref: str) -> dict:
    items = await archives_of(ctx, repo)
    if str(ref).strip().lower() == "latest":
        if not items:
            raise NotFound(f"*{repo['name']}* has no archives yet.")
        found = items[0]
    else:
        found = pick("archive", ref, items)
    ctx.target = f"archive {found['name']} in {repo['name']}"[:200]
    return found


async def backup_plan(ctx: ToolContext, ref: Ref) -> dict:
    items = (await ctx.api.get("/api/backup-plans/"))["backup_plans"]
    plan = pick("backup plan", ref, items)
    _target(ctx, "backup plan", plan["name"])
    return plan


async def schedule(ctx: ToolContext, ref: Ref) -> dict:
    items = (await ctx.api.get("/api/schedule/"))["jobs"]
    job = pick("schedule", ref, items)
    _target(ctx, "schedule", job["name"])
    return job


async def ssh_connection(ctx: ToolContext, ref: Ref) -> dict:
    items = (await ctx.api.get("/api/ssh-keys/connections"))["connections"]
    found = pick("SSH connection", ref, items, name_of=ssh_label)
    _target(ctx, "SSH connection", ssh_label(found))
    return found


async def agent(ctx: ToolContext, ref: Ref) -> dict:
    items = await ctx.api.get("/api/managed-machines/agents")
    found = pick("agent machine", ref, items)
    _target(ctx, "agent machine", found["name"])
    return found


def parse_since(value: Optional[str]) -> Optional[datetime]:
    """'24h', '7d', '30m' or an ISO date, as an aware UTC datetime."""
    if not value:
        return None
    text = value.strip().lower()
    units = {"m": 60, "h": 3600, "d": 86400}
    if text[:-1].isdigit() and text[-1:] in units:
        from datetime import timedelta

        return datetime.now(timezone.utc) - timedelta(
            seconds=int(text[:-1]) * units[text[-1]]
        )
    try:
        moment = datetime.fromisoformat(text.replace("z", "+00:00"))
    except ValueError:
        raise NotFound(
            f'"{value}" is not a time I understand. Use something like 24h, 7d or 2026-11-01.'
        ) from None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
