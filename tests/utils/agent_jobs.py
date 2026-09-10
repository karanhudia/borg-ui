"""The agent job a maintenance operation is handed to, as the server writes it.

`resolve_agent_maintenance_job` correlates an agent's report back to its
operation through `payload["operation"]["maintenance_job"]`, and the marker in
there decides whether it resolves at all. Tests used to hand-roll that dict in
seven modules, so a change to the rule meant editing eight payloads one at a
time and missing others; build them from here instead. With a repository row
the payload comes from `build_agent_repository_operation_payload`, the same
function the server calls, so a test cannot assert against a shape production
no longer writes.
"""

from typing import Any, Optional

from app.database.models import AgentJob, Repository


def maintenance_payload(
    kind: str,
    job_id: int,
    *,
    repository: Optional[Repository] = None,
    table: Optional[str] = "operations",
    operation: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """The payload of an agent job carrying the `kind` operation `job_id`.

    `table=None` builds the shape from before the marker existed, which the
    reaper still honours on purpose; another table name stands in for a job
    queued before the collapse, which resolves to nothing.
    """
    job_kind = f"repository.{kind}"
    if repository is not None:
        from app.services.repository_executor import (
            build_agent_repository_operation_payload,
        )

        payload = build_agent_repository_operation_payload(
            repository,
            job_kind,
            operation=operation,
            maintenance_job_kind=kind,
            maintenance_job_id=job_id,
        )
    else:
        payload = {
            "schema_version": 1,
            "job_kind": job_kind,
            "operation": {
                **(operation or {}),
                "maintenance_job": {
                    "kind": kind,
                    "id": job_id,
                    "table": "operations",
                },
            },
        }
    marker = payload["operation"]["maintenance_job"]
    if table is None:
        marker.pop("table", None)
    else:
        marker["table"] = table
    return payload


def agent_maintenance_job(
    db,
    agent,
    kind: str,
    job_id: int,
    *,
    repository: Optional[Repository] = None,
    status: str = "running",
    table: Optional[str] = "operations",
    operation: Optional[dict[str, Any]] = None,
    commit: bool = True,
    **columns: Any,
) -> AgentJob:
    """An `agent_jobs` row carrying that operation, added to `db`.

    Extra columns (`claimed_at`, `completed_at`, timestamps) pass through.
    """
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status=status,
        payload=maintenance_payload(
            kind, job_id, repository=repository, table=table, operation=operation
        ),
        **columns,
    )
    db.add(job)
    if commit:
        db.commit()
    else:
        db.flush()
    return job
