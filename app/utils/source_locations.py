from __future__ import annotations

from typing import Any, Optional

SourceLocation = dict[str, Any]


def clean_source_paths(paths: Optional[list[str]]) -> list[str]:
    cleaned: list[str] = []
    for path in paths or []:
        value = str(path).strip()
        if value:
            cleaned.append(value)
    return cleaned


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

            normalized.append(
                {
                    "source_type": location_type,
                    "source_ssh_connection_id": connection_id,
                    "agent_machine_id": agent_machine_id,
                    "paths": paths,
                }
            )
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
