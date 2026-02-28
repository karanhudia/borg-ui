"""
Stats Refresh Scheduler

Periodically refreshes repository statistics (archive count, size, last archive date)
for all repositories. This helps keep dashboard and repository data up-to-date,
especially for observe-only repositories where backups are managed externally.
"""

import asyncio
from datetime import datetime
import structlog
from app.database.models import Repository, SystemSettings
from app.database.database import SessionLocal
from app.api.repositories import update_repository_stats

logger = structlog.get_logger()


class StatsRefreshScheduler:
    """Scheduler for periodic repository stats refresh"""

    def __init__(self):
        self.running = False
        self._current_interval_minutes = 60  # Default interval

    async def refresh_all_repository_stats(self):
        """
        Refresh stats for all repositories.
        Called periodically based on the configured interval.
        """
        db = SessionLocal()
        try:
            now = datetime.utcnow()

            # Get all repositories
            repos = db.query(Repository).all()

            if not repos:
                logger.debug("No repositories to refresh stats for", time=now)
                return

            logger.info("Starting repository stats refresh",
                       count=len(repos),
                       time=now)

            success_count = 0
            error_count = 0

            for repo in repos:
                try:
                    # Refresh stats for this repository
                    result = await update_repository_stats(repo, db)
                    if result:
                        success_count += 1
                        logger.debug("Refreshed stats for repository",
                                   repo_id=repo.id,
                                   repo_name=repo.name)
                    else:
                        error_count += 1
                        logger.warning("Failed to refresh stats for repository",
                                     repo_id=repo.id,
                                     repo_name=repo.name)

                except Exception as e:
                    error_count += 1
                    logger.error("Error refreshing stats for repository",
                               repo_id=repo.id,
                               repo_name=repo.name if repo else "Unknown",
                               error=str(e))
                    # Continue with other repositories even if one fails
                    continue

            # Update last_stats_refresh timestamp
            settings = db.query(SystemSettings).first()
            if settings:
                settings.last_stats_refresh = datetime.utcnow()
                db.commit()

            # Publish one full MQTT snapshot after batch refresh commits.
            try:
                from app.services.mqtt_service import mqtt_service

                mqtt_service.sync_state_with_db(db, reason="repository refresh")
                logger.info("Synced MQTT state after stats refresh")
            except Exception as mqtt_error:
                logger.warning("Failed to sync MQTT state after stats refresh", error=str(mqtt_error))

            logger.info("Completed repository stats refresh",
                       total=len(repos),
                       success=success_count,
                       errors=error_count,
                       duration_repos=len(repos))

        except Exception as e:
            logger.error("Error in refresh_all_repository_stats", error=str(e))
        finally:
            db.close()

    def _get_refresh_interval_minutes(self) -> int:
        """Get the stats refresh interval from system settings"""
        db = SessionLocal()
        try:
            settings = db.query(SystemSettings).first()
            if settings and settings.stats_refresh_interval_minutes is not None:
                return settings.stats_refresh_interval_minutes
            return 60  # Default to 1 hour
        except Exception as e:
            logger.warning("Failed to get stats refresh interval from DB", error=str(e))
            return 60
        finally:
            db.close()

    async def start(self):
        """
        Start the scheduler background loop.
        Runs at the configured interval to refresh repository stats.
        """
        self.running = True
        self._current_interval_minutes = self._get_refresh_interval_minutes()

        if self._current_interval_minutes <= 0:
            logger.info("Stats refresh scheduler disabled (interval=0)")
            return

        logger.info("Stats refresh scheduler started",
                   refresh_interval_minutes=self._current_interval_minutes)

        while self.running:
            try:
                # Re-check interval in case it was changed
                new_interval = self._get_refresh_interval_minutes()

                if new_interval <= 0:
                    logger.info("Stats refresh disabled, stopping scheduler")
                    break

                if new_interval != self._current_interval_minutes:
                    logger.info("Stats refresh interval changed",
                               old_minutes=self._current_interval_minutes,
                               new_minutes=new_interval)
                    self._current_interval_minutes = new_interval

                # Run the refresh
                await self.refresh_all_repository_stats()

            except Exception as e:
                logger.error("Stats refresh scheduler error", error=str(e))

            # Wait for the configured interval before next refresh
            await asyncio.sleep(self._current_interval_minutes * 60)

        logger.info("Stats refresh scheduler stopped")

    def stop(self):
        """Stop the scheduler loop"""
        self.running = False
        logger.info("Stats refresh scheduler stop requested")


# Global instance
stats_refresh_scheduler = StatsRefreshScheduler()
