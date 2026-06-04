#!/usr/bin/env python3
"""Black-box smoke coverage for SSH-backed repositories using a localhost SSH server."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure


def ensure_public_key_authorized(auth_keys_path: Path, public_key: str) -> None:
    """Append the generated key to authorized_keys, using sudo when needed."""
    auth_keys_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = (
            auth_keys_path.read_text(encoding="utf-8")
            if auth_keys_path.exists()
            else ""
        )
        if public_key not in existing:
            with auth_keys_path.open("a", encoding="utf-8") as handle:
                if existing and not existing.endswith("\n"):
                    handle.write("\n")
                handle.write(public_key)
                handle.write("\n")
        return
    except PermissionError:
        pass

    helper = """
from pathlib import Path
import sys

path = Path(sys.argv[1])
public_key = sys.argv[2]
path.parent.mkdir(parents=True, exist_ok=True)
existing = path.read_text(encoding="utf-8") if path.exists() else ""
if public_key not in existing:
    with path.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\\n"):
            handle.write("\\n")
        handle.write(public_key)
        handle.write("\\n")
"""
    try:
        subprocess.run(
            ["sudo", sys.executable, "-c", helper, str(auth_keys_path), public_key],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SmokeFailure(f"Unable to update authorized_keys via sudo: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Run remote SSH smoke test")
    parser.add_argument("--url", default="http://localhost:8082")
    parser.add_argument("--host", default=os.environ.get("SSH_SMOKE_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("SSH_SMOKE_PORT", "2222"))
    )
    parser.add_argument(
        "--username", default=os.environ.get("SSH_SMOKE_USER", "borgsmoke")
    )
    parser.add_argument(
        "--authorized-keys",
        default=os.environ.get("SSH_SMOKE_AUTH_KEYS"),
        help="Path to the target user's authorized_keys file",
    )
    parser.add_argument(
        "--remote-repo-path",
        default=os.environ.get("SSH_SMOKE_REMOTE_REPO", "/home/borgsmoke/remote-repo"),
    )
    args = parser.parse_args()

    if not args.authorized_keys:
        print("Remote SSH smoke skipped: authorized_keys path not provided", flush=True)
        return 0

    auth_keys_path = Path(args.authorized_keys)

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        key_response = client.request_ok(
            "POST",
            "/api/ssh-keys/generate",
            headers=client._headers(json_body=True),
            json={"name": "SSH Smoke Key", "key_type": "ed25519"},
            expected=(200,),
        )
        key_payload = key_response.json()["ssh_key"]
        key_id = key_payload["id"]
        public_key = key_payload["public_key"].strip()
        if not public_key.startswith("ssh-"):
            raise SmokeFailure(f"Unexpected SSH public key payload: {key_payload}")

        ensure_public_key_authorized(auth_keys_path, public_key)

        test_response = client.request_ok(
            "POST",
            f"/api/ssh-keys/{key_id}/test-connection",
            headers=client._headers(json_body=True),
            json={"host": args.host, "username": args.username, "port": args.port},
            expected=(200,),
        )
        connection = test_response.json()["connection"]
        connection_id = connection["id"]
        if connection["status"] != "connected":
            raise SmokeFailure(
                f"SSH connection test did not connect: {test_response.json()}"
            )

        verify_response = client.request_ok(
            "POST", f"/api/ssh-keys/connections/{connection_id}/verify-borg"
        )
        verify_payload = verify_response.json()
        if not verify_payload.get("installed"):
            raise SmokeFailure(f"Remote Borg verification failed: {verify_payload}")

        source_root = client.prepare_source_tree(
            "ssh-remote-source",
            {"ssh-remote.txt": "ssh remote smoke\n"},
        )

        create_response = client.request_ok(
            "POST",
            "/api/repositories/",
            headers=client._headers(json_body=True),
            json={
                "name": "SSH Smoke Repo",
                "path": args.remote_repo_path,
                "connection_id": connection_id,
                "encryption": "none",
                "compression": "lz4",
                "repository_type": "ssh",
                "source_directories": [client.container_path(source_root)],
                "exclude_patterns": [],
            },
            expected=(200, 201),
        )
        repo_payload = create_response.json().get("repository", create_response.json())
        repo_id = repo_payload["id"]
        repo_path = repo_payload["path"]
        if not str(repo_path).startswith("ssh://"):
            raise SmokeFailure(f"Expected remote repository path, got {repo_payload}")

        backup_job_id = client.start_backup(repo_path)
        client.wait_for_job(
            "/api/backup/status",
            backup_job_id,
            expected={"completed", "completed_with_warnings"},
            timeout=120,
        )

        archives = client.list_archives(repo_path)
        if len(archives) != 1:
            raise SmokeFailure(f"Expected one archive in SSH repo, got {archives}")
        archive_name = archives[0]["name"]

        archive_info = client.get_archive_info(
            archive_name, repo_path, include_files=True
        )
        if archive_info["name"] != archive_name:
            raise SmokeFailure(f"Unexpected SSH archive info: {archive_info}")

        restore_items = client.restore_contents(repo_id, archive_name)
        if not restore_items:
            raise SmokeFailure("Expected restore contents from SSH repository")

        downloaded = client.download_archive_file(
            repo_path,
            archive_name,
            f"{source_root.as_posix().lstrip('/')}/ssh-remote.txt",
        )
        if downloaded != b"ssh remote smoke\n":
            raise SmokeFailure(
                f"Unexpected SSH archive download payload: {downloaded!r}"
            )

        client.log("Remote SSH smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
