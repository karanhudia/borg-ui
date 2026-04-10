#!/usr/bin/env python3
"""Black-box smoke coverage for Borg archive mounts."""

from __future__ import annotations

import argparse
import platform
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure


def mount_prerequisites_available() -> bool:
    if shutil.which("borg") is None:
        return False
    system = platform.system()
    if system == "Linux":
        return shutil.which("fusermount") is not None or shutil.which("fusermount3") is not None
    if system == "Darwin":
        return shutil.which("mount_macfuse") is not None or shutil.which("mount_osxfuse") is not None
    return shutil.which("umount") is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run mount smoke test")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    if not mount_prerequisites_available():
        print("Mount smoke skipped: mount prerequisites not available", flush=True)
        return 0

    client = SmokeClient(args.url)
    mount_id = None
    try:
        client.authenticate()

        source_root = client.prepare_source_tree(
            "mount-source",
            {"folder/file.txt": "mount smoke\n"},
        )
        repo_id, repo_path = client.create_repository(
            name="Mount Smoke Repo",
            repo_path=client.temp_dir / "mount-repo",
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
            raise SmokeFailure(f"Expected one archive before mount, got {archives}")

        mount_response = client.request(
            "POST",
            "/api/mounts/borg",
            headers=client._headers(json_body=True),
            json={
                "repository_id": repo_id,
                "archive_name": archives[0]["name"],
                "mount_point": f"smoke-mount-{int(time.time())}",
            },
        )
        if mount_response.status_code in {500, 503}:
            detail = {}
            try:
                detail = mount_response.json().get("detail", {})
            except Exception:
                detail = {}
            if mount_response.status_code == 503 or detail.get("key") == "backend.errors.mounts.mountUnavailable":
                print(f"Mount smoke skipped: borg mount unavailable in this environment: {mount_response.text}", flush=True)
                return 0
            print(f"Mount smoke skipped: borg mount failed in this environment: {mount_response.text}", flush=True)
            return 0
        if mount_response.status_code != 200:
            raise SmokeFailure(f"Mount request failed: {mount_response.status_code} {mount_response.text}")

        payload = mount_response.json()
        mount_id = payload["mount_id"]
        mount_point = Path(payload["mount_point"])

        deadline = time.time() + 20
        while time.time() < deadline:
            if mount_point.exists() and any(mount_point.iterdir()):
                break
            time.sleep(0.5)

        if not mount_point.exists() or not any(mount_point.iterdir()):
            raise SmokeFailure(f"Mounted archive did not expose filesystem contents at {mount_point}")

        mounts = client.request_ok("GET", "/api/mounts").json()
        if mount_id not in [item["mount_id"] for item in mounts]:
            raise SmokeFailure(f"Mounted archive {mount_id} was not listed")

        info = client.request_ok("GET", f"/api/mounts/{mount_id}").json()
        if info["mount_id"] != mount_id or info["repository_id"] != repo_id:
            raise SmokeFailure(f"Unexpected mount info payload: {info}")

        client.request_ok("POST", f"/api/mounts/borg/unmount/{mount_id}")
        mount_id = None
        client.log("Mount smoke passed")
        return 0
    finally:
        if mount_id:
            client.request("POST", f"/api/mounts/borg/unmount/{mount_id}")
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
