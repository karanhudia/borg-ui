import secrets
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import structlog

from app.database.database import get_db
from app.database.models import ApiToken
from app.core.security import get_current_user, get_password_hash
from app.database.models import User
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter(tags=["tokens"])


class TokenCreate(BaseModel):
    name: str


class TokenResponse(BaseModel):
    id: int
    name: str
    prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


class TokenCreatedResponse(BaseModel):
    id: int
    name: str
    token: str
    prefix: str
    created_at: datetime

    class Config:
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


@router.get("/settings/tokens", response_model=list[TokenResponse])
async def list_tokens(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tokens = db.query(ApiToken).filter(ApiToken.user_id == current_user.id).all()
    return tokens


@router.post("/settings/tokens", response_model=TokenCreatedResponse, status_code=201)
async def create_token(
    payload: TokenCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.name.strip():
        raise HTTPException(
            status_code=422,
            detail={"key": "backend.errors.tokens.nameRequired"},
        )

    raw_token = "borgui_" + secrets.token_urlsafe(32)
    prefix = raw_token[:12]
    token_hash = get_password_hash(raw_token)

    token = ApiToken(
        user_id=current_user.id,
        name=payload.name.strip(),
        token_hash=token_hash,
        prefix=prefix,
        created_at=datetime.now(timezone.utc),
    )
    db.add(token)
    db.commit()
    db.refresh(token)

    logger.info(
        "API token created", user=current_user.username, token_name=payload.name
    )

    return TokenCreatedResponse(
        id=token.id,
        name=token.name,
        token=raw_token,
        prefix=token.prefix,
        created_at=token.created_at,
    )


@router.delete("/settings/tokens/{token_id}", status_code=204)
async def revoke_token(
    token_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token = db.query(ApiToken).filter(ApiToken.id == token_id).first()
    if not token:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.tokens.notFound"}
        )
    if token.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"key": "backend.errors.tokens.cannotRevokeOtherUsersToken"},
        )

    db.delete(token)
    db.commit()
    logger.info("API token revoked", user=current_user.username, token_id=token_id)
