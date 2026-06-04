"""Integration tests for Borg 2 archive API paths with real borg2 execution."""

import json
import shutil

import pytest
from fastapi.testclient import TestClient

from app.database.models import Repository
from tests.integration.test_helpers import wait_for_job_terminal_status
from tests.utils.borg import (
    create_archive,
    create_source_tree,
    init_borg_repo,
    make_borg_test_env,
)


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
        state = LicensingState(instance_id="integration-borg-v2-archives")
        test_db.add(state)

    state.plan = "pro"
    state.status = "active"
    state.is_trial = False
    test_db.commit()


def _create_borg2_repo_with_archives(test_db, tmp_path):
    borg2_binary = _require_borg2_binary()
    _enable_borg_v2(test_db)

    repo_path = tmp_path / "borg2-archives-repo"
    source_path = tmp_path / "borg2-archives-source"
    source_path.mkdir()
    create_source_tree(
        source_path,
        {
            "file1.txt": "archive file 1\n",
            "subdir/file2.txt": "archive file 2\n",
        },
    )

    env = make_borg_test_env(str(tmp_path))
    init_borg_repo(borg2_binary, repo_path, env=env, encryption="none")
    create_archive(borg2_binary, repo_path, "test-archive-1", [source_path], env=env)

    (source_path / "file1.txt").write_text("archive file 1 updated\n", encoding="utf-8")
    (source_path / "file3.txt").write_text("archive file 3\n", encoding="utf-8")
    create_archive(borg2_binary, repo_path, "test-archive-2", [source_path], env=env)

    repo = Repository(
        name="Test Borg2 Archives Repo",
        path=str(repo_path),
        encryption="none",
        compression="lz4",
        repository_type="local",
        borg_version=2,
        archive_count=2,
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo, repo_path, source_path, ["test-archive-1", "test-archive-2"]


@pytest.mark.integration
@pytest.mark.requires_borg
class TestBorg2ArchivesIntegration:
    def test_list_archives_returns_raw_json_contract(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        tmp_path,
    ):
        repo, _repo_path, _source_path, archive_names = (
            _create_borg2_repo_with_archives(test_db, tmp_path)
        )

        response = test_client.get(
            f"/api/v2/archives/list?repository={repo.id}",
            headers=admin_headers,
        )

        assert response.status_code == 200, response.json()
        payload = response.json()
        assert "archives" in payload
        archives_data = json.loads(payload["archives"])
        archives = archives_data.get("archives", [])
        assert [archive["name"] for archive in archives] == archive_names

    def test_delete_archive_updates_job_contract_and_archive_listing(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        tmp_path,
    ):
        repo, _repo_path, _source_path, archive_names = (
            _create_borg2_repo_with_archives(test_db, tmp_path)
        )

        delete_response = test_client.delete(
            f"/api/v2/archives/{archive_names[0]}?repository={repo.id}",
            headers=admin_headers,
        )

        assert delete_response.status_code == 200, delete_response.json()
        delete_payload = delete_response.json()
        assert delete_payload["status"] == "pending"
        assert delete_payload["message"] == "backend.success.archives.deletionStarted"
        assert delete_payload["note"] == "compact required to free space"
        assert isinstance(delete_payload["job_id"], int)

        job_data = wait_for_job_terminal_status(
            test_client,
            "/api/v2/archives/delete-jobs",
            delete_payload["job_id"],
            admin_headers,
            timeout=90,
        )

        assert job_data["status"] == "completed"
        assert job_data["archive_name"] == archive_names[0]
        assert (
            job_data["progress_message"] == "Archive deleted and repository compacted"
        )

        list_response = test_client.get(
            f"/api/v2/archives/list?repository={repo.path}",
            headers=admin_headers,
        )
        assert list_response.status_code == 200
        archives_data = json.loads(list_response.json()["archives"])
        remaining = [archive["name"] for archive in archives_data.get("archives", [])]
        assert archive_names[0] not in remaining
        assert archive_names[1] in remaining
