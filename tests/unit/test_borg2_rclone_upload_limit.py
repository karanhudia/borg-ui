"""A Borg 2 repository behind rclone takes its upload limit as rclone's (#1307).

Borg 2.0.0b22 removed --upload-ratelimit, but Borg 2's rclone backend runs
rclone, which reads RCLONE_BWLIMIT from the environment. Measured on Borg
2.0.0b24 and rclone 1.75.0 (20 MB, no compression): no limit 5.5 s,
RCLONE_BWLIMIT=1M 25.0 s. The directional forms (1M:off, off:1M) did not
throttle, so the single value is set, and only on the create command. rclone's
K is KiB, the unit of upload_ratelimit_kib.
"""

from types import SimpleNamespace

import pytest

from agent.borg_ui_agent.backup import BackupCreatePayload
from app.core.borg_router import BorgRouter


def _repo(borg_version, path):
    return SimpleNamespace(borg_version=borg_version, path=path)


@pytest.mark.unit
@pytest.mark.parametrize(
    "borg_version,path,kib,expected",
    [
        (2, "rclone:remote:borg/repo", 512, 512),
        (2, "/backups/repo", 512, None),
        (2, "ssh://u@h/./repo", 512, None),
        (1, "/backups/repo", 512, 512),
        (2, "rclone:remote:borg/repo", None, None),
    ],
)
def test_upload_limit_applies_to_borg1_and_borg2_behind_rclone(
    borg_version, path, kib, expected
):
    assert BorgRouter(_repo(borg_version, path)).upload_ratelimit(kib) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "borg_version,path,kib,expected",
    [
        (2, "rclone:remote:borg/repo", 512, {"RCLONE_BWLIMIT": "512K"}),
        (2, "/backups/repo", 512, {}),
        (2, "rclone:remote:borg/repo", None, {}),
        # Borg 1 takes the limit as --upload-ratelimit on the command
        (1, "rclone:remote:borg/repo", 512, {}),
    ],
)
def test_backup_environment_carries_rclone_bwlimit_for_borg2_behind_rclone(
    borg_version, path, kib, expected
):
    assert BorgRouter(_repo(borg_version, path)).backup_environment(kib) == expected


def _repository(borg_version, path):
    return SimpleNamespace(
        id=1,
        path=path,
        borg_version=borg_version,
        remote_path=None,
        compression="lz4",
        exclude_patterns="[]",
        custom_flags=None,
        upload_ratelimit_kib=512,
        passphrase=None,
    )


@pytest.mark.unit
def test_agent_payload_carries_the_upload_limit_for_borg2_behind_rclone():
    from app.services.repository_executor import build_agent_backup_payload

    payload = build_agent_backup_payload(
        _repository(2, "rclone:remote:borg/repo"), "a", source_directories=["/s"]
    )

    assert payload["backup"]["upload_ratelimit_kib"] == 512


def _agent_backup(path, **backup):
    return {
        "job_kind": "backup.create",
        "repository": {"path": path, "borg_version": 2},
        "backup": {"archive_name": "a", "source_paths": ["/src"], **backup},
    }


@pytest.mark.unit
def test_agent_borg2_backup_behind_rclone_sets_rclone_bwlimit():
    payload = BackupCreatePayload.from_job_payload(
        _agent_backup("rclone:remote:borg/repo", upload_ratelimit_kib=512)
    )

    assert payload.environment["RCLONE_BWLIMIT"] == "512K"
    assert "--upload-ratelimit" not in payload.build_command()


@pytest.mark.unit
def test_agent_borg2_backup_elsewhere_has_no_rclone_bwlimit():
    payload = BackupCreatePayload.from_job_payload(
        _agent_backup("/backups/repo", upload_ratelimit_kib=512)
    )

    assert "RCLONE_BWLIMIT" not in payload.environment
