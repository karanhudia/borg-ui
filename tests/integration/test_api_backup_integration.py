import pytest
import json
from fastapi.testclient import TestClient
from app.services.backup_service import backup_service

@pytest.mark.integration
@pytest.mark.requires_borg
@pytest.mark.asyncio
class TestBackupCreationIntegration:
    """Integration tests for backup creation"""

    async def test_create_backup_dry_run(self):
        """
        Test that dry-run is not yet supported/exposed via this API 
        or verify existing behavior
        """
        pass

    async def test_create_backup_success(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        test_db
    ):
        """Test real backup creation"""
        repo, repo_path, test_data_path = db_borg_repo
        
        # Update repository source directories in DB
        repo.source_directories = json.dumps([str(test_data_path)])
        repo.compression = "lz4"
        test_db.commit()
        
        # Trigger backup via API (creates the job record)
        response = test_client.post(
            "/api/backup/start",
            json={
                "repository": str(repo_path)
            },
            headers=admin_headers
        )
        
        assert response.status_code in [200, 201, 202]
        job_id = response.json()["job_id"]
        
        # Wait for background task to complete (polling)
        import asyncio
        max_retries = 20
        for _ in range(max_retries):
            # Check status
            job_response = test_client.get(f"/api/backup/status/{job_id}", headers=admin_headers)
            job_data = job_response.json()
            
            if job_data["status"] in ["completed", "completed_with_warnings", "failed"]:
                break
                
            # Allow background task to progress
            await asyncio.sleep(0.2)
            
        assert job_data["status"] == "completed"
        
        # Verify archive exists
        list_response = test_client.get(
            f"/api/archives/list?repository={str(repo_path)}",
            headers=admin_headers
        )
        assert list_response.status_code == 200
        archives_json = list_response.json().get("archives", "{}")
        assert "manual-backup" in archives_json
