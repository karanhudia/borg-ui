#!/usr/bin/env python3
"""Black-box smoke coverage for permissions and failure-path contracts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure


def main() -> int:
    parser = argparse.ArgumentParser(description="Run permissions and failure smoke tests")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        source_root = client.prepare_source_tree(
            "permissions-source",
            {
                "public.txt": "viewer-visible\n",
                "nested/item.txt": "viewer nested\n",
            },
        )
        repo_id, repo_path = client.create_repository(
            name="Permissions Smoke Repo",
            repo_path=client.temp_dir / "permissions-repo",
            source_dirs=[source_root],
        )
        backup_job_id = client.start_backup(repo_path)
        client.wait_for_job(
            "/api/backup/status",
            backup_job_id,
            expected={"completed", "completed_with_warnings"},
            timeout=90,
        )

        archives = client.list_archives(repo_path)
        if len(archives) != 1:
            raise SmokeFailure(f"Expected one archive before permission checks, got {archives}")
        archive_name = archives[0]["name"]
        repo_root = source_root.as_posix().lstrip("/")

        viewer_username = "smoke-viewer"
        viewer_password = "smoke-viewer-pass"
        viewer_id = client.create_user(username=viewer_username, password=viewer_password, role="viewer")
        client.set_permission_scope(viewer_id, "viewer")
        viewer_token = client.authenticate(viewer_username, viewer_password)

        viewer_archives = client.list_archives(repo_path, token=viewer_token)
        if len(viewer_archives) != 1:
            raise SmokeFailure(f"Viewer should see repository archives, got {viewer_archives}")

        restore_items = client.restore_contents(repo_id, archive_name, token=viewer_token)
        if not restore_items:
            raise SmokeFailure("Viewer should be able to browse restore contents")

        download_bytes = client.download_archive_file(
            repo_path,
            archive_name,
            f"{repo_root}/public.txt",
            token=viewer_token,
        )
        if download_bytes != b"viewer-visible\n":
            raise SmokeFailure(f"Viewer archive download returned wrong content: {download_bytes!r}")

        for method, path, payload in [
            ("POST", "/api/backup/start", {"repository": repo_path}),
            ("DELETE", f"/api/archives/{archive_name}", None),
            ("POST", "/api/repositories/{repo_id}/compact".format(repo_id=repo_id), None),
            ("POST", "/api/repositories/{repo_id}/check".format(repo_id=repo_id), {"max_duration": 60}),
        ]:
            kwargs = {"token": viewer_token}
            if payload is not None:
                kwargs["headers"] = client._headers(token=viewer_token, json_body=True)
                kwargs["json"] = payload
            response = client.request(method, path, **kwargs)
            if response.status_code != 403:
                raise SmokeFailure(f"Viewer mutation {method} {path} should return 403, got {response.status_code}: {response.text}")

        missing_repo_job = client.start_backup(str(client.temp_dir / "missing-repo"))
        failed_job = client.wait_for_job("/api/backup/status", missing_repo_job, expected={"failed"}, timeout=45)
        if failed_job["status"] != "failed":
            raise SmokeFailure(f"Missing repository backup should fail, got {failed_job}")

        missing_archive_response = client.request("GET", f"/api/archives/does-not-exist/info", params={"repository": repo_path})
        if missing_archive_response.status_code != 500:
            raise SmokeFailure(
                f"Missing archive info should return 500 from Borg-backed endpoint, got {missing_archive_response.status_code}"
            )

        client.log("Permissions and failure smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
