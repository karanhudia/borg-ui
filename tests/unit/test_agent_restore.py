"""Unit tests for agent-side managed restore (repository.restore job kind)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import agent.borg_ui_agent.repository_ops as repository_ops
from agent.borg_ui_agent.repository_ops import (
    RepositoryOperationPayload,
    _resolve_restore_target,
    _verify_canary,
    execute_repository_operation_job,
)


class RecordingClient:
    def __init__(self):
        self.calls = []
        self.completed = None
        self.failed = None
        self.canceled = None

    def send_log(self, job_id, *, sequence, message, stream="stdout"):
        self.calls.append(("send_log", job_id, sequence, stream, message))

    def send_progress(self, job_id, progress):
        self.calls.append(("send_progress", job_id, progress))

    def complete_job(self, job_id, *, result):
        self.completed = result
        self.calls.append(("complete_job", job_id, result))

    def fail_job(self, job_id, *, error_message, return_code=None):
        self.failed = {"error_message": error_message, "return_code": return_code}
        self.calls.append(("fail_job", job_id, error_message, return_code))

    def cancel_job(self, job_id):
        self.canceled = job_id
        self.calls.append(("cancel_job", job_id))


def _make_fake_popen(*, files=None, lines=None, returncode=0, captured=None):
    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            self.cmd = cmd
            self.returncode = returncode
            self.stdout = list(lines or [])
            cwd = kwargs.get("cwd")
            if captured is not None:
                captured["cwd"] = cwd
                captured["cmd"] = cmd
            if files and cwd:
                base = Path(cwd)
                for rel, content in files.items():
                    target = base / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)

        def wait(self):
            return returncode

        def poll(self):
            return returncode

    return _FakePopen


def _restore_job(operation, *, borg_version=1, path="/agent/repo"):
    return {
        "id": 42,
        "payload": {
            "schema_version": 1,
            "job_kind": "repository.restore",
            "repository": {"path": path, "borg_version": borg_version},
            "operation": operation,
        },
    }


def _canary_manifest(archive_root: str, content: bytes):
    """Return a (files-dict, manifest_candidate) pair laying out a valid canary."""
    rel = ".borgui-canary/README.txt"
    manifest = {
        "files": [
            {
                "path": rel,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ]
    }
    files = {
        f"{archive_root}/{rel}": content,
        f"{archive_root}/.borgui-canary/manifest.json": json.dumps(manifest).encode(),
    }
    candidate = f"{archive_root}/.borgui-canary/manifest.json"
    return files, candidate


# --------------------------------------------------------------------------- #
# build_command
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_repository_restore_builds_borg1_command():
    payload = RepositoryOperationPayload.from_job_payload(
        _restore_job(
            {"archive": "arch", "paths": ["etc/hosts"], "strip_components": 2},
        )["payload"]
    )

    assert payload.build_command() == [
        "borg",
        "extract",
        "--progress",
        "--log-json",
        "--umask",
        "0022",
        "--strip-components",
        "2",
        "/agent/repo::arch",
        "--",
        "etc/hosts",
    ]


@pytest.mark.unit
def test_repository_restore_builds_borg2_command():
    payload = RepositoryOperationPayload.from_job_payload(
        _restore_job(
            {"archive": "arch", "paths": ["etc/hosts"]},
            borg_version=2,
        )["payload"]
    )

    assert payload.build_command() == [
        "borg2",
        "-r",
        "/agent/repo",
        "extract",
        "--progress",
        "--log-json",
        "--umask",
        "0022",
        "arch",
        "--",
        "etc/hosts",
    ]


@pytest.mark.unit
def test_repository_restore_rejects_non_list_paths():
    payload = RepositoryOperationPayload.from_job_payload(
        _restore_job({"archive": "arch", "paths": "etc/hosts"})["payload"]
    )
    with pytest.raises(ValueError, match="operation.paths to be a list"):
        payload.build_command()


# --------------------------------------------------------------------------- #
# target resolution
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_resolve_restore_target_path_creates_directory(tmp_path):
    dest = tmp_path / "restore" / "here"
    target_dir, is_temp = _resolve_restore_target(
        {"target": {"type": "path", "path": str(dest)}}
    )
    assert target_dir == str(dest)
    assert is_temp is False
    assert dest.is_dir()


@pytest.mark.unit
def test_resolve_restore_target_temp_is_disposable():
    target_dir, is_temp = _resolve_restore_target({"target": {"type": "temp"}})
    assert is_temp is True
    assert Path(target_dir).is_dir()
    Path(target_dir).rmdir()


@pytest.mark.unit
def test_resolve_restore_target_requires_target():
    with pytest.raises(ValueError, match="requires operation.target"):
        _resolve_restore_target({})


@pytest.mark.unit
def test_resolve_restore_target_rejects_relative_path():
    # borg extract runs with cwd=destination; a relative path would extract into
    # the agent's working directory, so it must be rejected.
    with pytest.raises(ValueError, match="must be absolute"):
        _resolve_restore_target({"target": {"type": "path", "path": "relative/dir"}})


# --------------------------------------------------------------------------- #
# canary verification
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_verify_canary_verified(tmp_path):
    files, candidate = _canary_manifest("arc", b"canary-payload")
    for rel, content in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    verdict = _verify_canary(str(tmp_path), {"manifest_candidates": [candidate]})
    assert verdict["status"] == "verified"
    assert verdict["verified_files"] == [".borgui-canary/README.txt"]


@pytest.mark.unit
def test_verify_canary_needs_backup_when_manifest_absent(tmp_path):
    verdict = _verify_canary(
        str(tmp_path), {"manifest_candidates": ["arc/.borgui-canary/manifest.json"]}
    )
    assert verdict["status"] == "needs_backup"


@pytest.mark.unit
def test_verify_canary_failed_on_hash_mismatch(tmp_path):
    files, candidate = _canary_manifest("arc", b"canary-payload")
    for rel, content in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    # Corrupt the extracted file so its hash no longer matches the manifest.
    (tmp_path / "arc/.borgui-canary/README.txt").write_bytes(b"tampered")

    verdict = _verify_canary(str(tmp_path), {"manifest_candidates": [candidate]})
    assert verdict["status"] == "failed"
    assert "hash mismatch" in verdict["message"]


@pytest.mark.unit
def test_verify_canary_ignores_traversal_manifest_candidate(tmp_path):
    # A manifest_candidate that escapes the restored tree must not be read; with
    # no in-tree manifest found, the verdict is needs_backup.
    verdict = _verify_canary(
        str(tmp_path), {"manifest_candidates": ["../../../../etc/hosts"]}
    )
    assert verdict["status"] == "needs_backup"


@pytest.mark.unit
def test_verify_canary_rejects_traversal_file_path(tmp_path):
    # A manifest whose files[].path escapes the restored tree must be rejected
    # rather than hashing an arbitrary file on the agent.
    manifest_rel = "arc/.borgui-canary/manifest.json"
    manifest_path = tmp_path / manifest_rel
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {"files": [{"path": "../../../../etc/hosts", "size": 1, "sha256": "x"}]}
        )
    )
    verdict = _verify_canary(str(tmp_path), {"manifest_candidates": [manifest_rel]})
    assert verdict["status"] == "failed"
    assert "escapes restore root" in verdict["message"]


@pytest.mark.unit
def test_verify_canary_failed_when_file_missing(tmp_path):
    _, candidate = _canary_manifest("arc", b"canary-payload")
    # Only write the manifest, not the file it references.
    manifest_path = tmp_path / candidate
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "files": [
            {
                "path": ".borgui-canary/README.txt",
                "size": 5,
                "sha256": hashlib.sha256(b"hello").hexdigest(),
            }
        ]
    }
    manifest_path.write_text(json.dumps(manifest))

    verdict = _verify_canary(str(tmp_path), {"manifest_candidates": [candidate]})
    assert verdict["status"] == "failed"
    assert "missing after restore" in verdict["message"]


# --------------------------------------------------------------------------- #
# executor
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_execute_restore_extracts_into_target_path(tmp_path, monkeypatch):
    dest = tmp_path / "dest"
    captured = {}
    monkeypatch.setattr(
        repository_ops.subprocess,
        "Popen",
        _make_fake_popen(lines=["restoring"], returncode=0, captured=captured),
    )
    client = RecordingClient()
    job = _restore_job(
        {"archive": "arch", "paths": [], "target": {"type": "path", "path": str(dest)}}
    )

    result = execute_repository_operation_job(job, client, should_cancel=None)

    assert result.status == "completed"
    assert captured["cwd"] == str(dest)
    assert dest.is_dir()
    assert client.completed is not None
    assert client.completed["return_code"] == 0


@pytest.mark.unit
def test_execute_restore_temp_target_verifies_and_cleans_up(tmp_path, monkeypatch):
    files, candidate = _canary_manifest("arc", b"canary-payload")
    captured = {}
    monkeypatch.setattr(
        repository_ops.subprocess,
        "Popen",
        _make_fake_popen(files=files, lines=[], returncode=0, captured=captured),
    )
    client = RecordingClient()
    job = _restore_job(
        {
            "archive": "arch",
            "paths": ["arc/.borgui-canary"],
            "target": {"type": "temp"},
            "verify": {"kind": "canary", "manifest_candidates": [candidate]},
        }
    )

    result = execute_repository_operation_job(job, client, should_cancel=None)

    assert result.status == "completed"
    assert client.completed["verification"]["status"] == "verified"
    # Temp target is removed after the job finishes.
    assert not Path(captured["cwd"]).exists()


@pytest.mark.unit
def test_execute_restore_hard_failure_fails_job(tmp_path, monkeypatch):
    dest = tmp_path / "dest"
    monkeypatch.setattr(
        repository_ops.subprocess,
        "Popen",
        _make_fake_popen(lines=["boom"], returncode=2),
    )
    client = RecordingClient()
    job = _restore_job(
        {"archive": "arch", "paths": [], "target": {"type": "path", "path": str(dest)}}
    )

    result = execute_repository_operation_job(job, client, should_cancel=None)

    assert result.status == "failed"
    assert client.failed["return_code"] == 2
    assert client.completed is None


@pytest.mark.unit
def test_execute_restore_cancellation(tmp_path, monkeypatch):
    dest = tmp_path / "dest"
    monkeypatch.setattr(
        repository_ops.subprocess,
        "Popen",
        _make_fake_popen(lines=["still going"], returncode=0),
    )
    client = RecordingClient()
    job = _restore_job(
        {"archive": "arch", "paths": [], "target": {"type": "path", "path": str(dest)}}
    )

    result = execute_repository_operation_job(job, client, should_cancel=lambda: True)

    assert result.status == "canceled"
    assert client.canceled == 42
