from app.services.backup_plan_execution_service import (
    _app_remote_source_connection_id_for_location,
    _source_script_assignments,
)


def _app_location(**overrides):
    location = {
        "source_type": "remote",
        "source_ssh_connection_id": 4,
        "agent_machine_id": None,
        "paths": ["/srv/immich"],
        "app": {
            "template_id": "immich",
            "root": "/srv/immich",
            "exclude_patterns": [],
            "script_execution_target": "source",
            "pre_backup_script_id": 12,
            "pre_backup_script_parameters": {},
        },
    }
    location.update(overrides)
    return location


def test_app_check_runs_as_a_source_pre_backup_script():
    locations = [
        {"source_type": "local", "paths": ["/home"]},
        _app_location(),
    ]

    [assignment] = _source_script_assignments(locations, "source-pre-backup")

    assert assignment["script_id"] == 12
    assert assignment["source_index"] == 2
    assert _source_script_assignments(locations, "source-post-backup") == []


def test_app_check_runs_on_the_ssh_machine_for_a_remote_source():
    assert _app_remote_source_connection_id_for_location(_app_location()) == 4
    local = _app_location(source_type="local", source_ssh_connection_id=None)
    assert _app_remote_source_connection_id_for_location(local) is None
