from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from app.database.models import Repository
from app.services.repository_executor import EXECUTOR_AGENT, repository_executor_type
from app.utils.source_locations import decode_source_locations

if TYPE_CHECKING:
    from app.database.models import BackupJob


@dataclass(frozen=True)
class BackupRoutePlan:
    supported: bool
    strategy: Optional[str]
    executor: str
    agent_machine_id: Optional[int]
    reason_key: Optional[str] = None
    display_params: dict[str, Any] = field(default_factory=dict)


def _repository_name(repository: Repository) -> str:
    return getattr(repository, "name", None) or f"Repository {repository.id}"


def _is_ssh_repository(repository: Repository) -> bool:
    repository_type = (getattr(repository, "repository_type", "") or "").lower()
    path = getattr(repository, "path", "") or ""
    return bool(
        getattr(repository, "connection_id", None)
        or repository_type == "ssh"
        or path.startswith("ssh://")
    )


def _unsupported(
    repository: Repository,
    *,
    reason_key: str,
    executor: str = "server",
    agent_machine_id: Optional[int] = None,
    extra_params: Optional[dict[str, Any]] = None,
) -> BackupRoutePlan:
    display_params = {
        "repository": _repository_name(repository),
        "agent_machine_id": agent_machine_id
        if agent_machine_id is not None
        else getattr(repository, "agent_machine_id", None),
    }
    if extra_params:
        display_params.update(extra_params)
    return BackupRoutePlan(
        supported=False,
        strategy=None,
        executor=executor,
        agent_machine_id=agent_machine_id,
        reason_key=reason_key,
        display_params=display_params,
    )


def _source_types(source_locations: list[dict[str, Any]]) -> set[str]:
    return {
        str(location.get("source_type") or "local").strip().lower()
        for location in source_locations
    }


def _remote_connection_ids(source_locations: list[dict[str, Any]]) -> set[int]:
    connection_ids: set[int] = set()
    for location in source_locations:
        if location.get("source_type") != "remote":
            continue
        connection_id = location.get("source_ssh_connection_id")
        if connection_id is not None:
            connection_ids.add(int(connection_id))
    return connection_ids


def _agent_machine_ids(source_locations: list[dict[str, Any]]) -> set[int]:
    agent_ids: set[int] = set()
    for location in source_locations:
        if location.get("source_type") != "agent":
            continue
        agent_id = location.get("agent_machine_id")
        if agent_id is not None:
            agent_ids.add(int(agent_id))
    return agent_ids


def plan_repository_route(
    repository: Repository, source_locations: list[dict[str, Any]]
) -> BackupRoutePlan:
    executor_type = repository_executor_type(repository)
    source_types = _source_types(source_locations)
    agent_source_ids = _agent_machine_ids(source_locations)
    remote_connection_ids = _remote_connection_ids(source_locations)
    repo_agent_id = getattr(repository, "agent_machine_id", None)

    if "agent" in source_types and len(source_types) > 1:
        return _unsupported(
            repository,
            reason_key="backend.errors.backupPlans.mixedAgentSourceUnsupported",
            executor=executor_type,
            agent_machine_id=repo_agent_id,
        )

    if executor_type == EXECUTOR_AGENT:
        if getattr(repository, "connection_id", None):
            return _unsupported(
                repository,
                reason_key="backend.errors.backupPlans.agentRepoSshTargetUnsupported",
                executor=EXECUTOR_AGENT,
                agent_machine_id=repo_agent_id,
            )
        if "local" in source_types:
            return _unsupported(
                repository,
                reason_key=(
                    "backend.errors.backupPlans.serverSourceToAgentRepoUnsupported"
                ),
                executor=EXECUTOR_AGENT,
                agent_machine_id=repo_agent_id,
            )
        if "remote" in source_types:
            return _unsupported(
                repository,
                reason_key="backend.errors.backupPlans.sshSourceToAgentRepoUnsupported",
                executor=EXECUTOR_AGENT,
                agent_machine_id=repo_agent_id,
            )
        if agent_source_ids != {int(repo_agent_id)}:
            return _unsupported(
                repository,
                reason_key="backend.errors.backupPlans.agentSourceMismatch",
                executor=EXECUTOR_AGENT,
                agent_machine_id=repo_agent_id,
                extra_params={
                    "source_agent_machine_id": next(iter(agent_source_ids), None)
                },
            )
        return BackupRoutePlan(
            supported=True,
            strategy="agent_direct",
            executor=EXECUTOR_AGENT,
            agent_machine_id=int(repo_agent_id),
            display_params={"repository": _repository_name(repository)},
        )

    if "agent" in source_types:
        return _unsupported(
            repository,
            reason_key="backend.errors.backupPlans.agentSourceToServerRepoUnsupported",
            executor="server",
            agent_machine_id=next(iter(agent_source_ids), None),
        )

    if _is_ssh_repository(repository):
        repo_connection_id = getattr(repository, "connection_id", None)
        if source_types == {"remote"} and remote_connection_ids == {
            int(repo_connection_id)
        }:
            strategy = "remote_direct"
        elif "remote" in source_types:
            strategy = "server_sshfs_pull_then_borg_ssh"
        else:
            strategy = "server_direct_borg_ssh"
    elif "remote" in source_types:
        strategy = "server_sshfs_pull"
    else:
        strategy = "server_direct"

    return BackupRoutePlan(
        supported=True,
        strategy=strategy,
        executor="server",
        agent_machine_id=None,
        display_params={"repository": _repository_name(repository)},
    )


def execution_mode_for_route(route: BackupRoutePlan) -> str:
    if route.executor == EXECUTOR_AGENT:
        return EXECUTOR_AGENT
    if route.strategy == "remote_direct":
        return "remote_ssh"
    return "local"


def source_locations_for_repository(repository: Repository) -> list[dict[str, Any]]:
    source_directories = []
    raw_sources = getattr(repository, "source_directories", None)
    if raw_sources:
        if isinstance(raw_sources, list):
            source_directories = raw_sources
        else:
            try:
                source_directories = json.loads(raw_sources)
            except (TypeError, json.JSONDecodeError):
                source_directories = []
    return decode_source_locations(
        getattr(repository, "source_locations", None),
        source_type="remote"
        if getattr(repository, "source_ssh_connection_id", None)
        else "local",
        source_ssh_connection_id=getattr(repository, "source_ssh_connection_id", None),
        source_directories=source_directories,
    )


def apply_repository_route_to_backup_job(
    backup_job: "BackupJob", repository: Repository
) -> None:
    source_locations = source_locations_for_repository(repository)
    route = plan_repository_route(repository, source_locations)
    if not route.supported:
        return

    backup_job.route_strategy = route.strategy
    backup_job.execution_mode = execution_mode_for_route(route)

    remote_connection_ids = _remote_connection_ids(source_locations)
    if len(remote_connection_ids) == 1:
        backup_job.source_ssh_connection_id = next(iter(remote_connection_ids))
