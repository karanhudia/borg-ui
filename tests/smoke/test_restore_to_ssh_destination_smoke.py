#!/usr/bin/env python3
"""Black-box smoke coverage for restoring to an SSH destination."""

from __future__ import annotations

import argparse
import sys
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run restore-to-SSH-destination smoke test"
    )
    add_ssh_smoke_args(parser)
    args = parser.parse_args()

    auth_keys_path = require_ssh_smoke_config(args)
    if auth_keys_path is None:
        return 0

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        ssh_key = client.generate_ssh_key(name="SSH Restore Destination Smoke Key")
        public_key = ssh_key["public_key"].strip()
        ensure_public_key_authorized(auth_keys_path, public_key)

        connection = client.create_ssh_connection(
            key_id=ssh_key["id"],
            host=args.host,
            username=args.username,
            port=args.port,
        )
        if connection["status"] != "connected":
            raise SmokeFailure(f"SSH connection test did not connect: {connection}")

        source_root = client.prepare_source_tree(
            "restore-to-ssh-source",
            {
                "docs/remote-dest.txt": "restore to ssh destination\n",
            },
        )
        repo_id, repo_path, _backup_job_id, _backup = (
            client.create_repository_and_backup(
                name=f"Restore To SSH Repo {client.temp_dir.name}",
                repo_path=client.temp_dir / "restore-to-ssh-repo",
                source_dirs=[source_root],
            )
        )

        archives = client.list_archives(repo_path)
        if len(archives) != 1:
            raise SmokeFailure(
                f"Expected one archive before restore-to-SSH, got {archives}"
            )
        archive_name = archives[0]["name"]

        destination_root = (
            Path(args.remote_root) / f"restore-dest-{client.temp_dir.name}"
        )
        destination_root.mkdir(parents=True, exist_ok=True)
        repo_root = client.container_path(source_root).lstrip("/")

        restore_job_id = client.start_restore(
            repository=repo_path,
            archive_name=archive_name,
            repository_id=repo_id,
            destination=destination_root.as_posix(),
            paths=[f"{repo_root}/docs"],
            destination_type="ssh",
            destination_connection_id=connection["id"],
        )
        client.wait_for_job(
            "/api/restore/status", restore_job_id, expected={"completed"}, timeout=180
        )

        restored_files = sorted(
            path for path in destination_root.rglob("remote-dest.txt") if path.is_file()
        )
        if not restored_files:
            all_files = sorted(
                path.relative_to(destination_root).as_posix()
                for path in destination_root.rglob("*")
                if path.is_file()
            )
            raise SmokeFailure(
                f"Restore to SSH destination did not produce expected file: {all_files}"
            )
        restored_file = restored_files[0]
        if restored_file.read_text(encoding="utf-8") != "restore to ssh destination\n":
            raise SmokeFailure(
                f"Unexpected restore-to-SSH file contents: {restored_file.read_text(encoding='utf-8')!r}"
            )

        client.log("Restore to SSH destination smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
