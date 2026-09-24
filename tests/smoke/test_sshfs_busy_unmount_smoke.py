#!/usr/bin/env python3
"""A busy SSHFS source mount must never let cleanup delete the remote files.

Reproduces the report where a shell left inside the SSHFS mount made the
post-backup unmount fail, and the temp-root cleanup then ran rmtree through the
still-live mount, deleting the remote machine's files. The remote tree is made
writable by the SSH user so the test fails loudly if that ever happens again.
Runs on the same host as Borg UI (as in the CI SSH smoke job).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure
from tests.smoke.ssh_smoke_helpers import (
    add_ssh_smoke_args,
    ensure_public_key_authorized,
    require_ssh_smoke_config,
)

SENTINELS = {
    "keep-me.txt": "remote data that must survive\n",
    "nested/deeper/keep-me-too.txt": "nested remote data\n",
}


def sshfs_mount_points(marker: str) -> list[str]:
    points = []
    for line in Path("/proc/mounts").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2].startswith("fuse.sshfs") and marker in parts[1]:
            points.append(parts[1].replace("\\040", " "))
    return points


def wait_for_sshfs_mount(marker: str, timeout: float = 60.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        points = sshfs_mount_points(marker)
        if points:
            return points[0]
        time.sleep(0.05)
    raise SmokeFailure(f"No SSHFS mount containing {marker!r} appeared")


def missing_sentinels(root: Path) -> list[str]:
    missing = [
        relative_path
        for relative_path, content in SENTINELS.items()
        if not (root / relative_path).is_file()
        or (root / relative_path).read_text(encoding="utf-8") != content
    ]
    if not (root / "payload.bin").is_file():
        missing.append("payload.bin")
    return missing


def make_tree_deletable(root: Path) -> None:
    """Let the SSH user delete everything, so a wipe through the mount succeeds."""
    for dirpath, _, filenames in os.walk(root):
        os.chmod(dirpath, 0o777)
        for name in filenames:
            os.chmod(os.path.join(dirpath, name), 0o666)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SSHFS busy-unmount smoke test")
    add_ssh_smoke_args(parser)
    args = parser.parse_args()

    auth_keys_path = require_ssh_smoke_config(args)
    if auth_keys_path is None:
        return 0

    client = SmokeClient(args.url)
    busy_holder = None
    try:
        client.authenticate()

        # Runs after other SSH smokes in the same instance: reuse the system key.
        ssh_key = client.request_ok("GET", "/api/ssh-keys/system-key").json()[
            "ssh_key"
        ] or client.generate_ssh_key(name="SSHFS Busy Unmount Smoke Key")
        ensure_public_key_authorized(auth_keys_path, ssh_key["public_key"].strip())
        connection = client.create_ssh_connection(
            key_id=ssh_key["id"],
            host=args.host,
            username=args.username,
            port=args.port,
        )
        if connection["status"] != "connected":
            raise SmokeFailure(f"SSH connection test did not connect: {connection}")
        client.request_ok(
            "PATCH",
            f"/api/ssh-keys/connections/{connection['id']}/backup-source",
            params={"enable": "true"},
        )

        run_id = client.temp_dir.name
        remote_source = Path(args.remote_root) / f"busy-unmount-{run_id}"
        for relative_path, content in SENTINELS.items():
            target = remote_source / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        # Big enough that the mount stays up long enough to pin it.
        client.write_incompressible_file(remote_source / "payload.bin", 64)
        # Debian's /usr/bin/X11 -> "." (the reporter's original failure): a
        # followed symlink here makes an endless X11/X11/... tree.
        (remote_source / "X11").symlink_to(".")
        make_tree_deletable(remote_source)

        repo_id, repo_path = client.create_repository(
            name=f"SSHFS Busy Unmount {run_id}",
            repo_path=str(client.temp_dir / "repo"),
            source_dirs=[str(remote_source)],
            extra={"source_connection_id": connection["id"]},
        )

        job_id = client.start_backup(repo_path)
        mount_point = wait_for_sshfs_mount(remote_source.name)
        # The reporter's shell: a process whose cwd pins the mount busy.
        busy_holder = subprocess.Popen(["sleep", "600"], cwd=mount_point)
        if mount_point not in sshfs_mount_points(remote_source.name):
            raise SmokeFailure("SSHFS mount detached before it could be pinned busy")
        client.log(f"Pinned SSHFS mount busy at {mount_point}")

        client.wait_for_job(
            "/api/backup/status",
            job_id,
            expected={"completed", "completed_with_warnings"},
            timeout=300,
        )

        # The job reports completed before its mount cleanup runs; keep the
        # mount pinned until cleanup has either detached it or wiped the files.
        deadline = time.monotonic() + 120
        while True:
            missing = missing_sentinels(remote_source)
            if missing:
                raise SmokeFailure(
                    f"Remote source files were deleted through the busy SSHFS mount: {missing}"
                )
            if not sshfs_mount_points(remote_source.name):
                break
            if time.monotonic() > deadline:
                raise SmokeFailure(
                    "Busy SSHFS mount was never detached after the backup"
                )
            time.sleep(0.5)
        missing = missing_sentinels(remote_source)
        if missing:
            raise SmokeFailure(
                f"Remote source files were deleted through the busy SSHFS mount: {missing}"
            )

        archive_name = client.list_archives(repo_path)[0]["name"]
        items = client.restore_contents(
            repo_id, archive_name, path=str(remote_source).lstrip("/")
        )
        x11 = next((item for item in items if item["name"] == "X11"), None)
        client.log(f"Archived X11 entry: {x11}")
        if x11 is None or x11.get("type") == "directory":
            raise SmokeFailure(f"X11 -> . was not archived as a symlink: {x11}")

        client.log("SSHFS busy unmount smoke passed")
        return 0
    finally:
        if busy_holder is not None:
            busy_holder.kill()
            busy_holder.wait()
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
