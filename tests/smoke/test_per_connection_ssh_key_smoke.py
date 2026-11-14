#!/usr/bin/env python3
"""Issue #1430: a connection that uses an extra (non-system) SSH key.

The target's authorized_keys holds only the extra key while this runs, so the
backup can only succeed if Borg really authenticates with the connection's key
and not the system key in ~/.ssh.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure
from tests.smoke.ssh_smoke_helpers import (
    add_ssh_smoke_args,
    replace_authorized_keys,
    require_ssh_smoke_config,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run per-connection SSH key smoke")
    add_ssh_smoke_args(parser)
    args = parser.parse_args()

    auth_keys_path = require_ssh_smoke_config(args)
    if auth_keys_path is None:
        return 0

    client = SmokeClient(args.url)
    previous_keys = None
    extra_id = None
    try:
        client.authenticate()
        client.generate_ssh_key(name="Per-Key Smoke System Key")

        run_id = client.temp_dir.name
        extra = client.request_ok(
            "POST",
            "/api/ssh-keys/generate",
            headers=client._headers(json_body=True),
            json={
                "name": f"per-key-smoke-{run_id}",
                "key_type": "ed25519",
                "system_key": False,
            },
            expected=(200,),
        ).json()["ssh_key"]
        extra_id = extra["id"]
        if extra["is_system_key"]:
            raise SmokeFailure(f"Extra key came back as the system key: {extra}")

        previous_keys = replace_authorized_keys(
            auth_keys_path, extra["public_key"].strip() + "\n"
        )

        connection = client.create_ssh_connection(
            key_id=extra_id, host=args.host, username=args.username, port=args.port
        )
        if connection["status"] != "connected":
            raise SmokeFailure(f"Extra-key connection did not connect: {connection}")
        listed = client.request_ok("GET", "/api/ssh-keys/connections").json()
        bound = next(c for c in listed["connections"] if c["id"] == connection["id"])
        if bound["ssh_key_id"] != extra_id:
            raise SmokeFailure(f"Connection not bound to the extra key: {bound}")

        # borg would create a missing remote_root as the SSH user and lock out
        # the smokes that later write there as this user, so share it like /tmp.
        remote_root = Path(args.remote_root)
        remote_root.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(PermissionError):
            remote_root.chmod(0o1777)

        source_root = client.prepare_source_tree(
            "per-key-source", {"per-key.txt": "per-connection key\n"}
        )
        repo_path = client.request_ok(
            "POST",
            "/api/repositories/",
            headers=client._headers(json_body=True),
            json={
                "name": f"Per-Key Smoke Repo {run_id}",
                "path": f"{args.remote_root}/per-key-repo-{run_id}",
                "connection_id": connection["id"],
                "repository_type": "ssh",
                "encryption": "none",
                "compression": "lz4",
                "source_directories": [client.container_path(source_root)],
                "exclude_patterns": [],
            },
            expected=(200, 201),
        ).json()["repository"]["path"]
        job_id = client.start_backup(repo_path)
        client.wait_for_job(
            "/api/backup/status",
            job_id,
            expected={"completed", "completed_with_warnings"},
            timeout=120,
        )
        archives = client.list_archives(repo_path)
        if len(archives) != 1:
            raise SmokeFailure(f"Expected one archive over the extra key: {archives}")

        refused = client.request_ok(
            "DELETE", f"/api/ssh-keys/{extra_id}", expected=(409,)
        ).json()["detail"]
        if refused.get("key") != "backend.errors.ssh.keyInUse":
            raise SmokeFailure(f"Deleting an in-use key was not refused: {refused}")

        client.log("Per-connection SSH key smoke passed")
        return 0
    finally:
        if previous_keys is not None:
            replace_authorized_keys(auth_keys_path, previous_keys)
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
