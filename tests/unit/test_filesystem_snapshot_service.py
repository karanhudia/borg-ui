import pytest

from app.services.filesystem_snapshot_service import (
    DEFAULT_SNAPSHOT_STAGING_ROOT,
    build_filesystem_snapshot_plans,
)


def test_builds_btrfs_snapshot_create_and_cleanup_templates():
    plans = build_filesystem_snapshot_plans(
        [
            {
                "source_type": "local",
                "paths": ["/srv/app"],
                "snapshot": {
                    "provider": "btrfs",
                    "staging_path": "/var/tmp/borg-ui/snapshots",
                    "recursive": False,
                },
            }
        ],
        job_id=42,
    )

    assert len(plans) == 1
    plan = plans[0]
    assert plan.provider == "btrfs"
    assert plan.source_path == "/srv/app"
    assert plan.backup_path == "/var/tmp/borg-ui/snapshots/job-42/0-app"
    assert plan.create_commands == [
        [
            "btrfs",
            "subvolume",
            "snapshot",
            "-r",
            "/srv/app",
            "/var/tmp/borg-ui/snapshots/job-42/0-app",
        ]
    ]
    assert plan.cleanup_commands == [
        ["btrfs", "subvolume", "delete", "/var/tmp/borg-ui/snapshots/job-42/0-app"]
    ]
    assert plan.cleanup_paths == ["/var/tmp/borg-ui/snapshots/job-42"]


def test_builds_btrfs_snapshot_with_default_staging_root():
    plans = build_filesystem_snapshot_plans(
        [
            {
                "source_type": "local",
                "paths": ["/"],
                "snapshot": {"provider": "btrfs"},
            }
        ],
        job_id=7,
    )

    assert plans[0].backup_path == f"{DEFAULT_SNAPSHOT_STAGING_ROOT}/job-7/0-root"


def test_builds_zfs_snapshot_paths_and_cleanup_templates():
    plans = build_filesystem_snapshot_plans(
        [
            {
                "source_type": "local",
                "paths": ["/srv/app/uploads", "/srv/app/config"],
                "snapshot": {
                    "provider": "zfs",
                    "dataset": "tank/app",
                    "mountpoint": "/srv/app",
                    "recursive": True,
                },
            }
        ],
        job_id=9,
    )

    assert [plan.backup_path for plan in plans] == [
        "/srv/app/.zfs/snapshot/borg-ui-9-0/uploads",
        "/srv/app/.zfs/snapshot/borg-ui-9-0/config",
    ]
    assert plans[0].create_commands == [
        ["zfs", "snapshot", "-r", "tank/app@borg-ui-9-0"]
    ]
    assert plans[0].cleanup_commands == [
        ["zfs", "destroy", "-r", "tank/app@borg-ui-9-0"]
    ]
    assert plans[1].create_commands == []
    assert plans[1].cleanup_commands == []


def test_zfs_snapshot_paths_must_be_under_mountpoint():
    with pytest.raises(ValueError, match="under zfs mountpoint"):
        build_filesystem_snapshot_plans(
            [
                {
                    "source_type": "local",
                    "paths": ["/srv/other"],
                    "snapshot": {
                        "provider": "zfs",
                        "dataset": "tank/app",
                        "mountpoint": "/srv/app",
                    },
                }
            ],
            job_id=10,
        )
