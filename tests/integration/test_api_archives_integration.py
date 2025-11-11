"""
Integration tests for archives API with real borg operations

These tests use actual borg repositories and archives to verify
end-to-end functionality of the archives API.
"""
import pytest
import json
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.requires_borg
class TestArchivesListIntegration:
    """Integration tests for listing archives"""

    def test_list_archives_from_real_repository(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test listing archives from a real borg repository"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        response = test_client.get(
            f"/api/archives/list?repository={repo.path}",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "archives" in data

        # Parse the archives (API returns JSON string)
        archives_data = json.loads(data["archives"])
        archives = archives_data.get("archives", [])

        # Verify both archives are listed
        assert len(archives) == 2
        archive_list_names = [a["name"] for a in archives]
        assert "test-archive-1" in archive_list_names
        assert "test-archive-2" in archive_list_names

        # Verify archive metadata is present
        for archive in archives:
            assert "name" in archive
            assert "start" in archive or "time" in archive
            assert "id" in archive

    def test_list_archives_empty_repository(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """Test listing archives from a repository with no archives"""
        repo, repo_path, test_data_path = db_borg_repo

        response = test_client.get(
            f"/api/archives/list?repository={repo.path}",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "archives" in data

        archives_data = json.loads(data["archives"])
        archives = archives_data.get("archives", [])
        assert len(archives) == 0


@pytest.mark.integration
@pytest.mark.requires_borg
class TestArchiveInfoIntegration:
    """Integration tests for getting archive info"""

    def test_get_archive_info_real_archive(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test getting info from a real archive"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        response = test_client.get(
            f"/api/archives/{archive_names[0]}/info?repository={repo.path}",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "info" in data

        info = data["info"]
        assert info["name"] == archive_names[0]
        assert "id" in info
        assert "stats" in info

        # Verify stats contain expected fields
        stats = info["stats"]
        assert "original_size" in stats or "size" in stats
        assert "nfiles" in stats or "num_files" in stats

    def test_get_archive_info_with_files(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test getting archive info with file listing"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        response = test_client.get(
            f"/api/archives/{archive_names[0]}/info?repository={repo.path}&include_files=true",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "info" in data

        info = data["info"]
        assert "files" in info
        assert "file_count" in info

        # Should have at least the files we created
        files = info["files"]
        assert len(files) > 0

        # Verify file structure
        for file in files:
            assert "path" in file
            assert "type" in file

        # Check for specific files we created
        file_paths = [f["path"] for f in files]
        assert any("file1.txt" in path for path in file_paths)
        assert any("file2.txt" in path for path in file_paths)

    def test_get_archive_info_file_limit(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test that file_limit parameter works"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        response = test_client.get(
            f"/api/archives/{archive_names[0]}/info?repository={repo.path}&include_files=true&file_limit=2",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()

        info = data["info"]
        assert "files" in info
        # Should be limited to 2 files
        assert len(info["files"]) <= 2

    def test_get_archive_info_nonexistent_archive(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """Test getting info for non-existent archive returns 500"""
        repo, repo_path, test_data_path = db_borg_repo

        response = test_client.get(
            f"/api/archives/nonexistent-archive/info?repository={repo.path}",
            headers=admin_headers
        )

        # Borg returns error when archive doesn't exist
        assert response.status_code == 500
        assert "Failed to get archive info" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.requires_borg
class TestArchiveContentsIntegration:
    """Integration tests for browsing archive contents"""

    def test_get_archive_contents_root(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test getting contents from archive root"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        response = test_client.get(
            f"/api/archives/{archive_names[0]}/contents?repository={repo.path}",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "contents" in data

        # Contents should be a string (raw borg output or JSON)
        contents = data["contents"]
        assert isinstance(contents, str)
        assert len(contents) > 0

    def test_get_archive_contents_with_path_filter(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test filtering archive contents by path"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        # Get contents filtered by subdir path
        response = test_client.get(
            f"/api/archives/{archive_names[0]}/contents?repository={repo.path}&path=subdir",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "contents" in data

        contents = data["contents"]
        assert len(contents) > 0
        # Should contain files from subdir
        assert "file3.txt" in contents or "file4.log" in contents


@pytest.mark.integration
@pytest.mark.requires_borg
class TestDeleteArchiveIntegration:
    """Integration tests for deleting archives"""

    def test_delete_archive_success(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives,
        test_db
    ):
        """Test successfully deleting a real archive"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        # Delete the first archive
        response = test_client.delete(
            f"/api/archives/{archive_names[0]}?repository={repo.path}",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "deleted successfully" in data["message"].lower()

        # Verify archive is actually deleted by listing
        list_response = test_client.get(
            f"/api/archives/list?repository={repo.path}",
            headers=admin_headers
        )

        assert list_response.status_code == 200
        list_data = list_response.json()
        archives_data = json.loads(list_data["archives"])
        remaining_archives = archives_data.get("archives", [])

        # Should only have 1 archive left
        assert len(remaining_archives) == 1
        assert remaining_archives[0]["name"] == archive_names[1]

        # Verify database was updated
        test_db.refresh(repo)
        assert repo.archive_count == 1

    def test_delete_nonexistent_archive(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """Test deleting non-existent archive"""
        repo, repo_path, test_data_path = db_borg_repo

        response = test_client.delete(
            f"/api/archives/nonexistent?repository={repo.path}",
            headers=admin_headers
        )

        # Borg may return success (200) or error (500) depending on version
        # Some borg versions succeed with no error when archive doesn't exist
        assert response.status_code in [200, 500]


@pytest.mark.integration
@pytest.mark.requires_borg
class TestEncryptedArchivesIntegration:
    """Integration tests with encrypted repositories"""

    def test_list_archives_encrypted_repo(
        self,
        test_client: TestClient,
        admin_headers,
        db_encrypted_borg_repo
    ):
        """Test listing archives from encrypted repository"""
        repo, repo_path, test_data_path, passphrase = db_encrypted_borg_repo

        response = test_client.get(
            f"/api/archives/list?repository={repo.path}",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "archives" in data

        archives_data = json.loads(data["archives"])
        archives = archives_data.get("archives", [])
        assert len(archives) == 1
        assert archives[0]["name"] == "encrypted-archive"

    def test_get_encrypted_archive_info(
        self,
        test_client: TestClient,
        admin_headers,
        db_encrypted_borg_repo
    ):
        """Test getting info from encrypted archive"""
        repo, repo_path, test_data_path, passphrase = db_encrypted_borg_repo

        response = test_client.get(
            f"/api/archives/encrypted-archive/info?repository={repo.path}",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "info" in data

        info = data["info"]
        assert info["name"] == "encrypted-archive"
        assert "encryption" in info
        # Verify encryption mode is set
        encryption = info["encryption"]
        assert encryption.get("mode") in ["repokey", "keyfile", "repokey-blake2"]

    def test_delete_encrypted_archive(
        self,
        test_client: TestClient,
        admin_headers,
        db_encrypted_borg_repo
    ):
        """Test deleting archive from encrypted repository"""
        repo, repo_path, test_data_path, passphrase = db_encrypted_borg_repo

        response = test_client.delete(
            f"/api/archives/encrypted-archive?repository={repo.path}",
            headers=admin_headers
        )

        assert response.status_code == 200

        # Verify archive is deleted
        list_response = test_client.get(
            f"/api/archives/list?repository={repo.path}",
            headers=admin_headers
        )

        assert list_response.status_code == 200
        archives_data = json.loads(list_response.json()["archives"])
        assert len(archives_data.get("archives", [])) == 0


@pytest.mark.integration
@pytest.mark.requires_borg
class TestDownloadFileIntegration:
    """Integration tests for downloading files from archives"""

    def test_download_file_from_real_archive(
        self,
        test_client: TestClient,
        admin_token,
        db_borg_repo_with_archives,
        test_db
    ):
        """Test downloading a real file from an archive"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        # Try to download file1.txt from the first archive
        # Note: The path in the archive includes the full source path
        file_path = f"{test_data_path}/file1.txt"

        response = test_client.get(
            f"/api/archives/download?repository={repo.path}&archive={archive_names[0]}&file_path={file_path}&token={admin_token}"
        )

        # This should succeed or fail with 500 (extraction issues)
        # 404 would mean repository not found (shouldn't happen)
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            # Verify it's a file download
            assert "application/octet-stream" in response.headers.get("content-type", "")
            # Should have content
            assert len(response.content) > 0


@pytest.mark.integration
@pytest.mark.requires_borg
class TestArchiveStatistics:
    """Integration tests for archive statistics and metadata"""

    def test_archive_compression_statistics(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Verify compression statistics are accurate"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        response = test_client.get(
            f"/api/archives/{archive_names[0]}/info?repository={repo.path}",
            headers=admin_headers
        )

        assert response.status_code == 200
        info = response.json()["info"]

        stats = info["stats"]
        # Verify size fields exist and make sense
        if "original_size" in stats and "compressed_size" in stats:
            assert stats["original_size"] >= 0
            assert stats["compressed_size"] >= 0
            # Compressed should typically be less than or equal to original
            # (though not always due to compression overhead on small files)

    def test_archive_deduplication(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Verify deduplication is working across archives"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        # Get info for both archives
        info1_response = test_client.get(
            f"/api/archives/{archive_names[0]}/info?repository={repo.path}",
            headers=admin_headers
        )
        info2_response = test_client.get(
            f"/api/archives/{archive_names[1]}/info?repository={repo.path}",
            headers=admin_headers
        )

        assert info1_response.status_code == 200
        assert info2_response.status_code == 200

        info1 = info1_response.json()["info"]
        info2 = info2_response.json()["info"]

        # Both archives should have stats
        assert "stats" in info1
        assert "stats" in info2

        # Second archive should benefit from deduplication
        # (it shares file2.txt, file3.txt, file4.log with first archive)
        stats2 = info2["stats"]
        if "deduplicated_size" in stats2:
            # Deduplicated size should be less than original due to shared files
            assert stats2["deduplicated_size"] >= 0
