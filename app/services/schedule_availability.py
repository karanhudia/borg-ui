"""Availability gates shared by availability-triggered backup schedules.

The gate is deliberately side-effect free: an unavailable source is a neutral
skip, never a failed backup job or notification-worthy scheduler exception.
"""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from typing import Iterable
from sqlalchemy.orm import Session

from app.database.database import run_transaction_off_loop
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


@dataclass(frozen=True)
class SSHAddress:
    """Where an SSH source listens, read from its connection before the
    probe: the probe holds no database session."""

    host: str | None
    port: int | None


def _ssh_reachable(connection: SSHAddress) -> bool:
    if not connection.host:
        return False
    try:
        with socket.create_connection(
            (connection.host, connection.port or 22), timeout=3
        ):
            return True
    except OSError:
        return False


# A probe is ("agent", agent machine id, reason) or ("ssh", address, reason),
# with the reason it gives when the source is unavailable. The connections are
# read in a thread, and the read ends before any probe runs: an SSH probe
# takes seconds, and the session would hold its pooled connection meanwhile.


def _ssh_address(db: Session, connection_id) -> SSHAddress | None:
    connection = db.get(SSHConnection, int(connection_id)) if connection_id else None
    if connection is None:
        return None
    return SSHAddress(connection.host, connection.port)


def _repository_probes(db: Session, repositories: list[Repository]) -> list[tuple]:
    probes = []
    for repository in repositories:
        if repository.agent_machine_id is not None:
            probes.append(
                (
                    "agent",
                    repository.agent_machine_id,
                    f"managed agent unavailable for {repository.name}",
                )
            )
        elif repository.source_ssh_connection_id is not None:
            probes.append(
                (
                    "ssh",
                    _ssh_address(db, repository.source_ssh_connection_id),
                    f"SSH source unavailable for {repository.name}",
                )
            )
    return probes


def _location_probes(db: Session, locations: list[dict]) -> list[tuple]:
    probes = []
    for location in locations:
        source_type = location.get("source_type", "local")
        if source_type == "agent":
            probes.append(
                ("agent", location.get("agent_machine_id"), "managed agent unavailable")
            )
        elif source_type == "remote":
            probes.append(
                (
                    "ssh",
                    _ssh_address(db, location.get("source_ssh_connection_id")),
                    "SSH source unavailable",
                )
            )
    return probes


async def _probes_available(probes: list[tuple]) -> AvailabilityDecision:
    """The first unavailable source decides, in the order given."""
    for kind, target, reason in probes:
        if kind == "agent":
            if target is None or not agent_connection_manager.is_connected(int(target)):
                return AvailabilityDecision(False, reason)
        elif target is None or not await asyncio.to_thread(_ssh_reachable, target):
            return AvailabilityDecision(False, reason)
    return AvailabilityDecision(True)


async def repositories_available(
    db: Session, repositories: Iterable[Repository]
) -> AvailabilityDecision:
    """Require every selected source to be available; local sources are available."""
    probes = await run_transaction_off_loop(
        db, _repository_probes, db, list(repositories)
    )
    return await _probes_available(probes)


async def source_locations_available(
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
    probes = await run_transaction_off_loop(db, _location_probes, db, locations)
    return await _probes_available(probes)
