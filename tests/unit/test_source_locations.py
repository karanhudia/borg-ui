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
