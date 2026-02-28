"""
MQTT Sync Scheduler for Borg Web UI.

Periodically synchronizes repository state with MQTT broker to ensure
Home Assistant devices stay in sync with database changes.
"""

import asyncio

import structlog

from app.services.mqtt_service import mqtt_service

logger = structlog.get_logger()

async def periodic_mqtt_sync(interval_minutes: int = 5):
    """
    Periodically publish DB-derived MQTT state to keep HA fully consistent.
    
    Args:
        interval_minutes: Sync interval in minutes (default: 5)
    """
    logger.info("Starting MQTT sync scheduler", interval_minutes=interval_minutes)
    
    while True:
        try:
            mqtt_service.sync_state(reason="periodic_scheduler")
            logger.info("MQTT periodic sync completed")
        except Exception as e:
            logger.error("Error in MQTT sync loop", error=str(e))
        
        # Wait for next interval
        await asyncio.sleep(interval_minutes * 60)

async def start_mqtt_sync_scheduler():
    """Start the MQTT sync scheduler with default 5-minute interval."""
    logger.info("Starting MQTT sync scheduler with 5-minute interval")
    await periodic_mqtt_sync(5)
