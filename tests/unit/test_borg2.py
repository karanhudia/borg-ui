import inspect
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.core.borg2 import (
    BORG2_ENCRYPTION_MODES,
    borg2,
    borg2_encryption_flags,
    borg2_repository_url_refusal,
    borg2_speaks_encryption_flags,
    normalize_repo_info_encryption,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archive_contents_uses_absolute_depth_for_browse():
    with patch.object(
        borg2,
        "_run_streaming",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_run:
        await borg2.list_archive_contents(
            repository="/repo",
            archive="archive-1",
            path="docs/sub",
            browse_depth=3,
        )

    mock_run.assert_awaited_once_with(
        [
            "borg2",
            "-r",
            "/repo",
            "list",
            "--json-lines",
            "--depth",
            "3",
            "archive-1",
            "docs/sub",
        ],
        max_lines=1_000_000,
        env={"TZ": "UTC"},
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archive_contents_omits_depth_when_not_requested():
    with patch.object(
        borg2,
        "_run_streaming",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_run:
        await borg2.list_archive_contents(
            repository="/repo",
            archive="archive-1",
            path="",
        )

    mock_run.assert_awaited_once_with(
        ["borg2", "-r", "/repo", "list", "--json-lines", "archive-1"],
        max_lines=1_000_000,
        env={"TZ": "UTC"},
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_archive_uses_restore_umask():
    with patch.object(
        borg2,
        "_run",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_run:
        await borg2.extract_archive(
            repository="/repo",
            archive="archive-1",
            paths=["home/user/file.txt"],
            destination="/restore",
        )

    mock_run.assert_awaited_once_with(
        [
            "borg2",
            "-r",
            "/repo",
            "extract",
            "--umask",
            "0022",
            "archive-1",
            "home/user/file.txt",
        ],
        timeout=3600,
        cwd="/restore",
        env=None,
    )


@pytest.mark.unit
def test_export_archive_tar_builds_stdout_command():
    stream = borg2.export_archive_tar(
        repository="/repo",
        archive="aid:archive-1",
        directory_path="/documents/Projects",
        strip_components=1,
    )

    assert stream.cmd == [
        "borg2",
        "-r",
        "/repo",
        "export-tar",
        "--strip-components",
        "1",
        "aid:archive-1",
        "-",
        "--",
        "documents/Projects",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rcreate_injects_managed_rclone_config_into_process_env(
    monkeypatch, tmp_path
):
    rclone_root = tmp_path / "rclone"
    monkeypatch.setattr(settings, "rclone_config_root", str(rclone_root))
    captured: dict[str, object] = {}

    class Process:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def create_subprocess_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        return Process()

    monkeypatch.setattr(
        "app.core.borg2.asyncio.create_subprocess_exec",
        create_subprocess_exec,
    )

    result = await borg2.rcreate(
        repository="rclone:prod-s3:borg-ui/direct",
        encryption="authenticated",
        passphrase="secret",
    )

    assert result["success"] is True
    assert captured["cmd"] == (
        borg2.borg_cmd,
        "-r",
        "rclone:prod-s3:borg-ui/direct",
        "repo-create",
        "--encryption",
        "authenticated-sha256",
    )  # the key stays in the repository: borg's default, no --key-location
    assert captured["env"]["RCLONE_CONFIG"] == str(rclone_root / "rclone.conf")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (
            "repokey-aes-ocb",
            ["--encryption", "aes256-ocb", "--key-location", "repokey"],
        ),
        (
            "keyfile-chacha20-poly1305",
            ["--encryption", "chacha20-poly1305", "--key-location", "keyfile"],
        ),
        ("authenticated", ["--encryption", "authenticated-sha256"]),
    ],
)
def test_encryption_mode_is_translated_to_the_repo_create_split(mode, expected):
    """Borg 2.0.0b22 takes the cipher and the key location as separate options;
    the combined name stays the vocabulary of the API, the UI and the stored
    repository row."""
    assert borg2_encryption_flags(mode) == expected


@pytest.mark.unit
def test_every_offered_encryption_mode_can_be_translated():
    """The list the API validates against and the table repo-create is built
    from are the same table, so a mode can never be offered without flags."""
    for mode in BORG2_ENCRYPTION_MODES:
        assert borg2_encryption_flags(mode)[0] == "--encryption"


@pytest.mark.unit
@pytest.mark.parametrize(
    "version, speaks",
    [
        ("2.0.0b21", False),
        ("2.0.0b22", True),
        ("2.0.0b24", True),
        ("2.0.0", True),
        # Only a version that reads as an older Borg 2 is refused: nothing
        # readable is not evidence of an old binary, and the message would
        # name an empty version.
        ("", True),
        (None, True),
        ("unknown", True),
    ],
)
def test_only_a_readably_old_borg2_is_refused_the_split_flags(version, speaks):
    assert borg2_speaks_encryption_flags(version) is speaks


@pytest.mark.unit
def test_the_unencrypted_mode_is_refused_not_mapped():
    """Borg 2.0.0b25 removed none-sha256/none-blake3 ("invalid choice:
    'none-sha256'"). The mode is not offered and not silently turned into
    another one: a repository created as `none` would not be what was asked
    for."""
    assert "none" not in BORG2_ENCRYPTION_MODES
    with pytest.raises(ValueError, match="2.0.0b25"):
        borg2_encryption_flags("none")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rcreate_reports_a_refused_mode_without_running_borg():
    with patch.object(borg2, "_run", new=AsyncMock()) as mock_run:
        result = await borg2.rcreate(repository="/repo", encryption="none")

    mock_run.assert_not_awaited()
    assert result["success"] is False
    assert "authenticated" in result["stderr"]


@pytest.mark.unit
def test_an_unknown_encryption_mode_is_rejected_by_name():
    """Rather than handing borg a value it will reject with an argparse error
    that names no caller."""
    with pytest.raises(ValueError, match="repokey-blake2-aes-ocb"):
        borg2_encryption_flags("repokey-blake2-aes-ocb")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prune_keep_within_is_sent_as_keep(monkeypatch):
    """Borg 2.0.0b22 removed --keep-within; --keep takes the same interval. The
    field keeps its name everywhere else — only the flag moved."""
    captured: dict[str, object] = {}

    class Process:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def create_subprocess_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        return Process()

    monkeypatch.setattr(
        "app.core.borg2.asyncio.create_subprocess_exec",
        create_subprocess_exec,
    )

    await borg2.prune_archives(repository="/repo", keep_within="1d")

    cmd = list(captured["cmd"])
    assert "--keep" in cmd
    assert cmd[cmd.index("--keep") + 1] == "1d"
    assert not [arg for arg in cmd if arg.startswith("--keep-within")]


@pytest.mark.unit
def test_repo_info_encryption_from_b22_gets_a_mode():
    """Verbatim from `borg2 repo-info --json` on 2.0.0b22: the single `mode`
    became `encryption` + `id_hash`, which left every reader of `mode` — the
    stored row, the API, the info dialog — showing nothing for an encrypted
    repository."""
    info = {
        "encryption": {"encryption": "aes256-ocb", "id_hash": "sha256"},
        "repository": {"id": "979d5a3d", "location": "/tmp/r"},
    }

    assert normalize_repo_info_encryption(info)["encryption"] == {
        "encryption": "aes256-ocb",
        "id_hash": "sha256",
        "mode": "aes256-ocb",
    }


@pytest.mark.unit
def test_repo_info_encryption_from_b21_is_left_alone():
    """Verbatim from 2.0.0b21, and the Borg 1 shape too: a `mode` that is
    already there is never rewritten."""
    info = {"encryption": {"mode": "repokey-aes-ocb"}}

    assert normalize_repo_info_encryption(info)["encryption"] == {
        "mode": "repokey-aes-ocb"
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    "info",
    [{}, {"encryption": None}, {"encryption": {}}, {"encryption": "unexpected"}],
)
def test_repo_info_without_a_usable_encryption_block_is_untouched(info):
    """An unencrypted repository, a failed call, or a shape nobody anticipated —
    none of them should have a mode invented for them."""
    before = dict(info)

    assert normalize_repo_info_encryption(info) == before


def _bypass_lock_commands() -> list[str]:
    """Every borg2 command builder that takes a bypass_lock argument.

    Read off the interface rather than listed, so a new command that accepts
    bypass_lock is covered the day it is added, and a renamed one fails loudly
    instead of quietly dropping out of the parametrisation.
    """
    names = [
        name
        for name, member in inspect.getmembers(borg2, inspect.iscoroutinefunction)
        if not name.startswith("_")
        and "bypass_lock" in inspect.signature(member).parameters
    ]
    assert names, "no borg2 command takes bypass_lock — has the interface moved?"
    return names


# Stand-ins for the arguments a command needs besides bypass_lock. Nothing is
# executed: create_subprocess_exec is replaced, so only the argv is built.
_ARGUMENTS = {
    "repository": "/repo",
    "archive": "series",
    "paths": ["etc/hosts"],
    "destination": "/restore",
    "path": "etc/hosts",
    "mount_point": "/mnt/repo",
}


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("command", _bypass_lock_commands())
async def test_no_borg2_command_carries_bypass_lock(monkeypatch, command):
    """--bypass-lock is a Borg 1 flag. Borg 2 has never had it — it is absent
    from the 2.0.0b21 and 2.0.0b22 sources alike — so a Borg 2 command carrying
    it dies at argument parsing, which reads as an unreachable repository rather
    than as a flag this Borg does not know. The argument stays (callers and the
    repository settings speak for both majors) and is ignored.
    """
    captured: dict[str, object] = {}

    class Process:
        returncode = 0

        async def communicate(self):
            return b"{}", b""

    async def create_subprocess_exec(*cmd, **_):
        captured["cmd"] = cmd
        return Process()

    monkeypatch.setattr(
        "app.core.borg2.asyncio.create_subprocess_exec", create_subprocess_exec
    )
    method = getattr(borg2, command)
    kwargs = {"bypass_lock": True}
    for name, parameter in inspect.signature(method).parameters.items():
        if parameter.default is inspect.Parameter.empty and name in _ARGUMENTS:
            kwargs[name] = _ARGUMENTS[name]

    await method(**kwargs)

    assert "--bypass-lock" not in list(captured["cmd"])


def _remote_path_commands() -> list[str]:
    """Every borg2 command that takes a remote_path argument, the ones that
    run a process and the ones that hand back a stream alike. Read off the
    interface for the reason `_bypass_lock_commands` is."""
    names = [
        name
        for name, member in inspect.getmembers(borg2, inspect.ismethod)
        if not name.startswith("_")
        and "remote_path" in inspect.signature(member).parameters
    ]
    assert names, "no borg2 command takes remote_path — has the interface moved?"
    return names


_REMOTE_PATH_ARGUMENTS = {
    **_ARGUMENTS,
    "archive_a": "aid:1",
    "archive_b": "aid:2",
    "source_paths": ["/data"],
    "directory_path": "etc",
}


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("command", _remote_path_commands())
async def test_borg2_remote_path_travels_in_the_environment(monkeypatch, command):
    """Borg 2.0.0b22 removed --remote-path in favour of BORG_REMOTE_PATH. A
    command line that still carries the option dies at argument parsing
    ("unrecognized arguments: --remote-path"), for every repository that has
    a remote path configured.
    """
    captured: dict[str, object] = {}

    class Process:
        returncode = 0
        stdout = None
        stderr = None

        async def communicate(self):
            return b"{}", b""

        async def wait(self):
            return 0

    async def create_subprocess_exec(*cmd, env=None, **_):
        captured["cmd"] = list(cmd)
        captured["env"] = env
        return Process()

    class Stream:
        def __init__(self, cmd, *, env=None, timeout=3600):
            captured["cmd"] = list(cmd)
            captured["env"] = env

    async def run_streaming(cmd, env=None, **_):
        captured["cmd"] = list(cmd)
        captured["env"] = borg2._base_env(env)
        return {"success": True, "stdout": ""}

    monkeypatch.setattr(
        "app.core.borg2.asyncio.create_subprocess_exec", create_subprocess_exec
    )
    monkeypatch.setattr("app.core.borg2.CommandLineStream", Stream)
    monkeypatch.setattr("app.core.borg2.CommandByteStream", Stream)
    monkeypatch.setattr(borg2, "_run_streaming", run_streaming)

    method = getattr(borg2, command)
    kwargs = {"remote_path": "/opt/borg2/bin/borg"}
    for name, parameter in inspect.signature(method).parameters.items():
        if (
            parameter.default is inspect.Parameter.empty
            and name in _REMOTE_PATH_ARGUMENTS
        ):
            kwargs[name] = _REMOTE_PATH_ARGUMENTS[name]

    result = method(**kwargs)
    if inspect.isawaitable(result):
        await result

    assert "--remote-path" not in captured["cmd"]
    assert "/opt/borg2/bin/borg" not in captured["cmd"]
    assert captured["env"]["BORG_REMOTE_PATH"] == "/opt/borg2/bin/borg"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_borg2_without_a_remote_path_leaves_the_environment_alone(monkeypatch):
    """An inherited BORG_REMOTE_PATH (the container's own) is not cleared by
    a repository that configures none."""
    monkeypatch.setenv("BORG_REMOTE_PATH", "borg2")
    with patch.object(
        borg2,
        "_run",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_run:
        await borg2.break_lock(repository="/repo", passphrase="secret")

    assert mock_run.await_args.kwargs["env"] == {"BORG_PASSPHRASE": "secret"}
    assert borg2._base_env()["BORG_REMOTE_PATH"] == "borg2"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rcreate_disables_the_store_cache():
    """repo-create must not create/validate the shared pack cache — borgstore
    rejects a populated cache directory and borg misreports that as
    "repository already exists"."""
    with patch.object(
        borg2,
        "_run",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_run:
        await borg2.rcreate(
            repository="/repo",
            encryption="repokey-aes-ocb",
            passphrase="secret",
        )

    env = mock_run.await_args.kwargs["env"]
    assert env["BORG_STORE_CACHE"] == ""
    assert env["BORG_PASSPHRASE"] == "secret"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rdelete_disables_the_store_cache():
    """repo-delete with the cache enabled would rmtree the shared cache
    directory (Store.destroy destroys the cache backend too)."""
    with patch.object(
        borg2,
        "_run",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_run:
        await borg2.rdelete(repository="/repo")

    assert mock_run.await_args.kwargs["env"] == {"BORG_STORE_CACHE": ""}


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["rdelete", "break_lock", "check_repository"])
async def test_commands_that_need_the_key_run_with_the_passphrase(command):
    """From Borg 2.0.0b25 the lock is sealed with the repository key, so
    break-lock and repo-delete --force ask for the passphrase like any other
    command (and exit 50 without one); check needs it for the index."""
    with patch.object(
        borg2,
        "_run",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_run:
        await getattr(borg2, command)(repository="/repo", passphrase="secret")

    assert mock_run.await_args.kwargs["env"]["BORG_PASSPHRASE"] == "secret"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,args",
    [
        ("list_archives", ("/repo",)),
        ("info_archive", ("/repo", "archive-1")),
        ("rinfo", ("/repo",)),
        ("info_repo", ("/repo",)),
    ],
)
async def test_machine_parsed_output_renders_timestamps_in_utc(method, args):
    with patch.object(
        borg2,
        "_run",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_run:
        await getattr(borg2, method)(*args, passphrase="pw")

    env = mock_run.await_args.kwargs["env"]
    assert env["TZ"] == "UTC"
    assert env["BORG_PASSPHRASE"] == "pw"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_hands_the_spawned_process_to_on_process():
    """#1028: `delete_archive_v2_service` cancels by terminating the process
    `_run` spawned, so `_run` has to hand it over."""
    seen = []

    result = await borg2._run(
        ["/bin/sh", "-c", "exit 0"], on_process=lambda process: seen.append(process)
    )

    assert result["success"] is True
    assert len(seen) == 1 and seen[0].returncode == 0


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["delete_archive", "compact"])
async def test_delete_and_compact_forward_on_process(method):
    hook = object()
    args = ("/repo", "archive-1") if method == "delete_archive" else ("/repo",)
    with patch.object(
        borg2,
        "_run",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_run:
        await getattr(borg2, method)(*args, on_process=hook)

    assert mock_run.await_args.kwargs["on_process"] is hook


_REST_URL = "rest://borg@repo.example/backups/one"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("command", _remote_path_commands())
async def test_no_borg2_command_runs_on_a_rest_url(monkeypatch, command):
    """Borg 2.0.0b25 dropped rest:// and reads such a URL as the local
    directory ./rest:/user@host/path: repo-create and create exit 0 there,
    and the backup never reaches the repository server. No command is
    started on one."""

    async def create_subprocess_exec(*cmd, **_):
        raise AssertionError(f"borg must not run: {cmd}")

    class Stream:
        def __init__(self, cmd, **_):
            raise AssertionError(f"borg must not run: {cmd}")

    monkeypatch.setattr(
        "app.core.borg2.asyncio.create_subprocess_exec", create_subprocess_exec
    )
    monkeypatch.setattr("app.core.borg2.CommandLineStream", Stream)
    monkeypatch.setattr("app.core.borg2.CommandByteStream", Stream)
    monkeypatch.setattr("app.core.borg2.borg2_binary_version", lambda _: "2.0.0b25")

    method = getattr(borg2, command)
    kwargs = {}
    for name, parameter in inspect.signature(method).parameters.items():
        if (
            parameter.default is inspect.Parameter.empty
            and name in _REMOTE_PATH_ARGUMENTS
        ):
            kwargs[name] = _REMOTE_PATH_ARGUMENTS[name]
    kwargs["repository"] = _REST_URL

    if inspect.iscoroutinefunction(method):
        result = await method(**kwargs)
        assert result["success"] is False
        assert "ssh://" in result["stderr"]
    else:
        with pytest.raises(ValueError, match="ssh://"):
            method(**kwargs)


@pytest.mark.unit
@pytest.mark.parametrize(
    "repository",
    [
        "/local/repo",
        "ssh://borg@repo.example/backups/one",
        "sftp://borg@repo.example/backups/one",
        "rclone:remote:backups/one",
        "/data/rest://looks-odd-but-is-a-path",
    ],
)
def test_other_repository_urls_are_left_alone(repository):
    assert borg2_repository_url_refusal(repository) is None


@pytest.mark.unit
def test_command_builders_outside_the_interface_refuse_a_rest_url(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr("app.core.borg2.borg2_binary_version", lambda _: "2.0.0b25")

    from app.core.borg_router import BorgRouter
    from app.services.v2.backup_service import backup_v2_service
    from app.services.v2.mount_service import mount_v2_service
    from app.services.v2.restore_service import restore_v2_service

    builders = [
        lambda: restore_v2_service.build_extract_command(_REST_URL, "aid:1"),
        lambda: mount_v2_service.build_mount_command(_REST_URL, "aid:1", "/mnt"),
        lambda: backup_v2_service.build_backup_create_command(
            _REST_URL, "series", "lz4", [], []
        ),
        lambda: BorgRouter(SimpleNamespace(borg_version=2)).build_break_lock_command(
            _REST_URL
        ),
    ]
    for build in builders:
        with pytest.raises(ValueError, match="ssh://"):
            build()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("banner", "refused"),
    [
        ("borg2 2.0.0b25\n", True),
        ("borg 2.0.0\n", True),
        # a configured binary may be any build, and these still speak rest://
        ("borg2 2.0.0b24\n", False),
        ("borg2 2.0.0b22\n", False),
        # nothing readable is not evidence of an old binary
        ("", True),
        ("borg 1.4.5\n", True),
    ],
)
def test_a_rest_url_is_refused_by_what_the_binary_reports(monkeypatch, banner, refused):
    from types import SimpleNamespace

    from app.core import borg2 as borg2_module

    monkeypatch.setattr(borg2_module, "_BINARY_VERSIONS", {})
    monkeypatch.setattr(
        borg2_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=banner, stderr=""),
    )

    refusal = borg2_repository_url_refusal(_REST_URL, "borg2")

    assert (refusal is not None) is refused


@pytest.mark.unit
def test_the_binary_is_not_probed_for_other_urls(monkeypatch):
    from app.core import borg2 as borg2_module

    def no_probe(*args, **kwargs):
        raise AssertionError("no probe for a URL that is not rest://")

    monkeypatch.setattr(borg2_module.subprocess, "run", no_probe)

    assert borg2_repository_url_refusal("ssh://borg@repo.example/one", "borg2") is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("occupied_by", "refused"),
    [
        (None, False),
        ("unrelated.txt", True),
        (".hidden", True),
        ("lost+found", True),
    ],
)
def test_a_restore_into_an_occupied_directory_is_refused(
    monkeypatch, tmp_path, occupied_by, refused
):
    """Borg 2.0.0b25 refuses to extract into a directory that is not empty
    (exit 33): the original location, a directory with a single dotfile, a
    fresh filesystem with its lost+found. Borg UI says so before Borg runs
    and does not reach for --continue, which skips a file that looks
    restored by type, mode, size and time."""
    from app.core.borg2 import borg2_restore_target_refusal
    from app.core.borg_errors import RestoreRefused
    from app.services.v2.restore_service import restore_v2_service

    monkeypatch.setattr("app.core.borg2.borg2_binary_version", lambda _: "2.0.0b25")
    if occupied_by == "lost+found":
        (tmp_path / occupied_by).mkdir()
    elif occupied_by:
        (tmp_path / occupied_by).write_text("x")
    destination = str(tmp_path)
    detail = {
        "key": "backend.errors.restore.borg2DestinationNotEmpty",
        "params": {"path": destination},
    }

    assert borg2_restore_target_refusal(destination) == (detail if refused else None)
    if refused:
        with pytest.raises(RestoreRefused) as raised:
            restore_v2_service.build_extract_command(
                "/repo", "aid:1", ["etc"], destination=destination
            )
        assert raised.value.detail == detail
    else:
        cmd = restore_v2_service.build_extract_command(
            "/repo", "aid:1", ["etc"], strip_components=1, destination=destination
        )
        assert cmd[3:] == [
            "extract",
            "--log-json",
            "--umask",
            "0022",
            "--strip-components",
            "1",
            "aid:1",
            "etc",
        ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("version", "refused"),
    [
        ("2.0.0b25", True),
        ("2.0.0b26", True),
        # extracts into a directory that holds files, as it always did
        ("2.0.0b24", False),
        ("2.0.0b22", False),
        # a version that cannot be read is not evidence of an old binary
        (None, True),
    ],
)
def test_the_refusal_follows_what_the_binary_reports(
    monkeypatch, tmp_path, version, refused
):
    from app.core.borg2 import borg2_restore_target_refusal

    monkeypatch.setattr("app.core.borg2.borg2_binary_version", lambda _: version)
    (tmp_path / "existing.txt").write_text("x")

    assert (borg2_restore_target_refusal(str(tmp_path), "borg2") is not None) is refused


@pytest.mark.unit
def test_an_empty_destination_does_not_probe_the_binary(monkeypatch, tmp_path):
    from app.core.borg2 import borg2_restore_target_refusal

    def no_probe(_binary):
        raise AssertionError("no probe for a directory that holds nothing")

    monkeypatch.setattr("app.core.borg2.borg2_binary_version", no_probe)

    assert borg2_restore_target_refusal(str(tmp_path), "borg2") is None


@pytest.mark.unit
def test_a_restore_that_names_no_destination_or_a_missing_one_is_built(tmp_path):
    from app.core.borg2 import borg2_restore_target_refusal
    from app.services.v2.restore_service import restore_v2_service

    assert borg2_restore_target_refusal(None) is None
    assert borg2_restore_target_refusal(str(tmp_path / "missing")) is None
    # a restore check extracts into a directory of its own making
    assert "--continue" not in restore_v2_service.build_extract_command(
        "/repo", "aid:1", ["etc"]
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_never_passes_continue(tmp_path):
    (tmp_path / "existing.txt").write_text("x")

    with patch.object(
        borg2,
        "_run",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_run:
        await borg2.extract_archive(
            repository="/repo",
            archive="aid:1",
            paths=["etc/hosts"],
            destination=str(tmp_path),
        )

    cmd = mock_run.await_args.args[0]
    assert "--continue" not in cmd
    assert cmd[-2:] == ["aid:1", "etc/hosts"]


@pytest.mark.unit
def test_borg1_restore_command_ignores_the_destination(tmp_path):
    from types import SimpleNamespace

    from app.core.borg_router import BorgRouter

    (tmp_path / "existing.txt").write_text("x")

    cmd = BorgRouter(SimpleNamespace(borg_version=1)).build_restore_extract_command(
        "/repo", "archive", ["etc"], destination=str(tmp_path)
    )

    assert cmd[:2] == ["borg", "extract"]
    assert "--continue" not in cmd


@pytest.mark.unit
@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        # 2.0.0b25 on a repository written by 2.0.0b22 to 2.0.0b24, and on a
        # directory that holds no repository: the same answer, exit 15
        (
            "Repository /backups/repo is not a valid repository. "
            "Check the repository config.",
            {"key": "backend.errors.repo.borg2RepositoryNotReadable"},
        ),
        # up to 2.0.0b24 the other format is named
        (
            "proto='file', path='/x' does not have a valid config. Check the "
            "repository config [repository version 3 is not supported by this "
            "borg version].",
            {
                "key": "backend.errors.archives.unsupportedRepositoryVersion",
                "params": {"version": 3},
            },
        ),
        ("Repository /backups/repo does not exist.", None),
        ("passphrase supplied in BORG_PASSPHRASE is incorrect", None),
        ("", None),
        (None, None),
    ],
)
def test_a_repository_this_borg2_cannot_read_gets_a_translatable_detail(
    stderr, expected
):
    from app.core.borg2 import borg2_unreadable_repository_detail

    assert borg2_unreadable_repository_detail(stderr) == expected
