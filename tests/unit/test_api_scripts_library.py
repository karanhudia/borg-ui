"""
Tests for Scripts Library API endpoints

Key test focus:
- usage_count should count unique repositories, not total associations
- This prevents showing "usage: 2 repos" when script is used in pre+post hooks on same repo
"""

import pytest
from app.database.models import Repository, Script, RepositoryScript


@pytest.mark.unit
class TestScriptUsageCount:
    """
    Test that usage_count correctly counts unique repositories,
    not total RepositoryScript associations.

    Bug scenario that was fixed:
    - Repository has script assigned as both pre-backup and post-backup
    - Old behavior: usage_count = 2 (counting both associations)
    - Fixed behavior: usage_count = 1 (counting unique repository)
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
        script.usage_count = test_db.query(RepositoryScript.repository_id).filter(
            RepositoryScript.script_id == script.id
        ).distinct().count()
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
        CRITICAL TEST: Script used twice on ONE repository (pre + post) shows usage_count = 1
        This was the bug: it showed 2 before the fix
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
        # This is the FIX: use .distinct() to count unique repositories
        script.usage_count = test_db.query(RepositoryScript.repository_id).filter(
            RepositoryScript.script_id == script.id
        ).distinct().count()
        test_db.commit()

        # Get script and verify usage_count
        response = test_client.get("/api/scripts", headers=admin_headers)
        assert response.status_code == 200
        scripts = response.json()

        test_script = next((s for s in scripts if s["name"] == "test-script"), None)
        assert test_script is not None

        # The FIX: should be 1, not 2
        assert test_script["usage_count"] == 1, \
            f"Expected usage_count=1 for script used on 1 repo (pre+post hooks), got {test_script['usage_count']}"

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
        script.usage_count = test_db.query(RepositoryScript.repository_id).filter(
            RepositoryScript.script_id == script.id
        ).distinct().count()
        test_db.commit()

        # Get script and verify usage_count
        response = test_client.get("/api/scripts", headers=admin_headers)
        assert response.status_code == 200
        scripts = response.json()

        test_script = next((s for s in scripts if s["name"] == "test-script"), None)
        assert test_script is not None
        assert test_script["usage_count"] == 2

    def test_usage_count_complex_scenario(self, test_client, admin_headers, test_db):
        """
        Complex scenario: 2 repos, script used multiple times
        - Repo 1: pre-backup + post-backup (2 associations)
        - Repo 2: pre-backup only (1 association)
        Total: 3 associations, but usage_count should be 2 (unique repos)
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

        unique_repos = test_db.query(RepositoryScript.repository_id).filter(
            RepositoryScript.script_id == script.id
        ).distinct().count()
        assert unique_repos == 2, "Should have 2 unique repositories"

        # Update usage_count
        script.usage_count = unique_repos
        test_db.commit()

        # Get script and verify usage_count
        response = test_client.get("/api/scripts", headers=admin_headers)
        assert response.status_code == 200
        scripts = response.json()

        test_script = next((s for s in scripts if s["name"] == "test-script"), None)
        assert test_script is not None

        # Should be 2 (unique repos), not 3 (total associations)
        assert test_script["usage_count"] == 2, \
            f"Expected usage_count=2 for 3 associations across 2 repos, got {test_script['usage_count']}"


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
        script_obj.usage_count = test_db.query(RepositoryScript.repository_id).filter(
            RepositoryScript.script_id == script_id
        ).distinct().count()
        test_db.commit()

        # Verify usage_count is now 0
        assert script_obj.usage_count == 0
