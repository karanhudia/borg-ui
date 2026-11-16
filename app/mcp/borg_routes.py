"""Borg 1/2 route selection for reads, mirroring the frontend's BorgApiClient.

`frontend/src/services/borgApi/client.ts` is the reference: a Borg 2
repository run locally uses /api/v2; agent repositories and Borg 1 use the
v1 routes. Later phases add the write operations here. Nothing else in the
backend may branch on Borg versions for MCP.
"""

from __future__ import annotations


def _v(repo: dict) -> str:
    if repo.get("execution_target") == "agent":
        return ""
    return "/v2" if repo.get("borg_version") == 2 else ""


def _borg_id(archive: dict) -> str:
    """The Borg archive id: index rows carry it as `borg_id`, live rows as `id`."""
    return str(archive.get("borg_id") or archive["id"])


def repository_info(repo: dict) -> tuple[str, dict]:
    return f"/api{_v(repo)}/repositories/{repo['id']}/info", {}


def repository_stats(repo: dict) -> tuple[str, dict]:
    return f"/api{_v(repo)}/repositories/{repo['id']}/stats", {}


def archives_list(repo: dict, **params) -> tuple[str, dict]:
    return f"/api{_v(repo)}/repositories/{repo['id']}/archives/live", params


def archive_info(repo: dict, archive: dict) -> tuple[str, dict]:
    # Borg 1 names are unique and the v1 route addresses Borg 1 by name; it
    # turns a Borg 2 id into an `aid:` selector itself.
    selector = archive["name"] if repo.get("borg_version") != 2 else _borg_id(archive)
    return (
        f"/api{_v(repo)}/archives/{selector}/info",
        {"repository": repo["id"], "include_files": False},
    )


def archive_contents(repo: dict, archive: dict, path: str) -> tuple[str, dict]:
    if _v(repo) == "/v2":
        return (
            f"/api/v2/archives/{_borg_id(archive)}/contents",
            {"repository": repo["id"], "path": path},
        )
    selector = (
        f"aid:{_borg_id(archive)}" if repo.get("borg_version") == 2 else archive["name"]
    )
    return f"/api/browse/{repo['id']}/{selector}", {"path": path}
