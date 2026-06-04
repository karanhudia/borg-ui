import json

import pytest

from app.utils.source_locations import (
    decode_source_locations,
    flatten_source_locations,
    legacy_source_fields,
    normalize_source_locations,
)


def test_normalize_agent_source_location_preserves_agent_endpoint():
    locations = normalize_source_locations(
        [
            {
                "source_type": "agent",
                "agent_machine_id": "7",
                "source_ssh_connection_id": None,
                "paths": [" /home/agent/data ", ""],
            }
        ]
    )

    assert locations == [
        {
            "source_type": "agent",
            "source_ssh_connection_id": None,
            "agent_machine_id": 7,
            "paths": ["/home/agent/data"],
        }
    ]


def test_decode_agent_source_locations_from_json():
    locations = decode_source_locations(
        json.dumps(
            [
                {
                    "source_type": "agent",
                    "agent_machine_id": 3,
                    "paths": ["/srv/app"],
                }
            ]
        )
    )

    assert locations[0]["source_type"] == "agent"
    assert locations[0]["agent_machine_id"] == 3
    assert locations[0]["paths"] == ["/srv/app"]


def test_flatten_agent_source_locations_preserves_compatibility():
    locations = normalize_source_locations(
        [
            {
                "source_type": "agent",
                "agent_machine_id": 11,
                "paths": ["/home/user", "/etc"],
            }
        ]
    )

    assert flatten_source_locations(locations) == ["/home/user", "/etc"]
    assert legacy_source_fields(locations) == ("agent", None, ["/home/user", "/etc"])


def test_normalize_local_btrfs_snapshot_location_preserves_config():
    locations = normalize_source_locations(
        [
            {
                "source_type": "local",
                "paths": ["/srv/app"],
                "snapshot": {
                    "provider": "btrfs",
                    "staging_path": " /var/tmp/borg-ui/snapshots ",
                    "recursive": True,
                    "ignored": "value",
                },
            }
        ]
    )

    assert locations == [
        {
            "source_type": "local",
            "source_ssh_connection_id": None,
            "agent_machine_id": None,
            "paths": ["/srv/app"],
            "snapshot": {
                "provider": "btrfs",
                "staging_path": "/var/tmp/borg-ui/snapshots",
                "recursive": True,
            },
        }
    ]


def test_normalize_local_zfs_snapshot_location_requires_dataset_and_mountpoint():
    locations = normalize_source_locations(
        [
            {
                "source_type": "local",
                "paths": ["/srv/app/uploads"],
                "snapshot": {
                    "provider": "zfs",
                    "dataset": " tank/app ",
                    "mountpoint": " /srv/app ",
                },
            }
        ]
    )

    assert locations[0]["snapshot"] == {
        "provider": "zfs",
        "dataset": "tank/app",
        "mountpoint": "/srv/app",
        "recursive": False,
    }


def test_normalize_source_location_preserves_database_metadata():
    locations = normalize_source_locations(
        [
            {
                "source_type": "remote",
                "source_ssh_connection_id": "12",
                "paths": [" /var/tmp/borg-ui/database-dumps/postgresql "],
                "database": {
                    "template_id": " postgresql ",
                    "engine": " PostgreSQL ",
                    "display_name": " Main PostgreSQL ",
                    "backup_strategy": " logical_dump ",
                    "detected_source_path": " /var/lib/postgresql/16/main ",
                    "detection_label": " backup@db.example ",
                    "capture_mode": "dump",
                    "dump_path": " /var/tmp/borg-ui/database-dumps/postgresql ",
                    "backup_paths": [" /var/tmp/borg-ui/database-dumps/postgresql "],
                    "script_execution_target": "source",
                    "ignored": "value",
                },
            }
        ]
    )

    assert locations == [
        {
            "source_type": "remote",
            "source_ssh_connection_id": 12,
            "agent_machine_id": None,
            "paths": ["/var/tmp/borg-ui/database-dumps/postgresql"],
            "database": {
                "template_id": "postgresql",
                "engine": "PostgreSQL",
                "display_name": "Main PostgreSQL",
                "backup_strategy": "logical_dump",
                "detected_source_path": "/var/lib/postgresql/16/main",
                "detection_label": "backup@db.example",
                "capture_mode": "dump",
                "dump_path": "/var/tmp/borg-ui/database-dumps/postgresql",
                "backup_paths": ["/var/tmp/borg-ui/database-dumps/postgresql"],
                "script_execution_target": "source",
            },
        }
    ]


def test_normalize_source_location_preserves_database_script_assignments():
    locations = normalize_source_locations(
        [
            {
                "source_type": "local",
                "paths": [" /var/tmp/borg-ui/database-dumps/sqlite "],
                "database": {
                    "template_id": " sqlite ",
                    "engine": " SQLite ",
                    "display_name": " App SQLite ",
                    "backup_strategy": " online_backup ",
                    "detected_source_path": " /srv/app/app.db ",
                    "capture_mode": "dump",
                    "dump_path": " /var/tmp/borg-ui/database-dumps/sqlite/app ",
                    "backup_paths": [" /var/tmp/borg-ui/database-dumps/sqlite/app "],
                    "script_execution_target": "source",
                    "pre_backup_script_id": "42",
                    "post_backup_script_id": "43",
                    "pre_backup_script_parameters": {
                        "SQLITE_DATABASE_PATH": " /srv/app/app.db ",
                        "SQLITE_DUMP_DIR": " /var/tmp/borg-ui/database-dumps/sqlite/app ",
                        "": "ignored",
                    },
                    "post_backup_script_parameters": {
                        "SQLITE_DUMP_DIR": " /var/tmp/borg-ui/database-dumps/sqlite/app "
                    },
                    "script_execution_order": "2",
                },
            }
        ]
    )

    assert locations[0]["database"]["pre_backup_script_id"] == 42
    assert locations[0]["database"]["post_backup_script_id"] == 43
    assert locations[0]["database"]["pre_backup_script_parameters"] == {
        "SQLITE_DATABASE_PATH": "/srv/app/app.db",
        "SQLITE_DUMP_DIR": "/var/tmp/borg-ui/database-dumps/sqlite/app",
    }
    assert locations[0]["database"]["post_backup_script_parameters"] == {
        "SQLITE_DUMP_DIR": "/var/tmp/borg-ui/database-dumps/sqlite/app"
    }
    assert locations[0]["database"]["script_execution_order"] == 2


def test_normalize_database_original_capture_uses_source_path_as_backup_path():
    locations = normalize_source_locations(
        [
            {
                "source_type": "local",
                "paths": ["/var/lib/postgresql/16/main"],
                "database": {
                    "template_id": "postgresql",
                    "engine": "PostgreSQL",
                    "display_name": "PostgreSQL database",
                    "backup_strategy": "physical_path",
                    "detected_source_path": "/var/lib/postgresql/16/main",
                    "capture_mode": "original",
                    "dump_path": "",
                    "backup_paths": ["/var/lib/postgresql/16/main"],
                    "script_execution_target": "source",
                },
            }
        ]
    )

    assert locations[0]["database"]["capture_mode"] == "original"
    assert locations[0]["database"]["dump_path"] is None
    assert locations[0]["database"]["backup_paths"] == ["/var/lib/postgresql/16/main"]


def test_database_source_location_rejects_invalid_capture_mode():
    with pytest.raises(ValueError, match="database capture mode"):
        normalize_source_locations(
            [
                {
                    "source_type": "local",
                    "paths": ["/var/tmp/borg-ui/database-dumps/postgresql"],
                    "database": {
                        "template_id": "postgresql",
                        "engine": "PostgreSQL",
                        "display_name": "PostgreSQL database",
                        "backup_strategy": "logical_dump",
                        "capture_mode": "snapshot",
                        "backup_paths": ["/var/tmp/borg-ui/database-dumps/postgresql"],
                    },
                }
            ]
        )


@pytest.mark.parametrize(
    "location",
    [
        {
            "source_type": "remote",
            "source_ssh_connection_id": 1,
            "paths": ["/srv/app"],
            "snapshot": {"provider": "btrfs"},
        },
        {
            "source_type": "agent",
            "agent_machine_id": 1,
            "paths": ["/srv/app"],
            "snapshot": {
                "provider": "zfs",
                "dataset": "tank/app",
                "mountpoint": "/srv/app",
            },
        },
    ],
)
def test_snapshot_locations_must_be_local(location):
    with pytest.raises(ValueError, match="Snapshot source locations require local"):
        normalize_source_locations([location])


@pytest.mark.parametrize(
    "snapshot",
    [
        {"provider": "xfs"},
        {"provider": "btrfs", "staging_path": "relative/path"},
        {"provider": "zfs", "dataset": "", "mountpoint": "/srv/app"},
        {"provider": "zfs", "dataset": "tank/app", "mountpoint": "relative/path"},
    ],
)
def test_snapshot_locations_reject_invalid_config(snapshot):
    with pytest.raises(ValueError, match="snapshot"):
        normalize_source_locations(
            [{"source_type": "local", "paths": ["/srv/app"], "snapshot": snapshot}]
        )


def test_infers_agent_source_location_from_agent_machine_id():
    assert normalize_source_locations(
        [{"agent_machine_id": 4, "paths": ["/data"]}]
    ) == [
        {
            "source_type": "agent",
            "source_ssh_connection_id": None,
            "agent_machine_id": 4,
            "paths": ["/data"],
        }
    ]


def test_remote_source_location_requires_ssh_connection():
    with pytest.raises(ValueError, match="Remote source locations require"):
        normalize_source_locations(
            [
                {
                    "source_type": "remote",
                    "source_ssh_connection_id": None,
                    "paths": ["/data"],
                }
            ]
        )


def test_agent_source_location_requires_agent_machine_id():
    with pytest.raises(ValueError, match="Agent source locations require"):
        normalize_source_locations(
            [{"source_type": "agent", "agent_machine_id": None, "paths": ["/data"]}]
        )


@pytest.mark.parametrize(
    "location",
    [
        {"source_type": "local", "source_ssh_connection_id": 1, "paths": ["/data"]},
        {"source_type": "local", "agent_machine_id": 2, "paths": ["/data"]},
        {
            "source_type": "remote",
            "source_ssh_connection_id": 1,
            "agent_machine_id": 2,
            "paths": ["/data"],
        },
        {
            "source_type": "agent",
            "source_ssh_connection_id": 1,
            "agent_machine_id": 2,
            "paths": ["/data"],
        },
    ],
)
def test_source_location_rejects_conflicting_endpoint_ids(location):
    with pytest.raises(ValueError, match="source locations"):
        normalize_source_locations([location])
