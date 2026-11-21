""" "This machine" API: set up and report on the host protection plan."""

from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import (
    get_current_admin_user,
    get_current_user,
    refuse_mcp_internal,
)
from app.database.database import get_db
from app.database.models import User
from app.services import this_machine as tm

router = APIRouter(
    prefix="/this-machine",
    tags=["This machine"],
    dependencies=[Depends(refuse_mcp_internal)],
)


class ThisMachineStatus(BaseModel):
    configured: bool
    plan_id: Optional[int] = None
    repository_id: Optional[int] = None
    in_data_volume: bool
    self_backup_supported: bool
    read_all_access: bool


def _self_backup_supported() -> bool:
    return settings.database_url.startswith("sqlite")


@router.get("", response_model=ThisMachineStatus)
def get_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ThisMachineStatus:
    plan = tm.system_plan(db)
    repository = tm.system_repository(db)
    if repository is not None:
        in_data_volume = tm.repository_in_data_volume(repository)
    else:
        _, _, _, in_data_volume = tm.plan_sources()
    return ThisMachineStatus(
        configured=plan is not None,
        plan_id=plan.id if plan else None,
        repository_id=repository.id if repository else None,
        in_data_volume=in_data_volume,
        self_backup_supported=_self_backup_supported(),
        read_all_access=tm.has_read_all(tm._host_root()),
    )


@router.get("/estimate")
def get_estimate(current_user: User = Depends(get_current_admin_user)) -> dict:
    sources, excludes, _, in_data_volume = tm.plan_sources()
    estimate = tm.estimate_size(sources, excludes)
    return {
        "bytes": estimate.bytes,
        "complete": estimate.complete,
        "in_data_volume": in_data_volume,
    }


@router.post("/setup", status_code=201)
async def setup(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> dict:
    return asdict(await tm.setup_this_machine(db, current_user))
