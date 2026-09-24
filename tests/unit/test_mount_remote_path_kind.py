"""How MountService decides whether a remote source path is a file.

The mount retries a missing absolute path relative to the login directory,
so the file check has to resolve the path the same way: a file reachable
only through that fallback was once judged a directory and then mounted as
one, which fails with "Not a directory". The SFTP-only fallback used an
`sftp stat` that OpenSSH's sftp does not have, so it called everything a
file. Behaviour here was checked against a real OpenSSH server with a shell
user and an internal-sftp-only user.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import mount_service as ms
from app.services.mount_service import MountService, _sftp_quote


def _connection(default_path=None):
    return SimpleNamespace(
        id=7, host="example.test", port=22, username="u", default_path=default_path
    )


def _process(returncode, stdout=b"", stderr=b""):
    process = AsyncMock()
    process.returncode = returncode
    process.communicate = AsyncMock(return_value=(stdout, stderr))
    return process


@pytest.fixture
def service():
    with patch.object(ms, "host_key_ssh_opts", return_value=[]):
        yield MountService.__new__(MountService)


@pytest.mark.unit
class TestRemotePathCandidates:
    def test_absolute_path_falls_back_to_login_relative(self, service):
        assert service._remote_path_candidates(_connection(), "/a/b.txt") == [
            "/a/b.txt",
            "a/b.txt",
        ]

    def test_no_fallback_when_connection_has_a_default_path(self, service):
        assert service._remote_path_candidates(_connection("/srv"), "/a/b.txt") == [
            "/a/b.txt"
        ]

    def test_root_and_relative_paths_have_no_fallback(self, service):
        assert service._remote_path_candidates(_connection(), "/") == ["/"]
        assert service._remote_path_candidates(_connection(), "a/b") == ["a/b"]


@pytest.mark.unit
class TestSftpQuote:
    @pytest.mark.parametrize(
        "path, expected",
        [
            ("/plain/path.txt", "/plain/path.txt"),
            ("/sp ace/f", r"/sp\ ace/f"),
            ('/we ird*/f"q.txt', r"/we\ ird\*/f\"q.txt"),
            ("/q'uote", r"/q\'uote"),
            ("/back\\slash", r"/back\\slash"),
            ("/g/[x]?", r"/g/\[x\]\?"),
        ],
    )
    def test_escapes_everything_sftp_would_split_or_glob(self, path, expected):
        assert _sftp_quote(path) == expected


@pytest.mark.unit
class TestShellCheck:
    async def test_file_found_only_login_relative_is_a_file(self, service):
        spawn = AsyncMock(return_value=_process(0, b"FILE\n"))
        with patch("asyncio.create_subprocess_exec", spawn):
            assert await service._check_remote_is_file(
                _connection(), "/backup-repo-test/good_file.txt", "/key"
            )

        remote_command = spawn.call_args.args[-1]
        # The first path that exists decides, as in the mount.
        assert remote_command == (
            "if test -e /backup-repo-test/good_file.txt; "
            "then test -f /backup-repo-test/good_file.txt; "
            "else test -f backup-repo-test/good_file.txt; fi "
            "&& echo 'FILE' || echo 'DIR'"
        )

    async def test_paths_are_shell_quoted(self, service):
        spawn = AsyncMock(return_value=_process(0, b"DIR\n"))
        with patch("asyncio.create_subprocess_exec", spawn):
            assert not await service._check_remote_is_file(
                _connection("/srv"), "/it's here; rm -rf ~", "/key"
            )
        assert spawn.call_args.args[-1] == (
            "test -f '/it'\"'\"'s here; rm -rf ~' && echo 'FILE' || echo 'DIR'"
        )

    async def test_directory(self, service):
        spawn = AsyncMock(return_value=_process(0, b"DIR\n"))
        with patch("asyncio.create_subprocess_exec", spawn):
            assert not await service._check_remote_is_file(_connection(), "/d", "/key")
        assert spawn.call_count == 1


@pytest.mark.unit
class TestSftpFallback:
    """An internal-sftp account answers the shell check with a refusal."""

    SFTP_ONLY = (1, b"This service allows sftp connections only.\n")

    async def _check(self, service, path, sftp_results, connection=None):
        processes = [_process(*self.SFTP_ONLY)] + [
            _process(code) for code in sftp_results
        ]
        spawn = AsyncMock(side_effect=processes)
        with patch("asyncio.create_subprocess_exec", spawn):
            result = await service._check_remote_is_file(
                connection or _connection(), path, "/key"
            )
        commands = [
            process.communicate.call_args.kwargs["input"].decode()
            for process in processes[1 : spawn.call_count]
        ]
        return result, commands, spawn

    async def test_directory_is_found_by_cd(self, service):
        result, commands, spawn = await self._check(service, "/d", [0])
        assert result is False
        assert commands == ["cd /d\n"]
        assert spawn.call_args_list[1].args[:3] == ("sftp", "-b", "-")

    async def test_file_is_listable_but_not_enterable(self, service):
        result, commands, _ = await self._check(service, "/f.txt", [1, 0])
        assert result is True
        assert commands == ["cd /f.txt\n", "ls -l /f.txt\n"]

    async def test_missing_absolute_path_resolves_login_relative(self, service):
        result, commands, _ = await self._check(service, "/rel/f.txt", [1, 1, 1, 0])
        assert result is True
        assert commands == [
            "cd /rel/f.txt\n",
            "ls -l /rel/f.txt\n",
            "cd rel/f.txt\n",
            "ls -l rel/f.txt\n",
        ]

    async def test_existing_absolute_path_wins_over_login_relative(self, service):
        # /rel exists as a directory, so the relative candidate is never asked.
        result, commands, _ = await self._check(service, "/rel", [0])
        assert result is False
        assert commands == ["cd /rel\n"]

    async def test_missing_everywhere_is_not_a_file(self, service):
        result, _, _ = await self._check(service, "/nope", [1, 1, 1, 1])
        assert result is False

    async def test_connection_failure_is_not_read_as_missing(self, service):
        # 255 is ssh failing to connect; sftp exits 1 only for a failed command.
        result, commands, _ = await self._check(service, "/f.txt", [255])
        assert result is False
        assert commands == ["cd /f.txt\n"]

    async def test_path_is_escaped_for_sftp(self, service):
        _, commands, _ = await self._check(
            service, '/we ird*/f"q.txt', [1, 0], connection=_connection("/srv")
        )
        assert commands == [
            r"cd /we\ ird\*/f\"q.txt" + "\n",
            r"ls -l /we\ ird\*/f\"q.txt" + "\n",
        ]
