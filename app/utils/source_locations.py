from __future__ import annotations

from typing import Any, Optional

from app.services.filesystem_snapshot_service import normalize_snapshot_config

SourceLocation = dict[str, Any]


def clean_source_paths(paths: Optional[list[str]]) -> list[str]:
    cleaned: list[str] = []
    for path in paths or []:
        value = str(path).strip()
        if value:
            cleaned.append(value)
    return cleaned


def _clean_optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _clean_optional_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _clean_parameter_values(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        if not key:
            continue
        if raw_value is None:
            cleaned[key] = ""
            continue
        cleaned[key] = str(raw_value).strip()
    return cleaned


def normalize_database_config(
    database: Any,
    *,
    source_paths: list[str],
) -> Optional[dict[str, Any]]:
    if not isinstance(database, dict):
        return None

    capture_mode = _clean_optional_string(database.get("capture_mode")) or "dump"
    if capture_mode not in {"dump", "original"}:
        raise ValueError("Invalid database capture mode")

    backup_paths = clean_source_paths(database.get("backup_paths"))
    if not backup_paths:
        backup_paths = list(source_paths)
    if not backup_paths:
        raise ValueError("Database source locations require backup paths")

    dump_path = _clean_optional_string(database.get("dump_path"))
    if capture_mode == "dump" and not dump_path:
        dump_path = backup_paths[0]
    if capture_mode == "original":
        dump_path = None

    script_execution_target = (
        _clean_optional_string(database.get("script_execution_target")) or "source"
    )
    if script_execution_target not in {"source", "server"}:
        raise ValueError("Invalid database script execution target")

    normalized: dict[str, Any] = {
        "template_id": _clean_optional_string(database.get("template_id"))
        or "database",
        "engine": _clean_optional_string(database.get("engine")) or "Database",
        "display_name": _clean_optional_string(database.get("display_name"))
        or _clean_optional_string(database.get("engine"))
        or "Database",
        "backup_strategy": _clean_optional_string(database.get("backup_strategy"))
        or "logical_dump",
        "detected_source_path": _clean_optional_string(
            database.get("detected_source_path")
        ),
        "detection_label": _clean_optional_string(database.get("detection_label")),
        "capture_mode": capture_mode,
        "dump_path": dump_path,
        "backup_paths": backup_paths,
        "script_execution_target": script_execution_target,
    }
    pre_script_id = _clean_optional_int(database.get("pre_backup_script_id"))
    if pre_script_id is not None:
        normalized["pre_backup_script_id"] = pre_script_id
        normalized["pre_backup_script_parameters"] = _clean_parameter_values(
            database.get("pre_backup_script_parameters")
        )

    post_script_id = _clean_optional_int(database.get("post_backup_script_id"))
    if post_script_id is not None:
        normalized["post_backup_script_id"] = post_script_id
        normalized["post_backup_script_parameters"] = _clean_parameter_values(
            database.get("post_backup_script_parameters")
        )

    execution_order = _clean_optional_int(database.get("script_execution_order"))
    if execution_order is not None:
        normalized["script_execution_order"] = execution_order

    return normalized


def normalize_source_locations(
    source_locations: Optional[list[dict[str, Any]]] = None,
    *,
    source_type: str = "local",
    source_ssh_connection_id: Optional[int] = None,
    source_directories: Optional[list[str]] = None,
) -> list[SourceLocation]:
    if source_locations:
        normalized: list[SourceLocation] = []
        for location in source_locations:
            paths = clean_source_paths(location.get("paths"))
            if not paths:
                continue

            location_type = str(location.get("source_type") or "").strip().lower()
            if location_type not in {"local", "remote", "agent"}:
                if location.get("agent_machine_id") not in (None, ""):
                    location_type = "agent"
                elif location.get("source_ssh_connection_id") not in (None, ""):
                    location_type = "remote"
                else:
                    location_type = "local"

            connection_id = location.get("source_ssh_connection_id")
            agent_machine_id = location.get("agent_machine_id")
            if location_type == "local":
                if connection_id not in (None, "") or agent_machine_id not in (
                    None,
                    "",
                ):
                    raise ValueError(
                        "Local source locations cannot include endpoint ids"
                    )
                connection_id = None
                agent_machine_id = None
            elif connection_id in ("", None):
                if location_type == "remote":
                    raise ValueError(
                        "Remote source locations require an SSH connection"
                    )
            else:
                if location_type == "agent":
                    raise ValueError(
                        "Agent source locations cannot include an SSH connection"
                    )
                connection_id = int(connection_id)

            if location_type == "remote":
                if agent_machine_id not in (None, ""):
                    raise ValueError(
                        "Remote source locations cannot include an agent id"
                    )
                agent_machine_id = None
            elif location_type == "agent":
                if agent_machine_id in (None, ""):
                    raise ValueError("Agent source locations require an agent machine")
                agent_machine_id = int(agent_machine_id)
                connection_id = None

            normalized_location = {
                "source_type": location_type,
                "source_ssh_connection_id": connection_id,
                "agent_machine_id": agent_machine_id,
                "paths": paths,
            }
            snapshot = normalize_snapshot_config(
                location.get("snapshot"),
                source_type=location_type,
            )
            if snapshot:
                normalized_location["snapshot"] = snapshot
            database = normalize_database_config(
                location.get("database"),
                source_paths=paths,
            )
            if database:
                normalized_location["database"] = database

            normalized.append(normalized_location)
        return normalized

    paths = clean_source_paths(source_directories)
    if not paths:
        return []

    legacy_type = (
        "remote"
        if source_type == "remote" or source_ssh_connection_id not in (None, "")
        else "local"
    )
    if legacy_type == "remote" and source_ssh_connection_id in (None, ""):
        raise ValueError("Remote source locations require an SSH connection")
    connection_id = (
        int(source_ssh_connection_id)
        if legacy_type == "remote" and source_ssh_connection_id not in (None, "")
        else None
    )
    return [
        {
            "source_type": legacy_type,
            "source_ssh_connection_id": connection_id,
            "agent_machine_id": None,
            "paths": paths,
        }
    ]


def flatten_source_locations(source_locations: list[SourceLocation]) -> list[str]:
    flattened: list[str] = []
    for location in source_locations:
        flattened.extend(clean_source_paths(location.get("paths")))
    return flattened


def legacy_source_fields(
    source_locations: list[SourceLocation],
) -> tuple[str, Optional[int], list[str]]:
    flattened = flatten_source_locations(source_locations)
    if not source_locations:
        return "local", None, flattened

    if len(source_locations) == 1:
        location = source_locations[0]
        location_type = location["source_type"]
        if location_type == "remote":
            return "remote", location["source_ssh_connection_id"], flattened
        if location_type == "agent":
            return "agent", None, flattened
        return "local", None, flattened

    return "mixed", None, flattened


def decode_source_locations(
    value: Optional[str],
    *,
    source_type: str = "local",
    source_ssh_connection_id: Optional[int] = None,
    source_directories: Optional[list[str]] = None,
) -> list[SourceLocation]:
    if value:
        import json

        try:
            decoded = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            decoded = None
        if isinstance(decoded, list):
            return normalize_source_locations(decoded)

    return normalize_source_locations(
        source_type=source_type,
        source_ssh_connection_id=source_ssh_connection_id,
        source_directories=source_directories,
    )
