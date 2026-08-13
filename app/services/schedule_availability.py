"""Availability gates shared by availability-triggered backup schedules.

The gate is deliberately side-effect free: an unavailable source is a neutral
skip, never a failed backup job or notification-worthy scheduler exception.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Iterable
from sqlalchemy.orm import Session

from app.database.models import Repository, SSHConnection
from app.services.agent_connection_manager import agent_connection_manager

DEFAULT_AVAILABILITY_CHECK_INTERVAL_MINUTES = 30
MIN_AVAILABILITY_CHECK_INTERVAL_MINUTES = 1
MAX_AVAILABILITY_CHECK_INTERVAL_MINUTES = 24 * 60
MAX_MIN_SUCCESS_INTERVAL_MINUTES = 365 * 24 * 60


@dataclass(frozen=True)
class AvailabilityDecision:
    available: bool
    reason: str | None = None


def validate_availability_intervals(
    check_minutes: int, min_success_minutes: int
) -> None:
    if (
        not MIN_AVAILABILITY_CHECK_INTERVAL_MINUTES
        <= check_minutes
        <= MAX_AVAILABILITY_CHECK_INTERVAL_MINUTES
    ):
        raise ValueError(
            "availability_check_interval_minutes must be between 1 and 1440"
        )
    if not 0 <= min_success_minutes <= MAX_MIN_SUCCESS_INTERVAL_MINUTES:
        raise ValueError("min_success_interval_minutes must be between 0 and 525600")


def _ssh_reachable(connection: SSHConnection) -> bool:
    if not connection.host:
        return False
    try:
        with socket.create_connection(
            (connection.host, connection.port or 22), timeout=3
        ):
            return True
    except OSError:
        return False


def repositories_available(
    db: Session, repositories: Iterable[Repository]
) -> AvailabilityDecision:
    """Require every selected source to be available; local sources are available."""
    for repository in repositories:
        if repository.agent_machine_id is not None:
            if not agent_connection_manager.is_connected(repository.agent_machine_id):
                return AvailabilityDecision(
                    False, f"managed agent unavailable for {repository.name}"
                )
            continue
        if repository.source_ssh_connection_id is not None:
            connection = db.get(SSHConnection, repository.source_ssh_connection_id)
            if connection is None or not _ssh_reachable(connection):
                return AvailabilityDecision(
                    False, f"SSH source unavailable for {repository.name}"
                )
    return AvailabilityDecision(True)


def source_locations_available(
    db: Session,
    locations: Iterable[dict],
    *,
    fallback_source_type: str = "local",
    fallback_ssh_connection_id: int | None = None,
) -> AvailabilityDecision:
    """Check plan source locations, falling back to the plan's legacy source fields."""
    locations = list(locations)
    if not locations:
        locations = [
            {
                "source_type": fallback_source_type,
                "source_ssh_connection_id": fallback_ssh_connection_id,
            }
        ]
    for location in locations:
        source_type = location.get("source_type", "local")
        if source_type == "agent":
            agent_id = location.get("agent_machine_id")
            if agent_id is None or not agent_connection_manager.is_connected(
                int(agent_id)
            ):
                return AvailabilityDecision(False, "managed agent unavailable")
        elif source_type == "remote":
            connection_id = location.get("source_ssh_connection_id")
            connection = (
                db.get(SSHConnection, int(connection_id)) if connection_id else None
            )
            if connection is None or not _ssh_reachable(connection):
                return AvailabilityDecision(False, "SSH source unavailable")
    return AvailabilityDecision(True)
