#!/usr/bin/env python3
"""Black-box smoke for backup plans whose source is a remote machine.

Runs against one sshd reached under two host names, which Borg UI stores as
two SSH connections, so "the repository's machine" and "another machine"
are both real:

1. A source on the repository's own connection backs up directly on that
   machine (`remote_direct`), with no hidden per-connection gate (#834).
2. Two plans on one repository: the second is refused with "active on the
   repository" at once, and the API keeps answering meanwhile. The refusal
   used to hold SQLite's write lock while recording the failure through a
   second session, freezing the whole server for about two minutes.
3. A single file on another machine, entered as an absolute path that only
   exists relative to the login directory, is pulled over SSHFS. The file
   check once missed that fallback, judged the file a directory and failed
   the mount with "Not a directory".
4. Optionally, the same file through an SFTP-only account, whose file check
   runs over sftp: that fallback once asked for an `sftp stat` OpenSSH does
   not have and called everything a file.

The smoke writes its sources straight to disk, so it must run on the SSH
host, with `--source-root` a directory inside `--login-home` it can write.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure
from tests.smoke.ssh_smoke_helpers import (
    add_ssh_smoke_args,
    ensure_public_key_authorized,
    require_ssh_smoke_config,
)

TERMINAL_RUN_STATUSES = {
    "completed",
    "completed_with_warnings",
    "failed",
    "partial",
    "cancelled",
}
# A refused plan repository is recorded within a second or two; the frozen
# server took four busy timeouts (two minutes) to get there.
REFUSAL_DEADLINE_SECONDS = 20
# Any single request slower than this means the event loop was blocked.
RESPONSIVE_REQUEST_SECONDS = 5
# About 48s of upload at the rate limit below: over twice the refusal
# deadline, so the first backup is still running when the check looks.
BLOCKER_SIZE_MB = 6
BLOCKER_RATELIMIT_KIB = 128


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_ssh_smoke_args(parser)
    parser.add_argument(
        "--alt-host",
        default=os.environ.get("SSH_SMOKE_ALT_HOST", "localhost"),
        help="A second name for the SSH host, stored as a separate connection",
    )
    parser.add_argument(
        "--login-home",
        default=os.environ.get("SSH_SMOKE_LOGIN_HOME"),
        help="The SSH user's login directory",
    )
    parser.add_argument(
        "--source-root",
        default=os.environ.get("SSH_SMOKE_SOURCE_ROOT"),
        help="A directory inside the login home this process can write",
    )
    parser.add_argument(
        "--sftp-user",
        default=os.environ.get("SSH_SMOKE_SFTP_USER"),
        help="Optional internal-sftp-only account on the same host",
    )
    parser.add_argument(
        "--sftp-authorized-keys",
        default=os.environ.get("SSH_SMOKE_SFTP_AUTH_KEYS"),
    )
    return parser.parse_args()


class PlanRoutesSmoke:
    def __init__(self, client: SmokeClient, args: argparse.Namespace):
        self.client = client
        self.args = args
        self.run_tag = client.temp_dir.name
        self.login_home = Path(args.login_home)
        self.source_dir = Path(args.source_root) / self.run_tag

    # -- API helpers ---------------------------------------------------------

    def _call(self, method: str, path: str, *, expected=(200,), json=None) -> dict:
        """A request that must answer promptly: a slow one is a blocked server."""
        started = time.monotonic()
        try:
            response = self.client.session.request(
                method,
                f"{self.client.base_url}{path}",
                headers=self.client._headers(json_body=json is not None),
                json=json,
                timeout=RESPONSIVE_REQUEST_SECONDS,
            )
        except requests.Timeout as exc:
            raise SmokeFailure(
                f"{method} {path} got no answer within {RESPONSIVE_REQUEST_SECONDS}s: "
                "the server is blocked"
            ) from exc
        elapsed = time.monotonic() - started
        if response.status_code not in expected:
            raise SmokeFailure(
                f"{method} {path} -> {response.status_code}: {response.text}"
            )
        if elapsed > RESPONSIVE_REQUEST_SECONDS:
            raise SmokeFailure(f"{method} {path} took {elapsed:.1f}s")
        return response.json()

    def _get(self, path: str) -> dict:
        return self._call("GET", path)

    def connection(self, key_id: int, host: str, username: str) -> dict:
        connection = self.client.create_ssh_connection(
            key_id=key_id, host=host, username=username, port=self.args.port
        )
        if connection["status"] != "connected":
            raise SmokeFailure(
                f"SSH connection to {username}@{host} failed: {connection}"
            )
        return connection

    def create_repository(self, connection_id: int) -> dict:
        response = self.client.request_ok(
            "POST",
            "/api/repositories/",
            headers=self.client._headers(json_body=True),
            json={
                "name": f"Plan Routes Repo {self.run_tag}",
                "path": f"{self.login_home}/plan-routes-repo-{self.run_tag}",
                "connection_id": connection_id,
                "encryption": "none",
                "compression": "none",
                "repository_type": "ssh",
                "source_directories": [],
                "exclude_patterns": [],
            },
            expected=(200, 201),
        )
        payload = response.json()
        return payload.get("repository", payload)

    def create_plan(
        self,
        name: str,
        *,
        repository_id: int,
        connection_id: int,
        path: str,
        upload_ratelimit_kib: Optional[int] = None,
    ) -> int:
        response = self.client.request_ok(
            "POST",
            "/api/backup-plans/",
            headers=self.client._headers(json_body=True),
            json={
                "name": f"{name} {self.run_tag}",
                "source_type": "remote",
                "source_ssh_connection_id": connection_id,
                "source_directories": [path],
                "source_locations": [
                    {
                        "source_type": "remote",
                        "source_ssh_connection_id": connection_id,
                        "agent_machine_id": None,
                        "paths": [path],
                    }
                ],
                "archive_name_template": "{plan_name}-{now}",
                "compression": "none",
                "upload_ratelimit_kib": upload_ratelimit_kib,
                "repositories": [
                    {"repository_id": repository_id, "execution_order": 1}
                ],
            },
            expected=(201,),
        )
        return response.json()["id"]

    def start_run(self, plan_id: int) -> int:
        return self._call("POST", f"/api/backup-plans/{plan_id}/run", expected=(202,))[
            "id"
        ]

    def wait_run(self, run_id: int, *, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            run = self._get(f"/api/backup-plans/runs/{run_id}")
            if run["status"] in TERMINAL_RUN_STATUSES:
                return run
            if time.monotonic() > deadline:
                raise SmokeFailure(
                    f"Plan run {run_id} still {run['status']} after {timeout}s: {run}"
                )
            time.sleep(0.5)

    def wait_backup_running(self, run_id: int, *, timeout: float = 60) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            run = self._get(f"/api/backup-plans/runs/{run_id}")
            job = (run.get("repositories") or [{}])[0].get("backup_job") or {}
            if job.get("status") == "running":
                return run
            if run["status"] in TERMINAL_RUN_STATUSES:
                raise SmokeFailure(f"Plan run {run_id} ended before running: {run}")
            if time.monotonic() > deadline:
                raise SmokeFailure(f"Backup of plan run {run_id} never started: {run}")
            time.sleep(0.25)

    @staticmethod
    def only_repository(run: dict) -> dict:
        repositories = run.get("repositories") or []
        if len(repositories) != 1:
            raise SmokeFailure(f"Expected one repository in the run: {run}")
        return repositories[0]

    def expect_completed(self, run: dict, *, route: str) -> str:
        child = self.only_repository(run)
        job = child.get("backup_job") or {}
        if run["status"] != "completed" or child["status"] != "completed":
            raise SmokeFailure(f"Expected a completed run: {run}")
        if job.get("route_strategy") != route:
            raise SmokeFailure(
                f"Expected route {route}, got {job.get('route_strategy')}"
            )
        if not job.get("archive_name"):
            raise SmokeFailure(f"Completed backup names no archive: {job}")
        return job["archive_name"]

    def expect_archived(self, repo_path: str, archive: str, member: str, body: bytes):
        downloaded = self.client.download_archive_file(repo_path, archive, member)
        if downloaded != body:
            raise SmokeFailure(
                f"{member} in {archive}: expected {body!r}, got {downloaded[:80]!r}"
            )

    # -- scenarios -----------------------------------------------------------

    def run(self) -> None:
        client = self.client
        args = self.args
        key = client.generate_ssh_key(name="Plan Routes Smoke Key")
        ensure_public_key_authorized(Path(args.authorized_keys), key["public_key"])

        repo_machine = self.connection(key["id"], args.host, args.username)
        other_machine = self.connection(key["id"], args.alt_host, args.username)
        if repo_machine["id"] == other_machine["id"]:
            raise SmokeFailure("--alt-host must be stored as a separate connection")
        repo = self.create_repository(repo_machine["id"])
        repo_path = repo["path"]

        direct_body = b"direct on the repository host\n"
        file_body = b"one file, reached through the login directory\n"
        (self.source_dir / "direct").mkdir(parents=True)
        (self.source_dir / "direct" / "direct.txt").write_bytes(direct_body)
        (self.source_dir / "file").mkdir()
        (self.source_dir / "file" / "one.txt").write_bytes(file_body)
        client.write_incompressible_file(
            self.source_dir / "big" / "blob.bin", BLOCKER_SIZE_MB
        )

        # The file as entered: absolute-looking, but only real below the home.
        home_relative = (self.source_dir / "file" / "one.txt").relative_to(
            self.login_home
        )
        login_relative_file = f"/{home_relative.as_posix()}"
        if Path(login_relative_file).exists():
            raise SmokeFailure(
                f"{login_relative_file} exists at the root; the login-relative "
                "fallback would not be exercised"
            )

        # 1. Same machine: direct, no backup-source gate (#834).
        direct_plan = self.create_plan(
            "Direct",
            repository_id=repo["id"],
            connection_id=repo_machine["id"],
            path=str(self.source_dir / "direct"),
        )
        run = self.wait_run(self.start_run(direct_plan), timeout=180)
        archive = self.expect_completed(run, route="remote_direct")
        self.expect_archived(
            repo_path,
            archive,
            f"{(self.source_dir / 'direct' / 'direct.txt').as_posix().lstrip('/')}",
            direct_body,
        )
        client.log("Direct backup on the repository host passed")

        # 2. Two plans on one repository.
        blocker_plan = self.create_plan(
            "Blocker",
            repository_id=repo["id"],
            connection_id=other_machine["id"],
            path=str(self.source_dir / "big"),
            upload_ratelimit_kib=BLOCKER_RATELIMIT_KIB,
        )
        file_plan = self.create_plan(
            "Login relative file",
            repository_id=repo["id"],
            connection_id=other_machine["id"],
            path=login_relative_file,
        )
        blocker_run = self.start_run(blocker_plan)
        self.wait_backup_running(blocker_run)
        refused_started = time.monotonic()
        refused = self.wait_run(
            self.start_run(file_plan), timeout=REFUSAL_DEADLINE_SECONDS
        )
        refused_child = self.only_repository(refused)
        if refused["status"] != "failed" or "active" not in (
            refused_child.get("error_message") or ""
        ):
            raise SmokeFailure(f"Expected a refusal for the busy repository: {refused}")
        # The first backup was still running through all of that.
        blocker_now = self._get(f"/api/backup-plans/runs/{blocker_run}")
        if blocker_now["status"] in TERMINAL_RUN_STATUSES:
            raise SmokeFailure(
                "The blocking backup ended before the refusal; raise "
                f"BLOCKER_SIZE_MB or lower BLOCKER_RATELIMIT_KIB: {blocker_now}"
            )
        client.log(
            "Second plan on a busy repository refused in "
            f"{time.monotonic() - refused_started:.1f}s, server responsive"
        )
        self.expect_completed(
            self.wait_run(blocker_run, timeout=300),
            route="server_sshfs_pull_then_borg_ssh",
        )

        # 3. The file, on another machine, through the login-relative path.
        run = self.wait_run(self.start_run(file_plan), timeout=180)
        archive = self.expect_completed(run, route="server_sshfs_pull_then_borg_ssh")
        self.expect_archived(
            repo_path, archive, login_relative_file.lstrip("/"), file_body
        )
        client.log("Login-relative single-file source over SSHFS passed")

        # 4. The file through an SFTP-only account.
        if not (args.sftp_user and args.sftp_authorized_keys):
            client.log("SFTP-only source skipped: no --sftp-user configured")
            return
        ensure_public_key_authorized(Path(args.sftp_authorized_keys), key["public_key"])
        sftp_machine = self.connection(key["id"], args.host, args.sftp_user)
        absolute_file = str(self.source_dir / "file" / "one.txt")
        sftp_plan = self.create_plan(
            "SFTP only file",
            repository_id=repo["id"],
            connection_id=sftp_machine["id"],
            path=absolute_file,
        )
        run = self.wait_run(self.start_run(sftp_plan), timeout=180)
        archive = self.expect_completed(run, route="server_sshfs_pull_then_borg_ssh")
        self.expect_archived(repo_path, archive, absolute_file.lstrip("/"), file_body)
        client.log("Single-file source through an SFTP-only account passed")

    def cleanup(self) -> None:
        shutil.rmtree(self.source_dir, ignore_errors=True)


def main() -> int:
    args = _parse_args()
    if require_ssh_smoke_config(args) is None:
        return 0
    if not (args.login_home and args.source_root):
        print(
            "Remote source plan routes smoke skipped: --login-home and "
            "--source-root are required",
            flush=True,
        )
        return 0

    client = SmokeClient(args.url)
    smoke = PlanRoutesSmoke(client, args)
    try:
        client.authenticate()
        smoke.run()
        client.log("Remote source plan routes smoke passed")
        return 0
    finally:
        smoke.cleanup()
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
