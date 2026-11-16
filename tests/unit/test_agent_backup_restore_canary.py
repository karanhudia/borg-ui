"""#1534: a managed agent's backup carries the managed restore canary.

Borg runs on the agent's host, so the server sends the canary files with the
backup job and the agent archives them under the path the restore check
extracts. An agent that does not advertise `backup.restore_canary` gets the
job without them.
"""

import base64
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.borg_ui_agent.backup import (
    RESTORE_CANARY_CAPABILITY as AGENT_RESTORE_CANARY_CAPABILITY,
    BackupCreatePayload,
    execute_backup_create_job,
)
from agent.borg_ui_agent.repository_ops import _verify_canary
from agent.borg_ui_agent.runtime import get_capabilities
from app.database.models import Operation, Repository
from app.services.operations.backup_facade import BackupJobFacade
from app.services.repository_executor import (
    RESTORE_CANARY_CAPABILITY,
    agent_stages_restore_canary,
    build_agent_backup_payload,
    queue_agent_backup_job,
)
from app.services.restore_check_canary import (
    CANARY_MANIFEST,
    agent_restore_canary_payload,
    get_restore_canary_archive_paths,
    verify_restored_canary,
)
from tests.unit.test_agent_repository_server_borg import _agent, _repo
from tests.unit.test_agent_runtime import BackupClient, FakeProcess

CANARY_SOURCE = ".borg-ui/restore-canaries/repository-42/.borgui-canary"


def _repository(**overrides):
    values = {
        "id": 42,
        "name": "Agent repository",
        "path": "/agent/repo",
        "borg_version": 1,
        "compression": "lz4",
        "source_directories": json.dumps(["/data"]),
        "restore_check_canary_enabled": True,
    }
    return Repository(**{**values, **overrides})


def _write(root: Path, files: dict[str, str]) -> None:
    for path, content in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(content))


# -- server: what the job carries ---------------------------------------------


@pytest.mark.unit
def test_the_capability_name_is_the_same_on_both_sides():
    assert RESTORE_CANARY_CAPABILITY == AGENT_RESTORE_CANARY_CAPABILITY
    assert RESTORE_CANARY_CAPABILITY in get_capabilities()


@pytest.mark.unit
def test_the_canary_payload_restores_to_what_the_restore_check_verifies(tmp_path):
    repository = _repository()

    canary = agent_restore_canary_payload(repository)

    assert canary["source_path"] == CANARY_SOURCE
    assert [canary["source_path"]] == get_restore_canary_archive_paths(repository)
    assert all(path.startswith(f"{CANARY_SOURCE}/") for path in canary["files"])
    _write(tmp_path, canary["files"])
    verified = [
        ".borgui-canary/README.txt",
        ".borgui-canary/nested/check.json",
        ".borgui-canary/binary/check.bin",
    ]
    # the server's own check, and the agent's, which a restore check runs
    assert (
        verify_restored_canary(repository, str(tmp_path))["verified_files"] == verified
    )
    assert _verify_canary(
        str(tmp_path),
        {"manifest_candidates": [f"{CANARY_SOURCE}/{CANARY_MANIFEST}"]},
    ) == {"status": "verified", "verified_files": verified}


@pytest.mark.unit
@pytest.mark.parametrize(
    "settings",
    [
        {"restore_check_canary_enabled": False},
        {"restore_check_full_archive": True},
        {"restore_check_paths": json.dumps(["etc/hosts"])},
    ],
)
def test_no_canary_payload_outside_canary_mode(settings):
    repository = _repository(**settings)

    assert agent_restore_canary_payload(repository) is None
    payload = build_agent_backup_payload(
        repository, "daily", include_restore_canary=True
    )
    assert "restore_canary" not in payload["backup"]


@pytest.mark.unit
def test_the_backup_payload_carries_the_canary_only_when_asked():
    repository = _repository()

    with_canary = build_agent_backup_payload(
        repository, "daily", include_restore_canary=True
    )
    without = build_agent_backup_payload(repository, "daily")

    assert with_canary["backup"]["restore_canary"] == agent_restore_canary_payload(
        repository
    )
    # the canary is not one of the user's sources
    assert with_canary["backup"]["source_paths"] == ["/data"]
    assert "restore_canary" not in without["backup"]


def _queued_backup(test_client, admin_headers, test_db, repo):
    response = test_client.post(
        "/api/backup/start", json={"repository": repo.path}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    operation = test_db.get(Operation, response.json()["job_id"])
    return queue_agent_backup_job(test_db, BackupJobFacade(test_db, operation), repo)


@pytest.mark.unit
def test_an_agent_that_stages_the_canary_gets_it(test_client, admin_headers, test_db):
    agent = _agent(test_db)
    agent.capabilities = [*agent.capabilities, RESTORE_CANARY_CAPABILITY]
    test_db.commit()
    repo = _repo(test_db, agent, borg_version=1, restore_check_canary_enabled=True)

    agent_job = _queued_backup(test_client, admin_headers, test_db, repo)

    canary = agent_job.payload["backup"]["restore_canary"]
    assert canary == agent_restore_canary_payload(repo)
    assert agent_job.payload["backup"]["source_paths"] == ["/data"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "borg1, borg_version, stages",
    [
        ("1.4.5", 1, True),
        ("1.4.0", 1, True),
        ("2.0.0b25", 1, True),  # not a Borg 1 version: the agent decides
        ("", 1, True),
        ("1.2.8", 1, False),
        ("1.1.18", 1, False),
        ("1.2.8", 2, True),  # a Borg 2 repository does not run that Borg 1
    ],
)
def test_borg1_before_1_4_cannot_archive_the_staged_canary(borg1, borg_version, stages):
    """The agent hands the canary to Borg as `<staging>/./<path>`, which
    Borg 1 reads from 1.4 on."""
    agent = SimpleNamespace(
        capabilities=[RESTORE_CANARY_CAPABILITY],
        borg_versions=[
            {"major": 1, "version": borg1},
            {"major": 2, "version": "2.0.0b25"},
        ],
    )
    repository = _repository(borg_version=borg_version)

    assert agent_stages_restore_canary(agent, repository) is stages
    assert agent_stages_restore_canary(None, repository) is False
    agent.capabilities = []
    assert agent_stages_restore_canary(agent, repository) is False


@pytest.mark.unit
def test_an_older_agent_gets_the_backup_job_it_always_got(
    test_client, admin_headers, test_db
):
    """An agent before `backup.restore_canary` ignores the key; it is not
    sent, so the job is what that agent's server has always queued."""
    repo = _repo(
        test_db, _agent(test_db), borg_version=1, restore_check_canary_enabled=True
    )

    agent_job = _queued_backup(test_client, admin_headers, test_db, repo)

    assert set(agent_job.payload["backup"]) == {
        "archive_name",
        "source_paths",
        "compression",
        "exclude_patterns",
        "custom_flags",
    }


# -- agent: staging and archiving ---------------------------------------------


def _job_payload(canary=None, borg_version=1, **backup):
    backup = {"archive_name": "archive", "source_paths": ["/src"], **backup}
    if canary is not None:
        backup["restore_canary"] = canary
    return {
        "job_kind": "backup.create",
        "repository": {
            "path": "/repo" if borg_version == 1 else "ssh://borg@host/repo",
            "borg_version": borg_version,
        },
        "backup": backup,
    }


def _canary():
    return agent_restore_canary_payload(_repository())


class _Borg:
    """Stands in for `borg create` and looks at what it was started with."""

    def __init__(self):
        self.cmd = None
        self.kwargs = None
        self.staged = {}
        self.sources_are_files = []

    def __call__(self, cmd, **kwargs):
        self.cmd = cmd
        self.kwargs = kwargs
        root, sep, _path = cmd[-1].partition("/./")
        if sep:
            self.sources_are_files = [
                os.path.isfile(arg) for arg in cmd if arg.startswith(f"{root}/./")
            ]
            self.staged = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in Path(root).rglob("*")
                if path.is_file()
            }
        return FakeProcess([], 0)

    @property
    def staging_root(self):
        root, sep, _path = self.cmd[-1].partition("/./")
        return root if sep else None


def _canary_sources(borg):
    """The sources that name the staged canary."""
    return [arg for arg in borg.cmd if arg.startswith(f"{borg.staging_root}/./")]


def _without_canary(borg):
    """The command as it would be without the staged canary's arguments."""
    include = f"--pattern=+pp:{borg.staging_root}"
    assert borg.cmd.count(include) == 1
    sources = _canary_sources(borg)
    assert borg.cmd[-len(sources) :] == sources
    return [arg for arg in borg.cmd[: -len(sources)] if arg != include]


def _borg_version(monkeypatch, output):
    """What `borg --version` prints on this agent's host."""

    def run(cmd, **kwargs):
        assert cmd[1:] == ["--version"]
        if isinstance(output, BaseException):
            raise output
        return SimpleNamespace(stdout=output, stderr="")

    monkeypatch.setattr("agent.borg_ui_agent.backup.subprocess.run", run)


def _run(monkeypatch, payload, borg_version="borg 1.4.5\n"):
    _borg_version(monkeypatch, borg_version)
    borg = _Borg()
    monkeypatch.setattr("agent.borg_ui_agent.backup.subprocess.Popen", borg)
    client = BackupClient()
    result = execute_backup_create_job({"id": 7, "payload": payload}, client)
    return borg, client, result


def _log_lines(client):
    return [call[4] for call in client.calls if call[0] == "send_log"]


@pytest.mark.unit
def test_a_job_without_the_canary_parses_as_before():
    payload = BackupCreatePayload.from_job_payload(_job_payload())

    assert payload.restore_canary is None
    assert payload.build_command()[-1] == "/src"


@pytest.mark.unit
@pytest.mark.parametrize("borg_version", [1, 2])
def test_the_agent_archives_the_canary_under_its_relative_path(
    monkeypatch, borg_version
):
    canary = _canary()
    plain, _client, _result = _run(monkeypatch, _job_payload(borg_version=borg_version))

    borg, client, result = _run(
        monkeypatch,
        _job_payload(canary, borg_version=borg_version),
        # a Borg 2 is not asked: every one the agent runs reads `/./`
        borg_version=OSError("not asked") if borg_version == 2 else "borg 1.4.5\n",
    )

    assert result.status == "completed"
    # the canary's files are the last sources: `/./` ends the part of the
    # path Borg leaves out of the archive
    assert _canary_sources(borg) == [
        f"{borg.staging_root}/./{path}" for path in canary["files"]
    ]
    assert all(path.startswith(f"{CANARY_SOURCE}/") for path in canary["files"])
    assert os.path.isabs(borg.staging_root)
    # the rest is the command without the canary, plus the include that
    # keeps the staging directory out of reach of the user's excludes
    assert _without_canary(borg) == plain.cmd
    # ... and Borg runs where it always ran
    assert borg.kwargs == plain.kwargs
    assert borg.staged == {
        path: base64.b64decode(content) for path, content in canary["files"].items()
    }
    # the staging directory is gone once the backup ended
    assert not os.path.exists(borg.staging_root)
    assert not any("Restore canary" in line for line in _log_lines(client))


@pytest.mark.unit
def test_relative_inputs_keep_their_meaning(monkeypatch):
    """Borg is not moved for the canary, so a relative source or pattern file
    still names what it named."""
    relative = {
        "source_paths": ["/src", "relative/src"],
        "custom_flags": "--exclude-from excludes.txt --pattern 'R data'",
    }
    plain, _client, _result = _run(monkeypatch, _job_payload(**relative))

    borg, _client, result = _run(monkeypatch, _job_payload(_canary(), **relative))

    assert result.status == "completed"
    assert _without_canary(borg) == plain.cmd
    assert "cwd" not in borg.kwargs
    assert borg.staging_root is not None


@pytest.mark.unit
@pytest.mark.parametrize("borg_version", [1, 2])
def test_the_canary_include_comes_before_every_user_pattern(monkeypatch, borg_version):
    """Borg matches a pattern against the whole staging path and takes the
    first match: an exclude of the temporary directory or of `*.json` must
    not drop the canary (measured on Borg 1.4.5 and 2.0.0b25)."""
    borg, _client, _result = _run(
        monkeypatch,
        _job_payload(
            _canary(),
            borg_version=borg_version,
            exclude_patterns=["/tmp", "*.json"],
            custom_flags=["--pattern=- *.bin", "--exclude-from=/etc/excludes"],
        ),
    )

    include = f"--pattern=+pp:{borg.staging_root}"
    patterns = [
        index
        for index, argument in enumerate(borg.cmd)
        if argument.startswith(("--exclude", "--pattern"))
    ]
    assert borg.cmd[patterns[0]] == include
    assert len(patterns) == 5 and borg.cmd.count(include) == 1
    # it names the staging directory only, so it includes nothing of the user's
    assert borg.staging_root.rsplit("/", 1)[-1].startswith("borg-ui-canary-")


@pytest.mark.unit
@pytest.mark.parametrize("borg_version", [1, 2])
def test_a_tag_file_exclusion_finds_no_canary_directory(monkeypatch, borg_version):
    """`--exclude-if-present=manifest.json` drops every directory Borg walks
    that holds such a file, and no pattern keeps it. Borg is handed the
    canary's files, not their directory, so it walks none of them (measured
    on Borg 1.4.5 and 2.0.0b25)."""
    canary = _canary()
    assert any(path.endswith(f"/{CANARY_MANIFEST}") for path in canary["files"])

    borg, _client, result = _run(
        monkeypatch,
        _job_payload(
            canary,
            borg_version=borg_version,
            custom_flags=[f"--exclude-if-present={CANARY_MANIFEST}"],
        ),
    )

    assert result.status == "completed"
    assert f"--exclude-if-present={CANARY_MANIFEST}" in borg.cmd
    assert len(_canary_sources(borg)) == len(canary["files"])
    assert borg.sources_are_files == [True] * len(canary["files"])


@pytest.mark.unit
def test_the_staging_directory_is_removed_when_borg_cannot_start(monkeypatch):
    _borg_version(monkeypatch, "borg 1.4.5\n")
    roots = []

    def fail(cmd, **kwargs):
        roots.append(cmd[-1].partition("/./")[0])
        assert os.path.isdir(roots[0])
        raise OSError("borg not found")

    monkeypatch.setattr("agent.borg_ui_agent.backup.subprocess.Popen", fail)

    result = execute_backup_create_job(
        {"id": 7, "payload": _job_payload(_canary())}, BackupClient()
    )

    assert result.status == "failed"
    assert roots and not os.path.exists(roots[0])


@pytest.mark.unit
@pytest.mark.parametrize(
    "version",
    [
        "borg 1.2.8\n",
        "borg 1.1.18\n",
        "no version here\n",
        OSError("borg not found"),
    ],
)
def test_borg1_that_does_not_strip_the_staging_path_backs_up_without_the_canary(
    monkeypatch, version
):
    """Borg 1 before 1.4 would archive the canary under the staging
    directory's path, where no restore check looks for it."""
    plain, _client, _result = _run(monkeypatch, _job_payload())

    borg, client, result = _run(
        monkeypatch, _job_payload(_canary()), borg_version=version
    )

    assert result.status == "completed"
    assert borg.cmd == plain.cmd
    assert (
        "Restore canary not added to this backup: it needs Borg 1.4 or newer"
        in _log_lines(client)
    )


@pytest.mark.unit
def test_the_version_is_asked_of_the_borg_the_backup_runs(monkeypatch):
    asked = []

    def run(cmd, **kwargs):
        asked.append(cmd)
        return SimpleNamespace(stdout="borg 1.4.5\n", stderr="")

    monkeypatch.setattr("agent.borg_ui_agent.backup.subprocess.run", run)
    monkeypatch.setattr("agent.borg_ui_agent.backup.subprocess.Popen", _Borg())
    payload = _job_payload(_canary())
    payload["repository"]["borg_binary"] = "/opt/borg/bin/borg"

    execute_backup_create_job({"id": 7, "payload": payload}, BackupClient())

    assert asked == [["/opt/borg/bin/borg", "--version"]]


@pytest.mark.unit
def test_a_host_that_cannot_stage_the_canary_still_backs_up(monkeypatch):
    def read_only(*args, **kwargs):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr("agent.borg_ui_agent.backup.tempfile.mkdtemp", read_only)

    borg, client, result = _run(monkeypatch, _job_payload(_canary()))

    assert result.status == "completed"
    assert borg.cmd[-1] == "/src"
    assert any(
        line.startswith("Restore canary not added to this backup: could not write it")
        for line in _log_lines(client)
    )


@pytest.mark.unit
def test_a_canary_file_that_cannot_be_written_leaves_no_directory(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "agent.borg_ui_agent.backup.tempfile.mkdtemp",
        lambda **kwargs: str(tmp_path / "staging"),
    )
    (tmp_path / "staging").mkdir()

    def full(self, data):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(Path, "write_bytes", full)

    borg, _client, result = _run(monkeypatch, _job_payload(_canary()))

    assert result.status == "completed"
    assert borg.cmd[-1] == "/src"
    assert not (tmp_path / "staging").exists()


@pytest.mark.unit
@pytest.mark.parametrize(
    "canary",
    [
        "not an object",
        {"source_path": CANARY_SOURCE},
        {"source_path": CANARY_SOURCE, "files": {}},
        {"source_path": "/etc", "files": {"/etc/passwd": "eA=="}},
        {"source_path": "../up", "files": {"../up/file": "eA=="}},
        {"source_path": "a/./b", "files": {"a/./b/file": "eA=="}},
        {"source_path": "--option", "files": {"--option/file": "eA=="}},
        {"source_path": "canary", "files": {"elsewhere/file": "eA=="}},
        {"source_path": "canary", "files": {"canary/../../file": "eA=="}},
        {"source_path": "canary", "files": {"canary\\file": "eA=="}},
        {"source_path": "canary", "files": {"canary/file": "not base64"}},
        {"source_path": "canary", "files": {"canary/file": 7}},
    ],
)
def test_a_canary_that_could_leave_its_directory_is_refused(monkeypatch, canary):
    started = []
    monkeypatch.setattr(
        "agent.borg_ui_agent.backup.subprocess.Popen",
        lambda *args, **kwargs: started.append(args),
    )
    client = BackupClient()

    result = execute_backup_create_job(
        {"id": 7, "payload": _job_payload(canary)}, client
    )

    assert result.status == "failed"
    assert "Invalid backup.create payload" in result.message
    assert started == []
