#!/usr/bin/env python3
"""Black-box smoke coverage for encrypted repository and keyfile flows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure


def main() -> int:
    parser = argparse.ArgumentParser(description="Run encrypted repository smoke tests")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    try:
        client.authenticate()
        run_id = client.temp_dir.name

        source_root = client.prepare_source_tree(
            "encrypted-source",
            {
                "docs/secret.txt": "repokey smoke\n",
                "docs/nested/extra.txt": "nested repokey\n",
            },
        )

        repokey_repo_id, repokey_repo_path, _backup_job_id, _backup_data = (
            client.create_repository_and_backup(
                name=f"Repokey Smoke Repo {run_id}",
                repo_path=client.temp_dir / "repokey-repo",
                source_dirs=[source_root],
                encryption="repokey",
                passphrase="repokey-smoke-passphrase",
            )
        )

        archives = client.list_archives(repokey_repo_path)
        if len(archives) != 1:
            raise SmokeFailure(f"Expected one archive in repokey repo, got {archives}")
        archive_name = archives[0]["name"]
        archive_info = client.get_archive_info(
            archive_name, repokey_repo_path, include_files=True
        )
        encryption = archive_info.get("encryption", {})
        if encryption.get("mode") not in {"repokey", "repokey-blake2"}:
            raise SmokeFailure(f"Unexpected repokey encryption payload: {archive_info}")

        selected_restore_dir = client.temp_dir / "repokey-restore"
        selected_restore_dir.mkdir(parents=True, exist_ok=True)
        repo_root = client.container_path(source_root).lstrip("/")
        restore_job_id = client.start_restore(
            repository=repokey_repo_path,
            archive_name=archive_name,
            repository_id=repokey_repo_id,
            destination=selected_restore_dir,
            paths=[f"{repo_root}/docs"],
        )
        client.wait_for_job(
            "/api/restore/status", restore_job_id, expected={"completed"}, timeout=90
        )
        restored = sorted(
            path.relative_to(selected_restore_dir).as_posix()
            for path in selected_restore_dir.rglob("*")
            if path.is_file()
        )
        if not any(path.endswith("docs/secret.txt") for path in restored):
            raise SmokeFailure(
                f"Repokey restore did not produce expected file set: {restored}"
            )

        keyfile_source = client.prepare_source_tree(
            "keyfile-source",
            {"keyfile.txt": "keyfile smoke\n"},
        )
        keyfile_repo_path = client.temp_dir / "keyfile-repo"
        keyfile_passphrase = "keyfile-smoke-passphrase"
        client.run_borg(
            ["init", "--encryption=keyfile", str(keyfile_repo_path)],
            env={"BORG_PASSPHRASE": keyfile_passphrase},
        )
        client.run_borg(
            ["create", f"{keyfile_repo_path}::seed-archive", str(keyfile_source)],
            env={"BORG_PASSPHRASE": keyfile_passphrase},
        )
        exported_key = client.temp_dir / "exported.key"
        client.create_borg_key_export(
            keyfile_repo_path, keyfile_passphrase, exported_key
        )

        imported_repo_id, imported_repo_path = client.import_repository(
            name=f"Keyfile Smoke Repo {run_id}",
            repo_path=keyfile_repo_path,
            encryption="keyfile",
            source_dirs=[keyfile_source],
            passphrase=keyfile_passphrase,
            keyfile_content=exported_key.read_text(encoding="utf-8"),
        )
        client.upload_keyfile(imported_repo_id, exported_key)
        keyfile_bytes = client.download_keyfile(imported_repo_id)
        if not keyfile_bytes:
            raise SmokeFailure("Downloaded keyfile was empty")

        keyfile_archives = client.list_archives(imported_repo_path)
        if len(keyfile_archives) != 1:
            raise SmokeFailure(
                f"Expected imported keyfile repo to expose one archive, got {keyfile_archives}"
            )

        client.log("Encrypted repository smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
