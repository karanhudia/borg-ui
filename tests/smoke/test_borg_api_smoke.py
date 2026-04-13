#!/usr/bin/env python3
"""Black-box smoke coverage for the core Borg API happy path."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Borg API smoke test")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        source_root = client.prepare_source_tree(
            "core-source",
            {
                "root.txt": "root smoke data\n",
                "nested/notes.txt": "nested smoke data\n",
            },
        )
        restore_root = client.temp_dir / "restore"
        restore_root.mkdir(parents=True, exist_ok=True)

        repo_id, repo_path, _backup_job_id, backup_data = client.create_repository_and_backup(
            name="Smoke Repo",
            repo_path=client.temp_dir / "repo",
            source_dirs=[source_root],
        )
        client.log(f"Backup completed with status {backup_data['status']}")

        archives = client.list_archives(repo_id)
        if len(archives) != 1:
            raise SmokeFailure(f"Expected exactly one archive, got {archives}")
        archive_name = archives[0]["name"]

        archive_info = client.get_archive_info(archive_name, repo_id, include_files=True)
        if archive_info["name"] != archive_name:
            raise SmokeFailure(f"Archive info mismatch: {archive_info}")

        repo_root = client.container_path(source_root).lstrip("/")
        root_items = client.restore_contents(repo_id, archive_name)
        root_names = [item["name"] for item in root_items]
        if repo_root.split("/")[0] not in root_names:
            raise SmokeFailure(f"Unexpected restore root listing: {root_names}")

        preview = client.preview_restore(
            repository=repo_id,
            repository_id=repo_id,
            archive_name=archive_name,
            destination=restore_root,
            paths=[f"{repo_root}/nested"],
        )
        if not isinstance(preview, str):
            raise SmokeFailure(f"Unexpected restore preview payload: {preview!r}")
        if any(restore_root.iterdir()):
            raise SmokeFailure("Restore preview should not write files to destination")

        nested_items = client.restore_contents(repo_id, archive_name, path=repo_root)
        nested_names = [item["name"] for item in nested_items]
        if "nested" not in nested_names or "root.txt" not in nested_names:
            raise SmokeFailure(f"Unexpected nested listing: {nested_names}")

        file_bytes = client.download_archive_file(repo_id, archive_name, f"{repo_root}/nested/notes.txt")
        if file_bytes != b"nested smoke data\n":
            raise SmokeFailure(f"Archive download content mismatch: {file_bytes!r}")

        restore_job_id = client.start_restore(
            repository=repo_id,
            archive_name=archive_name,
            repository_id=repo_id,
            destination=restore_root,
            paths=[f"{repo_root}/nested"],
        )
        client.wait_for_job("/api/restore/status", restore_job_id, expected={"completed"}, timeout=90)
        restored_files = sorted(path.relative_to(restore_root).as_posix() for path in restore_root.rglob("*") if path.is_file())
        if not any(path.endswith("nested/notes.txt") for path in restored_files):
            raise SmokeFailure(f"Selected restore did not yield expected file set: {restored_files}")
        if any(path.endswith("root.txt") for path in restored_files):
            raise SmokeFailure(f"Selected restore unexpectedly included root file: {restored_files}")

        delete_response = client.request_ok(
            "DELETE",
            f"/api/archives/{archive_name}",
            params={"repository": repo_path},
        )
        delete_job_id = delete_response.json()["job_id"]
        client.wait_for_job("/api/archives/delete-jobs", delete_job_id, expected={"completed"}, timeout=90)

        if client.list_archives(repo_path):
            raise SmokeFailure("Expected archive deletion to remove the final archive")

        client.log("Core Borg API smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
