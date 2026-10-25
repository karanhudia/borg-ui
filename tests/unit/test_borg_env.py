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
    """Borg 2's pack cache downloads each pack once instead of
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


@pytest.mark.unit
def test_setup_borg_env_asks_borg_for_modern_exit_codes(monkeypatch):
    """Borg 2 uses the modern codes by default; Borg 1.4 needs the variable.
    Without it the same failure reports a specific code from a backup and a
    bare legacy 2 from every other path. An operator can still pin legacy."""
    monkeypatch.delenv("BORG_EXIT_CODES", raising=False)

    assert setup_borg_env()["BORG_EXIT_CODES"] == "modern"

    monkeypatch.setenv("BORG_EXIT_CODES", "legacy")
    assert setup_borg_env()["BORG_EXIT_CODES"] == "legacy"


@pytest.mark.unit
def test_borg1_exec_env_asks_for_modern_exit_codes(monkeypatch):
    """The Borg 1 wrapper builds its own environment, so it needs the same
    default; otherwise the vocabulary depends on which path ran borg."""
    from app.core.borg import borg

    monkeypatch.delenv("BORG_EXIT_CODES", raising=False)

    assert borg._build_exec_env()["BORG_EXIT_CODES"] == "modern"

    monkeypatch.setenv("BORG_EXIT_CODES", "legacy")
    assert borg._build_exec_env()["BORG_EXIT_CODES"] == "legacy"


@pytest.mark.unit
def test_borg1_argv_carries_the_env_lock_wait():
    """Borg 1.4 never reads BORG_LOCK_WAIT (its --lock-wait defaults to 1s),
    so the env value has to reach it as the common option (#1216)."""
    from app.utils.borg_env import with_lock_wait

    env = {"BORG_LOCK_WAIT": "180"}

    assert with_lock_wait(["borg", "prune", "repo"], env) == [
        "borg",
        "--lock-wait",
        "180",
        "prune",
        "repo",
    ]
    # Borg 2 reads the variable itself; a caller's explicit flag wins.
    assert with_lock_wait(["borg2", "prune"], env) == ["borg2", "prune"]
    assert with_lock_wait(["borg", "info", "--lock-wait", "5"], env) == [
        "borg",
        "info",
        "--lock-wait",
        "5",
    ]
    assert with_lock_wait(["borg", "info"], {}) == ["borg", "info"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_borg1_interface_runs_borg_with_its_lock_wait(monkeypatch):
    from app.core import borg as borg_module

    seen = {}

    class _Process:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_exec(*cmd, **kwargs):
        seen["cmd"] = list(cmd)
        return _Process()

    monkeypatch.setattr(borg_module.asyncio, "create_subprocess_exec", fake_exec)

    await borg_module.borg._execute_command(["borg", "list", "repo"])

    assert seen["cmd"][:3] == ["borg", "--lock-wait", "20"]


@pytest.mark.parametrize("builder", ["repository", "ssh_key"])
def test_env_builders_remove_the_key_file_when_building_fails(
    builder, tmp_path, monkeypatch
):
    """The caller removes the temporary SSH key only once it has the env, so a
    builder that fails after writing the key removes it itself."""
    from app.utils import borg_env

    key_file = tmp_path / "ssh-key"
    key_file.write_text("private-key\n")

    def fail(**kwargs):
        raise RuntimeError("env setup failed")

    monkeypatch.setattr(borg_env, "setup_borg_env", fail)
    with pytest.raises(RuntimeError, match="env setup failed"):
        if builder == "repository":
            monkeypatch.setattr(
                borg_env, "resolve_repo_ssh_key_file", lambda repo, db: str(key_file)
            )
            borg_env.build_repository_borg_env(
                SimpleNamespace(path="ssh://borg@example.com/repo"), None
            )
        else:
            monkeypatch.setattr(
                borg_env,
                "resolve_ssh_key_file_by_id",
                lambda key_id, db=None: str(key_file),
            )
            borg_env.build_ssh_key_borg_env(
                path="ssh://borg@example.com/repo", ssh_key_id=1
            )

    assert not key_file.exists()
