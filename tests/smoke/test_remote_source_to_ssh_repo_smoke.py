#!/usr/bin/env python3
"""Black-box smoke coverage for remote-source backups into SSH repositories."""

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
        description="Run remote-source to SSH repository smoke test"
    )
    add_ssh_smoke_args(parser)
    args = parser.parse_args()

    auth_keys_path = require_ssh_smoke_config(args)
    if auth_keys_path is None:
        return 0

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        ssh_key = client.generate_ssh_key(name="SSH Remote Source Smoke Key")
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

        verify_payload = client.verify_ssh_connection_borg(connection["id"])
        if not verify_payload.get("installed"):
            raise SmokeFailure(f"Remote Borg verification failed: {verify_payload}")
        backup_source_payload = client.request_ok(
            "PATCH",
            f"/api/ssh-keys/connections/{connection['id']}/backup-source",
            params={"enable": "true"},
        ).json()
        if not backup_source_payload.get("is_backup_source"):
            raise SmokeFailure(
                f"Unable to enable SSH connection as backup source: {backup_source_payload}"
            )

        run_id = client.temp_dir.name
        remote_source_path = Path(args.remote_root) / f"remote-source-{run_id}"
        remote_source_path.mkdir(parents=True, exist_ok=True)
        (remote_source_path / "remote-source.txt").write_text(
            "remote source backup smoke\n", encoding="utf-8"
        )

        remote_repo_path = f"{args.remote_root}/remote-source-repo-{run_id}"
        create_response = client.request_ok(
            "POST",
            "/api/repositories/",
            headers=client._headers(json_body=True),
            json={
                "name": f"Remote Source SSH Repo {run_id}",
                "path": remote_repo_path,
                "connection_id": connection["id"],
                "encryption": "none",
                "compression": "lz4",
                "repository_type": "ssh",
                "source_directories": [remote_source_path.as_posix()],
                "source_connection_id": connection["id"],
                "exclude_patterns": [],
            },
            expected=(200, 201),
        )
        repo_payload = create_response.json().get("repository", create_response.json())
        repo_path = repo_payload["path"]
        if not str(repo_path).startswith("ssh://"):
            raise SmokeFailure(f"Expected remote repository path, got {repo_payload}")

        backup_job_id = client.start_backup(repo_path)
        client.wait_for_job(
            "/api/backup/status",
            backup_job_id,
            expected={"completed", "completed_with_warnings"},
            timeout=180,
        )
        status_payload = client.request_ok(
            "GET", f"/api/backup/status/{backup_job_id}"
        ).json()
        if status_payload.get("route_strategy") != "remote_direct":
            raise SmokeFailure(
                f"Expected remote_direct route strategy, got {status_payload}"
            )
        if status_payload.get("execution_mode") != "remote_ssh":
            raise SmokeFailure(
                f"Expected remote_ssh execution mode, got {status_payload}"
            )

        archives = client.list_archives(repo_path)
        if len(archives) != 1:
            raise SmokeFailure(
                f"Expected one archive in remote-source SSH repo, got {archives}"
            )
        archive_name = archives[0]["name"]

        downloaded = client.download_archive_file(
            repo_path,
            archive_name,
            f"{remote_source_path.as_posix().lstrip('/')}/remote-source.txt",
        )
        if downloaded != b"remote source backup smoke\n":
            raise SmokeFailure(
                f"Unexpected remote-source archive download payload: {downloaded!r}"
            )

        client.log("Remote source to SSH repository smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
