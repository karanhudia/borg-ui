#!/usr/bin/env python3
"""Shared helpers for SSH-backed smoke tests."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


class SSHSmokeConfig(argparse.Namespace):
    url: str
    host: str
    port: int
    username: str
    authorized_keys: str | None
    remote_root: str


def add_ssh_smoke_args(parser: argparse.ArgumentParser, *, default_url: str = "http://localhost:8082") -> None:
    parser.add_argument("--url", default=default_url)
    parser.add_argument("--host", default=os.environ.get("SSH_SMOKE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SSH_SMOKE_PORT", "2222")))
    parser.add_argument("--username", default=os.environ.get("SSH_SMOKE_USER", "borgsmoke"))
    parser.add_argument(
        "--authorized-keys",
        default=os.environ.get("SSH_SMOKE_AUTH_KEYS"),
        help="Path to the target user's authorized_keys file",
    )
    parser.add_argument(
        "--remote-root",
        default=os.environ.get("SSH_SMOKE_REMOTE_ROOT", "/tmp/borg-ui-ssh-smoke"),
        help="Root directory on the SSH host used for smoke test repositories and restore destinations",
    )


def require_ssh_smoke_config(args: SSHSmokeConfig) -> Path | None:
    if not args.authorized_keys:
        print("Remote SSH smoke skipped: authorized_keys path not provided", flush=True)
        return None
    return Path(args.authorized_keys)


def ensure_public_key_authorized(auth_keys_path: Path, public_key: str) -> None:
    """Append the generated key to authorized_keys, using sudo when needed."""
    auth_keys_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = auth_keys_path.read_text(encoding="utf-8") if auth_keys_path.exists() else ""
        if public_key not in existing:
            with auth_keys_path.open("a", encoding="utf-8") as handle:
                if existing and not existing.endswith("\n"):
                    handle.write("\n")
                handle.write(public_key)
                handle.write("\n")
        return
    except PermissionError:
        pass

    helper = """
from pathlib import Path
import sys

path = Path(sys.argv[1])
public_key = sys.argv[2]
path.parent.mkdir(parents=True, exist_ok=True)
existing = path.read_text(encoding="utf-8") if path.exists() else ""
if public_key not in existing:
    with path.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\\n"):
            handle.write("\\n")
        handle.write(public_key)
        handle.write("\\n")
"""
    try:
        subprocess.run(
            ["sudo", sys.executable, "-c", helper, str(auth_keys_path), public_key],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Unable to update authorized_keys via sudo: {exc}") from exc

