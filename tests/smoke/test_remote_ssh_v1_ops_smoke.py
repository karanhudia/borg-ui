#!/usr/bin/env python3
"""Black-box smoke coverage for Borg 1 SSH repository maintenance and restore flows."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure
from tests.smoke.ssh_smoke_helpers import add_ssh_smoke_args, ensure_public_key_authorized, require_ssh_smoke_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Borg 1 SSH repository operations smoke test")
    add_ssh_smoke_args(parser)
    args = parser.parse_args()

    auth_keys_path = require_ssh_smoke_config(args)
    if auth_keys_path is None:
        return 0

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        ssh_key = client.generate_ssh_key(name="SSH V1 Ops Smoke Key")
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
            "ssh-v1-ops-source",
            {
                "docs/root.txt": "ssh v1 root\n",
                "docs/nested/leaf.txt": "ssh v1 leaf\n",
            },
        )
        remote_repo_path = f"{args.remote_root}/v1-ops-repo-{run_id}"
        repo_id, repo_path = client.create_repository(
            name=f"SSH V1 Ops Repo {run_id}",
            repo_path=remote_repo_path,
            source_dirs=[source_root],
            extra={
                "connection_id": connection["id"],
                "repository_type": "ssh",
            },
        )

        for index in range(3):
            (source_root / "docs" / f"version-{index}.txt").write_text(f"ssh v1 version {index}\n", encoding="utf-8")
            backup_job_id = client.start_backup(repo_path)
            client.wait_for_job("/api/backup/status", backup_job_id, expected={"completed", "completed_with_warnings"}, timeout=120)
            time.sleep(1)

        archives = client.list_archives(repo_path)
        if len(archives) < 3:
            raise SmokeFailure(f"Expected at least 3 archives in SSH repo, got {archives}")
        archive_name = archives[-1]["name"]

        archive_info = client.get_archive_info(archive_name, repo_path, include_files=True)
        if archive_info.get("name") != archive_name:
            raise SmokeFailure(f"Unexpected SSH archive info payload: {archive_info}")

        repo_root = client.container_path(source_root).lstrip("/")
        preview_dest = client.temp_dir / "ssh-v1-preview"
        preview_dest.mkdir(parents=True, exist_ok=True)
        preview = client.preview_restore(
            repository=repo_path,
            repository_id=repo_id,
            archive_name=archive_name,
            destination=preview_dest,
            paths=[f"{repo_root}/docs"],
        )
        if not isinstance(preview, str):
            raise SmokeFailure(f"Unexpected SSH restore preview payload: {preview!r}")
        if any(preview_dest.iterdir()):
            raise SmokeFailure("SSH restore preview should not write files to destination")

        restore_root = client.temp_dir / "ssh-v1-restore"
        restore_root.mkdir(parents=True, exist_ok=True)
        restore_job_id = client.start_restore(
            repository=repo_path,
            archive_name=archive_name,
            repository_id=repo_id,
            destination=restore_root,
            paths=[f"{repo_root}/docs"],
        )
        client.wait_for_job("/api/restore/status", restore_job_id, expected={"completed"}, timeout=120)
        restored_files = sorted(path.relative_to(restore_root).as_posix() for path in restore_root.rglob("*") if path.is_file())
        if not any(path.endswith("docs/nested/leaf.txt") for path in restored_files):
            raise SmokeFailure(f"SSH restore did not produce expected files: {restored_files}")

        check_response = client.request_ok(
            "POST",
            f"/api/repositories/{repo_id}/check",
            headers=client._headers(json_body=True),
            json={"max_duration": 120},
        )
        check_job_id = check_response.json().get("job_id")
        if not isinstance(check_job_id, int):
            raise SmokeFailure(f"Unexpected SSH check response: {check_response.json()}")
        client.wait_for_job("/api/repositories/check-jobs", check_job_id, expected={"completed", "completed_with_warnings"}, timeout=120)

        compact_response = client.request_ok("POST", f"/api/repositories/{repo_id}/compact")
        compact_job_id = compact_response.json().get("job_id")
        if not isinstance(compact_job_id, int):
            raise SmokeFailure(f"Unexpected SSH compact response: {compact_response.json()}")
        client.wait_for_job("/api/repositories/compact-jobs", compact_job_id, expected={"completed", "completed_with_warnings"}, timeout=120)

        prune_response = client.request_ok(
            "POST",
            f"/api/repositories/{repo_id}/prune",
            headers=client._headers(json_body=True),
            json={
                "keep_hourly": 0,
                "keep_daily": 1,
                "keep_weekly": 0,
                "keep_monthly": 0,
                "keep_quarterly": 0,
                "keep_yearly": 0,
                "dry_run": False,
            },
        )
        prune_payload = prune_response.json()
        if prune_payload.get("status") != "completed":
            raise SmokeFailure(f"Unexpected SSH prune response: {prune_payload}")

        archives_after_prune = client.list_archives(repo_path)
        if len(archives_after_prune) != 1:
            raise SmokeFailure(f"Expected SSH prune to leave exactly one archive, got {archives_after_prune}")

        final_archive = archives_after_prune[0]["name"]
        delete_response = client.request_ok(
            "DELETE",
            f"/api/archives/{final_archive}",
            params={"repository": repo_path},
        )
        delete_job_id = delete_response.json().get("job_id")
        if not isinstance(delete_job_id, int):
            raise SmokeFailure(f"Unexpected SSH delete response: {delete_response.json()}")
        client.wait_for_job("/api/archives/delete-jobs", delete_job_id, expected={"completed"}, timeout=120)

        remaining_archives = client.list_archives(repo_path)
        if remaining_archives:
            raise SmokeFailure(f"Expected SSH delete to remove final archive, got {remaining_archives}")

        client.log("Remote SSH Borg 1 operations smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
