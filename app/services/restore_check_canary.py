from __future__ import annotations

import base64
import hashlib
import json
import shlex
from pathlib import Path
from typing import Any

from app.config import settings
from app.database.models import Repository

CANARY_ARCHIVE_NAMESPACE = ".borg-ui/restore-canaries"
CANARY_DIRNAME = ".borgui-canary"
CANARY_MANIFEST = "manifest.json"


def _repo_canary_root(repository: Repository) -> Path:
    return (
        Path(settings.data_dir)
        / CANARY_ARCHIVE_NAMESPACE
        / f"repository-{repository.id}"
    )


def _canary_archive_root(repository: Repository) -> str:
    return f"{CANARY_ARCHIVE_NAMESPACE}/repository-{repository.id}"


def _legacy_canary_archive_root(repository: Repository) -> str:
    return str(
        (Path(settings.data_dir) / "restore-canaries" / f"repository-{repository.id}")
        .as_posix()
        .lstrip("/")
    )


def _build_canary_entries(repository: Repository) -> dict[str, bytes]:
    repo_marker = f"borg-ui-canary-repository-{repository.id}".encode("utf-8")
    binary_payload = hashlib.sha256(repo_marker).digest() * 8
    return {
        f"{CANARY_DIRNAME}/README.txt": (
            "Borg UI managed restore canary.\n"
            f"Repository: {repository.name}\n"
            f"Repository ID: {repository.id}\n"
        ).encode("utf-8"),
        f"{CANARY_DIRNAME}/nested/check.json": json.dumps(
            {
                "repository_id": repository.id,
                "repository_name": repository.name,
                "kind": "restore_canary",
            },
            sort_keys=True,
        ).encode("utf-8"),
        f"{CANARY_DIRNAME}/binary/check.bin": binary_payload,
    }


def _parse_restore_check_paths(raw_paths: Any) -> list[str]:
    if not raw_paths:
        return []
    if isinstance(raw_paths, list):
        return [path for path in raw_paths if isinstance(path, str) and path.strip()]
    if not isinstance(raw_paths, str):
        return []
    try:
        parsed = json.loads(raw_paths)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [path for path in parsed if isinstance(path, str) and path.strip()]


def should_include_restore_canary(repository: Repository) -> bool:
    """Return whether future backups for this repository should include canary files."""
    if not bool(getattr(repository, "restore_check_canary_enabled", False)):
        return False
    if bool(getattr(repository, "restore_check_full_archive", False)):
        return False
    return not _parse_restore_check_paths(
        getattr(repository, "restore_check_paths", None)
    )


def _canary_manifest_bytes(entries: dict[str, bytes]) -> bytes:
    manifest_entries: list[dict[str, str | int]] = [
        {
            "path": relative_path,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for relative_path, content in entries.items()
    ]
    return json.dumps({"files": manifest_entries}, indent=2, sort_keys=True).encode(
        "utf-8"
    )


def ensure_restore_canary(repository: Repository) -> Path:
    root = _repo_canary_root(repository)
    root.mkdir(parents=True, exist_ok=True)

    entries = _build_canary_entries(repository)
    for relative_path, content in entries.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    manifest_target = root / CANARY_DIRNAME / CANARY_MANIFEST
    manifest_target.write_bytes(_canary_manifest_bytes(entries))
    return root / CANARY_DIRNAME


def remote_restore_canary_staging(
    repository: Repository,
    job: Any | None = None,
) -> tuple[str, str, str] | None:
    """Shell snippet that stages the managed canary on a remote-direct host.

    Remote-direct backups run Borg on the SSH host, so the canary payload must
    exist there. Returns ``(script, canary_root, archive_source_path)`` where
    ``script`` writes the same files ``ensure_restore_canary`` writes locally
    under the SSH user's ``$HOME``, ``canary_root`` is the directory Borg must
    run from (``$HOME``, so the relative source resolves), and
    ``archive_source_path`` is the path to hand to Borg relative to that root
    so the archive keeps the hidden ``.borg-ui/restore-canaries`` namespace the
    restore check extracts. Returns None when the repository does not use
    canary mode.

    If job is provided, job-level overrides (full_archive, probe_paths) take
    precedence over repository settings and disable canary staging.

    The script never carries user-controlled text outside base64: every path
    is built from constants and the integer repository id, and every file body
    is written as ``printf '%s' <b64> | base64 -d`` so the generated README
    (which names the repository) cannot inject shell.
    """
    # Job-level overrides take precedence over repository settings
    if job and (
        getattr(job, "full_archive", False) or getattr(job, "probe_paths", None)
    ):
        return None

    if not should_include_restore_canary(repository):
        return None

    archive_root = _canary_archive_root(repository)
    # Borg is run from $HOME so the relative archive source keeps the hidden
    # .borg-ui/restore-canaries/repository-<id> namespace in the archive.
    canary_root = "$HOME"
    canary_dir = f"$HOME/{archive_root}"
    entries = _build_canary_entries(repository)
    files = {
        **entries,
        f"{CANARY_DIRNAME}/{CANARY_MANIFEST}": _canary_manifest_bytes(entries),
    }

    commands = []
    for relative_path, content in files.items():
        parent = relative_path.rsplit("/", 1)[0]
        commands.append(f'mkdir -p "{canary_dir}/{parent}"')
        encoded = base64.b64encode(content).decode("ascii")
        commands.append(
            f"printf '%s' {shlex.quote(encoded)} | base64 -d > "
            f'"{canary_dir}/{relative_path}"'
        )

    return (
        " && ".join(commands),
        canary_root,
        f"{archive_root}/{CANARY_DIRNAME}",
    )


def get_restore_canary_archive_paths(repository: Repository) -> list[str]:
    archive_root = _canary_archive_root(repository)
    return [f"{archive_root}/{CANARY_DIRNAME}"]


def get_legacy_restore_canary_archive_paths(repository: Repository) -> list[str]:
    archive_root = _legacy_canary_archive_root(repository)
    return [f"{archive_root}/{CANARY_DIRNAME}"]


def to_restore_canary_archive_source_path(
    source_path: str, data_dir: str | Path | None = None
) -> str | None:
    """Return the archive-relative source path for Borg UI canary files."""
    source = Path(source_path)
    if not source.is_absolute():
        normalized = source.as_posix().strip("/")
        if normalized.startswith(f"{CANARY_ARCHIVE_NAMESPACE}/"):
            return normalized
        return None

    try:
        relative = source.resolve().relative_to(
            Path(data_dir or settings.data_dir).resolve()
        )
    except ValueError:
        return None

    normalized = relative.as_posix().strip("/")
    if normalized.startswith(f"{CANARY_ARCHIVE_NAMESPACE}/"):
        return normalized
    return None


def verify_restored_canary(repository: Repository, restore_destination: str) -> dict:
    restore_root = Path(restore_destination)
    archive_roots = [
        _canary_archive_root(repository),
        _legacy_canary_archive_root(repository),
    ]
    manifest_path = None
    archive_root = None
    for candidate_root in archive_roots:
        candidate = restore_root / candidate_root / CANARY_DIRNAME / CANARY_MANIFEST
        if candidate.exists():
            manifest_path = candidate
            archive_root = candidate_root
            break

    if manifest_path is None or archive_root is None:
        raise FileNotFoundError(
            "The Borg UI canary file was not found in the latest archive. "
            "Run a backup while canary mode is enabled, then run this restore check again."
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files", [])
    verified_files = []
    for file_entry in files:
        relative_path = file_entry["path"]
        target = restore_root / archive_root / relative_path
        if not target.exists():
            raise FileNotFoundError(f"Canary file missing after restore: {target}")
        content = target.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != file_entry["sha256"]:
            raise ValueError(f"Canary hash mismatch for {relative_path}")
        if len(content) != file_entry["size"]:
            raise ValueError(f"Canary size mismatch for {relative_path}")
        verified_files.append(relative_path)

    return {"verified_files": verified_files, "manifest_path": str(manifest_path)}
