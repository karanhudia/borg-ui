#!/usr/bin/env python3
"""Shared helpers for live-server smoke tests."""

from __future__ import annotations

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

from tests.integration.test_helpers import DockerPathHelper, parse_archives_payload
from tests.utils.jobs import wait_for_payload_status


class SmokeFailure(RuntimeError):
    """Raised when a live smoke assertion fails."""


class SmokeClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.token: Optional[str] = None
        self.path_helper = DockerPathHelper(base_url, container_mode=False)
        self.temp_dir = self._make_temp_dir()

    def _make_temp_dir(self) -> Path:
        base_dir = os.environ.get("BORG_UI_SMOKE_TMPDIR")
        if base_dir:
            root = Path(base_dir)
        else:
            root = REPO_ROOT / ".tmp" / "smoke"
        root.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="borg-ui-smoke-", dir=root))

    def cleanup(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def log(self, message: str) -> None:
        print(message, flush=True)

    def _headers(self, *, token: Optional[str] = None, json_body: bool = False) -> dict:
        headers = {}
        auth_token = token or self.token
        if auth_token:
            headers["X-Borg-Authorization"] = f"Bearer {auth_token}"
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def request(
        self, method: str, path: str, *, token: Optional[str] = None, **kwargs
    ) -> requests.Response:
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

    def request_ok(
        self,
        method: str,
        path: str,
        *,
        expected: Iterable[int] = (200,),
        token: Optional[str] = None,
        **kwargs,
    ):
        response = self.request(method, path, token=token, **kwargs)
        if response.status_code not in set(expected):
            raise SmokeFailure(
                f"{method} {path} returned {response.status_code}: {response.text}"
            )
        return response

    def authenticate(self, username: str = "admin", password: str = "admin123") -> str:
        response = self.session.post(
            f"{self.base_url}/api/auth/login",
            data={"username": username, "password": password},
            timeout=20,
        )
        if response.status_code != 200:
            raise SmokeFailure(
                f"Authentication failed for {username}: {response.status_code} {response.text}"
            )
        token = response.json()["access_token"]
        if username == "admin":
            self.token = token
        self.log(f"Authenticated as {username}")
        return token

    def system_info(self) -> dict:
        return self.request_ok("GET", "/api/system/info").json()

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
        repo_path: Path | str,
        source_dirs: list[Path | str],
        encryption: str = "none",
        passphrase: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> tuple[int, str]:
        payload = {
            "name": name,
            "path": self.container_path(repo_path)
            if isinstance(repo_path, Path)
            else str(repo_path),
            "encryption": encryption,
            "compression": "lz4",
            "repository_type": "local",
            "source_directories": [
                self.container_path(path) if isinstance(path, Path) else str(path)
                for path in source_dirs
            ],
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

    def create_repository_v2(
        self,
        *,
        name: str,
        repo_path: Path | str,
        source_dirs: list[Path | str],
        encryption: str = "none",
        passphrase: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> tuple[int, str]:
        payload = {
            "name": name,
            "path": self.container_path(repo_path)
            if isinstance(repo_path, Path)
            else str(repo_path),
            "borg_version": 2,
            "encryption": encryption,
            "compression": "lz4",
            "source_directories": [
                self.container_path(path) if isinstance(path, Path) else str(path)
                for path in source_dirs
            ],
            "exclude_patterns": [],
        }
        if passphrase:
            payload["passphrase"] = passphrase
        if extra:
            payload.update(extra)
        response = self.request_ok(
            "POST",
            "/api/v2/repositories/",
            headers=self._headers(json_body=True),
            json=payload,
            expected=(200, 201),
        )
        data = response.json()
        repo_id = data["id"]
        self.log(f"Created Borg 2 repository {repo_id} ({name})")
        return repo_id, payload["path"]

    def import_repository(
        self,
        *,
        name: str,
        repo_path: Path | str,
        encryption: str,
        source_dirs: list[Path | str],
        passphrase: Optional[str] = None,
        keyfile_content: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> tuple[int, str]:
        payload = {
            "name": name,
            "path": self.container_path(repo_path)
            if isinstance(repo_path, Path)
            else str(repo_path),
            "encryption": encryption,
            "source_directories": [
                self.container_path(path) if isinstance(path, Path) else str(path)
                for path in source_dirs
            ],
        }
        if passphrase:
            payload["passphrase"] = passphrase
        if keyfile_content:
            payload["keyfile_content"] = keyfile_content
        if extra:
            payload.update(extra)
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

    def import_repository_v2(
        self,
        *,
        name: str,
        repo_path: Path | str,
        encryption: str,
        source_dirs: list[Path | str],
        passphrase: Optional[str] = None,
        keyfile_content: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> tuple[int, str]:
        payload = {
            "name": name,
            "path": self.container_path(repo_path)
            if isinstance(repo_path, Path)
            else str(repo_path),
            "borg_version": 2,
            "encryption": encryption,
            "source_directories": [
                self.container_path(path) if isinstance(path, Path) else str(path)
                for path in source_dirs
            ],
        }
        if passphrase:
            payload["passphrase"] = passphrase
        if keyfile_content:
            payload["keyfile_content"] = keyfile_content
        if extra:
            payload.update(extra)
        response = self.request_ok(
            "POST",
            "/api/v2/repositories/import",
            headers=self._headers(json_body=True),
            json=payload,
            expected=(200, 201),
        )
        data = response.json()
        repo_id = data["id"]
        self.log(f"Imported Borg 2 repository {repo_id} ({name})")
        return repo_id, payload["path"]

    def create_user(
        self,
        *,
        username: str,
        password: str,
        role: str = "viewer",
        full_name: Optional[str] = None,
    ) -> int:
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

    def assign_repository_permission(
        self, user_id: int, repo_id: int, role: str
    ) -> None:
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

    def start_backup_v2(
        self, repository_id: int, *, token: Optional[str] = None
    ) -> dict:
        response = self.request_ok(
            "POST",
            "/api/v2/backup/run",
            token=token,
            headers=self._headers(token=token, json_body=True),
            json={"repository_id": repository_id},
            expected=(200, 201, 202),
        )
        payload = response.json()
        if "job_id" in payload:
            self.log(f"Started Borg 2 backup job {payload['job_id']}")
        else:
            self.log("Borg 2 backup completed synchronously")
        return payload

    def create_repository_and_backup(
        self,
        *,
        name: str,
        repo_path: Path,
        source_dirs: list[Path],
        token: Optional[str] = None,
        timeout: float = 90.0,
        encryption: str = "none",
        passphrase: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> tuple[int, str, int, dict]:
        repo_id, repository_path = self.create_repository(
            name=name,
            repo_path=repo_path,
            source_dirs=source_dirs,
            encryption=encryption,
            passphrase=passphrase,
            extra=extra,
        )
        job_id = self.start_backup(repository_path, token=token)
        job_data = self.wait_for_job(
            "/api/backup/status",
            job_id,
            expected={"completed", "completed_with_warnings"},
            token=token,
            timeout=timeout,
        )
        return repo_id, repository_path, job_id, job_data

    def create_repository_and_backup_v2(
        self,
        *,
        name: str,
        repo_path: Path,
        source_dirs: list[Path],
        token: Optional[str] = None,
        timeout: float = 90.0,
        encryption: str = "none",
        passphrase: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> tuple[int, str, int, dict]:
        repo_id, repository_path = self.create_repository_v2(
            name=name,
            repo_path=repo_path,
            source_dirs=source_dirs,
            encryption=encryption,
            passphrase=passphrase,
            extra=extra,
        )
        backup_response = self.start_backup_v2(repo_id, token=token)
        job_id = backup_response.get("job_id", 0)
        if job_id:
            job_data = self.wait_for_job(
                "/api/backup/status",
                job_id,
                expected={"completed", "completed_with_warnings"},
                token=token,
                timeout=timeout,
            )
        else:
            job_data = {"status": "completed", **backup_response}
        return repo_id, repository_path, job_id, job_data

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
        def fetch_payload():
            response = self.request_ok("GET", f"{endpoint}/{job_id}", token=token)
            return response.json()

        try:
            return wait_for_payload_status(
                fetch_payload,
                expected=expected,
                timeout=timeout,
                poll_interval=0.5,
                terminal=terminal,
                description=f"{endpoint}/{job_id}",
            )
        except TimeoutError as exc:
            raise SmokeFailure(str(exc)) from exc

    def wait_for_running(
        self,
        endpoint: str,
        job_id: int,
        *,
        token: Optional[str] = None,
        timeout: float = 30.0,
    ) -> dict:
        def fetch_payload():
            response = self.request_ok("GET", f"{endpoint}/{job_id}", token=token)
            return response.json()

        try:
            return wait_for_payload_status(
                fetch_payload,
                expected={"running"},
                timeout=timeout,
                poll_interval=0.25,
                terminal=None,
                description=f"{endpoint}/{job_id} running state",
            )
        except TimeoutError as exc:
            raise SmokeFailure(str(exc)) from exc

    def list_archives(
        self, repository: int | str, *, token: Optional[str] = None
    ) -> list[dict]:
        response = self.request_ok(
            "GET",
            "/api/archives/list",
            token=token,
            params={"repository": str(repository)},
        )
        return parse_archives_payload(response.json())

    def list_archives_v2(
        self, repository: int | str, *, token: Optional[str] = None
    ) -> list[dict]:
        response = self.request_ok(
            "GET",
            "/api/v2/archives/list",
            token=token,
            params={"repository": str(repository)},
        )
        return parse_archives_payload(response.json())

    def generate_ssh_key(self, *, name: str = "SSH Smoke Key") -> dict:
        response = self.request_ok(
            "POST",
            "/api/ssh-keys/generate",
            headers=self._headers(json_body=True),
            json={"name": name, "key_type": "ed25519"},
            expected=(200,),
        )
        return response.json()["ssh_key"]

    def create_ssh_connection(
        self,
        *,
        key_id: int,
        host: str,
        username: str,
        port: int,
        default_path: Optional[str] = None,
        ssh_path_prefix: Optional[str] = None,
        mount_point: Optional[str] = None,
        use_sftp_mode: bool = True,
    ) -> dict:
        payload = {
            "host": host,
            "username": username,
            "port": port,
            "password": "",
            "use_sftp_mode": use_sftp_mode,
        }
        if default_path is not None:
            payload["default_path"] = default_path
        if ssh_path_prefix is not None:
            payload["ssh_path_prefix"] = ssh_path_prefix
        if mount_point is not None:
            payload["mount_point"] = mount_point
        response = self.request_ok(
            "POST",
            f"/api/ssh-keys/{key_id}/test-connection",
            headers=self._headers(json_body=True),
            json=payload,
            expected=(200,),
        )
        return response.json()["connection"]

    def verify_ssh_connection_borg(self, connection_id: int) -> dict:
        response = self.request_ok(
            "POST", f"/api/ssh-keys/connections/{connection_id}/verify-borg"
        )
        return response.json()

    def browse_archive_contents_v2(
        self,
        repository: int | str,
        archive_id: str,
        *,
        path: Optional[str] = None,
        token: Optional[str] = None,
    ) -> list[dict]:
        params = {"repository": str(repository)}
        if path:
            params["path"] = path
        response = self.request_ok(
            "GET",
            f"/api/v2/archives/{archive_id}/contents",
            token=token,
            params=params,
        )
        return response.json()["items"]

    def get_archive_info(
        self,
        archive_name: str,
        repository: int | str,
        *,
        token: Optional[str] = None,
        include_files: bool = False,
    ) -> dict:
        params = {"repository": str(repository)}
        if include_files:
            params["include_files"] = "true"
        response = self.request_ok(
            "GET", f"/api/archives/{archive_name}/info", token=token, params=params
        )
        return response.json()["info"]

    def get_archive_info_v2(
        self,
        archive_id: str,
        repository: int | str,
        *,
        token: Optional[str] = None,
        include_files: bool = False,
    ) -> dict:
        params = {"repository": str(repository)}
        if include_files:
            params["include_files"] = "true"
        response = self.request_ok(
            "GET", f"/api/v2/archives/{archive_id}/info", token=token, params=params
        )
        return response.json()["info"]

    def restore_contents(
        self,
        repo_id: int,
        archive_name: str,
        *,
        path: Optional[str] = None,
        token: Optional[str] = None,
    ) -> list[dict]:
        params = {"path": path} if path else None
        response = self.request_ok(
            "GET",
            f"/api/browse/{repo_id}/{archive_name}",
            token=token,
            params=params,
        )
        return response.json()["items"]

    def preview_restore(
        self,
        *,
        repository: int | str,
        repository_id: int,
        archive_name: str,
        destination: Path | str,
        paths: list[str],
        destination_type: str = "local",
        destination_connection_id: Optional[int] = None,
        token: Optional[str] = None,
    ) -> str:
        payload = {
            "repository": str(repository),
            "archive": archive_name,
            "paths": paths,
            "destination": self.container_path(destination)
            if isinstance(destination, Path)
            else str(destination),
            "repository_id": repository_id,
            "destination_type": destination_type,
        }
        if destination_connection_id is not None:
            payload["destination_connection_id"] = destination_connection_id
        response = self.request_ok(
            "POST",
            "/api/restore/preview",
            token=token,
            headers=self._headers(token=token, json_body=True),
            json=payload,
        )
        return response.json()["preview"]

    def download_archive_file(
        self,
        repository: int | str,
        archive_name: str,
        file_path: str,
        *,
        token: Optional[str] = None,
    ) -> bytes:
        response = self.request_ok(
            "GET",
            "/api/archives/download",
            token=token,
            params={
                "repository": str(repository),
                "archive": archive_name,
                "file_path": file_path,
            },
        )
        return response.content

    def download_archive_file_v2(
        self,
        repository: int | str,
        archive_name: str,
        file_path: str,
        *,
        token: Optional[str] = None,
    ) -> bytes:
        response = self.request_ok(
            "GET",
            "/api/v2/archives/download",
            token=token,
            params={
                "repository": str(repository),
                "archive": archive_name,
                "file_path": file_path,
            },
        )
        return response.content

    def start_restore(
        self,
        *,
        repository: int | str,
        archive_name: str,
        repository_id: int,
        destination: Path | str,
        paths: list[str],
        destination_type: str = "local",
        destination_connection_id: Optional[int] = None,
        token: Optional[str] = None,
    ) -> int:
        payload = {
            "repository": str(repository),
            "archive": archive_name,
            "paths": paths,
            "destination": self.container_path(destination)
            if isinstance(destination, Path)
            else str(destination),
            "repository_id": repository_id,
            "destination_type": destination_type,
        }
        if destination_connection_id is not None:
            payload["destination_connection_id"] = destination_connection_id
        response = self.request_ok(
            "POST",
            "/api/restore/start",
            token=token,
            headers=self._headers(token=token, json_body=True),
            json=payload,
        )
        return response.json()["job_id"]

    def create_schedule(
        self,
        *,
        name: str,
        cron_expression: str,
        repository_ids: list[int],
        token: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> int:
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

    def run_schedule_now(
        self, schedule_id: int, *, token: Optional[str] = None
    ) -> None:
        self.request_ok("POST", f"/api/schedule/{schedule_id}/run-now", token=token)

    def download_keyfile(self, repo_id: int) -> bytes:
        response = self.request_ok("GET", f"/api/repositories/{repo_id}/keyfile")
        return response.content

    def upload_keyfile(self, repo_id: int, keyfile_path: Path) -> None:
        with keyfile_path.open("rb") as handle:
            response = self.request_ok(
                "POST",
                f"/api/repositories/{repo_id}/keyfile",
                files={
                    "keyfile": (keyfile_path.name, handle, "application/octet-stream")
                },
            )
        if response.status_code != 200:
            raise SmokeFailure(
                f"Failed to upload keyfile for repo {repo_id}: {response.text}"
            )

    def create_borg_key_export(
        self, repo_path: Path, passphrase: str, output_path: Path
    ) -> None:
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

    def run_borg(
        self, args: list[str], *, env: Optional[dict[str, str]] = None
    ) -> subprocess.CompletedProcess:
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

    def wait_for_job_record_count(
        self, path: str, count: int, *, timeout: float = 60.0
    ) -> dict:
        deadline = time.time() + timeout
        last_payload = None
        while time.time() < deadline:
            response = self.request_ok("GET", path)
            last_payload = response.json()
            jobs = last_payload.get("jobs", [])
            if len(jobs) >= count:
                return last_payload
            time.sleep(0.5)
        raise SmokeFailure(
            f"Timed out waiting for {count} jobs at {path}: {last_payload}"
        )

    def wait_for_backup_job(
        self,
        repository_path: str,
        *,
        statuses: set[str],
        token: Optional[str] = None,
        timeout: float = 60.0,
    ) -> dict:
        deadline = time.time() + timeout
        last_payload = None
        while time.time() < deadline:
            response = self.request_ok(
                "GET",
                "/api/backup/jobs",
                token=token,
                params={"manual_only": "true"},
            )
            last_payload = response.json()
            matches = [
                job
                for job in last_payload.get("jobs", [])
                if job.get("repository") == repository_path
                and job.get("status") in statuses
            ]
            if matches:
                return max(matches, key=lambda job: int(job.get("id", 0)))
            time.sleep(0.5)
        raise SmokeFailure(
            f"Timed out waiting for backup job for repository {repository_path}: {last_payload}"
        )
