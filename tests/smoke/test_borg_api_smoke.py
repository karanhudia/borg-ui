#!/usr/bin/env python3
"""
Black-box Borg API smoke test against a running Borg UI instance.

This script exercises the core Borg-backed flow through FastAPI:
- authenticate
- create repository
- run backup and wait for completion
- list archives and inspect archive metadata
- browse archive contents
- download a file
- restore a selected path
- delete the archive and verify it is gone
"""

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.integration.test_helpers import DockerPathHelper


class BorgApiSmoke:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.token = None
        self.path_helper = DockerPathHelper(base_url, container_mode=False)
        self.temp_dir = Path(tempfile.mkdtemp(prefix="borg-ui-smoke-"))
        self.repo_path = self.temp_dir / "repo"
        self.source_path = self.temp_dir / "source"
        self.restore_path = self.temp_dir / "restore"
        self.created_repo_id = None

    def cleanup(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def log(self, message: str) -> None:
        print(message, flush=True)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def authenticate(self) -> None:
        response = self.session.post(
            f"{self.base_url}/api/auth/login",
            data={"username": "admin", "password": "admin123"},
            timeout=10,
        )
        response.raise_for_status()
        self.token = response.json()["access_token"]
        self.log("Authenticated")

    def prepare_files(self) -> None:
        nested = self.source_path / "nested"
        nested.mkdir(parents=True, exist_ok=True)
        self.restore_path.mkdir(parents=True, exist_ok=True)
        (self.source_path / "root.txt").write_text("root smoke data\n", encoding="utf-8")
        (nested / "notes.txt").write_text("nested smoke data\n", encoding="utf-8")
        self.log(f"Prepared source tree under {self.source_path}")

    def create_repository(self) -> tuple[int, str]:
        repo_path = self.path_helper.to_container_path(str(self.repo_path))
        source_path = self.path_helper.to_container_path(str(self.source_path))
        response = self.session.post(
            f"{self.base_url}/api/repositories/",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={
                "name": "Smoke Repo",
                "path": repo_path,
                "encryption": "none",
                "compression": "lz4",
                "repository_type": "local",
                "source_directories": [source_path],
                "exclude_patterns": [],
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        repo_data = payload.get("repository", payload)
        repo_id = repo_data["id"]
        self.created_repo_id = repo_id
        self.log(f"Created repository {repo_id}")
        return repo_id, repo_path

    def start_backup(self, repository_path: str) -> int:
        response = self.session.post(
            f"{self.base_url}/api/backup/start",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"repository": repository_path},
            timeout=30,
        )
        response.raise_for_status()
        job_id = response.json()["job_id"]
        self.log(f"Started backup job {job_id}")
        return job_id

    def wait_for_job(self, endpoint: str, job_id: int, expected: set[str], timeout: float = 60.0) -> dict:
        deadline = time.time() + timeout
        last_payload = None
        while time.time() < deadline:
            response = self.session.get(
                f"{self.base_url}{endpoint}/{job_id}",
                headers=self._headers(),
                timeout=15,
            )
            response.raise_for_status()
            last_payload = response.json()
            status = last_payload.get("status")
            if status in expected:
                return last_payload
            if status in {"failed", "cancelled", "completed", "completed_with_warnings"} and status not in expected:
                raise RuntimeError(f"Job {job_id} reached unexpected status {status}: {last_payload}")
            time.sleep(0.5)
        raise TimeoutError(f"Timed out waiting for {endpoint}/{job_id}: {last_payload}")

    def list_archives(self, repository_path: str) -> list[dict]:
        response = self.session.get(
            f"{self.base_url}/api/archives/list",
            headers=self._headers(),
            params={"repository": repository_path},
            timeout=30,
        )
        response.raise_for_status()
        archives_raw = response.json()["archives"]
        archives_payload = json.loads(archives_raw) if isinstance(archives_raw, str) else archives_raw
        archives = archives_payload.get("archives", [])
        self.log(f"Listed {len(archives)} archive(s)")
        return archives

    def get_archive_info(self, archive_name: str, repository_path: str) -> dict:
        response = self.session.get(
            f"{self.base_url}/api/archives/{archive_name}/info",
            headers=self._headers(),
            params={"repository": repository_path, "include_files": "true"},
            timeout=30,
        )
        response.raise_for_status()
        info = response.json()["info"]
        self.log(f"Fetched archive info for {archive_name}")
        return info

    def browse_archive(self, repo_id: int, archive_name: str, source_root: str) -> None:
        root_response = self.session.get(
            f"{self.base_url}/api/restore/contents/{repo_id}/{archive_name}",
            headers=self._headers(),
            timeout=30,
        )
        root_response.raise_for_status()
        root_names = [item["name"] for item in root_response.json()["items"]]
        if source_root.split("/")[0] not in root_names:
            raise AssertionError(f"Expected root listing to contain {source_root.split('/')[0]}: {root_names}")

        nested_response = self.session.get(
            f"{self.base_url}/api/restore/contents/{repo_id}/{archive_name}",
            headers=self._headers(),
            params={"path": source_root},
            timeout=30,
        )
        nested_response.raise_for_status()
        nested_names = [item["name"] for item in nested_response.json()["items"]]
        if "nested" not in nested_names or "root.txt" not in nested_names:
            raise AssertionError(f"Unexpected nested listing: {nested_names}")
        self.log("Browsed archive contents")

    def download_file(self, archive_name: str, repository_path: str, file_path: str) -> None:
        response = self.session.get(
            f"{self.base_url}/api/archives/download",
            headers=self._headers(),
            params={
                "repository": repository_path,
                "archive": archive_name,
                "file_path": file_path,
            },
            timeout=60,
        )
        response.raise_for_status()
        if response.content != b"nested smoke data\n":
            raise AssertionError("Downloaded file contents did not match expected data")
        self.log("Downloaded archived file")

    def restore_selected_path(self, repo_id: int, archive_name: str, repository_path: str, selected_path: str) -> None:
        response = self.session.post(
            f"{self.base_url}/api/restore/start",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={
                "repository": repository_path,
                "archive": archive_name,
                "paths": [selected_path],
                "destination": str(self.restore_path),
                "repository_id": repo_id,
            },
            timeout=30,
        )
        response.raise_for_status()
        job_id = response.json()["job_id"]
        self.wait_for_job("/api/restore/status", job_id, {"completed"}, timeout=60)

        restored_files = {
            path.relative_to(self.restore_path).as_posix()
            for path in self.restore_path.rglob("*")
            if path.is_file()
        }
        if not any(path.endswith("nested/notes.txt") for path in restored_files):
            raise AssertionError(f"Expected selected restore output, got {sorted(restored_files)}")
        if any(path.endswith("root.txt") for path in restored_files):
            raise AssertionError(f"Restore should not include unselected root file: {sorted(restored_files)}")
        self.log("Restored selected archive path")

    def delete_archive(self, archive_name: str, repository_path: str) -> None:
        response = self.session.delete(
            f"{self.base_url}/api/archives/{archive_name}",
            headers=self._headers(),
            params={"repository": repository_path},
            timeout=30,
        )
        response.raise_for_status()
        delete_job_id = response.json()["job_id"]
        self.wait_for_job("/api/archives/delete-jobs", delete_job_id, {"completed"}, timeout=60)
        self.log(f"Deleted archive {archive_name}")

    def run(self) -> None:
        self.authenticate()
        self.prepare_files()
        repo_id, repository_path = self.create_repository()

        backup_job_id = self.start_backup(repository_path)
        backup_data = self.wait_for_job(
            "/api/backup/status",
            backup_job_id,
            {"completed", "completed_with_warnings"},
            timeout=90,
        )
        self.log(f"Backup completed with status {backup_data['status']}")

        archives = self.list_archives(repository_path)
        if len(archives) != 1:
            raise AssertionError(f"Expected exactly one archive, got {archives}")
        archive_name = archives[0]["name"]

        archive_info = self.get_archive_info(archive_name, repository_path)
        if archive_info["name"] != archive_name:
            raise AssertionError(f"Archive info did not match archive name: {archive_info}")

        source_root = self.source_path.as_posix().lstrip("/")
        file_path = f"{source_root}/nested/notes.txt"
        selected_path = f"{source_root}/nested"

        self.browse_archive(repo_id, archive_name, source_root)
        self.download_file(archive_name, repository_path, file_path)
        self.restore_selected_path(repo_id, archive_name, repository_path, selected_path)
        self.delete_archive(archive_name, repository_path)

        remaining_archives = self.list_archives(repository_path)
        if remaining_archives:
            raise AssertionError(f"Expected archive deletion to be complete, found {remaining_archives}")
        self.log("Core Borg API smoke passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    smoke = BorgApiSmoke(args.url)
    try:
        smoke.run()
        return 0
    finally:
        smoke.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
