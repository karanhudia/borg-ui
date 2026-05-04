import shutil

import pytest

from app.config import settings
from app.database.models import Repository
from app.services.restore_check_canary import (
    CANARY_ARCHIVE_NAMESPACE,
    CANARY_DIRNAME,
    ensure_restore_canary,
    get_restore_canary_archive_paths,
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
