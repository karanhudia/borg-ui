"""
MQTT service for Borg Web UI.

Home Assistant sensor state is always published from database state so that:
- state can be fully reconstructed from DB records
- reconnect/startup/periodic sync all use one code path
- change-triggered syncs stay simple
"""

import datetime
import json
from typing import Any, Dict, List, Optional, Set

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.database.models import BackupJob, MQTTSyncState, Repository
from app.utils.datetime_utils import serialize_datetime

import paho.mqtt.client as mqtt

logger = structlog.get_logger()

REPOSITORY_SYNC_STATE_KEY = "home_assistant_repo_ids_v1"
PENDING_DELETED_REPOSITORY_SYNC_STATE_KEY = "home_assistant_deleted_repo_ids_v1"
TERMINAL_JOB_STATUSES = {
    "completed",
    "completed_with_warnings",
    "failed",
    "cancelled",
}
REPOSITORY_SENSOR_DEFINITIONS = [
    {
        "component": "sensor",
        "suffix": "status",
        "topic_suffix": "status",
        "name": "Status",
        "value_template": "{{ value_json.status }}",
        "icon": "mdi:database-check",
    },
    {
        "component": "sensor",
        "suffix": "size",
        "topic_suffix": "size",
        "name": "Size",
        "value_template": "{{ value_json.used }}",
        "unit_of_measurement": "B",
        "device_class": "data_size",
        "icon": "mdi:harddisk",
    },
    {
        "component": "sensor",
        "suffix": "archives",
        "topic_suffix": "archives",
        "name": "Archives",
        "value_template": "{{ value_json.count }}",
        "icon": "mdi:archive",
    },
    {
        "component": "sensor",
        "suffix": "last_backup",
        "topic_suffix": "last_backup",
        "name": "Last Backup",
        "value_template": "{{ value_json.timestamp }}",
        "device_class": "timestamp",
        "icon": "mdi:clock-outline",
    },
    {
        "component": "sensor",
        "suffix": "backup_status",
        "topic_suffix": "backup/status",
        "name": "Backup Status",
        "value_template": "{{ value_json.status }}",
        "icon": "mdi:database-sync",
    },
    {
        "component": "sensor",
        "suffix": "backup_progress",
        "topic_suffix": "backup/progress",
        "name": "Backup Progress",
        "value_template": "{{ value_json.percent | int }}",
        "unit_of_measurement": "%",
        "state_class": "measurement",
        "icon": "mdi:progress-clock",
    },
    {
        "component": "sensor",
        "suffix": "backup_eta",
        "topic_suffix": "backup/progress",
        "name": "Backup ETA",
        "value_template": "{{ value_json.eta_timestamp }}",
        "device_class": "timestamp",
        "icon": "mdi:timer-outline",
    },
]
REPOSITORY_DISCOVERY_COMPONENTS = [
    (definition["component"], definition["suffix"])
    for definition in REPOSITORY_SENSOR_DEFINITIONS
]
REPOSITORY_STATE_TOPICS = [
    "status",
    "size",
    "archives",
    "last_backup",
    "backup/status",
    "backup/progress",
]

def _get_app_version():
    #TODO provide actual version
    return "unknown"

def _serialize_first_datetime(
    *values: Optional[datetime.datetime],
) -> Optional[str]:
    """Serialize the first non-null datetime from a list of candidates."""
    for value in values:
        if value is not None:
            return serialize_datetime(value)
    return None


class MQTTSyncStateStore:
    """Persistence helper for MQTT sync marker rows."""

    @staticmethod
    def load_id_set(db: Session, sync_key: str) -> Set[int]:
        """Load a set[int] sync marker from DB."""
        try:
            state_row = (
                db.query(MQTTSyncState)
                .filter(MQTTSyncState.sync_key == sync_key)
                .first()
            )
            if not state_row or not state_row.sync_value:
                return set()

            parsed = json.loads(state_row.sync_value)
            if not isinstance(parsed, list):
                logger.warning(
                    "Invalid MQTT sync metadata shape; expected list",
                    sync_key=sync_key,
                )
                return set()

            return {int(item) for item in parsed}
        except Exception as e:
            logger.warning(
                "Failed loading MQTT sync metadata",
                sync_key=sync_key,
                error=str(e),
            )
            return set()

    @staticmethod
    def save_id_set(
        db: Session,
        sync_key: str,
        id_set: Set[int],
        commit: bool = True,
    ) -> None:
        """Persist a set[int] sync marker to DB."""
        state_value = json.dumps(sorted(id_set))
        state_row = (
            db.query(MQTTSyncState)
            .filter(MQTTSyncState.sync_key == sync_key)
            .first()
        )

        if state_row:
            state_row.sync_value = state_value
        else:
            db.add(
                MQTTSyncState(
                    sync_key=sync_key,
                    sync_value=state_value,
                )
            )

        if commit:
            db.commit()


class BackupJobQueryService:
    """Read-model queries for per-repository backup jobs."""

    @staticmethod
    def _latest_jobs_subquery(
        db: Session,
        *,
        status_filter: Optional[str] = None,
        order_field: Any = BackupJob.created_at,
    ):
        query = (
            db.query(
                BackupJob.id.label("job_id"),
                BackupJob.repository.label("repository"),
                BackupJob.status.label("status"),
                func.row_number()
                .over(
                    partition_by=BackupJob.repository,
                    order_by=(order_field.desc(), BackupJob.id.desc()),
                )
                .label("row_num"),
            )
            .filter(BackupJob.repository.isnot(None))
        )
        if status_filter:
            query = query.filter(BackupJob.status == status_filter)
        return query.subquery()

    def fetch_failed_repositories(
        self,
        db: Session,
        path_to_id: Dict[str, int],
    ) -> Set[int]:
        """Return repository IDs whose latest backup job failed."""
        if not path_to_id:
            return set()

        latest_jobs = self._latest_jobs_subquery(db)
        latest_rows = (
            db.query(
                latest_jobs.c.repository,
                latest_jobs.c.status,
            )
            .filter(
                latest_jobs.c.row_num == 1,
                latest_jobs.c.repository.in_(list(path_to_id.keys())),
            )
            .all()
        )

        failed_ids: Set[int] = set()
        for repository_path, status in latest_rows:
            if status != "failed":
                continue
            repo_id = path_to_id.get(repository_path)
            if repo_id:
                failed_ids.add(repo_id)
        return failed_ids

    def fetch_latest_backup_jobs_by_repository(
        self,
        db: Session,
    ) -> Dict[str, BackupJob]:
        """
        Return latest backup job row per repository path.

        Uses a window function so only one row per repository is materialized.
        """
        latest_jobs = self._latest_jobs_subquery(db)
        rows = (
            db.query(BackupJob)
            .join(latest_jobs, BackupJob.id == latest_jobs.c.job_id)
            .filter(latest_jobs.c.row_num == 1)
            .all()
        )
        return {job.repository: job for job in rows if job.repository}

    def fetch_running_backup_jobs_by_repository(
        self,
        db: Session,
    ) -> Dict[str, BackupJob]:
        """Return latest running backup job row per repository path."""
        latest_running_jobs = self._latest_jobs_subquery(
            db,
            status_filter="running",
            order_field=func.coalesce(BackupJob.started_at, BackupJob.created_at),
        )
        rows = (
            db.query(BackupJob)
            .join(latest_running_jobs, BackupJob.id == latest_running_jobs.c.job_id)
            .filter(latest_running_jobs.c.row_num == 1)
            .all()
        )
        return {job.repository: job for job in rows if job.repository}


class HomeAssistantDiscoveryPublisher:
    """Home Assistant discovery and retained-topic cleanup publisher."""

    def __init__(self, mqtt_service: "MQTTService"):
        self._mqtt_service = mqtt_service

    def get_home_assistant_device_info(
        self,
        is_repository: bool = False,
        repo_id: Optional[int] = None,
        repository_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build Home Assistant device metadata for discovery payloads."""
        if is_repository:
            return {
                "identifiers": [f"borg_ui_repo_{repo_id}"],
                "name": repository_name or f"Repository {repo_id}",
                "manufacturer": self._mqtt_service.config[
                    "home_assistant_device_manufacturer"
                ],
                "model": "Repository",
                "sw_version": _get_app_version(),
                "via_device": self._mqtt_service.config[
                    "home_assistant_device_identifiers"
                ],
            }

        return {
            "identifiers": [
                self._mqtt_service.config["home_assistant_device_identifiers"]
            ],
            "name": self._mqtt_service.config["home_assistant_device_name"],
            "manufacturer": self._mqtt_service.config[
                "home_assistant_device_manufacturer"
            ],
            "model": "Server",
            "sw_version": _get_app_version(),
        }

    def publish_home_assistant_discovery(
        self,
        component: str,
        config: Dict[str, Any],
        node_id: str,
        is_repository: bool = False,
        repo_id: Optional[int] = None,
        repository_name: Optional[str] = None,
    ) -> bool:
        """Publish Home Assistant MQTT discovery message."""
        if (
            not self._mqtt_service.config["home_assistant_enabled"]
            or not self._mqtt_service.config["enabled"]
        ):
            logger.debug("Home Assistant MQTT discovery disabled")
            return False

        discovery_topic = (
            f"homeassistant/{component}/{node_id}/{config['unique_id']}/config"
        )
        discovery_config = config.copy()
        discovery_config["device"] = self.get_home_assistant_device_info(
            is_repository,
            repo_id,
            repository_name,
        )
        discovery_config["availability"] = [
            {
                "topic": f"{self._mqtt_service.config['base_topic']}/status",
                "value_template": "{{ value_json.status }}",
                "payload_available": "online",
                "payload_not_available": "offline",
            }
        ]

        return self._mqtt_service.publish(
            discovery_topic,
            discovery_config,
            qos=1,
            use_base_topic=False,
        )

    def setup_home_assistant_sensors(self) -> bool:
        """Publish Home Assistant discovery messages for server sensors."""
        if (
            not self._mqtt_service.config["home_assistant_enabled"]
            or not self._mqtt_service.config["enabled"]
        ):
            return False

        node_id = self._mqtt_service.config["home_assistant_device_identifiers"]
        base_topic = self._mqtt_service.config["base_topic"]

        last_backup_sensor = {
            "name": "Last Backup",
            "unique_id": f"{node_id}_last_backup",
            "state_topic": f"{base_topic}/backup/last",
            "json_attributes_topic": f"{base_topic}/backup/last",
            "json_attributes_template": "{{ value_json | tojson }}",
            "value_template": "{{ value_json.timestamp }}",
            "device_class": "timestamp",
            "icon": "mdi:clock-outline",
        }

        backup_binary_sensor = {
            "name": "Backup State",
            "unique_id": f"{node_id}_backup_success",
            "state_topic": f"{base_topic}/backup/success",
            "json_attributes_topic": f"{base_topic}/backup/success",
            "json_attributes_template": "{{ value_json | tojson }}",
            "value_template": "{{ value_json.success }}",
            "payload_on": "false",
            "payload_off": "true",
            "icon": "mdi:check-circle",
            "device_class": "problem",
        }

        success = True
        if not self.publish_home_assistant_discovery(
            "sensor",
            last_backup_sensor,
            node_id,
        ):
            success = False
        if not self.publish_home_assistant_discovery(
            "binary_sensor",
            backup_binary_sensor,
            node_id,
        ):
            success = False
        return success

    def _build_repository_sensor_config(
        self,
        definition: Dict[str, Any],
        repository_id: int,
        node_id: str,
        repo_topic: str,
    ) -> Dict[str, Any]:
        state_topic = f"{repo_topic}/{definition['topic_suffix']}"
        sensor_config: Dict[str, Any] = {
            "name": definition["name"],
            "unique_id": f"{node_id}_repo_{repository_id}_{definition['suffix']}",
            "state_topic": state_topic,
            "value_template": definition["value_template"],
        }

        if definition.get("include_json_attributes", True):
            sensor_config["json_attributes_topic"] = state_topic
            sensor_config["json_attributes_template"] = "{{ value_json | tojson }}"

        passthrough_keys = (
            "unit_of_measurement",
            "device_class",
            "state_class",
            "icon",
            "payload_on",
            "payload_off",
        )
        for key in passthrough_keys:
            value = definition.get(key)
            if value is not None:
                sensor_config[key] = value
        return sensor_config

    def setup_repository_sensors(
        self,
        repository_id: int,
        repository_name: str,
    ) -> bool:
        """Publish Home Assistant discovery messages for repository sensors."""
        if (
            not self._mqtt_service.config["home_assistant_enabled"]
            or not self._mqtt_service.config["enabled"]
        ):
            return False

        node_id = self._mqtt_service.config["home_assistant_device_identifiers"]
        base_topic = self._mqtt_service.config["base_topic"]
        repo_topic = f"{base_topic}/repositories/{repository_id}"
        success = True

        for definition in REPOSITORY_SENSOR_DEFINITIONS:
            sensor_config = self._build_repository_sensor_config(
                definition,
                repository_id,
                node_id,
                repo_topic,
            )
            if not self.publish_home_assistant_discovery(
                definition["component"],
                sensor_config,
                node_id,
                is_repository=True,
                repo_id=repository_id,
                repository_name=repository_name,
            ):
                success = False
        return success

    def remove_repository_from_home_assistant(self, repository_id: int) -> bool:
        """
        Remove all retained discovery/state topics for a deleted repository.

        Empty retained payload on discovery topics tells Home Assistant to delete
        entities.
        """
        node_id = self._mqtt_service.config["home_assistant_device_identifiers"]
        success = True

        for component, suffix in REPOSITORY_DISCOVERY_COMPONENTS:
            unique_id = f"{node_id}_repo_{repository_id}_{suffix}"
            discovery_topic = (
                f"homeassistant/{component}/{node_id}/{unique_id}/config"
            )
            if not self._mqtt_service._publish_raw(
                discovery_topic,
                "",
                qos=1,
                use_base_topic=False,
            ):
                success = False

        for suffix in REPOSITORY_STATE_TOPICS:
            if not self._mqtt_service._publish_raw(
                f"repositories/{repository_id}/{suffix}",
                "",
                qos=1,
            ):
                success = False

        return success


class ServerStatePublisher:
    """Publishes broker state for server-wide backup sensors."""

    def __init__(self, mqtt_service: "MQTTService"):
        self._mqtt_service = mqtt_service

    def publish_server_state_from_db(self, db: Session) -> bool:
        """Publish server-level sensor topics from backup_jobs table."""
        running_job = (
            db.query(BackupJob)
            .filter(BackupJob.status == "running")
            .order_by(BackupJob.started_at.desc(), BackupJob.id.desc())
            .first()
        )
        latest_job = (
            db.query(BackupJob)
            .order_by(BackupJob.created_at.desc(), BackupJob.id.desc())
            .first()
        )
        latest_terminal_job = (
            db.query(BackupJob)
            .filter(BackupJob.status.in_(TERMINAL_JOB_STATUSES))
            .order_by(BackupJob.completed_at.desc(), BackupJob.id.desc())
            .first()
        )

        running_timestamp = (
            _serialize_first_datetime(
                running_job.started_at,
                running_job.created_at,
                running_job.completed_at,
            )
            if running_job
            else None
        )
        terminal_timestamp = (
            _serialize_first_datetime(
                latest_terminal_job.completed_at,
                latest_terminal_job.started_at,
                latest_terminal_job.created_at,
            )
            if latest_terminal_job
            else None
        )
        latest_job_timestamp = (
            _serialize_first_datetime(
                latest_job.completed_at,
                latest_job.started_at,
                latest_job.created_at,
            )
            if latest_job
            else None
        )
        idle_timestamp = terminal_timestamp or latest_job_timestamp

        status_payload: Dict[str, Any] = {
            "status": "running" if running_job else "idle",
            "timestamp": running_timestamp if running_job else idle_timestamp,
        }
        if running_job:
            status_payload["job_id"] = running_job.id
            status_payload["repository"] = running_job.repository
        elif latest_job:
            status_payload["last_job_id"] = latest_job.id
            status_payload["last_job_status"] = latest_job.status
            status_payload["repository"] = latest_job.repository

        if running_job:
            progress_value = running_job.progress_percent
            if progress_value is None:
                progress_value = float(running_job.progress or 0)
            estimated_time_remaining = int(running_job.estimated_time_remaining or 0)

            # Calculate ETA timestamp
            eta_timestamp = None
            if estimated_time_remaining > 0:
                eta_time = (datetime.datetime.now(datetime.timezone.utc) +
                            datetime.timedelta(seconds=estimated_time_remaining))
                eta_timestamp = serialize_datetime(eta_time)

            progress_payload: Dict[str, Any] = {
                "status": "running",
                "percent": round(float(progress_value), 2),
                "job_id": running_job.id,
                "repository": running_job.repository,
                "timestamp": running_timestamp,
                "eta_timestamp": eta_timestamp,
            }
        else:
            progress_payload = {
                "status": "idle",
                "timestamp": idle_timestamp,
            }

        if latest_terminal_job:
            last_payload: Dict[str, Any] = {
                "timestamp": terminal_timestamp,
                "status": latest_terminal_job.status,
                "job_id": latest_terminal_job.id,
                "repository": latest_terminal_job.repository,
            }
            success_value = latest_terminal_job.status in {
                "completed",
                "completed_with_warnings",
            }
            success_payload: Dict[str, Any] = {
                "success": str(success_value).lower(),
                "timestamp": terminal_timestamp,
                "status": latest_terminal_job.status,
                "job_id": latest_terminal_job.id,
                "repository": latest_terminal_job.repository,
            }
            if not success_value and latest_terminal_job.error_message:
                success_payload["error"] = latest_terminal_job.error_message
        else:
            last_payload = {"timestamp": None}
            success_payload = {"success": "true", "timestamp": None}

        success = True
        if not self._mqtt_service.publish("backup/status", status_payload, qos=1):
            success = False
        if not self._mqtt_service.publish("backup/progress", progress_payload, qos=1):
            success = False
        if not self._mqtt_service.publish("backup/last", last_payload, qos=1):
            success = False
        if not self._mqtt_service.publish("backup/success", success_payload, qos=1):
            success = False
        return success


class RepositoryStatePublisher:
    """Maps repository/job records to per-repository MQTT topic payloads."""

    def __init__(self, mqtt_service: "MQTTService"):
        self._mqtt_service = mqtt_service

    def publish_repository_data(
        self,
        repository: Repository,
        failed_repository_ids: Set[int],
        latest_jobs_by_repository: Dict[str, BackupJob],
        running_jobs_by_repository: Dict[str, BackupJob],
    ) -> bool:
        """Publish all per-repository state topics from repository table."""
        try:
            success = True
            size_bytes = self.parse_size_to_bytes(repository.total_size or "0")
            if not self._mqtt_service.publish_repository_size(
                repository.id,
                size_bytes,
                0,
                size_bytes,
            ):
                success = False

            archive_count = repository.archive_count or 0
            if not self._mqtt_service.publish_repository_archives(
                repository.id,
                archive_count,
            ):
                success = False

            timestamp = (
                serialize_datetime(repository.last_backup)
                if repository.last_backup
                else None
            )
            if not self._mqtt_service.publish_repository_last_backup(
                repository.id,
                timestamp,
                repository.path,
            ):
                success = False

            status = self.get_repository_status(repository, failed_repository_ids)
            if not self._mqtt_service.publish_repository_status(
                repository.id,
                status,
                repository.path,
            ):
                success = False

            running_job = running_jobs_by_repository.get(repository.path)
            latest_job = latest_jobs_by_repository.get(repository.path)
            running_timestamp = (
                _serialize_first_datetime(
                    running_job.started_at,
                    running_job.created_at,
                    running_job.completed_at,
                )
                if running_job
                else None
            )
            latest_job_timestamp = (
                _serialize_first_datetime(
                    latest_job.completed_at,
                    latest_job.started_at,
                    latest_job.created_at,
                )
                if latest_job
                else None
            )
            status_timestamp = running_timestamp or latest_job_timestamp

            eta_timestamp = None
            if running_job:
                progress_value = running_job.progress_percent
                if progress_value is None:
                    progress_value = float(running_job.progress or 0)

                # Map progress to backup status phases (matching UI logic)
                if progress_value == 0:
                    backup_status = "initializing"
                elif progress_value >= 100:
                    backup_status = "finalizing"
                else:
                    backup_status = "processing files"

                backup_status_job_id = running_job.id
                last_job_status = running_job.status
                progress_status = "running"
                progress_job_id = running_job.id
                estimated_time_remaining = int(running_job.estimated_time_remaining or 0)
                # Calculate ETA timestamp
                if estimated_time_remaining > 0:
                    eta_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=estimated_time_remaining)
                    eta_timestamp = serialize_datetime(eta_time)
            elif latest_job:
                backup_status = latest_job.status
                backup_status_job_id = latest_job.id
                last_job_status = latest_job.status
                progress_value = 0.0
                progress_status = "idle"
                progress_job_id = None
            else:
                backup_status = "idle"
                backup_status_job_id = None
                last_job_status = None
                progress_value = 0.0
                progress_status = "idle"
                progress_job_id = None

            if not self._mqtt_service.publish_repository_backup_status(
                repository.id,
                backup_status,
                repository.path,
                backup_status_job_id,
                last_job_status,
                status_timestamp,
            ):
                success = False
            if not self._mqtt_service.publish_repository_backup_progress(
                repository.id,
                progress_value,
                progress_status,
                repository.path,
                progress_job_id,
                status_timestamp,
                eta_timestamp,
            ):
                success = False
            return success
        except Exception as e:
            logger.error(
                "Failed to publish repository data",
                repository_id=repository.id,
                error=str(e),
                exc_info=True,
            )
            return False

    @staticmethod
    def parse_size_to_bytes(size_str: str) -> int:
        """Parse human-readable size string to bytes."""
        if not size_str:
            return 0

        normalized = size_str.strip().upper().replace(" ", "")
        multipliers = [
            ("PB", 1024**5),
            ("TB", 1024**4),
            ("GB", 1024**3),
            ("MB", 1024**2),
            ("KB", 1024),
            ("B", 1),
        ]

        for unit, multiplier in multipliers:
            if normalized.endswith(unit):
                try:
                    number = float(normalized[: -len(unit)])
                    return int(number * multiplier)
                except ValueError:
                    return 0

        try:
            return int(float(normalized))
        except ValueError:
            return 0

    @staticmethod
    def get_repository_status(
        repository: Repository,
        failed_repository_ids: Optional[Set[int]] = None,
    ) -> str:
        """Determine repository health from DB-derived fields."""
        failed_repository_ids = failed_repository_ids or set()
        repository_id = getattr(repository, "id", None)
        if repository_id in failed_repository_ids:
            return "failed"
        if not repository.last_backup:
            return "no_backup"

        now = datetime.datetime.now(datetime.timezone.utc)
        last_backup = repository.last_backup

        if last_backup.tzinfo is None:
            last_backup = last_backup.replace(tzinfo=datetime.timezone.utc)
        else:
            last_backup = last_backup.astimezone(datetime.timezone.utc)

        days_since_backup = (now - last_backup).days
        if days_since_backup > 7:
            return "stale"
        if days_since_backup > 3:
            return "warning"
        return "healthy"


def build_mqtt_runtime_config(settings_obj: Any) -> Dict[str, Any]:
    """Build runtime MQTT config from persisted system settings."""
    return {
        "enabled": bool(settings_obj.mqtt_enabled and settings_obj.mqtt_beta_enabled),
        "broker_url": settings_obj.mqtt_broker_url,
        "broker_port": settings_obj.mqtt_broker_port,
        "username": settings_obj.mqtt_username,
        "password": settings_obj.mqtt_password,
        "client_id": settings_obj.mqtt_client_id,
        "qos": settings_obj.mqtt_qos,
        "tls_enabled": settings_obj.mqtt_tls_enabled,
        "tls_ca_cert": settings_obj.mqtt_tls_ca_cert,
        "tls_client_cert": settings_obj.mqtt_tls_client_cert,
        "tls_client_key": settings_obj.mqtt_tls_client_key,
    }


class MQTTService:
    """Service for publishing MQTT messages and Home Assistant discovery/state."""

    def __init__(self):
        self.client = None
        self.connected = False
        self.config = {
            "enabled": False,
            "broker_url": None,
            "broker_port": 1883,
            "username": None,
            "password": None,
            "client_id": "borg-ui",
            "keepalive": 60,
            "tls_enabled": False,
            "tls_ca_cert": None,
            "tls_client_cert": None,
            "tls_client_key": None,
            "base_topic": "borg-ui",
            "qos": 1,
            # Home Assistant settings
            "home_assistant_enabled": True,
            "home_assistant_device_name": "Borg",
            "home_assistant_device_manufacturer": "Borg UI",
            "home_assistant_device_model": "Backup",
            "home_assistant_device_identifiers": "borg_ui",
        }
        self._sync_state_store = MQTTSyncStateStore()
        self._job_query_service = BackupJobQueryService()
        self._discovery_publisher = HomeAssistantDiscoveryPublisher(self)
        self._server_state_publisher = ServerStatePublisher(self)
        self._repository_state_publisher = RepositoryStatePublisher(self)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(self, config: Dict[str, Any]):
        """Configure MQTT service with settings."""
        self.config.update(config)
        self.config["enabled"] = bool(config.get("enabled", False))
        self._validate_config()

        # Always tear down existing client before re-initializing.
        if self.client:
            self.disconnect()
            self.client = None

        if self.config["enabled"]:
            self._initialize_client()

    def _validate_config(self):
        """Validate MQTT configuration."""
        required_fields = ["broker_url", "base_topic"]
        for field in required_fields:
            if not self.config.get(field) and self.config["enabled"]:
                raise ValueError(f"Missing required MQTT config: {field}")

    def _initialize_client(self):
        """Initialize MQTT client."""
        try:
            self.client = mqtt.Client(
                client_id=self.config["client_id"],
                protocol=mqtt.MQTTv311,
            )

            self.client.enable_logger()
            self.client.reconnect_delay_set(min_delay=1, max_delay=60)

            if self.config["username"] and self.config["password"]:
                self.client.username_pw_set(
                    self.config["username"],
                    self.config["password"],
                )

            if self.config["tls_enabled"]:
                if self.config["tls_ca_cert"]:
                    self.client.tls_set(
                        ca_certs=self.config["tls_ca_cert"],
                        certfile=self.config["tls_client_cert"],
                        keyfile=self.config["tls_client_key"],
                    )
                else:
                    self.client.tls_set()

            self.client.will_set(
                f"{self.config['base_topic']}/status",
                json.dumps({"status": "offline"}),
                qos=1,
                retain=True,
            )

            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_publish = self._on_publish

            self._connect()

        except Exception as e:
            logger.error("Failed to initialize MQTT client", error=str(e))
            self.connected = False

    # ------------------------------------------------------------------
    # Connection Handling
    # ------------------------------------------------------------------

    def _connect(self):
        """Connect to MQTT broker."""
        if not self.client:
            return

        try:
            broker_url = self.config["broker_url"]
            broker_port = self.config["broker_port"]
            keepalive = self.config["keepalive"]

            logger.info(
                "Connecting to MQTT broker",
                broker_url=broker_url,
                broker_port=broker_port,
            )

            self.client.connect(broker_url, broker_port, keepalive)
            self.client.loop_start()

        except Exception as e:
            logger.error(
                "Failed to connect to MQTT broker",
                broker_url=self.config["broker_url"],
                error=str(e),
            )
            self.connected = False

    def _on_connect(self, client, userdata, flags, rc):
        """Callback when client connects."""
        if rc == 0:
            logger.info("Connected to MQTT broker successfully")
            self.connected = True
            # Re-publish a full DB-derived snapshot on every connect/reconnect.
            self.sync_state(reason="mqtt_connect")
        else:
            logger.error(
                "MQTT connection failed",
                rc=rc,
                message=mqtt.connack_string(rc),
            )
            self.connected = False

    def _on_disconnect(self, client, userdata, rc):
        """Callback when client disconnects."""
        if rc != 0:
            logger.warning("Unexpected MQTT disconnection", rc=rc)
        else:
            logger.info("Disconnected from MQTT broker")
        self.connected = False

    def _on_publish(self, client, userdata, mid):
        """Callback when a message is published."""
        logger.debug("MQTT message published", message_id=mid)

    # ------------------------------------------------------------------
    # State Checks
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        return bool(
            self.config["enabled"]
            and self.config["broker_url"]
        )

    def is_connected(self) -> bool:
        return self.connected

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish(
        self,
        topic: str,
        payload: Dict[str, Any],
        qos: Optional[int] = None,
        use_base_topic: bool = True,
    ):
        """Publish a message to MQTT broker."""
        if not self.is_configured():
            logger.debug("MQTT not configured, skipping publish")
            return False

        if not self.is_connected():
            logger.warning("MQTT not connected, skipping publish")
            return False

        try:
            base_topic = self.config["base_topic"]
            full_topic = (
                f"{base_topic}/{topic}" if use_base_topic and base_topic else topic
            )

            payload_json = json.dumps(payload)
            final_qos = qos if qos is not None else self.config["qos"]

            result = self.client.publish(
                full_topic,
                payload_json,
                qos=final_qos,
                retain=True,
            )

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(
                    "MQTT message queued",
                    topic=full_topic,
                    qos=final_qos,
                )
                return True

            logger.error(
                "Failed to publish MQTT message",
                topic=full_topic,
                rc=result.rc,
                message=mqtt.error_string(result.rc),
            )
            return False
        except Exception as e:
            logger.error(
                "Exception publishing MQTT message",
                topic=topic,
                error=str(e),
            )
            return False

    def _publish_raw(
        self,
        topic: str,
        payload: str,
        qos: Optional[int] = None,
        use_base_topic: bool = True,
    ) -> bool:
        """Publish a raw payload (used for retained tombstones)."""
        if not self.is_configured():
            logger.debug("MQTT not configured, skipping raw publish")
            return False

        if not self.is_connected():
            logger.warning("MQTT not connected, skipping raw publish")
            return False

        try:
            base_topic = self.config["base_topic"]
            full_topic = (
                f"{base_topic}/{topic}" if use_base_topic and base_topic else topic
            )
            final_qos = qos if qos is not None else self.config["qos"]

            result = self.client.publish(
                full_topic,
                payload,
                qos=final_qos,
                retain=True,
            )
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug("MQTT raw message queued", topic=full_topic, qos=final_qos)
                return True

            logger.error(
                "Failed to publish MQTT raw message",
                topic=full_topic,
                rc=result.rc,
                message=mqtt.error_string(result.rc),
            )
            return False
        except Exception as e:
            logger.error("Exception publishing MQTT raw message", topic=topic, error=str(e))
            return False

    # ------------------------------------------------------------------
    # Home Assistant Discovery
    # ------------------------------------------------------------------

    def _get_home_assistant_device_info(
        self,
        is_repository: bool = False,
        repo_id: Optional[int] = None,
        repository_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get device information for Home Assistant MQTT discovery."""
        return self._discovery_publisher.get_home_assistant_device_info(
            is_repository=is_repository,
            repo_id=repo_id,
            repository_name=repository_name,
        )

    def publish_home_assistant_discovery(
        self,
        component: str,
        config: Dict[str, Any],
        node_id: str,
        is_repository: bool = False,
        repo_id: Optional[int] = None,
        repository_name: Optional[str] = None,
    ):
        """Publish Home Assistant MQTT discovery message."""
        return self._discovery_publisher.publish_home_assistant_discovery(
            component=component,
            config=config,
            node_id=node_id,
            is_repository=is_repository,
            repo_id=repo_id,
            repository_name=repository_name,
        )

    def publish_availability(self):
        if not self.config["enabled"]:
            return False
        return self.publish("status", {"status": "online"}, qos=1)

    # ------------------------------------------------------------------
    # Home Assistant Discovery Definitions
    # ------------------------------------------------------------------

    def setup_home_assistant_sensors(self):
        """Publish Home Assistant discovery messages for server sensors."""
        return self._discovery_publisher.setup_home_assistant_sensors()

    def setup_repository_sensors(
        self,
        repository_id: int,
        repository_name: str,
        repository_path: Optional[str] = None,
    ):
        """Publish Home Assistant discovery messages for repository sensors."""
        # `repository_path` is kept for compatibility with existing call sites.
        _ = repository_path
        return self._discovery_publisher.setup_repository_sensors(
            repository_id=repository_id,
            repository_name=repository_name,
        )

    # ------------------------------------------------------------------
    # Topic Publishers
    # ------------------------------------------------------------------

    def publish_repository_status(
        self,
        repository_id: int,
        status: str,
        repository: Optional[str] = None,
        archive: Optional[str] = None,
    ):
        if not self.config["enabled"]:
            return False
        payload = {
            "status": status,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        if repository:
            payload["repository"] = repository
        if archive:
            payload["archive"] = archive
        return self.publish(f"repositories/{repository_id}/status", payload, qos=1)

    def publish_repository_size(self, repository_id: int, used: int, free: int, total: int):
        if not self.config["enabled"]:
            return False
        return self.publish(
            f"repositories/{repository_id}/size",
            {"used": used, "free": free, "total": total},
            qos=1,
        )

    def publish_repository_archives(self, repository_id: int, count: int):
        if not self.config["enabled"]:
            return False
        return self.publish(
            f"repositories/{repository_id}/archives",
            {"count": count},
            qos=1,
        )

    def publish_repository_last_backup(
        self,
        repository_id: int,
        timestamp: Optional[str],
        repository: Optional[str] = None,
        archive: Optional[str] = None,
        stats: Optional[Dict[str, Any]] = None,
    ):
        if not self.config["enabled"]:
            return False

        payload: Dict[str, Any] = {"timestamp": timestamp}
        if repository:
            payload["repository"] = repository
        if archive:
            payload["archive"] = archive
        if stats:
            payload["stats"] = stats

        return self.publish(
            f"repositories/{repository_id}/last_backup",
            payload,
            qos=1,
        )

    def publish_repository_backup_status(
        self,
        repository_id: int,
        status: str,
        repository: Optional[str] = None,
        job_id: Optional[int] = None,
        last_job_status: Optional[str] = None,
        timestamp: Optional[str] = None,
    ):
        if not self.config["enabled"]:
            return False

        payload: Dict[str, Any] = {
            "status": status,
            "timestamp": timestamp,
        }
        if repository:
            payload["repository"] = repository
        if job_id is not None:
            payload["job_id"] = job_id
        if last_job_status:
            payload["last_job_status"] = last_job_status

        return self.publish(
            f"repositories/{repository_id}/backup/status",
            payload,
            qos=1,
        )

    def publish_repository_backup_progress(
        self,
        repository_id: int,
        percent: float,
        status: str = "idle",
        repository: Optional[str] = None,
        job_id: Optional[int] = None,
        timestamp: Optional[str] = None,
        eta_timestamp: Optional[str] = None,
    ):
        if not self.config["enabled"]:
            return False

        int_percent = int(round(float(percent)))
        int_percent = max(0, min(100, int_percent))
        payload: Dict[str, Any] = {
            "status": status,
            "percent": int_percent,
            "timestamp": timestamp,
        }
        # Only include eta_timestamp when it's present (i.e., job is running)
        if eta_timestamp is not None:
            payload["eta_timestamp"] = eta_timestamp

        if repository:
            payload["repository"] = repository
        if job_id is not None:
            payload["job_id"] = job_id

        return self.publish(
            f"repositories/{repository_id}/backup/progress",
            payload,
            qos=1,
        )

    # ------------------------------------------------------------------
    # DB-Derived State Synchronization
    # ------------------------------------------------------------------

    def sync_state(self, reason: str = "manual") -> bool:
        """Open a DB session and publish all Home Assistant state from DB."""
        if not self.config["enabled"]:
            logger.debug("MQTT not enabled, skipping DB state sync", reason=reason)
            return False

        db = SessionLocal()
        try:
            return self.sync_state_with_db(db, reason=reason)
        finally:
            db.close()

    def sync_state_with_db(self, db: Session, reason: str = "manual") -> bool:
        """Publish server and repository Home Assistant state from DB."""
        if not self.config["enabled"]:
            logger.debug("MQTT not enabled, skipping DB state sync", reason=reason)
            return False

        if not self.is_connected():
            logger.debug("MQTT not connected, skipping DB state sync", reason=reason)
            return False

        repositories: List[Repository] = []
        try:
            logger.info("Starting MQTT DB-derived state sync", reason=reason)

            repositories = db.query(Repository).all()
            current_repo_ids = {repo.id for repo in repositories}
            previously_synced_repo_ids = self._load_sync_id_set(
                db,
                REPOSITORY_SYNC_STATE_KEY,
            )
            pending_deleted_repo_ids = self._load_sync_id_set(
                db,
                PENDING_DELETED_REPOSITORY_SYNC_STATE_KEY,
            )
            stale_repo_ids = (previously_synced_repo_ids - current_repo_ids) | pending_deleted_repo_ids

            success = True
            if not self.publish_availability():
                success = False
            if not self.setup_home_assistant_sensors():
                success = False
            if not self._publish_server_state_from_db(db):
                success = False

            cleaned_stale_repo_ids: Set[int] = set()
            for stale_repo_id in sorted(stale_repo_ids):
                logger.info(
                    "Removing stale repository discovery from Home Assistant",
                    repository_id=stale_repo_id,
                    reason=reason,
                )
                stale_cleanup_success = self._remove_repository_from_home_assistant(
                    stale_repo_id
                )
                if not stale_cleanup_success:
                    success = False
                if stale_cleanup_success:
                    cleaned_stale_repo_ids.add(stale_repo_id)

            path_to_id = {repo.path: repo.id for repo in repositories}
            failed_repository_ids = self._fetch_failed_repositories(db, path_to_id)
            latest_jobs_by_repository = self._fetch_latest_backup_jobs_by_repository(db)
            running_jobs_by_repository = self._fetch_running_backup_jobs_by_repository(db)

            for repo in repositories:
                if not self.setup_repository_sensors(repo.id, repo.name, repo.path):
                    success = False
                if not self.publish_repository_data(
                    repo,
                    failed_repository_ids,
                    latest_jobs_by_repository,
                    running_jobs_by_repository,
                ):
                    success = False

            if success:
                pending_deleted_after_sync = (
                    pending_deleted_repo_ids - cleaned_stale_repo_ids
                )
                if pending_deleted_after_sync != pending_deleted_repo_ids:
                    self._save_sync_id_set(
                        db,
                        PENDING_DELETED_REPOSITORY_SYNC_STATE_KEY,
                        pending_deleted_after_sync,
                        commit=False,
                    )
                self._save_sync_id_set(
                    db,
                    REPOSITORY_SYNC_STATE_KEY,
                    current_repo_ids,
                    commit=False,
                )
                db.commit()
            else:
                db.rollback()
                logger.warning(
                    "MQTT DB-derived state sync had publish failures; "
                    "kept previous synced repository IDs for retry",
                    reason=reason,
                    stale_repositories=len(stale_repo_ids),
                )

            logger.info(
                "Completed MQTT DB-derived state sync",
                reason=reason,
                repositories=len(repositories),
            )
            return success
        except Exception as e:
            logger.error("Failed MQTT DB-derived state sync", reason=reason, error=str(e))
            return False

    def queue_deleted_repository_cleanup(self, db: Session, repository_id: int) -> None:
        """
        Queue a deleted repository ID for cleanup on future successful MQTT sync.

        This persists deletion intent in DB, so cleanup still happens after outages.
        """
        pending_ids = self._load_sync_id_set(
            db,
            PENDING_DELETED_REPOSITORY_SYNC_STATE_KEY,
        )
        pending_ids.add(repository_id)
        self._save_sync_id_set(
            db,
            PENDING_DELETED_REPOSITORY_SYNC_STATE_KEY,
            pending_ids,
        )

    def _load_sync_id_set(self, db: Session, sync_key: str) -> Set[int]:
        """Load a set[int] sync marker from DB."""
        return self._sync_state_store.load_id_set(db, sync_key)

    def _save_sync_id_set(
        self,
        db: Session,
        sync_key: str,
        id_set: Set[int],
        commit: bool = True,
    ) -> None:
        """Persist a set[int] sync marker to DB."""
        self._sync_state_store.save_id_set(db, sync_key, id_set, commit=commit)

    def _remove_repository_from_home_assistant(self, repository_id: int) -> bool:
        """
        Remove all retained discovery/state topics for a deleted repository.

        Empty retained payload on discovery topics tells Home Assistant to delete entities.
        """
        return self._discovery_publisher.remove_repository_from_home_assistant(
            repository_id
        )

    def _publish_server_state_from_db(self, db: Session) -> bool:
        """Publish server-level sensor topics from backup_jobs table."""
        return self._server_state_publisher.publish_server_state_from_db(db)

    def publish_repository_data(
        self,
        repository: Repository,
        failed_repository_ids: Set[int],
        latest_jobs_by_repository: Dict[str, BackupJob],
        running_jobs_by_repository: Dict[str, BackupJob],
    ) -> bool:
        """Publish all per-repository state topics from repository table."""
        return self._repository_state_publisher.publish_repository_data(
            repository=repository,
            failed_repository_ids=failed_repository_ids,
            latest_jobs_by_repository=latest_jobs_by_repository,
            running_jobs_by_repository=running_jobs_by_repository,
        )

    def _fetch_failed_repositories(self, db: Session, path_to_id: Dict[str, int]) -> Set[int]:
        """Return repository IDs whose latest backup job failed."""
        return self._job_query_service.fetch_failed_repositories(db, path_to_id)

    def _fetch_latest_backup_jobs_by_repository(self, db: Session) -> Dict[str, BackupJob]:
        """Return latest backup job row per repository path."""
        return self._job_query_service.fetch_latest_backup_jobs_by_repository(db)

    def _fetch_running_backup_jobs_by_repository(self, db: Session) -> Dict[str, BackupJob]:
        """Return latest running backup job row per repository path."""
        return self._job_query_service.fetch_running_backup_jobs_by_repository(db)

    def _parse_size_to_bytes(self, size_str: str) -> int:
        """Parse human-readable size string to bytes."""
        return self._repository_state_publisher.parse_size_to_bytes(size_str)

    def _get_repository_status(
        self,
        repository: Repository,
        failed_repository_ids: Optional[Set[int]] = None,
    ) -> str:
        """Determine repository health from DB-derived fields."""
        return self._repository_state_publisher.get_repository_status(
            repository,
            failed_repository_ids=failed_repository_ids,
        )

    # ------------------------------------------------------------------
    # Disconnect
    # ------------------------------------------------------------------

    def disconnect(self):
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception as e:
                logger.error("Error disconnecting from MQTT broker", error=str(e))
            finally:
                self.connected = False
                self.client = None


mqtt_service = MQTTService()
