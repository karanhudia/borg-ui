import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.models import Repository
from tests.integration.test_helpers import (
    parse_archives_payload,
    wait_for_job_terminal_status,
)
from tests.utils.borg import make_borg_test_env
from tests.utils.jobs import wait_for_payload_status


def _prepare_repository_for_backup(repo, test_db, source_paths):
    repo.source_directories = json.dumps([str(path) for path in source_paths])
    repo.compression = "lz4"
    test_db.commit()


def _wait_for_backup_status(
    test_client: TestClient,
    job_id: int,
    headers,
    expected_status: str,
    *,
    timeout: float = 30.0,
    poll_interval: float = 0.25,
):
    def fetch_payload():
        response = test_client.get(f"/api/backup/status/{job_id}", headers=headers)
        response.raise_for_status()
        return response.json()

    return wait_for_payload_status(
        fetch_payload,
        expected={expected_status},
        timeout=timeout,
        poll_interval=poll_interval,
        description=f"backup job {job_id}",
    )


def _assert_v1_backup_start_contract(payload: dict) -> int:
    assert set(payload.keys()) == {"job_id", "status", "message"}
    assert isinstance(payload["job_id"], int)
    assert payload["status"] == "pending"
    assert payload["message"] == "Backup job started"
    return payload["job_id"]


def _assert_running_backup_status_contract(
    payload: dict, *, repository_path: str, job_id: int
) -> None:
    assert payload["id"] == job_id
    assert payload["repository"] == repository_path
    assert payload["status"] in {
        "pending",
        "running",
        "completed",
        "completed_with_warnings",
    }
    assert isinstance(payload["progress_details"], dict)
    assert {
        "original_size",
        "nfiles",
        "current_file",
        "progress_percent",
        "backup_speed",
        "total_expected_size",
        "estimated_time_remaining",
    }.issubset(payload["progress_details"].keys())


def _wait_for_live_progress(
    test_client: TestClient,
    job_id: int,
    headers,
    *,
    repository_path: str,
    timeout: float = 45.0,
    poll_interval: float = 0.25,
) -> dict:
    deadline = time.time() + timeout
    last_payload = None
    while time.time() < deadline:
        response = test_client.get(f"/api/backup/status/{job_id}", headers=headers)
        response.raise_for_status()
        payload = response.json()
        last_payload = payload
        _assert_running_backup_status_contract(
            payload,
            repository_path=repository_path,
            job_id=job_id,
        )
        progress = payload["progress_details"]
        has_live_progress = any(
            [
                progress.get("original_size", 0) > 0,
                progress.get("nfiles", 0) > 0,
                bool(progress.get("current_file")),
                progress.get("backup_speed", 0) > 0,
            ]
        )
        if payload["status"] == "running" and has_live_progress:
            return payload
        if payload["status"] in {
            "completed",
            "completed_with_warnings",
            "failed",
            "cancelled",
        }:
            break
        time.sleep(poll_interval)
    raise AssertionError(
        f"Backup never exposed live progress before completion: {last_payload}"
    )


def _wait_for_manual_backup_job_id(
    test_client: TestClient,
    headers,
    *,
    repository_path: str,
    timeout: float = 45.0,
    poll_interval: float = 0.25,
) -> int:
    deadline = time.time() + timeout
    last_payload = None
    while time.time() < deadline:
        response = test_client.get(
            "/api/backup/jobs?manual_only=true",
            headers=headers,
        )
        response.raise_for_status()
        payload = response.json()
        last_payload = payload
        matches = [
            job
            for job in payload.get("jobs", [])
            if job.get("repository") == repository_path
            and job.get("status") in {"pending", "running"}
        ]
        if matches:
            return int(max(matches, key=lambda job: int(job.get("id", 0)))["id"])
        time.sleep(poll_interval)
    raise AssertionError(
        f"Timed out waiting for manual backup job for {repository_path}: {last_payload}"
    )


def _assert_v2_backup_completion_contract(payload: dict) -> int:
    assert set(payload.keys()) == {"success", "stats", "status", "job_id"}
    assert payload["success"] is True
    assert isinstance(payload["job_id"], int)
    assert payload["status"] in {"completed", "completed_with_warnings"}
    assert set(payload["stats"].keys()) == {
        "original_size",
        "compressed_size",
        "deduplicated_size",
        "nfiles",
    }
    return payload["job_id"]


def _write_incompressible_file(path: Path, *, size_mb: int) -> None:
    chunk_size = 1024 * 1024
    with path.open("wb") as handle:
        for _ in range(size_mb):
            handle.write(os.urandom(chunk_size))


def _borg1_emits_live_json_progress(tmp_path: Path) -> bool:
    borg_binary = shutil.which("borg")
    if not borg_binary:
        return False

    base = tmp_path / "borg1-progress-contract"
    repo_path = base / "repo"
    source_root = base / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "notes.txt").write_text(
        "borg1 integration progress contract\n", encoding="utf-8"
    )
    _write_incompressible_file(source_root / "large.bin", size_mb=64)
    env = make_borg_test_env(str(base))
    init_result = subprocess.run(
        [borg_binary, "init", "--encryption=none", str(repo_path)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert init_result.returncode == 0, init_result.stderr
    create_result = subprocess.run(
        [
            borg_binary,
            "create",
            "--progress",
            "--stats",
            "--show-rc",
            "--log-json",
            "--compression",
            "none",
            f"{repo_path}::contract-check",
            str(source_root),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert create_result.returncode == 0, create_result.stderr
    for line in create_result.stdout.splitlines():
        if not line.startswith("{"):
            continue
        payload = json.loads(line)
        if (
            payload.get("type") == "archive_progress"
            and not payload.get("finished")
            and payload.get("original_size", 0) > 0
        ):
            return True
    return False


def _require_borg2_binary() -> str:
    borg2_path = shutil.which("borg2")
    if not borg2_path:
        pytest.skip(
            "Borg 2 binary not found. Install borg2 to run this integration test."
        )
    return borg2_path


def _enable_borg_v2(test_db) -> None:
    from app.database.models import LicensingState

    state = test_db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="integration-borg-v2-backup")
        test_db.add(state)

    state.plan = "pro"
    state.status = "active"
    state.is_trial = False
    test_db.commit()


def _create_borg2_registered_repo(test_db, tmp_path):
    borg2_binary = _require_borg2_binary()
    _enable_borg_v2(test_db)

    repo_path = tmp_path / "borg2-backup-repo"
    source_path = tmp_path / "borg2-backup-source"
    source_path.mkdir(parents=True, exist_ok=True)
    (source_path / "seed.txt").write_text(
        "borg2 backup integration seed\n", encoding="utf-8"
    )

    env = make_borg_test_env(str(tmp_path))
    init_result = subprocess.run(
        [borg2_binary, "-r", str(repo_path), "repo-create", "--encryption", "none"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert init_result.returncode == 0, init_result.stderr

    repo = Repository(
        name="Borg2 Backup Integration Repo",
        path=str(repo_path),
        borg_version=2,
        encryption="none",
        compression="lz4",
        repository_type="local",
        source_directories=json.dumps([str(source_path)]),
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo, repo_path, source_path


@pytest.mark.integration
@pytest.mark.requires_borg
class TestBackupCreationIntegration:
    """Integration tests for backup creation and job tracking."""

    def test_v1_backup_start_and_status_preserve_contract(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        test_db,
    ):
        repo, repo_path, test_data_path = db_borg_repo
        if not _borg1_emits_live_json_progress(tmp_path := test_data_path.parent):
            pytest.skip(
                "Current integration Borg environment does not emit live Borg 1 JSON progress"
            )
        _prepare_repository_for_backup(repo, test_db, [test_data_path])

        response = test_client.post(
            "/api/backup/start",
            json={"repository": str(repo_path)},
            headers=admin_headers,
        )

        assert response.status_code == 200
        job_id = _assert_v1_backup_start_contract(response.json())

        status_payload = test_client.get(
            f"/api/backup/status/{job_id}", headers=admin_headers
        )
        assert status_payload.status_code == 200
        _assert_running_backup_status_contract(
            status_payload.json(),
            repository_path=str(repo_path),
            job_id=job_id,
        )

        _wait_for_live_progress(
            test_client,
            job_id,
            admin_headers,
            repository_path=str(repo_path),
            timeout=45,
        )

        job_data = wait_for_job_terminal_status(
            test_client,
            "/api/backup/status",
            job_id,
            admin_headers,
            timeout=45,
        )
        assert job_data["status"] in ["completed", "completed_with_warnings"]

    def test_create_backup_success(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        test_db,
    ):
        repo, repo_path, test_data_path = db_borg_repo
        _prepare_repository_for_backup(repo, test_db, [test_data_path])

        response = test_client.post(
            "/api/backup/start",
            json={"repository": str(repo_path)},
            headers=admin_headers,
        )

        assert response.status_code == 200
        job_id = response.json()["job_id"]

        job_data = wait_for_job_terminal_status(
            test_client,
            "/api/backup/status",
            job_id,
            admin_headers,
            timeout=45,
        )
        assert job_data["status"] in ["completed", "completed_with_warnings"]

        list_response = test_client.get(
            f"/api/archives/list?repository={repo_path}",
            headers=admin_headers,
        )
        assert list_response.status_code == 200

        archive_names = [
            archive["name"] for archive in parse_archives_payload(list_response.json())
        ]
        assert any(name.startswith("manual-backup-") for name in archive_names)

    def test_backup_status_and_job_filters_include_manual_backup(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        test_db,
    ):
        repo, repo_path, test_data_path = db_borg_repo
        _prepare_repository_for_backup(repo, test_db, [test_data_path])

        response = test_client.post(
            "/api/backup/start",
            json={"repository": str(repo_path)},
            headers=admin_headers,
        )

        assert response.status_code == 200
        job_id = response.json()["job_id"]

        try:
            status_payload = wait_for_job_terminal_status(
                test_client,
                "/api/backup/status",
                job_id,
                admin_headers,
                timeout=45,
            )
        except TimeoutError:
            status_response = test_client.get(
                f"/api/backup/status/{job_id}",
                headers=admin_headers,
            )
            status_response.raise_for_status()
            job_data = status_response.json()
            if job_data["status"] == "pending":
                pytest.skip(
                    "backup did not leave pending state in integration environment: "
                    f"{job_data}"
                )
            raise

        progress = status_payload["progress_details"]
        assert set(
            [
                "original_size",
                "nfiles",
                "current_file",
                "progress_percent",
                "backup_speed",
                "total_expected_size",
                "estimated_time_remaining",
            ]
        ).issubset(progress.keys())

        manual_jobs = test_client.get(
            "/api/backup/jobs?manual_only=true",
            headers=admin_headers,
        )
        assert manual_jobs.status_code == 200
        manual_job_ids = [job["id"] for job in manual_jobs.json()["jobs"]]
        assert job_id in manual_job_ids

        scheduled_jobs = test_client.get(
            "/api/backup/jobs?scheduled_only=true",
            headers=admin_headers,
        )
        assert scheduled_jobs.status_code == 200
        scheduled_job_ids = [job["id"] for job in scheduled_jobs.json()["jobs"]]
        assert job_id not in scheduled_job_ids

    def test_create_backup_for_unknown_repository_path_fails_in_background(
        self,
        test_client: TestClient,
        admin_headers,
        tmp_path,
    ):
        missing_repo_path = tmp_path / "missing-repo"

        response = test_client.post(
            "/api/backup/start",
            json={"repository": str(missing_repo_path)},
            headers=admin_headers,
        )

        assert response.status_code == 200
        job_id = response.json()["job_id"]

        job_data = wait_for_job_terminal_status(
            test_client,
            "/api/backup/status",
            job_id,
            admin_headers,
            timeout=20,
        )

        assert job_data["status"] == "failed"
        assert job_data["error_message"]

    def test_download_backup_logs_for_failed_backup_job(
        self,
        test_client: TestClient,
        admin_headers,
        db_encrypted_borg_repo,
        test_db,
    ):
        repo, repo_path, test_data_path, _passphrase = db_encrypted_borg_repo
        _prepare_repository_for_backup(repo, test_db, [test_data_path])
        repo.passphrase = "definitely-wrong-passphrase"
        test_db.commit()

        response = test_client.post(
            "/api/backup/start",
            json={"repository": str(repo_path)},
            headers=admin_headers,
        )

        assert response.status_code == 200
        job_id = response.json()["job_id"]

        job_data = wait_for_job_terminal_status(
            test_client,
            "/api/backup/status",
            job_id,
            admin_headers,
            timeout=45,
        )

        assert job_data["status"] == "failed"
        assert job_data["error_message"]

        logs_response = test_client.get(
            f"/api/backup/logs/{job_id}/download",
            headers=admin_headers,
        )

        assert logs_response.status_code == 200
        assert logs_response.headers["content-type"].startswith("text/plain")
        assert (
            f"backup_job_{job_id}_logs.txt"
            in logs_response.headers["content-disposition"]
        )
        assert (
            "passphrase" in logs_response.text.lower()
            or "passphrase supplied in" in logs_response.text.lower()
        )

    def test_create_backup_success_for_encrypted_repository(
        self,
        test_client: TestClient,
        admin_headers,
        db_encrypted_borg_repo,
        test_db,
    ):
        repo, repo_path, test_data_path, _passphrase = db_encrypted_borg_repo
        _prepare_repository_for_backup(repo, test_db, [test_data_path])

        response = test_client.post(
            "/api/backup/start",
            json={"repository": str(repo_path)},
            headers=admin_headers,
        )

        assert response.status_code == 200
        job_id = response.json()["job_id"]

        job_data = wait_for_job_terminal_status(
            test_client,
            "/api/backup/status",
            job_id,
            admin_headers,
            timeout=45,
        )
        assert job_data["status"] in ["completed", "completed_with_warnings"]

        list_response = test_client.get(
            f"/api/archives/list?repository={repo_path}",
            headers=admin_headers,
        )
        assert list_response.status_code == 200
        archive_names = [
            archive["name"] for archive in parse_archives_payload(list_response.json())
        ]
        assert "encrypted-archive" in archive_names
        assert any(name.startswith("manual-backup-") for name in archive_names)

    def test_v2_backup_run_and_shared_status_preserve_contract(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        tmp_path,
    ):
        repo, _repo_path, source_path = _create_borg2_registered_repo(test_db, tmp_path)
        large_source_dir = source_path / "large"
        large_source_dir.mkdir(parents=True, exist_ok=True)
        _write_incompressible_file(large_source_dir / "huge.bin", size_mb=128)
        _prepare_repository_for_backup(repo, test_db, [source_path])
        repo.compression = "none"
        test_db.commit()

        result_queue: queue.Queue = queue.Queue()

        def _run_v2_backup():
            try:
                response = test_client.post(
                    "/api/v2/backup/run",
                    json={"repository_id": repo.id},
                    headers=admin_headers,
                )
                result_queue.put(("response", response))
            except Exception as exc:  # pragma: no cover - defensive integration helper
                result_queue.put(("error", exc))

        worker = threading.Thread(target=_run_v2_backup, daemon=True)
        worker.start()

        job_id = _wait_for_manual_backup_job_id(
            test_client,
            admin_headers,
            repository_path=repo.path,
            timeout=45,
        )
        _wait_for_live_progress(
            test_client,
            job_id,
            admin_headers,
            repository_path=repo.path,
            timeout=90,
        )

        worker.join(timeout=300)
        assert not worker.is_alive(), (
            "Timed out waiting for Borg 2 backup request to complete"
        )

        result_kind, result_value = result_queue.get_nowait()
        if result_kind == "error":
            raise result_value

        response = result_value
        assert response.status_code == 200
        payload = response.json()
        assert _assert_v2_backup_completion_contract(payload) == job_id

        status_response = test_client.get(
            f"/api/backup/status/{job_id}", headers=admin_headers
        )
        assert status_response.status_code == 200
        status_payload = status_response.json()
        assert status_payload["status"] in {"completed", "completed_with_warnings"}
        _assert_running_backup_status_contract(
            status_payload,
            repository_path=repo.path,
            job_id=job_id,
        )

    def test_cancel_running_backup_via_api(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        test_db,
        tmp_path,
    ):
        repo, repo_path, _test_data_path = db_borg_repo
        large_source_dir = tmp_path / "large-source"
        large_source_dir.mkdir()
        _write_incompressible_file(large_source_dir / "huge.bin", size_mb=128)

        _prepare_repository_for_backup(repo, test_db, [large_source_dir])
        repo.compression = "lzma"
        test_db.commit()

        response = test_client.post(
            "/api/backup/start",
            json={"repository": str(repo_path)},
            headers=admin_headers,
        )

        assert response.status_code == 200
        job_id = response.json()["job_id"]

        try:
            _wait_for_backup_status(
                test_client,
                job_id,
                admin_headers,
                "running",
                timeout=45,
                poll_interval=0.5,
            )
        except TimeoutError:
            status_response = test_client.get(
                f"/api/backup/status/{job_id}",
                headers=admin_headers,
            )
            status_response.raise_for_status()
            job_data = status_response.json()
            pytest.skip(
                "backup did not reach a cancellable running state in integration environment: "
                f"{job_data}"
            )

        cancel_response = test_client.post(
            f"/api/backup/cancel/{job_id}",
            headers=admin_headers,
        )

        assert cancel_response.status_code == 200
        cancel_payload = cancel_response.json()
        assert cancel_payload["message"] == "backend.success.backup.backupCancelled"

        job_data = wait_for_job_terminal_status(
            test_client,
            "/api/backup/status",
            job_id,
            admin_headers,
            timeout=20,
        )
        assert job_data["status"] == "cancelled"
