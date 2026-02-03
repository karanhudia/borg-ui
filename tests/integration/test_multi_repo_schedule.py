
import pytest
import shutil
import subprocess
import os
import asyncio
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.models import ScheduledJob, Repository, ScheduledJobRepository
from app.api.schedule import execute_multi_repo_schedule

@pytest.mark.integration
@pytest.mark.requires_borg
@pytest.mark.asyncio
async def test_multi_repo_schedule_execution_real(
    db_session: Session,
    tmp_path,
    borg_binary
):
    """
    Test execute_multi_repo_schedule with REAL borg repositories.
    This ensures that the session handling is correct throughout the entire lifecycle.
    """
    
    # --- Helper to create a repo ---
    def create_repo(name, index):
        repo_path = tmp_path / f"repo-{index}"
        data_path = tmp_path / f"data-{index}"
        repo_path.mkdir()
        data_path.mkdir()
        
        # Create a test file
        (data_path / "test.txt").write_text(f"Content for repo {index}")

        # Init borg repo
        subprocess.run(
            [borg_binary, "init", "--encryption=none", str(repo_path)],
            check=True, capture_output=True
        )
        
        # Add to DB
        repo = Repository(
            name=name,
            path=str(repo_path),
            repository_type="local",
            source_directories=f'["{str(data_path)}"]',
            encryption="none", # Important for skipping password prompt
            mode="full",
            created_at=datetime.now(timezone.utc)
        )
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)
        return repo

    # 1. Setup: Create 2 real repositories
    repo1 = create_repo("Real Repo 1", 1)
    repo2 = create_repo("Real Repo 2", 2)

    # 2. Setup: Create a scheduled job
    job = ScheduledJob(
        name="Real Multi Repo Job",
        cron_expression="* * * * *",
        enabled=True,
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    # 3. Setup: Link repositories
    link1 = ScheduledJobRepository(scheduled_job_id=job.id, repository_id=repo1.id, execution_order=0)
    link2 = ScheduledJobRepository(scheduled_job_id=job.id, repository_id=repo2.id, execution_order=1)
    db_session.add(link1)
    db_session.add(link2)
    db_session.commit()

    # 4. Execute the multi-repo schedule
    # This should succeed for BOTH repositories if the session is handled correctly.
    print("\n[TEST] Starting execution...")
    try:
        await execute_multi_repo_schedule(job, db_session)
    except Exception as e:
        print(f"\n[TEST] Execution failed with exception: {e}")
        # Failure here is expected if the bug is present (detached instance)
        # But specifically, if the session closes, the second repo lookup might fail or detached error occurs
        pass

    # 5. Verification: Check if archives exist in BOTH repos
    print("\n[TEST] Verifying archives...")
    
    def check_archive_exists(repo_path):
        result = subprocess.run(
            [borg_binary, "list", "--json", str(repo_path)],
            capture_output=True, text=True
        )
        return job.name in result.stdout

    repo1_has_backup = check_archive_exists(repo1.path)
    repo2_has_backup = check_archive_exists(repo2.path)

    print(f"[TEST] Repo 1 has backup: {repo1_has_backup}")
    print(f"[TEST] Repo 2 has backup: {repo2_has_backup}")

    assert repo1_has_backup, "Repository 1 should have a backup"
    assert repo2_has_backup, "Repository 2 should have a backup (failed due to session closure bug?)"

    # 6. Verify session usage after execution
    try:
        db_session.refresh(job)
        print(f"[TEST] Session is alive. Job name: {job.name}")
    except Exception as e:
        pytest.fail(f"Session is closed or detached: {e}")
