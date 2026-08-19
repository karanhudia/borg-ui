import inspect
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.core.borg2 import (
    BORG2_ENCRYPTION_MODES,
    borg2,
    borg2_encryption_flags,
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
        env=None,
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
        env=None,
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
        encryption="none",
    )

    assert result["success"] is True
    assert captured["cmd"] == (
        borg2.borg_cmd,
        "-r",
        "rclone:prod-s3:borg-ui/direct",
        "repo-create",
        "--encryption",
        "none",
    )  # 'none' has no key, so repo-create gets no --key-location
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
        ("authenticated", ["--encryption", "authenticated"]),
        ("none", ["--encryption", "none"]),
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
