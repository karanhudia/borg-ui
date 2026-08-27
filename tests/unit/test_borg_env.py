from types import SimpleNamespace

from app.database.models import Repository, SSHConnection
from app.utils.borg_env import effective_repository_remote_path


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
