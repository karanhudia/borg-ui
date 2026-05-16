from __future__ import annotations

import json
from typing import Any, Optional

from pydantic import BaseModel, Field


class SourceLocationPayload(BaseModel):
    source_type: str = "local"
    source_ssh_connection_id: Optional[int] = None
    source_directories: list[str] = Field(default_factory=list)


def decode_json_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return decoded if isinstance(decoded, list) else []


def payload_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return dict(value)


def normalize_source_locations(
    source_locations: Any = None,
    *,
    source_type: str = "local",
    source_ssh_connection_id: Optional[int] = None,
    source_directories: Any = None,
) -> list[dict[str, Any]]:
    if source_locations not in (None, ""):
        raw_locations = decode_json_list(source_locations)
    else:
        legacy_directories = decode_json_list(source_directories)
        raw_locations = (
            [
                {
                    "source_type": source_type,
                    "source_ssh_connection_id": source_ssh_connection_id,
                    "source_directories": legacy_directories,
                }
            ]
            if legacy_directories
            else []
        )

    normalized: list[dict[str, Any]] = []
    for raw in raw_locations:
        if not (
            isinstance(raw, dict) or hasattr(raw, "model_dump") or hasattr(raw, "dict")
        ):
            continue
        location = payload_to_dict(raw)
        location_type = location.get("source_type") or "local"
        connection_id = location.get("source_ssh_connection_id")
        if connection_id is None:
            connection_id = location.get("source_connection_id")
        directories = [
            path.strip()
            for path in decode_json_list(location.get("source_directories"))
            if isinstance(path, str) and path.strip()
        ]
        normalized.append(
            {
                "source_type": location_type,
                "source_ssh_connection_id": (
                    int(connection_id) if connection_id not in (None, "") else None
                ),
                "source_directories": directories,
            }
        )
    return normalized


def source_locations_from_legacy(
    *,
    source_type: str = "local",
    source_ssh_connection_id: Optional[int] = None,
    source_directories: Any = None,
) -> list[dict[str, Any]]:
    return normalize_source_locations(
        None,
        source_type=source_type,
        source_ssh_connection_id=source_ssh_connection_id,
        source_directories=source_directories,
    )


def source_locations_from_record(record: Any) -> list[dict[str, Any]]:
    return normalize_source_locations(
        getattr(record, "source_locations", None),
        source_type=getattr(record, "source_type", None) or "local",
        source_ssh_connection_id=getattr(record, "source_ssh_connection_id", None),
        source_directories=getattr(record, "source_directories", None),
    )


def flatten_source_directories(source_locations: list[dict[str, Any]]) -> list[str]:
    return [
        path
        for location in source_locations
        for path in location.get("source_directories", [])
    ]


def summarize_legacy_source_fields(
    source_locations: list[dict[str, Any]],
) -> tuple[str, Optional[int], list[str]]:
    source_directories = flatten_source_directories(source_locations)
    if len(source_locations) == 1:
        location = source_locations[0]
        return (
            location["source_type"],
            location["source_ssh_connection_id"]
            if location["source_type"] == "remote"
            else None,
            source_directories,
        )
    return "mixed" if source_locations else "local", None, source_directories
