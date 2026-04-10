import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.database.models import DeleteArchiveJob, LicensingState, Repository


def _enable_borg_v2(test_db):
    state = test_db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="test-instance-v2-archives")
        test_db.add(state)
    state.plan = "pro"
    state.status = "active"
    state.is_trial = False
    test_db.commit()


def _create_v2_repo(test_db, *, name="V2 Archive Repo", path="/tmp/v2-archive-repo"):
    repo = Repository(
        name=name,
        path=path,
        encryption="repokey-aes-ocb",
        compression="lz4",
        repository_type="local",
        borg_version=2,
        source_directories=json.dumps(["/data/source"]),
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


@pytest.mark.unit
class TestV2ArchiveRoutes:
    def test_archive_routes_are_feature_gated_by_plan(self, test_client: TestClient, admin_headers):
        response = test_client.get(
            "/api/v2/archives/list?repository=1",
            headers=admin_headers,
        )

        assert response.status_code == 403
        assert response.json()["detail"]["key"] == "backend.errors.plan.featureNotAvailable"

    def test_list_archives_by_repository_id(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)

        with patch(
            "app.api.v2.archives.borg2.list_archives",
            new=AsyncMock(return_value={"success": True, "stdout": json.dumps({"archives": [{"name": "archive-1"}]}), "stderr": ""}),
        ) as mock_list:
            response = test_client.get(f"/api/v2/archives/list?repository={repo.id}", headers=admin_headers)

        assert response.status_code == 200
        assert response.json() == {"archives": json.dumps({"archives": [{"name": "archive-1"}]})}
        mock_list.assert_awaited_once_with(
            repo.path,
            passphrase=None,
            remote_path=None,
            bypass_lock=False,
        )

    def test_list_archives_returns_404_for_unknown_repo(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)

        response = test_client.get("/api/v2/archives/list?repository=/missing/repo", headers=admin_headers)

        assert response.status_code == 404
        assert response.json()["detail"]["key"] == "backend.errors.restore.repositoryNotFound"

    def test_get_archive_info_by_path_includes_files(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db, path="/tmp/v2-info-repo")

        info_payload = {
            "archives": [
                {
                    "name": "archive-1",
                    "id": "id-1",
                    "stats": {"original_size": 123},
                }
            ],
            "repository": {"id": 7},
            "encryption": {"mode": "repokey-aes-ocb"},
            "cache": {"path": "/cache"},
        }
        contents_payload = "\n".join(
            [
                json.dumps(
                    {
                        "path": "docs/report.txt",
                        "type": "f",
                        "mode": "rw",
                        "user": "root",
                        "group": "root",
                        "size": 11,
                        "mtime": "2026-04-04T00:00:00",
                    }
                ),
                "not-json",
                json.dumps(
                    {
                        "path": "docs/ignored.txt",
                        "type": "f",
                        "mode": "rw",
                        "user": "root",
                        "group": "root",
                        "size": 22,
                        "mtime": "2026-04-04T00:00:01",
                    }
                ),
            ]
        )

        with patch(
            "app.api.v2.archives.borg2.info_archive",
            new=AsyncMock(return_value={"success": True, "stdout": json.dumps(info_payload), "stderr": ""}),
        ) as mock_info:
            with patch(
                "app.api.v2.archives.borg2.list_archive_contents",
                new=AsyncMock(return_value={"success": True, "stdout": contents_payload, "stderr": ""}),
            ) as mock_contents:
                response = test_client.get(
                    f"/api/v2/archives/archive-1/info?repository={repo.path}&include_files=true&file_limit=1",
                    headers=admin_headers,
                )

        assert response.status_code == 200
        info = response.json()["info"]
        assert info["name"] == "archive-1"
        assert info["repository"] == {"id": 7}
        assert info["encryption"] == {"mode": "repokey-aes-ocb"}
        assert info["file_count"] == 1
        assert info["files"] == [
            {
                "path": "docs/report.txt",
                "type": "f",
                "mode": "rw",
                "user": "root",
                "group": "root",
                "size": 11,
                "mtime": "2026-04-04T00:00:00",
                "healthy": True,
            }
        ]
        mock_info.assert_awaited_once()
        mock_contents.assert_awaited_once()

    def test_get_archive_info_returns_raw_text_for_invalid_json(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)

        with patch(
            "app.api.v2.archives.borg2.info_archive",
            new=AsyncMock(return_value={"success": True, "stdout": "plain text payload", "stderr": ""}),
        ):
            response = test_client.get(
                f"/api/v2/archives/archive-1/info?repository={repo.id}",
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json()["info"] == "plain text payload"

    def test_get_archive_contents_filters_nested_paths(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)

        stdout = "\n".join(
            [
                json.dumps({"path": "docs", "type": "d", "size": 0, "mtime": "2026-04-04T00:00:00"}),
                json.dumps({"path": "docs/report.txt", "type": "f", "size": 11, "mtime": "2026-04-04T00:00:01"}),
                json.dumps({"path": "docs/sub", "type": "d", "size": 0, "mtime": "2026-04-04T00:00:02"}),
                json.dumps({"path": "docs/sub/notes.txt", "type": "f", "size": 5, "mtime": "2026-04-04T00:00:03"}),
            ]
        )

        with patch(
            "app.api.v2.archives.borg2.list_archive_contents",
            new=AsyncMock(return_value={"success": True, "stdout": stdout, "stderr": ""}),
        ):
            response = test_client.get(
                f"/api/v2/archives/archive-1/contents?repository={repo.path}&path=docs",
                headers=admin_headers,
            )

        assert response.status_code == 200
        items = response.json()["items"]
        assert {item["name"] for item in items} == {"report.txt", "sub"}
        sub_dir = next(item for item in items if item["name"] == "sub")
        assert sub_dir["type"] == "directory"
        assert sub_dir["size"] == 5

    def test_get_archive_contents_resolves_archive_id_to_name(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)
        archive_id = "10614da295b13209b207fc2499d67e7f10c24f4a1745e482bd3fc2595e4ec7fd"

        with patch(
            "app.api.v2.archives.borg2.list_archives",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "stdout": json.dumps({"archives": [{"id": archive_id, "name": "archive-1"}]}),
                    "stderr": "",
                }
            ),
        ) as mock_archives, patch(
            "app.api.v2.archives.borg2.list_archive_contents",
            new=AsyncMock(return_value={"success": True, "stdout": "", "stderr": ""}),
        ) as mock_contents:
            response = test_client.get(
                f"/api/v2/archives/{archive_id}/contents?repository={repo.id}",
                headers=admin_headers,
            )

        assert response.status_code == 200
        mock_archives.assert_awaited_once()
        mock_contents.assert_awaited_once_with(
            repo.path,
            "archive-1",
            passphrase=None,
            remote_path=None,
            bypass_lock=False,
        )

    def test_download_file_success(self, test_client: TestClient, admin_headers, test_db, tmp_path):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)
        archive_path = tmp_path / "extract"

        async def _extract_side_effect(*args, **kwargs):
            target = archive_path / "documents" / "report.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("hello borg2")
            return {"success": True, "stderr": ""}

        with patch("app.api.v2.archives.tempfile.mkdtemp", return_value=str(archive_path)):
            with patch(
                "app.api.v2.archives.borg2.extract_archive",
                new=AsyncMock(side_effect=_extract_side_effect),
            ):
                response = test_client.get(
                    f"/api/v2/archives/download?repository={repo.id}&archive=archive-1&file_path=/documents/report.txt",
                    headers=admin_headers,
                )

        assert response.status_code == 200
        assert response.content == b"hello borg2"

    def test_download_file_returns_500_when_extract_fails(self, test_client: TestClient, admin_headers, test_db, tmp_path):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)

        with patch("app.api.v2.archives.tempfile.mkdtemp", return_value=str(tmp_path)):
            with patch(
                "app.api.v2.archives.borg2.extract_archive",
                new=AsyncMock(return_value={"success": False, "stderr": "extract failed"}),
            ):
                response = test_client.get(
                    f"/api/v2/archives/download?repository={repo.id}&archive=archive-1&file_path=/documents/report.txt",
                    headers=admin_headers,
                )

        assert response.status_code == 500
        assert response.json()["detail"]["key"] == "backend.errors.archives.failedExtractFile"

    def test_download_file_returns_404_when_extracted_file_is_missing(self, test_client: TestClient, admin_headers, test_db, tmp_path):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)

        with patch("app.api.v2.archives.tempfile.mkdtemp", return_value=str(tmp_path)):
            with patch(
                "app.api.v2.archives.borg2.extract_archive",
                new=AsyncMock(return_value={"success": True, "stderr": ""}),
            ):
                response = test_client.get(
                    f"/api/v2/archives/download?repository={repo.id}&archive=archive-1&file_path=/documents/missing.txt",
                    headers=admin_headers,
                )

        assert response.status_code == 404
        assert response.json()["detail"]["key"] == "backend.errors.archives.fileNotFoundAfterExtraction"

    def test_delete_archive_requires_admin(self, test_client: TestClient, auth_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)

        response = test_client.delete(
            f"/api/v2/archives/archive-1?repository={repo.id}",
            headers=auth_headers,
        )

        assert response.status_code == 403
        assert response.json()["detail"]["key"] == "backend.errors.archives.adminAccessRequired"

    def test_delete_archive_success_creates_job(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)

        with patch("app.api.v2.archives.asyncio.create_task", return_value=object()) as mock_create_task:
            response = test_client.delete(
                f"/api/v2/archives/archive-1?repository={repo.id}",
                headers=admin_headers,
            )

            scheduled = mock_create_task.call_args.args[0]
            scheduled.close()

        assert response.status_code == 200
        assert response.json()["status"] == "pending"
        job = test_db.query(DeleteArchiveJob).first()
        assert job is not None
        assert job.archive_name == "archive-1"
        assert job.repository_id == repo.id

    def test_delete_archive_rejects_duplicate_running_job(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)
        test_db.add(
            DeleteArchiveJob(
                repository_id=repo.id,
                repository_path=repo.path,
                archive_name="archive-1",
                status="running",
            )
        )
        test_db.commit()

        response = test_client.delete(
            f"/api/v2/archives/archive-1?repository={repo.id}",
            headers=admin_headers,
        )

        assert response.status_code == 409
        assert response.json()["detail"]["key"] == "backend.errors.archives.deleteAlreadyRunning"

    def test_delete_job_status_returns_logs(self, test_client: TestClient, admin_headers, test_db, tmp_path):
        _enable_borg_v2(test_db)
        log_file = tmp_path / "delete.log"
        log_file.write_text("archive deleted")
        job = DeleteArchiveJob(
            repository_id=1,
            repository_path="/tmp/v2-archive-repo",
            archive_name="archive-1",
            status="completed",
            log_file_path=str(log_file),
            has_logs=True,
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/v2/archives/delete-jobs/{job.id}",
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["logs"] == "archive deleted"
        assert body["has_logs"] is True

    def test_delete_job_status_returns_404_when_missing(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)

        response = test_client.get("/api/v2/archives/delete-jobs/9999", headers=admin_headers)

        assert response.status_code == 404
        assert response.json()["detail"]["key"] == "backend.errors.archives.deleteJobNotFound"
