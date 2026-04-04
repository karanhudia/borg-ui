#!/usr/bin/env python3
"""Shared helpers for live-server smoke tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.integration.test_helpers import DockerPathHelper


class SmokeFailure(RuntimeError):
    """Raised when a live smoke assertion fails."""


class SmokeClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.token: Optional[str] = None
        self.path_helper = DockerPathHelper(base_url, container_mode=False)
        self.temp_dir = Path(tempfile.mkdtemp(prefix="borg-ui-smoke-"))

    def cleanup(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def log(self, message: str) -> None:
        print(message, flush=True)

    def _headers(self, *, token: Optional[str] = None, json_body: bool = False) -> dict:
        headers = {}
        auth_token = token or self.token
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def request(self, method: str, path: str, *, token: Optional[str] = None, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", {})
        auth_headers = self._headers(token=token)
        auth_headers.update(headers)
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            headers=auth_headers,
            timeout=kwargs.pop("timeout", 60),
            **kwargs,
        )
        return response

    def request_ok(self, method: str, path: str, *, expected: Iterable[int] = (200,), token: Optional[str] = None, **kwargs):
        response = self.request(method, path, token=token, **kwargs)
        if response.status_code not in set(expected):
            raise SmokeFailure(f"{method} {path} returned {response.status_code}: {response.text}")
        return response

    def authenticate(self, username: str = "admin", password: str = "admin123") -> str:
        response = self.session.post(
            f"{self.base_url}/api/auth/login",
            data={"username": username, "password": password},
            timeout=20,
        )
        if response.status_code != 200:
            raise SmokeFailure(f"Authentication failed for {username}: {response.status_code} {response.text}")
        token = response.json()["access_token"]
        if username == "admin":
            self.token = token
        self.log(f"Authenticated as {username}")
        return token

    def prepare_source_tree(self, name: str, files: dict[str, str]) -> Path:
        root = self.temp_dir / name
        for relative_path, content in files.items():
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return root

    def write_incompressible_file(self, path: Path, size_mb: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            for _ in range(size_mb):
                handle.write(os.urandom(1024 * 1024))

    def container_path(self, path: Path | str) -> str:
        return self.path_helper.to_container_path(str(path))

    def create_repository(
        self,
        *,
        name: str,
        repo_path: Path,
        source_dirs: list[Path],
        encryption: str = "none",
        passphrase: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> tuple[int, str]:
        payload = {
            "name": name,
            "path": self.container_path(repo_path),
            "encryption": encryption,
            "compression": "lz4",
            "repository_type": "local",
            "source_directories": [self.container_path(path) for path in source_dirs],
            "exclude_patterns": [],
        }
        if passphrase:
            payload["passphrase"] = passphrase
        if extra:
            payload.update(extra)
        response = self.request_ok(
            "POST",
            "/api/repositories/",
            headers=self._headers(json_body=True),
            json=payload,
            expected=(200, 201),
        )
        data = response.json().get("repository", response.json())
        repo_id = data["id"]
        repo_path_value = payload["path"]
        self.log(f"Created repository {repo_id} ({name})")
        return repo_id, repo_path_value

    def import_repository(
        self,
        *,
        name: str,
        repo_path: Path,
        encryption: str,
        source_dirs: list[Path],
        passphrase: Optional[str] = None,
        keyfile_content: Optional[str] = None,
    ) -> tuple[int, str]:
        payload = {
            "name": name,
            "path": self.container_path(repo_path),
            "encryption": encryption,
            "source_directories": [self.container_path(path) for path in source_dirs],
        }
        if passphrase:
            payload["passphrase"] = passphrase
        if keyfile_content:
            payload["keyfile_content"] = keyfile_content
        response = self.request_ok(
            "POST",
            "/api/repositories/import",
            headers=self._headers(json_body=True),
            json=payload,
            expected=(200, 201),
        )
        data = response.json().get("repository", response.json())
        repo_id = data["id"]
        self.log(f"Imported repository {repo_id} ({name})")
        return repo_id, payload["path"]

    def create_user(self, *, username: str, password: str, role: str = "viewer", full_name: Optional[str] = None) -> int:
        payload = {"username": username, "password": password, "role": role}
        if full_name:
            payload["full_name"] = full_name
        response = self.request_ok(
            "POST",
            "/api/settings/users",
            headers=self._headers(json_body=True),
            json=payload,
            expected=(200, 201),
        )
        user = response.json()["user"]
        self.log(f"Created user {user['id']} ({username})")
        return user["id"]

    def set_permission_scope(self, user_id: int, role: Optional[str]) -> None:
        self.request_ok(
            "PUT",
            f"/api/settings/users/{user_id}/permissions/scope",
            headers=self._headers(json_body=True),
            json={"all_repositories_role": role},
        )

    def assign_repository_permission(self, user_id: int, repo_id: int, role: str) -> None:
        self.request_ok(
            "POST",
            f"/api/settings/users/{user_id}/permissions",
            headers=self._headers(json_body=True),
            json={"repository_id": repo_id, "role": role},
            expected=(201,),
        )

    def start_backup(self, repository_path: str, *, token: Optional[str] = None) -> int:
        response = self.request_ok(
            "POST",
            "/api/backup/start",
            token=token,
            headers=self._headers(token=token, json_body=True),
            json={"repository": repository_path},
            expected=(200, 201, 202),
        )
        job_id = response.json()["job_id"]
        self.log(f"Started backup job {job_id}")
        return job_id

    def wait_for_job(
        self,
        endpoint: str,
        job_id: int,
        *,
        expected: set[str],
        token: Optional[str] = None,
        timeout: float = 90.0,
        terminal: Optional[set[str]] = None,
    ) -> dict:
        deadline = time.time() + timeout
        last_payload = None
        terminal_statuses = terminal or {"failed", "cancelled", "completed", "completed_with_warnings"}
        while time.time() < deadline:
            response = self.request_ok("GET", f"{endpoint}/{job_id}", token=token)
            last_payload = response.json()
            status = last_payload.get("status")
            if status in expected:
                return last_payload
            if status in terminal_statuses and status not in expected:
                raise SmokeFailure(f"Job {endpoint}/{job_id} reached unexpected status {status}: {last_payload}")
            time.sleep(0.5)
        raise SmokeFailure(f"Timed out waiting for {endpoint}/{job_id}: {last_payload}")

    def wait_for_running(self, endpoint: str, job_id: int, *, token: Optional[str] = None, timeout: float = 30.0) -> dict:
        deadline = time.time() + timeout
        last_payload = None
        while time.time() < deadline:
            response = self.request_ok("GET", f"{endpoint}/{job_id}", token=token)
            last_payload = response.json()
            if last_payload.get("status") == "running":
                return last_payload
            time.sleep(0.25)
        raise SmokeFailure(f"Timed out waiting for running state on {endpoint}/{job_id}: {last_payload}")

    def list_archives(self, repository_path: str, *, token: Optional[str] = None) -> list[dict]:
        response = self.request_ok(
            "GET",
            "/api/archives/list",
            token=token,
            params={"repository": repository_path},
        )
        archives_raw = response.json()["archives"]
        archives_payload = json.loads(archives_raw) if isinstance(archives_raw, str) else archives_raw
        return archives_payload.get("archives", [])

    def get_archive_info(self, archive_name: str, repository_path: str, *, token: Optional[str] = None, include_files: bool = False) -> dict:
        params = {"repository": repository_path}
        if include_files:
            params["include_files"] = "true"
        response = self.request_ok("GET", f"/api/archives/{archive_name}/info", token=token, params=params)
        return response.json()["info"]

    def restore_contents(self, repo_id: int, archive_name: str, *, path: Optional[str] = None, token: Optional[str] = None) -> list[dict]:
        params = {"path": path} if path else None
        response = self.request_ok(
            "GET",
            f"/api/restore/contents/{repo_id}/{archive_name}",
            token=token,
            params=params,
        )
        return response.json()["items"]

    def download_archive_file(self, repository_path: str, archive_name: str, file_path: str, *, token: Optional[str] = None) -> bytes:
        response = self.request_ok(
            "GET",
            "/api/archives/download",
            token=token,
            params={"repository": repository_path, "archive": archive_name, "file_path": file_path},
        )
        return response.content

    def start_restore(
        self,
        *,
        repository_path: str,
        archive_name: str,
        repository_id: int,
        destination: Path,
        paths: list[str],
        token: Optional[str] = None,
    ) -> int:
        response = self.request_ok(
            "POST",
            "/api/restore/start",
            token=token,
            headers=self._headers(token=token, json_body=True),
            json={
                "repository": repository_path,
                "archive": archive_name,
                "paths": paths,
                "destination": str(destination),
                "repository_id": repository_id,
            },
        )
        return response.json()["job_id"]

    def create_schedule(self, *, name: str, cron_expression: str, repository_ids: list[int], token: Optional[str] = None, extra: Optional[dict] = None) -> int:
        payload = {
            "name": name,
            "cron_expression": cron_expression,
            "repository_ids": repository_ids,
            "enabled": True,
        }
        if len(repository_ids) == 1:
            payload["repository_id"] = repository_ids[0]
        if extra:
            payload.update(extra)
        response = self.request_ok(
            "POST",
            "/api/schedule/",
            token=token,
            headers=self._headers(token=token, json_body=True),
            json=payload,
            expected=(200, 201),
        )
        data = response.json()
        schedule = data.get("schedule") or data.get("job") or data
        return schedule["id"]

    def run_schedule_now(self, schedule_id: int, *, token: Optional[str] = None) -> None:
        self.request_ok("POST", f"/api/schedule/{schedule_id}/run-now", token=token)

    def download_keyfile(self, repo_id: int) -> bytes:
        response = self.request_ok("GET", f"/api/repositories/{repo_id}/keyfile")
        return response.content

    def upload_keyfile(self, repo_id: int, keyfile_path: Path) -> None:
        with keyfile_path.open("rb") as handle:
            response = self.request_ok(
                "POST",
                f"/api/repositories/{repo_id}/keyfile",
                files={"keyfile": (keyfile_path.name, handle, "application/octet-stream")},
            )
        if response.status_code != 200:
            raise SmokeFailure(f"Failed to upload keyfile for repo {repo_id}: {response.text}")

    def create_borg_key_export(self, repo_path: Path, passphrase: str, output_path: Path) -> None:
        env = {
            **os.environ.copy(),
            "BORG_PASSPHRASE": passphrase,
            "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK": "yes",
            "BORG_RELOCATED_REPO_ACCESS_IS_OK": "yes",
        }
        subprocess.run(
            ["borg", "key", "export", str(repo_path), str(output_path)],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

    def run_borg(self, args: list[str], *, env: Optional[dict[str, str]] = None) -> subprocess.CompletedProcess:
        merged_env = os.environ.copy()
        merged_env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
        merged_env["BORG_RELOCATED_REPO_ACCESS_IS_OK"] = "yes"
        if env:
            merged_env.update(env)
        return subprocess.run(
            ["borg", *args],
            check=True,
            capture_output=True,
            text=True,
            env=merged_env,
        )

    def wait_for_job_record_count(self, path: str, count: int, *, timeout: float = 60.0) -> dict:
        deadline = time.time() + timeout
        last_payload = None
        while time.time() < deadline:
            response = self.request_ok("GET", path)
            last_payload = response.json()
            jobs = last_payload.get("jobs", [])
            if len(jobs) >= count:
                return last_payload
            time.sleep(0.5)
        raise SmokeFailure(f"Timed out waiting for {count} jobs at {path}: {last_payload}")
