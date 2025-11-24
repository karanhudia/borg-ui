from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator, Dict, Any
import asyncio
import json
import structlog
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.security import get_current_user
from app.database.models import User
from app.database.database import get_db
from app.core.borg import BorgInterface
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter(tags=["events"])

# Initialize Borg interface
borg = BorgInterface()

# Store active connections for broadcasting
active_connections: Dict[str, asyncio.Queue] = {}

class EventManager:
    """Manages real-time events and broadcasting"""

    def __init__(self):
        self.connections: Dict[str, asyncio.Queue] = {}
        self._lock = None

    @property
    def lock(self):
        """Lazy-load the asyncio lock when event loop is available"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def add_connection(self, user_id: str) -> asyncio.Queue:
        """Add a new connection for a user"""
        async with self.lock:
            queue = asyncio.Queue()
            self.connections[user_id] = queue
            logger.debug("Added SSE connection", user_id=user_id, total_connections=len(self.connections))
            return queue

    async def remove_connection(self, user_id: str):
        """Remove a connection for a user"""
        async with self.lock:
            if user_id in self.connections:
                del self.connections[user_id]
                logger.debug("Removed SSE connection", user_id=user_id, total_connections=len(self.connections))
    
    async def broadcast_event(self, event_type: str, data: Dict[str, Any], user_id: str = None):
        """Broadcast an event to all connections or a specific user"""
        event = {
            "type": event_type,
            "data": data,
            "timestamp": serialize_datetime(datetime.utcnow())
        }

        async with self.lock:
            if user_id:
                # Send to specific user
                if user_id in self.connections:
                    try:
                        await self.connections[user_id].put(event)
                    except Exception as e:
                        logger.error("Failed to send event to user", user_id=user_id, error=str(e))
            else:
                # Broadcast to all users
                for uid, queue in self.connections.items():
                    try:
                        await queue.put(event)
                    except Exception as e:
                        logger.error("Failed to broadcast event to user", user_id=uid, error=str(e))
    
    async def get_connection_count(self) -> int:
        """Get the number of active connections"""
        async with self.lock:
            return len(self.connections)

# Global event manager instance
event_manager = EventManager()

def format_sse_event(event: Dict[str, Any]) -> str:
    """Format an event as Server-Sent Event"""
    return f"data: {json.dumps(event)}\n\n"

async def event_generator(user_id: str) -> AsyncGenerator[str, None]:
    """Generate SSE events for a user"""
    queue = await event_manager.add_connection(user_id)
    
    try:
        # Send initial connection event
        yield format_sse_event({
            "type": "connection_established",
            "data": {"message": "SSE connection established"},
            "timestamp": serialize_datetime(datetime.utcnow())
        })
        
        # Keep connection alive and send events
        while True:
            try:
                # Wait for events with timeout
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield format_sse_event(event)
            except asyncio.TimeoutError:
                # Send keepalive ping
                yield ":\n\n"
            except Exception as e:
                logger.error("Error in event generator", user_id=user_id, error=str(e))
                break
    except Exception as e:
        logger.error("Event generator error", user_id=user_id, error=str(e))
    finally:
        await event_manager.remove_connection(user_id)

@router.get("/stream")
async def stream_events(
    request: Request,
    token: str = None
):
    """Stream real-time events via Server-Sent Events"""
    try:
        # Try to get user from token query parameter (for EventSource)
        # or from Authorization header
        from app.core.security import verify_token
        from app.database.database import SessionLocal

        token_str = None
        if token:
            # Token from query parameter
            token_str = token
        else:
            # Try to get from Authorization header
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token_str = auth_header.split(" ")[1]

        if not token_str:
            raise HTTPException(status_code=401, detail="Not authenticated")

        # Verify token and get username
        username = verify_token(token_str)
        if not username:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")

        # Create a scoped database session just for authentication
        # Close it immediately to avoid holding connections during SSE streaming
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == username).first()
            if not user or not user.is_active:
                raise HTTPException(status_code=401, detail="User not found or inactive")
            user_id = str(user.id)
        finally:
            db.close()  # IMPORTANT: Close DB connection before starting SSE stream

        return StreamingResponse(
            event_generator(user_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Cache-Control"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start event stream", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to start event stream")

# Background task for periodic system status updates
# DISABLED: This was causing excessive borg --version/--help calls every 30 seconds
# Borg version is now cached on startup and doesn't change during runtime
# async def periodic_system_status():
#     """Send periodic system status updates"""
#     while True:
#         try:
#             # Get system information
#             system_info = await borg.get_system_info()
#
#             if system_info["success"]:
#                 await event_manager.broadcast_event(
#                     "system_status",
#                     {
#                         "type": "periodic_update",
#                         "data": system_info
#                     }
#                 )
#
#             # Wait for 30 seconds before next update
#             await asyncio.sleep(30)
#         except Exception as e:
#             logger.error("Error in periodic system status", error=str(e))
#             await asyncio.sleep(30)

# Background task for monitoring backup jobs
async def monitor_backup_jobs():
    """Monitor and update backup job status"""
    while True:
        try:
            # TODO: Implement backup job monitoring
            # This would check the status of running backup jobs
            # and send progress updates via SSE
            
            await asyncio.sleep(5)  # Check every 5 seconds
        except Exception as e:
            logger.error("Error in backup job monitoring", error=str(e))
            await asyncio.sleep(5)

# Startup event to start background tasks
@router.on_event("startup")
async def startup_event():
    """Start background tasks on startup"""
    # asyncio.create_task(periodic_system_status())  # DISABLED: Causes excessive borg command spam
    asyncio.create_task(monitor_backup_jobs())
    logger.info("Started SSE background tasks")
