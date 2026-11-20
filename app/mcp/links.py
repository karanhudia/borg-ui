"""Hand-off links into the web UI (spec 2026-11-14-mcp-server, 5.9).

A tool that needs a secret prepares what it can and links to the dialog
where the user types the secret themselves. Links never carry a secret.
"""

from __future__ import annotations

from urllib.parse import urlencode

from app.core.oidc import build_external_base_url

SECRET_WORDS = ("passphrase", "password", "private_key", "secret", "token")


def base_url(request) -> str:
    """PUBLIC_BASE_URL when set, else the request's host, plus BASE_PATH."""
    root_path = (request.scope.get("root_path") or "").rstrip("/")
    return f"{build_external_base_url(request).rstrip('/')}{root_path}"


def web(ctx, page: str, **params) -> str:
    clean = {}
    for key, value in params.items():
        key = key.rstrip("_")  # `import_` for the reserved word
        if any(word in key.lower() for word in SECRET_WORDS):
            raise ValueError(f"Hand-off links never carry {key}")
        if value is not None:
            clean[key] = value
    query = f"?{urlencode(clean)}" if clean else ""
    return f"{ctx.base_url.rstrip('/')}/{page}{query}"


def repository(ctx, repo_id: int) -> str:
    return web(ctx, "repositories", reveal=repo_id)


def import_repository(ctx, **fields) -> str:
    return web(ctx, "repositories", import_=1, **fields)


def ssh_deploy(ctx, host: str, username: str, port: int = 22) -> str:
    return web(
        ctx, "ssh-connections", deploy=1, host=host, username=username, port=port
    )


def rclone_remote(ctx, remote_id: int) -> str:
    return web(ctx, "cloud-storage", edit=remote_id)


def new_user(ctx, **fields) -> str:
    return web(ctx, "settings/users", new=1, **fields)
