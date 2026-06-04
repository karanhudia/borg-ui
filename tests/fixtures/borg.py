"""
Borg fixtures for integration testing with real borg repositories
"""

import pytest
import os
from app.database.models import Repository
from tests.utils.borg import (
    create_archive,
    create_source_tree,
    init_borg_repo,
    require_borg_binary,
)


@pytest.fixture
def borg_binary():
    """Check if borg is available"""
    return require_borg_binary()


@pytest.fixture
def temp_borg_repo(tmp_path, borg_binary):
    """
    Create a temporary borg repository for testing.
    Returns a tuple of (repo_path, test_data_path)
    """
    # Create directories
    repo_path = tmp_path / "test-repo"
    test_data_path = tmp_path / "test-data"

    test_data_path.mkdir()
    init_borg_repo(borg_binary, repo_path)

    yield repo_path, test_data_path

    # Cleanup is automatic with tmp_path


@pytest.fixture
def borg_repo_with_archives(temp_borg_repo, borg_binary):
    """
    Create a borg repository with some test archives.
    Returns (repo_path, test_data_path, list_of_archive_names)
    """
    repo_path, test_data_path = temp_borg_repo

    create_source_tree(
        test_data_path,
        {
            "file1.txt": "Content of file 1",
            "file2.txt": "Content of file 2",
            "subdir/file3.txt": "Content of file 3",
            "subdir/file4.log": "Log content",
        },
    )

    # Create first archive
    archive1 = "test-archive-1"
    create_archive(borg_binary, repo_path, archive1, [test_data_path])

    # Modify files and create second archive
    (test_data_path / "file1.txt").write_text("Modified content of file 1")
    (test_data_path / "file5.txt").write_text("New file 5")

    archive2 = "test-archive-2"
    create_archive(borg_binary, repo_path, archive2, [test_data_path])

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
        repository_type="local",
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
        archive_count=len(archive_names),
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

    test_data_path.mkdir()

    passphrase = "test-passphrase-123"

    # Initialize encrypted repository
    env = os.environ.copy()
    env["BORG_PASSPHRASE"] = passphrase

    init_borg_repo(borg_binary, repo_path, env=env, encryption="repokey")

    # Create some test data
    (test_data_path / "secret.txt").write_text("Secret data")

    # Create an archive
    create_archive(
        borg_binary, repo_path, "encrypted-archive", [test_data_path], env=env
    )

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
        archive_count=1,
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)

    return repo, repo_path, test_data_path, passphrase


@pytest.fixture
def keyfile_borg_repo(tmp_path, borg_binary):
    """
    Create a keyfile-encrypted borg repository for testing.
    Returns (repo_path, test_data_path, passphrase, keyfile_path)

    This fixture is critical for testing the keyfile import bug fix.
    """
    repo_path = tmp_path / "keyfile-repo"
    test_data_path = tmp_path / "keyfile-data"
    keyfile_export_path = tmp_path / "exported-key.txt"

    test_data_path.mkdir()

    passphrase = "test-keyfile-pass-456"

    # Initialize with keyfile encryption
    env = os.environ.copy()
    env["BORG_PASSPHRASE"] = passphrase

    init_borg_repo(borg_binary, repo_path, env=env, encryption="keyfile")

    # Export the keyfile for import testing
    # This simulates a user who has an existing keyfile-encrypted repository
    from tests.utils.borg import run_borg

    result = run_borg(
        borg_binary,
        ["key", "export", str(repo_path), str(keyfile_export_path)],
        env=env,
        check=False,
    )

    if result.returncode != 0:
        pytest.fail(f"Failed to export keyfile: {result.stderr}")

    # Create test archive
    (test_data_path / "secret-file.txt").write_text("Keyfile-protected data")

    create_archive(borg_binary, repo_path, "keyfile-archive", [test_data_path], env=env)

    yield repo_path, test_data_path, passphrase, keyfile_export_path
