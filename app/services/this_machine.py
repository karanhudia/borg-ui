""" "This machine": the plan and repository Borg UI creates to protect its host.

Spec: docs/engineering/specs/2026-11-20-this-machine.md
"""

from typing import Optional

from fastapi import HTTPException

THIS_MACHINE_ROLE = "this_machine"


def require_system_delete_confirmed(
    system_role: Optional[str], confirmed: bool
) -> None:
    """Deleting a system plan or repository stops Borg UI protecting the host
    and itself, so the caller has to say it means it."""
    if system_role and not confirmed:
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.thisMachine.confirmDelete"},
        )
