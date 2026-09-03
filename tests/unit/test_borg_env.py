"""The server-side Borg environment builders share the pack-cache defaults."""

import pytest
from app.core.borg2 import borg2
from app.utils.borg_env import setup_borg_env
from types import SimpleNamespace
from app.database.models import Repository, SSHConnection
from app.utils.borg_env import effective_repository_remote_path
from app.utils.ssh_utils import resolve_repository_ssh_connection


def test_effective_repository_remote_path_keeps_configured_command_without_sudo():
    repository = SimpleNamespace(
        remote_path="/opt/borg/bin/borg",
        repository_connection=SimpleNamespace(
            use_sudo=False, borg_binary_path="/usr/bin/borg"
        ),
    )

    assert effective_repository_remote_path(repository) == "/opt/borg/bin/borg"


def test_effective_repository_remote_path_runs_remote_server_as_root():
    repository = SimpleNamespace(
        remote_path="/opt/borg/bin/borg",
        repository_connection=SimpleNamespace(
            use_sudo=True, borg_binary_path="/usr/local/bin/borg"
        ),
    )

    assert (
        effective_repository_remote_path(repository) == "sudo -n -H /usr/local/bin/borg"
    )


def test_effective_repository_remote_path_quotes_the_remote_binary_path():
    repository = SimpleNamespace(
        remote_path=None,
        repository_connection=SimpleNamespace(
            use_sudo=True, borg_binary_path="/opt/Borg Backup/borg"
        ),
    )

    assert (
        effective_repository_remote_path(repository)
        == "sudo -n -H '/opt/Borg Backup/borg'"
    )


def test_effective_repository_remote_path_matches_legacy_ssh_repository_connection(
    test_db,
):
    connection = SSHConnection(
        host="backup.example",
        username="backup",
        port=2222,
        use_sudo=True,
        borg_binary_path="/usr/local/bin/borg",
    )
    repository = Repository(
        name="Legacy SSH repository",
        path="ssh://backup@backup.example:2222/./srv/borg",
        repository_type="ssh",
    )
    test_db.add_all([connection, repository])
    test_db.commit()

    assert (
        effective_repository_remote_path(repository, test_db)
        == "sudo -n -H /usr/local/bin/borg"
    )


def test_legacy_ssh_repository_requires_an_unambiguous_connection(test_db):
    repository = Repository(
        name="Ambiguous legacy SSH repository",
        path="ssh://backup@backup.example:2222/./srv/borg",
        repository_type="ssh",
    )
    test_db.add_all(
        [
            SSHConnection(host="backup.example", username="backup", port=2222),
            SSHConnection(host="backup.example", username="backup", port=2222),
            repository,
        ]
    )
    test_db.commit()

    assert resolve_repository_ssh_connection(repository, test_db) is None


@pytest.mark.unit
def test_setup_borg_env_enables_the_pack_cache_with_a_bounded_size(monkeypatch):
    """Borg 2.0.0b23's pack cache downloads each pack once instead of
    re-transferring it on every listing; borg puts it under its own cache
    directory. An empty container-level BORG_STORE_CACHE disables it.
    Borg 1 ignores both variables."""
    monkeypatch.delenv("BORG_STORE_CACHE", raising=False)
    monkeypatch.delenv("BORG_PACK_CACHE_SIZE", raising=False)

    env = setup_borg_env()

    assert env["BORG_STORE_CACHE"] == "1"
    assert env["BORG_PACK_CACHE_SIZE"] == str(2 * 1024**3)

    monkeypatch.setenv("BORG_STORE_CACHE", "")
    monkeypatch.setenv("BORG_PACK_CACHE_SIZE", "1000000")
    env = setup_borg_env()
    assert env["BORG_STORE_CACHE"] == ""
    assert env["BORG_PACK_CACHE_SIZE"] == "1000000"


@pytest.mark.unit
def test_borg2_base_env_carries_the_same_pack_cache_defaults(monkeypatch):
    monkeypatch.delenv("BORG_STORE_CACHE", raising=False)
    monkeypatch.delenv("BORG_PACK_CACHE_SIZE", raising=False)

    env = borg2._base_env()

    assert env["BORG_STORE_CACHE"] == "1"
    assert env["BORG_PACK_CACHE_SIZE"] == str(2 * 1024**3)
