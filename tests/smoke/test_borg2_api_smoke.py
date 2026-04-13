#!/usr/bin/env python3
"""Black-box smoke coverage for the Borg 2 API paths."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure


def _assert_job_start_response(payload: dict, *, expected_message: str) -> int:
    if set(payload.keys()) != {"job_id", "status", "message"}:
        raise SmokeFailure(f"Unexpected Borg 2 job start payload: {payload}")
    if not isinstance(payload["job_id"], int):
        raise SmokeFailure(f"Expected integer job_id in payload: {payload}")
    if payload["status"] != "running":
        raise SmokeFailure(f"Expected running job status in payload: {payload}")
    if payload["message"] != expected_message:
        raise SmokeFailure(f"Unexpected Borg 2 job start message: {payload}")
    return payload["job_id"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Borg 2 API smoke test")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        system_info = client.system_info()
        feature_access = system_info.get("feature_access", {})
        if not feature_access.get("borg_v2"):
            print("Borg 2 smoke skipped: borg_v2 feature not enabled", flush=True)
            return 0

        if not system_info.get("borg2_version"):
            print("Borg 2 smoke skipped: borg2 binary not available in app", flush=True)
            return 0

        if shutil.which("borg2") is None:
            print(
                "Borg 2 smoke skipped: borg2 binary not available on smoke runner",
                flush=True,
            )
            return 0

        source_root = client.prepare_source_tree(
            "borg2-source",
            {
                "root.txt": "borg2 smoke data\n",
                "nested/notes.txt": "borg2 nested smoke data\n",
            },
        )

        repo_id, repo_path, _backup_job_id, backup_data = (
            client.create_repository_and_backup_v2(
                name="Borg2 Smoke Repo",
                repo_path=client.temp_dir / "borg2-repo",
                source_dirs=[source_root],
                encryption="none",
            )
        )
        client.log(f"Borg 2 backup completed with status {backup_data['status']}")

        archives_response = client.request_ok(
            "GET", f"/api/v2/repositories/{repo_id}/archives"
        )
        archives = archives_response.json()["archives"]
        if len(archives) != 1:
            raise SmokeFailure(f"Expected exactly one Borg 2 archive, got {archives}")

        archive_name = archives[0]["name"]
        archive_id = archives[0].get("id") or archive_name
        info_response = client.request_ok("GET", f"/api/v2/repositories/{repo_id}/info")
        info_payload = info_response.json()["info"]
        if "repository" not in info_payload:
            raise SmokeFailure(f"Unexpected Borg 2 info payload: {info_payload}")

        archive_info = client.get_archive_info_v2(
            archive_id, repo_id, include_files=True
        )
        if archive_info.get("name") != archive_name:
            raise SmokeFailure(
                f"Unexpected Borg 2 archive info payload: {archive_info}"
            )

        browse_items = client.browse_archive_contents_v2(repo_id, archive_id)
        if not browse_items:
            raise SmokeFailure("Expected Borg 2 archive browse payload")

        repo_root = client.container_path(source_root).lstrip("/")
        downloaded = client.download_archive_file_v2(
            repo_id, archive_name, f"{repo_root}/nested/notes.txt"
        )
        if downloaded != b"borg2 nested smoke data\n":
            raise SmokeFailure(
                f"Unexpected Borg 2 archive download payload: {downloaded!r}"
            )

        imported_repo_path = client.temp_dir / "borg2-import-repo"
        subprocess.run(
            [
                "borg2",
                "-r",
                str(imported_repo_path),
                "repo-create",
                "--encryption",
                "none",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        imported_repo_id, _ = client.import_repository_v2(
            name="Imported Borg2 Smoke Repo",
            repo_path=imported_repo_path,
            encryption="none",
            source_dirs=[source_root],
        )
        imported_info = client.request_ok(
            "GET", f"/api/v2/repositories/{imported_repo_id}/info"
        ).json()
        if imported_info.get("borg_version") != 2:
            raise SmokeFailure(
                f"Expected imported repository to report borg_version=2: {imported_info}"
            )

        check_response = client.request_ok(
            "POST",
            "/api/v2/backup/check",
            headers=client._headers(json_body=True),
            json={"repository_id": repo_id},
        )
        check_job_id = _assert_job_start_response(
            check_response.json(),
            expected_message="backend.success.repo.checkJobStarted",
        )
        client.wait_for_job(
            "/api/repositories/check-jobs",
            check_job_id,
            expected={"completed", "completed_with_warnings"},
            timeout=120,
        )

        compact_response = client.request_ok(
            "POST",
            "/api/v2/backup/compact",
            headers=client._headers(json_body=True),
            json={"repository_id": repo_id},
        )
        compact_job_id = _assert_job_start_response(
            compact_response.json(),
            expected_message="backend.success.repo.compactJobStarted",
        )
        client.wait_for_job(
            "/api/repositories/compact-jobs",
            compact_job_id,
            expected={"completed", "completed_with_warnings"},
            timeout=120,
        )

        delete_response = client.request_ok(
            "DELETE",
            f"/api/v2/archives/{archive_id}",
            params={"repository": str(repo_id)},
        )
        delete_payload = delete_response.json()
        delete_job_id = delete_payload.get("job_id")
        if not isinstance(delete_job_id, int):
            raise SmokeFailure(f"Unexpected Borg 2 delete response: {delete_payload}")
        client.wait_for_job(
            "/api/archives/delete-jobs",
            delete_job_id,
            expected={"completed"},
            timeout=120,
        )

        remaining_archives = client.list_archives_v2(repo_id)
        if remaining_archives:
            raise SmokeFailure(
                f"Expected Borg 2 delete to remove the final archive, got {remaining_archives}"
            )

        client.log(f"Borg 2 archive available: {archive_name}")
        client.log("Borg 2 API smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
