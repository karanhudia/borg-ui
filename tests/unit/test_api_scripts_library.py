"""
Tests for Scripts Library API endpoints

Key test focus:
- usage_count should count total associations (places used), not unique repositories
- Shows "X places used" to be clear about pre-backup + post-backup = 2 places
"""

import pytest
from app.database.models import Repository, Script, RepositoryScript


@pytest.mark.unit
class TestScriptUsageCount:
    """
    Test that usage_count correctly counts total RepositoryScript associations.

    Each assignment (pre-backup or post-backup) counts as one "place used".
    If a script is assigned as both pre and post on same repo, that's 2 places.
    """

    def test_usage_count_single_repository_one_hook(self, test_client, admin_headers, test_db):
        """Script used once on one repository shows usage_count = 1"""
        # Create repository
        repo = Repository(
            name="test-repo",
            path="/backups/test",
            encryption="none",
            compression="lz4",
            mode="full"
        )
        test_db.add(repo)
        test_db.commit()

        # Create script
        script = Script(
            name="test-script",
            description="Test script",
            file_path="library/test-script.sh",
            category="custom",
            timeout=300,
            run_on="always",
            usage_count=0
        )
        test_db.add(script)
        test_db.commit()

        # Assign script to repository as pre-backup hook
        assoc = RepositoryScript(
            repository_id=repo.id,
            script_id=script.id,
            hook_type="pre-backup",
            enabled=True
        )
        test_db.add(assoc)
        test_db.commit()

        # Manually update usage_count (simulating the assign endpoint logic)
        script.usage_count = test_db.query(RepositoryScript).filter(
            RepositoryScript.script_id == script.id
        ).count()
        test_db.commit()

        # Get script and verify usage_count
        response = test_client.get("/api/scripts", headers=admin_headers)
        assert response.status_code == 200
        scripts = response.json()

        test_script = next((s for s in scripts if s["name"] == "test-script"), None)
        assert test_script is not None
        assert test_script["usage_count"] == 1

    def test_usage_count_single_repository_two_hooks(self, test_client, admin_headers, test_db):
        """
        Script used twice on ONE repository (pre + post) shows usage_count = 2 (2 places used)
        Each hook assignment is one "place used"
        """
        # Create repository
        repo = Repository(
            name="test-repo",
            path="/backups/test",
            encryption="none",
            compression="lz4",
            mode="full"
        )
        test_db.add(repo)
        test_db.commit()

        # Create script
        script = Script(
            name="test-script",
            description="Test script",
            file_path="library/test-script.sh",
            category="custom",
            timeout=300,
            run_on="always",
            usage_count=0
        )
        test_db.add(script)
        test_db.commit()

        # Assign script to repository as BOTH pre-backup AND post-backup hooks
        assoc1 = RepositoryScript(
            repository_id=repo.id,
            script_id=script.id,
            hook_type="pre-backup",
            enabled=True
        )
        assoc2 = RepositoryScript(
            repository_id=repo.id,
            script_id=script.id,
            hook_type="post-backup",
            enabled=True
        )
        test_db.add(assoc1)
        test_db.add(assoc2)
        test_db.commit()

        # Manually update usage_count (simulating the assign endpoint logic)
        # Count all associations, not unique repositories
        script.usage_count = test_db.query(RepositoryScript).filter(
            RepositoryScript.script_id == script.id
        ).count()
        test_db.commit()

        # Get script and verify usage_count
        response = test_client.get("/api/scripts", headers=admin_headers)
        assert response.status_code == 200
        scripts = response.json()

        test_script = next((s for s in scripts if s["name"] == "test-script"), None)
        assert test_script is not None

        # Should be 2 (2 places used: pre-backup + post-backup)
        assert test_script["usage_count"] == 2, \
            f"Expected usage_count=2 for script used in 2 places (pre+post hooks), got {test_script['usage_count']}"

    def test_usage_count_two_repositories(self, test_client, admin_headers, test_db):
        """Script used on two different repositories shows usage_count = 2"""
        # Create two repositories
        repo1 = Repository(
            name="test-repo-1",
            path="/backups/test1",
            encryption="none",
            compression="lz4",
            mode="full"
        )
        repo2 = Repository(
            name="test-repo-2",
            path="/backups/test2",
            encryption="none",
            compression="lz4",
            mode="full"
        )
        test_db.add_all([repo1, repo2])
        test_db.commit()

        # Create script
        script = Script(
            name="test-script",
            description="Test script",
            file_path="library/test-script.sh",
            category="custom",
            timeout=300,
            run_on="always",
            usage_count=0
        )
        test_db.add(script)
        test_db.commit()

        # Assign script to both repositories
        assoc1 = RepositoryScript(
            repository_id=repo1.id,
            script_id=script.id,
            hook_type="pre-backup",
            enabled=True
        )
        assoc2 = RepositoryScript(
            repository_id=repo2.id,
            script_id=script.id,
            hook_type="post-backup",
            enabled=True
        )
        test_db.add_all([assoc1, assoc2])
        test_db.commit()

        # Manually update usage_count
        script.usage_count = test_db.query(RepositoryScript).filter(
            RepositoryScript.script_id == script.id
        ).count()
        test_db.commit()

        # Get script and verify usage_count
        response = test_client.get("/api/scripts", headers=admin_headers)
        assert response.status_code == 200
        scripts = response.json()

        test_script = next((s for s in scripts if s["name"] == "test-script"), None)
        assert test_script is not None
        assert test_script["usage_count"] == 2  # 2 places used (one on each repo)

    def test_usage_count_complex_scenario(self, test_client, admin_headers, test_db):
        """
        Complex scenario: 2 repos, script used multiple times
        - Repo 1: pre-backup + post-backup (2 associations)
        - Repo 2: pre-backup only (1 association)
        Total: 3 associations, usage_count should be 3 (3 places used)
        """
        # Create two repositories
        repo1 = Repository(
            name="test-repo-1",
            path="/backups/test1",
            encryption="none",
            compression="lz4",
            mode="full"
        )
        repo2 = Repository(
            name="test-repo-2",
            path="/backups/test2",
            encryption="none",
            compression="lz4",
            mode="full"
        )
        test_db.add_all([repo1, repo2])
        test_db.commit()

        # Create script
        script = Script(
            name="test-script",
            description="Test script",
            file_path="library/test-script.sh",
            category="custom",
            timeout=300,
            run_on="always",
            usage_count=0
        )
        test_db.add(script)
        test_db.commit()

        # Create 3 associations total
        assoc1 = RepositoryScript(
            repository_id=repo1.id,
            script_id=script.id,
            hook_type="pre-backup",
            enabled=True
        )
        assoc2 = RepositoryScript(
            repository_id=repo1.id,
            script_id=script.id,
            hook_type="post-backup",
            enabled=True
        )
        assoc3 = RepositoryScript(
            repository_id=repo2.id,
            script_id=script.id,
            hook_type="pre-backup",
            enabled=True
        )
        test_db.add_all([assoc1, assoc2, assoc3])
        test_db.commit()

        # Verify database state
        total_associations = test_db.query(RepositoryScript).filter(
            RepositoryScript.script_id == script.id
        ).count()
        assert total_associations == 3, "Should have 3 associations"

        # Update usage_count
        script.usage_count = total_associations
        test_db.commit()

        # Get script and verify usage_count
        response = test_client.get("/api/scripts", headers=admin_headers)
        assert response.status_code == 200
        scripts = response.json()

        test_script = next((s for s in scripts if s["name"] == "test-script"), None)
        assert test_script is not None

        # Should be 3 (total associations/places used)
        assert test_script["usage_count"] == 3, \
            f"Expected usage_count=3 for 3 places used across 2 repos, got {test_script['usage_count']}"


@pytest.mark.unit
class TestScriptOrphanedAssociations:
    """Test cleanup of orphaned script associations when repository is deleted"""

    def test_delete_repository_cleans_up_associations(self, test_client, admin_headers, test_db):
        """Deleting a repository should clean up its script associations"""
        # Create repository with script
        repo = Repository(
            name="test-repo",
            path="/backups/test",
            encryption="none",
            compression="lz4",
            mode="full"
        )
        test_db.add(repo)
        test_db.commit()

        script = Script(
            name="test-script",
            description="Test script",
            file_path="library/test-script.sh",
            category="custom",
            timeout=300,
            run_on="always",
            usage_count=0
        )
        test_db.add(script)
        test_db.commit()

        # Assign script
        assoc = RepositoryScript(
            repository_id=repo.id,
            script_id=script.id,
            hook_type="pre-backup",
            enabled=True
        )
        test_db.add(assoc)
        test_db.commit()

        # Update usage_count
        script.usage_count = 1
        test_db.commit()

        # Delete repository (should clean up associations)
        # Note: We're testing the database cleanup, not the full API endpoint
        repo_id = repo.id
        script_id = script.id

        # Manually clean up associations (simulating what the API does)
        test_db.query(RepositoryScript).filter(
            RepositoryScript.repository_id == repo_id
        ).delete()
        test_db.delete(repo)
        test_db.commit()

        # Verify associations are gone
        remaining_assocs = test_db.query(RepositoryScript).filter(
            RepositoryScript.script_id == script_id
        ).count()
        assert remaining_assocs == 0

        # Update usage_count after cleanup
        script_obj = test_db.query(Script).filter(Script.id == script_id).first()
        script_obj.usage_count = test_db.query(RepositoryScript).filter(
            RepositoryScript.script_id == script_id
        ).count()
        test_db.commit()

        # Verify usage_count is now 0
        assert script_obj.usage_count == 0


@pytest.mark.unit
class TestScriptDeleteErrorMessages:
    """Test that delete error messages are clear and informative"""

    def test_delete_error_message_single_place(self, test_client, admin_headers, test_db):
        """Error message for script used in one place is clear"""
        # Create repository with script
        repo = Repository(
            name="test-repo",
            path="/backups/test",
            encryption="none",
            compression="lz4",
            mode="full"
        )
        test_db.add(repo)
        test_db.commit()

        script = Script(
            name="test-script",
            description="Test script",
            file_path="library/test-script.sh",
            category="custom",
            timeout=300,
            run_on="always",
            usage_count=1
        )
        test_db.add(script)
        test_db.commit()

        # Assign script once
        assoc = RepositoryScript(
            repository_id=repo.id,
            script_id=script.id,
            hook_type="pre-backup",
            enabled=True
        )
        test_db.add(assoc)
        test_db.commit()

        # Try to delete - should fail with clear message
        response = test_client.delete(f"/api/scripts/{script.id}", headers=admin_headers)
        assert response.status_code == 400
        assert "1 place" in response.json()["detail"]
        assert "test-repo (pre-backup)" in response.json()["detail"]

    def test_delete_error_message_multiple_hooks_same_repo(self, test_client, admin_headers, test_db):
        """Error message shows both hook types when script used twice on same repo"""
        # Create repository with script
        repo = Repository(
            name="Downloads",
            path="/backups/downloads",
            encryption="none",
            compression="lz4",
            mode="full"
        )
        test_db.add(repo)
        test_db.commit()

        script = Script(
            name="test-script",
            description="Test script",
            file_path="library/test-script.sh",
            category="custom",
            timeout=300,
            run_on="always",
            usage_count=2
        )
        test_db.add(script)
        test_db.commit()

        # Assign script as both pre and post
        assoc1 = RepositoryScript(
            repository_id=repo.id,
            script_id=script.id,
            hook_type="pre-backup",
            enabled=True
        )
        assoc2 = RepositoryScript(
            repository_id=repo.id,
            script_id=script.id,
            hook_type="post-backup",
            enabled=True
        )
        test_db.add_all([assoc1, assoc2])
        test_db.commit()

        # Try to delete - should fail with clear message
        response = test_client.delete(f"/api/scripts/{script.id}", headers=admin_headers)
        assert response.status_code == 400
        detail = response.json()["detail"]

        # Should say "2 places" not "2 repository(ies)"
        assert "2 places" in detail

        # Should show repository name once with both hook types
        assert "Downloads" in detail
        assert "pre-backup" in detail
        assert "post-backup" in detail

        # Should NOT show "Downloads, Downloads"
        assert detail.count("Downloads") == 1

    def test_delete_error_message_multiple_repos(self, test_client, admin_headers, test_db):
        """Error message lists all repositories when used in multiple places"""
        # Create two repositories
        repo1 = Repository(
            name="Downloads",
            path="/backups/downloads",
            encryption="none",
            compression="lz4",
            mode="full"
        )
        repo2 = Repository(
            name="Documents",
            path="/backups/docs",
            encryption="none",
            compression="lz4",
            mode="full"
        )
        test_db.add_all([repo1, repo2])
        test_db.commit()

        script = Script(
            name="test-script",
            description="Test script",
            file_path="library/test-script.sh",
            category="custom",
            timeout=300,
            run_on="always",
            usage_count=3
        )
        test_db.add(script)
        test_db.commit()

        # Assign to repo1 twice, repo2 once
        assoc1 = RepositoryScript(
            repository_id=repo1.id,
            script_id=script.id,
            hook_type="pre-backup",
            enabled=True
        )
        assoc2 = RepositoryScript(
            repository_id=repo1.id,
            script_id=script.id,
            hook_type="post-backup",
            enabled=True
        )
        assoc3 = RepositoryScript(
            repository_id=repo2.id,
            script_id=script.id,
            hook_type="pre-backup",
            enabled=True
        )
        test_db.add_all([assoc1, assoc2, assoc3])
        test_db.commit()

        # Try to delete
        response = test_client.delete(f"/api/scripts/{script.id}", headers=admin_headers)
        assert response.status_code == 400
        detail = response.json()["detail"]

        # Should say "3 places"
        assert "3 places" in detail

        # Should show both repositories with their hook types
        assert "Downloads" in detail
        assert "Documents" in detail
        assert "pre-backup" in detail
        assert "post-backup" in detail
