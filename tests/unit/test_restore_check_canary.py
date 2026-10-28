import base64
import re
import shlex
import shutil

import pytest

from app.config import settings
from app.database.models import Repository
from app.services.restore_check_canary import (
    CANARY_ARCHIVE_NAMESPACE,
    CANARY_DIRNAME,
    ensure_restore_canary,
    get_restore_canary_archive_paths,
    remote_restore_canary_staging,
    should_include_restore_canary,
    to_restore_canary_archive_source_path,
    verify_restored_canary,
)


@pytest.mark.unit
def test_restore_canary_uses_hidden_archive_namespace(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    repository = Repository(id=2, name="Documents")

    canary_path = ensure_restore_canary(repository)

    assert canary_path == (
        tmp_path / CANARY_ARCHIVE_NAMESPACE / "repository-2" / CANARY_DIRNAME
    )
    assert get_restore_canary_archive_paths(repository) == [
        ".borg-ui/restore-canaries/repository-2/.borgui-canary"
    ]
    assert (
        to_restore_canary_archive_source_path(str(canary_path))
        == ".borg-ui/restore-canaries/repository-2/.borgui-canary"
    )


@pytest.mark.unit
def test_verify_restored_canary_accepts_hidden_archive_namespace(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
    repository = Repository(id=2, name="Documents")
    source_canary_path = ensure_restore_canary(repository)

    restore_destination = tmp_path / "restore"
    restored_canary_path = (
        restore_destination / ".borg-ui/restore-canaries/repository-2/.borgui-canary"
    )
    restored_canary_path.parent.mkdir(parents=True)
    shutil.copytree(source_canary_path, restored_canary_path)

    result = verify_restored_canary(repository, str(restore_destination))

    assert result["verified_files"] == [
        ".borgui-canary/README.txt",
        ".borgui-canary/nested/check.json",
        ".borgui-canary/binary/check.bin",
    ]


@pytest.mark.unit
def test_should_include_restore_canary_requires_explicit_canary_mode():
    repository = Repository(
        id=2,
        name="Documents",
        restore_check_canary_enabled=False,
        restore_check_paths=None,
        restore_check_full_archive=False,
    )

    assert should_include_restore_canary(repository) is False

    repository.restore_check_canary_enabled = True
    assert should_include_restore_canary(repository) is True

    repository.restore_check_paths = '["etc/hostname"]'
    assert should_include_restore_canary(repository) is False

    repository.restore_check_paths = "[]"
    repository.restore_check_full_archive = True
    assert should_include_restore_canary(repository) is False


@pytest.mark.unit
def test_remote_restore_canary_staging_follows_canary_mode():
    repository = Repository(
        id=2,
        name="Documents",
        restore_check_canary_enabled=False,
        restore_check_paths=None,
        restore_check_full_archive=False,
    )

    assert remote_restore_canary_staging(repository) is None

    repository.restore_check_canary_enabled = True
    assert remote_restore_canary_staging(repository) is not None

    repository.restore_check_paths = '["etc/hostname"]'
    assert remote_restore_canary_staging(repository) is None

    repository.restore_check_paths = "[]"
    repository.restore_check_full_archive = True
    assert remote_restore_canary_staging(repository) is None


@pytest.mark.unit
def test_remote_restore_canary_staging_writes_the_local_canary_files(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    repository = Repository(
        id=2,
        name="Documents",
        restore_check_canary_enabled=True,
        restore_check_paths=None,
        restore_check_full_archive=False,
    )
    local_root = ensure_restore_canary(repository)

    staging = remote_restore_canary_staging(repository)

    assert staging is not None
    script, canary_root, archive_source_path = staging
    assert canary_root == "$HOME"
    assert archive_source_path == get_restore_canary_archive_paths(repository)[0]

    # Every written file is a base64 payload aimed at a path under the root.
    writes = re.findall(r"printf '%s' ([^ ]+) \| base64 -d > \"([^\"]+)\"", script)
    assert writes, script
    staged = {}
    for encoded, target in writes:
        assert target.startswith(
            f"{canary_root}/.borg-ui/restore-canaries/repository-{repository.id}/.borgui-canary/"
        )
        relative = target.removeprefix(f"{canary_root}/")
        staged[relative] = base64.b64decode(shlex.split(encoded)[0].encode("ascii"))

    # The staged dict has paths relative to $HOME.
    # The local_root already includes .borgui-canary, so relative_to(local_root)
    # gives paths like .borgui-canary/README.txt. The staged dict has the full
    # path under $HOME which is canary_root + relative_prefix + subpath.
    expected = {
        f".borg-ui/restore-canaries/repository-{repository.id}/.borgui-canary/{path.relative_to(local_root).as_posix()}": (
            path.read_bytes()
        )
        for path in sorted(local_root.rglob("*"))
        if path.is_file()
    }
    assert staged == expected
    # The manifest lands inside the canary dir, next to the payload files.
    assert (
        f".borg-ui/restore-canaries/repository-{repository.id}/{CANARY_DIRNAME}/manifest.json"
        in staged
    )
