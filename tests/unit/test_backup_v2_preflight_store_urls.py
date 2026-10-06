"""The Borg 2 backup preflight checks only what the server reaches as a directory.

Before a backup the server checks that a repository on its file system exists.
A server Borg 2 repository can also live behind a URL Borg 2 opens itself
(sftp://, s3:, b2:, http(s)://, rclone:, ssh://); such a URL is no directory
on the server and must not fail that check.
"""

import json
from types import SimpleNamespace

import pytest

from app.core.borg2 import REMOVED_REPOSITORY_URL_MESSAGE
from app.core.borg_router import BorgRouter

STORE_URLS = [
    "sftp://borg@backup.example.com/srv/repo",
    "SFTP://borg@backup.example.com/srv/repo",
    "s3:profile@/bucket/repo",
    "b2:bucket/repo",
    "http://backup.example.com:8080/repo",
    "https://backup.example.com/repo",
    "rclone:remote:repo",
    "ssh://borg@backup.example.com/./repo",
]


def _router(path: str) -> BorgRouter:
    return BorgRouter(
        SimpleNamespace(
            id=1,
            path=path,
            borg_version=2,
            executor_type="server",
            execution_target="local",
        )
    )


@pytest.mark.unit
@pytest.mark.parametrize("path", STORE_URLS)
def test_store_url_passes_the_preflight(path):
    _router(path).validate_local_repository_access()


@pytest.mark.unit
def test_rest_url_gets_the_borg2_answer():
    """Borg 2.0.0b25 reads rest:// as a local directory; the preflight says
    that rather than "directory does not exist"."""
    with pytest.raises(ValueError) as raised:
        _router(
            "rest://borg@backup.example.com/srv/repo"
        ).validate_local_repository_access()

    assert str(raised.value) == REMOVED_REPOSITORY_URL_MESSAGE


@pytest.mark.unit
def test_missing_local_directory_still_fails(tmp_path):
    path = str(tmp_path / "missing")

    with pytest.raises(ValueError) as raised:
        _router(path).validate_local_repository_access()

    assert json.loads(str(raised.value)) == {
        "key": "backend.errors.repo.repositoryDirNotExist",
        "params": {"path": path},
    }


@pytest.mark.unit
def test_existing_local_directory_passes(tmp_path):
    _router(str(tmp_path)).validate_local_repository_access()
