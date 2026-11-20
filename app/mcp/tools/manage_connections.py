"""Manage: SSH keys, connections and host keys (spec 5.5 Manage, 5.9; phase 4)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.mcp import links, resolve
from app.mcp.levels import Level
from app.mcp.registry import tool
from app.mcp.render import ToolResult


async def _keys(ctx) -> list[dict]:
    return (await ctx.api.get("/api/ssh-keys"))["ssh_keys"]


class GenerateKeyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Name for the key.", examples=["Offsite"])
    key_type: Literal["ed25519", "rsa", "ecdsa"] = Field(
        "ed25519", description="Key type; ed25519 unless a server needs another."
    )
    system_key: Optional[bool] = Field(
        None,
        description="Make it Borg UI's main key. Leave out: it becomes the main key only when there is none yet.",
    )


@tool(
    name="generate_ssh_key",
    title="Create an SSH key",
    description=(
        "Generates a new SSH key pair on the Borg UI server and shows its public "
        "key, to add to a backup server's authorized_keys. The private key stays "
        "on the server and is never shown."
    ),
    level=Level.MANAGE,
    routes=("GET /api/ssh-keys", "POST /api/ssh-keys/generate"),
    read_only=False,
    idempotent=False,
)
async def generate_ssh_key(ctx, args: GenerateKeyArgs) -> ToolResult:
    system_key = args.system_key
    if system_key is None:
        system_key = not any(key.get("is_system_key") for key in await _keys(ctx))
    answer = await ctx.api.post(
        "/api/ssh-keys/generate",
        json={"name": args.name, "key_type": args.key_type, "system_key": system_key},
    )
    key = answer.get("ssh_key") or {}
    ctx.target = f"SSH key {args.name}"[:200]
    return ToolResult(
        "\n".join(
            [
                f"✓ Created the SSH key *{args.name}* ({args.key_type}).",
                "",
                "Public key, for the server's ~/.ssh/authorized_keys:",
                "",
                f"```\n{key.get('public_key', '')}\n```",
                "",
                "Want me to add a connection that uses it?",
            ]
        ),
        {"ssh_key_id": key.get("id"), "public_key": key.get("public_key")},
    )


class AddConnectionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(
        description="Server name or address.", examples=["backups.example.com"]
    )
    username: str = Field(description="SSH user.", examples=["backup"])
    port: int = Field(22, description="SSH port.")
    ssh_key: Optional[str] = Field(
        None, description="Key name or id. Leave out for Borg UI's main key."
    )


@tool(
    name="add_ssh_connection",
    title="Add an SSH connection",
    description=(
        "Adds an SSH connection and tests it with a key that is already on the "
        "server. When the key is not there yet, the answer shows the public key "
        "to add, and a link to deploy it in the web UI with the server's "
        "password. Never takes a password here."
    ),
    level=Level.MANAGE,
    routes=("GET /api/ssh-keys", "POST /api/ssh-keys/{key_id}/test-connection"),
    read_only=False,
)
async def add_ssh_connection(ctx, args: AddConnectionArgs) -> ToolResult:
    keys = await _keys(ctx)
    if args.ssh_key:
        key = resolve.pick("SSH key", args.ssh_key, keys)
    else:
        key = next((k for k in keys if k.get("is_system_key")), None)
        if key is None:
            return ToolResult(
                "Borg UI has no SSH key yet. Want me to create one with generate_ssh_key?",
                is_error=True,
            )
    label = f"{args.username}@{args.host}" + (
        f":{args.port}" if args.port != 22 else ""
    )
    ctx.target = f"SSH connection {label}"[:200]
    answer = await ctx.api.post(
        f"/api/ssh-keys/{key['id']}/test-connection",
        json={"host": args.host, "username": args.username, "port": args.port},
    )
    connection = answer.get("connection") or {}
    data = {"connection_id": connection.get("id"), "status": connection.get("status")}
    if answer.get("success"):
        return ToolResult(
            f"✓ Connected to *{label}* with the key *{key['name']}*.\n\n"
            "Want me to create a repository there?",
            data,
        )
    link = links.ssh_deploy(ctx, args.host, args.username, args.port)
    return ToolResult(
        "\n".join(
            [
                f"⚠ Saved *{label}*, but the key *{key['name']}* is not on that server yet.",
                "",
                "Either add this line to ~/.ssh/authorized_keys on the server:",
                "",
                f"```\n{key.get('public_key', '')}\n```",
                "",
                f"or open {link} and enter the server's password there to deploy it.",
                "Then ask me to test the connection.",
            ]
        ),
        {**data, "deploy_url": link},
    )


# Host and user stay out: changing them points at a different server.
UPDATE_SSH_FIELDS = frozenset(
    {
        "default_path",
        "ssh_path_prefix",
        "mount_point",
        "use_sftp_mode",
        "use_sudo",
        "port",
    }
)


class UpdateConnectionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ssh_connection: str = Field(
        description="Connection as user@host or its id.",
        examples=["borg@backups.example.com"],
    )
    default_path: Optional[str] = Field(None, description="Folder browsing starts in.")
    ssh_path_prefix: Optional[str] = Field(
        None, description="Prefix for SSH commands, e.g. /volume1 on Synology."
    )
    mount_point: Optional[str] = Field(
        None, description="Logical mount point, e.g. /offsite."
    )
    use_sftp_mode: Optional[bool] = Field(None, description="Use SFTP for key deploys.")
    use_sudo: Optional[bool] = Field(None, description="Run remote commands with sudo.")
    port: Optional[int] = Field(None, description="SSH port.")


@tool(
    name="update_ssh_connection",
    title="Change an SSH connection",
    description=(
        "Changes an SSH connection's port, default folder, path prefix, mount "
        "point, SFTP mode or sudo use. The server and user stay the same; add "
        "a new connection for a different server."
    ),
    level=Level.MANAGE,
    routes=(
        "GET /api/ssh-keys/connections",
        "PUT /api/ssh-keys/connections/{connection_id}",
    ),
    read_only=False,
)
async def update_ssh_connection(ctx, args: UpdateConnectionArgs) -> ToolResult:
    changes = {
        k: v
        for k, v in args.model_dump(exclude={"ssh_connection"}).items()
        if v is not None and k in UPDATE_SSH_FIELDS
    }
    if not changes:
        return ToolResult(
            "Tell me what to change: port, default folder, path prefix, mount point, SFTP mode or sudo.",
            is_error=True,
        )
    connection = await resolve.ssh_connection(ctx, args.ssh_connection)
    await ctx.api.put(f"/api/ssh-keys/connections/{connection['id']}", json=changes)
    lines = [f"✓ Updated *{resolve.ssh_label(connection)}*.", ""]
    for key, value in changes.items():
        before = connection.get(key)
        shown = f"{before} → {value}" if before not in (None, "") else str(value)
        lines.append(f"- {key.replace('_', ' ')}: {shown}")
    return ToolResult(
        "\n".join(lines), {"connection_id": connection["id"], "changed": changes}
    )


class TrustHostKeyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ssh_connection: str = Field(
        description="Connection as user@host or its id.",
        examples=["borg@backups.example.com"],
    )
    fingerprint: Optional[str] = Field(
        None,
        description="The fingerprint the user confirmed. Leave out on the first call to see it.",
        examples=["SHA256:..."],
    )


@tool(
    name="trust_host_key",
    title="Trust a server's host key",
    description=(
        "Pins an SSH server's host key in two calls. The first shows the "
        "fingerprint and trusts nothing; ask the user to compare it with the "
        "server's own. The second, with that fingerprint, trusts the key only "
        "if the server still shows the same one."
    ),
    level=Level.MANAGE,
    routes=(
        "GET /api/ssh-keys/connections",
        "GET /api/ssh-keys/connections/{connection_id}/host-key",
        "POST /api/ssh-keys/connections/{connection_id}/host-key/trust",
    ),
    read_only=False,
)
async def trust_host_key(ctx, args: TrustHostKeyArgs) -> ToolResult:
    connection = await resolve.ssh_connection(ctx, args.ssh_connection)
    label = resolve.ssh_label(connection)
    base = f"/api/ssh-keys/connections/{connection['id']}/host-key"
    scan = await ctx.api.get(base)
    observed, seen = scan.get("observed_key"), scan.get("observed_fingerprint")
    if not observed or not seen:
        return ToolResult(
            f"✗ *{label}* did not answer with a host key. Check the server is up and the port is right.",
            is_error=True,
        )
    if not args.fingerprint:
        trusted = scan.get("trusted_fingerprint")
        lines = [f"*{label}* shows this host key: `{seen}`", ""]
        if trusted and trusted != seen:
            lines += [f"⚠ Borg UI trusted a different key before: `{trusted}`.", ""]
        lines.append(
            "Nothing is trusted yet. Ask the user to compare it with the server's own "
            "fingerprint (`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the "
            "server), then call me again with it."
        )
        return ToolResult(
            "\n".join(lines), {"observed_fingerprint": seen, "trusted": False}
        )
    if args.fingerprint.strip() != seen:
        return ToolResult(
            f"✗ Not trusted. *{label}* now shows a different key (`{seen}`) from the one "
            "confirmed. Check with the server's admin before trusting anything.",
            {"observed_fingerprint": seen, "trusted": False},
            is_error=True,
        )
    await ctx.api.post(f"{base}/trust", json={"key": observed})
    return ToolResult(
        f"✓ Borg UI now trusts *{label}*'s host key `{seen}`.",
        {"observed_fingerprint": seen, "trusted": True},
    )
