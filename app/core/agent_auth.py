from datetime import datetime
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import Optional

from app.core.security import verify_password
from app.database.database import (
    end_read_keeping_loaded,
    get_db,
    handler_uses_session_on_loop,
)
from app.database.models import AgentMachine

AGENT_AUTH_HEADER = "X-Borg-Agent-Authorization"
AGENT_TOKEN_PREFIX_LENGTH = 20
# An agent in one of these states may not authenticate, and nothing it sends
# may move it back to online.
INACTIVE_AGENT_STATUSES = ("disabled", "revoked", "deleted")


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
            if agent.status in INACTIVE_AGENT_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"key": "backend.errors.agents.agentDisabled"},
                )
            return agent

    raise _invalid_agent_credentials()


# A plain `def`, so FastAPI runs it in the threadpool: the token check is a bcrypt
# comparison, which on the event loop would hold every other request of the
# process, whatever the route itself is.
def get_current_agent(request: Request, db: Session = Depends(get_db)) -> AgentMachine:
    cached_agent = getattr(request.state, "current_agent", None)
    if cached_agent is not None:
        return cached_agent

    token = get_agent_token_from_request(request)
    agent = resolve_agent_from_token(token, db)
    # The token lookup's connection goes back to the pool now, not when the
    # request ends: the handler may first wait for a worker thread or a
    # connection of its own.
    if not handler_uses_session_on_loop(request):
        end_read_keeping_loaded(db, agent)
    request.state.current_agent = agent
    return agent


def agent_is_active(db: Session, agent_machine_id: int) -> bool:
    """Whether the agent may still act, read from the row, not from an object
    loaded earlier in a long-lived session."""
    current = (
        db.query(AgentMachine.status)
        .filter(AgentMachine.id == agent_machine_id)
        .scalar()
    )
    return current is not None and current not in INACTIVE_AGENT_STATUSES


def mark_agent_online(db: Session, agent_machine_id: int, now: datetime) -> bool:
    """Mark an agent online and seen, unless it was revoked, disabled or
    deleted. The WHERE guard decides on the row: an open session or a
    request authenticated before the revocation must not undo it. False
    means the agent is no longer allowed in."""
    marked = (
        db.query(AgentMachine)
        .filter(
            AgentMachine.id == agent_machine_id,
            AgentMachine.status.notin_(INACTIVE_AGENT_STATUSES),
        )
        .update(
            {
                AgentMachine.status: "online",
                AgentMachine.last_seen_at: now,
                AgentMachine.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    return bool(marked)
