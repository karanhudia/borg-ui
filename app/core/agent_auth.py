from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import Optional

from app.core.security import verify_password
from app.database.database import get_db
from app.database.models import AgentMachine

AGENT_AUTH_HEADER = "X-Borg-Agent-Authorization"
AGENT_TOKEN_PREFIX_LENGTH = 20


def get_agent_token_from_request(request: Request) -> Optional[str]:
    auth_header = request.headers.get(AGENT_AUTH_HEADER)
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    return auth_header.split(" ", 1)[1].strip()


def _invalid_agent_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"key": "backend.errors.agents.invalidCredentials"},
        headers={"WWW-Authenticate": "Bearer"},
    )


def resolve_agent_from_token(token: Optional[str], db: Session) -> AgentMachine:
    if not token:
        raise _invalid_agent_credentials()

    token_prefix = token[:AGENT_TOKEN_PREFIX_LENGTH]
    candidates = (
        db.query(AgentMachine).filter(AgentMachine.token_prefix == token_prefix).all()
    )

    for agent in candidates:
        if verify_password(token, agent.token_hash):
            if agent.status in ("disabled", "revoked"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"key": "backend.errors.agents.agentDisabled"},
                )
            return agent

    raise _invalid_agent_credentials()


async def get_current_agent(
    request: Request, db: Session = Depends(get_db)
) -> AgentMachine:
    cached_agent = getattr(request.state, "current_agent", None)
    if cached_agent is not None:
        return cached_agent

    token = get_agent_token_from_request(request)
    agent = resolve_agent_from_token(token, db)
    request.state.current_agent = agent
    return agent
