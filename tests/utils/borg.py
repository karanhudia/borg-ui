"""Shared Borg helpers for integration and smoke tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Optional

import pytest

if TYPE_CHECKING:
    from app.database.models import Repository


def require_borg_binary() -> str:
    """Return the Borg binary path or skip the test if unavailable."""
    borg_path = shutil.which("borg")
    if not borg_path:
        pytest.skip("Borg binary not found. Install borgbackup to run integration tests.")
    return borg_path


def make_borg_test_env(base_path: str) -> dict:
    """Build a Borg-safe environment rooted under a temporary directory."""
    borg_home = Path(base_path) / "borg-home"
    borg_base_dir = Path(base_path) / "borg-base"
    borg_home.mkdir(parents=True, exist_ok=True)
    borg_base_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["HOME"] = str(borg_home)
    env["BORG_BASE_DIR"] = str(borg_base_dir)
    env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
    env["BORG_RELOCATED_REPO_ACCESS_IS_OK"] = "yes"
    return env


def run_borg(
    borg_binary: str,
    args: list[str],
    *,
    env: Optional[dict] = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run Borg with a predictable environment."""
    merged_env = os.environ.copy()
    merged_env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
    merged_env["BORG_RELOCATED_REPO_ACCESS_IS_OK"] = "yes"
    if env:
        merged_env.update(env)
    result = subprocess.run(
        [borg_binary, *args],
        capture_output=True,
        text=True,
        env=merged_env,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr or f"borg {' '.join(args)} failed")
    return result


def init_borg_repo(
    borg_binary: str,
    repo_path: Path,
    *,
    env: Optional[dict] = None,
    encryption: str = "none",
) -> Path:
    """Initialize a Borg repository."""
    repo_path.mkdir(parents=True, exist_ok=True)
    borg_name = Path(borg_binary).name
    if borg_name.startswith("borg2"):
        run_borg(borg_binary, ["-r", str(repo_path), "repo-create", "--encryption", encryption], env=env)
    else:
        run_borg(borg_binary, ["init", f"--encryption={encryption}", str(repo_path)], env=env)
    return repo_path


def create_archive(
    borg_binary: str,
    repo_path: Path,
    archive_name: str,
    source_paths: Iterable[Path | str],
    *,
    env: Optional[dict] = None,
) -> subprocess.CompletedProcess:
    """Create an archive from one or more source paths."""
    borg_name = Path(borg_binary).name
    if borg_name.startswith("borg2"):
        args = ["-r", str(repo_path), "create", archive_name, *[str(path) for path in source_paths]]
    else:
        args = ["create", f"{repo_path}::{archive_name}", *[str(path) for path in source_paths]]
    return run_borg(borg_binary, args, env=env)


def list_archive_names(
    borg_binary: str,
    repo_path: Path | str,
    *,
    env: Optional[dict] = None,
) -> list[str]:
    """Return archive names for a repository."""
    result = run_borg(borg_binary, ["list", "--short", str(repo_path)], env=env)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def get_latest_archive_name(
    borg_binary: str,
    repo_path: Path | str,
    *,
    env: Optional[dict] = None,
) -> str:
    """Return the newest archive name, asserting one exists."""
    archives = list_archive_names(borg_binary, repo_path, env=env)
    assert archives, f"expected at least one archive in {repo_path}"
    return archives[-1]


def list_archive_paths(
    borg_binary: str,
    repo_path: Path | str,
    archive_name: str,
    *,
    env: Optional[dict] = None,
) -> set[str]:
    """Return the set of file paths inside an archive."""
    result = run_borg(
        borg_binary,
        ["list", "--json-lines", f"{repo_path}::{archive_name}"],
        env=env,
    )
    archive_paths: set[str] = set()
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        path = payload.get("path")
        if path:
            archive_paths.add(path)
    return archive_paths


def create_source_tree(root: Path, files: dict[str, str]) -> Path:
    """Create a source tree from a relative-path to contents mapping."""
    for relative_path, content in files.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def create_registered_local_repository(
    *,
    test_db,
    borg_binary: str,
    tmp_path: Path,
    name: str,
    slug: str,
    source_files: dict[str, str],
    borg_env: Optional[dict] = None,
    encryption: str = "none",
    passphrase: Optional[str] = None,
) -> tuple["Repository", Path, Path]:
    """Create a Borg repo plus a matching local Repository database record."""
    from app.database.models import Repository

    repo_path = tmp_path / f"{slug}-repo"
    source_path = tmp_path / f"{slug}-data"
    source_path.mkdir(parents=True, exist_ok=True)
    create_source_tree(source_path, source_files)

    env = borg_env.copy() if borg_env else None
    if passphrase:
        env = env or os.environ.copy()
        env["BORG_PASSPHRASE"] = passphrase

    init_borg_repo(borg_binary, repo_path, env=env, encryption=encryption)

    repo = Repository(
        name=name,
        path=str(repo_path),
        encryption=encryption,
        passphrase=passphrase,
        compression="lz4",
        repository_type="local",
        mode="full",
        source_directories=json.dumps([str(source_path)]),
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo, repo_path, source_path
