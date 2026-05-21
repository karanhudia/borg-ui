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
