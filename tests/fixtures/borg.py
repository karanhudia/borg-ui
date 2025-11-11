"""
Borg fixtures for integration testing with real borg repositories
"""
import pytest
import subprocess
import tempfile
import shutil
import os
from pathlib import Path
from app.database.models import Repository


@pytest.fixture
def borg_binary():
    """Check if borg is available"""
    borg_path = shutil.which("borg")
    if not borg_path:
        pytest.skip("Borg binary not found. Install borgbackup to run integration tests.")
    return borg_path


@pytest.fixture
def temp_borg_repo(tmp_path, borg_binary):
    """
    Create a temporary borg repository for testing.
    Returns a tuple of (repo_path, test_data_path)
    """
    # Create directories
    repo_path = tmp_path / "test-repo"
    test_data_path = tmp_path / "test-data"

    repo_path.mkdir()
    test_data_path.mkdir()

    # Initialize borg repository (unencrypted for simplicity in tests)
    result = subprocess.run(
        [borg_binary, "init", "--encryption=none", str(repo_path)],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        pytest.fail(f"Failed to initialize borg repository: {result.stderr}")

    yield repo_path, test_data_path

    # Cleanup is automatic with tmp_path


@pytest.fixture
def borg_repo_with_archives(temp_borg_repo, borg_binary):
    """
    Create a borg repository with some test archives.
    Returns (repo_path, test_data_path, list_of_archive_names)
    """
    repo_path, test_data_path = temp_borg_repo

    # Create test files
    (test_data_path / "file1.txt").write_text("Content of file 1")
    (test_data_path / "file2.txt").write_text("Content of file 2")

    subdir = test_data_path / "subdir"
    subdir.mkdir()
    (subdir / "file3.txt").write_text("Content of file 3")
    (subdir / "file4.log").write_text("Log content")

    # Create first archive
    archive1 = "test-archive-1"
    result = subprocess.run(
        [
            borg_binary, "create",
            f"{repo_path}::{archive1}",
            str(test_data_path)
        ],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        pytest.fail(f"Failed to create archive 1: {result.stderr}")

    # Modify files and create second archive
    (test_data_path / "file1.txt").write_text("Modified content of file 1")
    (test_data_path / "file5.txt").write_text("New file 5")

    archive2 = "test-archive-2"
    result = subprocess.run(
        [
            borg_binary, "create",
            f"{repo_path}::{archive2}",
            str(test_data_path)
        ],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        pytest.fail(f"Failed to create archive 2: {result.stderr}")

    return repo_path, test_data_path, [archive1, archive2]


@pytest.fixture
def db_borg_repo(test_db, temp_borg_repo):
    """
    Create a borg repository and register it in the database.
    Returns both the Repository model and the paths.
    """
    repo_path, test_data_path = temp_borg_repo

    # Create repository in database
    repo = Repository(
        name="Test Integration Repo",
        path=str(repo_path),
        encryption="none",
        compression="lz4",
        repository_type="local"
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)

    return repo, repo_path, test_data_path


@pytest.fixture
def db_borg_repo_with_archives(test_db, borg_repo_with_archives):
    """
    Create a borg repository with archives and register it in the database.
    Returns (Repository model, repo_path, test_data_path, archive_names)
    """
    repo_path, test_data_path, archive_names = borg_repo_with_archives

    # Create repository in database
    repo = Repository(
        name="Test Integration Repo with Archives",
        path=str(repo_path),
        encryption="none",
        compression="lz4",
        repository_type="local",
        archive_count=len(archive_names)
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)

    return repo, repo_path, test_data_path, archive_names


@pytest.fixture
def encrypted_borg_repo(tmp_path, borg_binary):
    """
    Create an encrypted borg repository for testing.
    Returns (repo_path, test_data_path, passphrase)
    """
    repo_path = tmp_path / "encrypted-repo"
    test_data_path = tmp_path / "encrypted-data"

    repo_path.mkdir()
    test_data_path.mkdir()

    passphrase = "test-passphrase-123"

    # Initialize encrypted repository
    env = os.environ.copy()
    env["BORG_PASSPHRASE"] = passphrase

    result = subprocess.run(
        [borg_binary, "init", "--encryption=repokey", str(repo_path)],
        capture_output=True,
        text=True,
        env=env
    )

    if result.returncode != 0:
        pytest.fail(f"Failed to initialize encrypted repository: {result.stderr}")

    # Create some test data
    (test_data_path / "secret.txt").write_text("Secret data")

    # Create an archive
    result = subprocess.run(
        [
            borg_binary, "create",
            f"{repo_path}::encrypted-archive",
            str(test_data_path)
        ],
        capture_output=True,
        text=True,
        env=env
    )

    if result.returncode != 0:
        pytest.fail(f"Failed to create encrypted archive: {result.stderr}")

    yield repo_path, test_data_path, passphrase


@pytest.fixture
def db_encrypted_borg_repo(test_db, encrypted_borg_repo):
    """
    Create an encrypted borg repository and register it in the database.
    """
    repo_path, test_data_path, passphrase = encrypted_borg_repo

    repo = Repository(
        name="Test Encrypted Repo",
        path=str(repo_path),
        encryption="repokey",
        passphrase=passphrase,
        compression="lz4",
        repository_type="local",
        archive_count=1
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)

    return repo, repo_path, test_data_path, passphrase
