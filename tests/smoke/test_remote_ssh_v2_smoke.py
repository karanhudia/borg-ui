#!/usr/bin/env python3
"""Black-box smoke coverage for Borg 2 SSH repository lifecycle and archive operations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure
from tests.smoke.ssh_smoke_helpers import add_ssh_smoke_args, ensure_public_key_authorized, require_ssh_smoke_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Borg 2 SSH smoke test")
    add_ssh_smoke_args(parser)
    args = parser.parse_args()

    auth_keys_path = require_ssh_smoke_config(args)
    if auth_keys_path is None:
        return 0

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        system_info = client.system_info()
        feature_access = system_info.get("feature_access", {})
        if not feature_access.get("borg_v2"):
            print("Remote Borg 2 smoke skipped: borg_v2 feature not enabled", flush=True)
            return 0
        if not system_info.get("borg2_version"):
            print("Remote Borg 2 smoke skipped: borg2 binary not available in app", flush=True)
            return 0

        ssh_key = client.generate_ssh_key(name="SSH V2 Smoke Key")
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

        run_id = client.temp_dir.name
        source_root = client.prepare_source_tree(
            "ssh-v2-source",
            {
                "root.txt": "ssh borg2 root\n",
                "nested/notes.txt": "ssh borg2 nested\n",
            },
        )
        remote_repo_root = Path(args.remote_root)
        remote_repo_path = f"ssh://{args.username}@{args.host}:{args.port}/{(remote_repo_root / f'v2-repo-{run_id}').as_posix().lstrip('/')}"

        repo_id, repo_path = client.create_repository_v2(
            name=f"SSH Borg2 Repo {run_id}",
            repo_path=remote_repo_path,
            source_dirs=[source_root],
            extra={"connection_id": connection["id"]},
        )
        if repo_path != remote_repo_path:
            raise SmokeFailure(f"Unexpected SSH Borg 2 repository path: {repo_path}")

        backup_response = client.start_backup_v2(repo_id)
        backup_job_id = backup_response.get("job_id", 0)
        if backup_job_id:
            client.wait_for_job("/api/backup/status", backup_job_id, expected={"completed", "completed_with_warnings"}, timeout=120)

        archives = client.list_archives_v2(repo_id)
        if len(archives) != 1:
            raise SmokeFailure(f"Expected exactly one SSH Borg 2 archive, got {archives}")
        archive_name = archives[0]["name"]
        archive_id = archives[0].get("id") or archive_name

        repo_info = client.request_ok("GET", f"/api/v2/repositories/{repo_id}/info").json()
        if repo_info.get("borg_version") != 2:
            raise SmokeFailure(f"Unexpected SSH Borg 2 repository info: {repo_info}")

        archive_info = client.get_archive_info_v2(archive_id, repo_id, include_files=True)
        if archive_info.get("name") != archive_name:
            raise SmokeFailure(f"Unexpected SSH Borg 2 archive info payload: {archive_info}")

        browse_items = client.browse_archive_contents_v2(repo_id, archive_id)
        if not browse_items:
            raise SmokeFailure("Expected SSH Borg 2 archive browse payload")

        repo_root = client.container_path(source_root).lstrip("/")
        downloaded = client.download_archive_file_v2(repo_id, archive_name, f"{repo_root}/nested/notes.txt")
        if downloaded != b"ssh borg2 nested\n":
            raise SmokeFailure(f"Unexpected SSH Borg 2 download payload: {downloaded!r}")

        check_response = client.request_ok(
            "POST",
            "/api/v2/backup/check",
            headers=client._headers(json_body=True),
            json={"repository_id": repo_id},
        )
        check_job_id = check_response.json().get("job_id")
        if not isinstance(check_job_id, int):
            raise SmokeFailure(f"Unexpected SSH Borg 2 check response: {check_response.json()}")
        client.wait_for_job("/api/repositories/check-jobs", check_job_id, expected={"completed", "completed_with_warnings"}, timeout=120)

        compact_response = client.request_ok(
            "POST",
            "/api/v2/backup/compact",
            headers=client._headers(json_body=True),
            json={"repository_id": repo_id},
        )
        compact_job_id = compact_response.json().get("job_id")
        if not isinstance(compact_job_id, int):
            raise SmokeFailure(f"Unexpected SSH Borg 2 compact response: {compact_response.json()}")
        client.wait_for_job("/api/repositories/compact-jobs", compact_job_id, expected={"completed", "completed_with_warnings"}, timeout=120)

        delete_response = client.request_ok(
            "DELETE",
            f"/api/v2/archives/{archive_id}",
            params={"repository": str(repo_id)},
        )
        delete_job_id = delete_response.json().get("job_id")
        if not isinstance(delete_job_id, int):
            raise SmokeFailure(f"Unexpected SSH Borg 2 delete response: {delete_response.json()}")
        client.wait_for_job("/api/archives/delete-jobs", delete_job_id, expected={"completed"}, timeout=120)
        if client.list_archives_v2(repo_id):
            raise SmokeFailure("Expected SSH Borg 2 delete to remove the final archive")

        client.request_ok("DELETE", f"/api/repositories/{repo_id}")

        imported_repo_id, _ = client.import_repository_v2(
            name=f"Imported SSH Borg2 Repo {run_id}",
            repo_path=remote_repo_path,
            encryption="none",
            source_dirs=[source_root],
            extra={"connection_id": connection["id"]},
        )
        imported_info = client.request_ok("GET", f"/api/v2/repositories/{imported_repo_id}/info").json()
        if imported_info.get("borg_version") != 2:
            raise SmokeFailure(f"Expected imported SSH Borg 2 repository to report borg_version=2: {imported_info}")

        client.log("Remote SSH Borg 2 smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
