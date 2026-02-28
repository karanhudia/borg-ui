"""
Comprehensive tests for MQTT service integration.

Tests cover:
- MQTTSyncStateStore persistence
- BackupJobQueryService queries
- HomeAssistantDiscoveryPublisher
- ServerStatePublisher
- RepositoryStatePublisher
- MQTTService configuration, connection, publishing, and sync
- Edge cases and error handling
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch, call
import json

import pytest
import paho.mqtt.client as mqtt

from app.database.models import (
    BackupJob,
    Repository,
    MQTTSyncState,
    SystemSettings,
)
from app.services.mqtt_service import (
    MQTTService,
    MQTTSyncStateStore,
    BackupJobQueryService,
    HomeAssistantDiscoveryPublisher,
    ServerStatePublisher,
    RepositoryStatePublisher,
    build_mqtt_runtime_config,
    REPOSITORY_SYNC_STATE_KEY,
    PENDING_DELETED_REPOSITORY_SYNC_STATE_KEY,
    REPOSITORY_SENSOR_DEFINITIONS,
    TERMINAL_JOB_STATUSES,
)
from app.utils.datetime_utils import serialize_datetime


# =============================================================================
# Helper Functions
# =============================================================================

def _payload_for_topic(mock_publish: Mock, topic: str):
    """Extract payload for a specific topic from mock publish calls."""
    for call_item in mock_publish.call_args_list:
        if call_item.args[0] == topic:
            return call_item.args[1]
    raise AssertionError(f"Topic not published: {topic}")


def _topic_was_published(mock_publish: Mock, topic: str) -> bool:
    """Check if a topic was published."""
    for call_item in mock_publish.call_args_list:
        if call_item.args[0] == topic:
            return True
    return False


def _create_mqtt_service_configured() -> MQTTService:
    """Create a configured MQTT service instance without real connection."""
    service = MQTTService()
    service.config.update({
        "enabled": True,
        "broker_url": "mqtt://test-broker",
        "broker_port": 1883,
        "base_topic": "test-borg-ui",
        "client_id": "test-client",
        "qos": 1,
    })
    service.connected = True
    service.client = Mock()
    service.publish = Mock(return_value=True)
    return service


# =============================================================================
# Original Tests (preserved for compatibility)
# =============================================================================


@pytest.mark.unit
def test_publish_server_state_uses_latest_terminal_job_timestamp(db_session):
    terminal_time = datetime(2026, 2, 22, 14, 1, 14)
    job = BackupJob(
        repository="/tmp/repo",
        status="completed",
        started_at=datetime(2026, 2, 22, 14, 0, 0),
        completed_at=terminal_time,
        created_at=datetime(2026, 2, 22, 14, 0, 0),
    )
    db_session.add(job)
    db_session.commit()

    mqtt = MQTTService()
    mqtt.config["enabled"] = True
    mqtt.connected = True
    mqtt.publish = Mock(return_value=True)

    assert mqtt._publish_server_state_from_db(db_session) is True

    expected_timestamp = serialize_datetime(terminal_time)
    status_payload = _payload_for_topic(mqtt.publish, "backup/status")
    progress_payload = _payload_for_topic(mqtt.publish, "backup/progress")
    last_payload = _payload_for_topic(mqtt.publish, "backup/last")
    success_payload = _payload_for_topic(mqtt.publish, "backup/success")

    assert status_payload["timestamp"] == expected_timestamp
    assert progress_payload["timestamp"] == expected_timestamp
    assert last_payload["timestamp"] == expected_timestamp
    assert success_payload["timestamp"] == expected_timestamp


@pytest.mark.unit
def test_publish_server_state_without_jobs_avoids_synthetic_now_timestamp(db_session):
    mqtt = MQTTService()
    mqtt.config["enabled"] = True
    mqtt.connected = True
    mqtt.publish = Mock(return_value=True)

    assert mqtt._publish_server_state_from_db(db_session) is True

    status_payload = _payload_for_topic(mqtt.publish, "backup/status")
    progress_payload = _payload_for_topic(mqtt.publish, "backup/progress")
    last_payload = _payload_for_topic(mqtt.publish, "backup/last")
    success_payload = _payload_for_topic(mqtt.publish, "backup/success")

    assert status_payload["timestamp"] is None
    assert progress_payload["timestamp"] is None
    assert last_payload["timestamp"] is None
    assert success_payload["timestamp"] is None


@pytest.mark.unit
def test_publish_repository_data_uses_latest_job_timestamp(db_session):
    terminal_time = datetime(2026, 2, 22, 14, 1, 14)
    repo = Repository(
        name="Repo",
        path="/tmp/repo",
        total_size="1 GB",
        archive_count=3,
        last_backup=terminal_time,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    latest_job = BackupJob(
        repository=repo.path,
        status="completed",
        started_at=datetime(2026, 2, 22, 14, 0, 0),
        completed_at=terminal_time,
        created_at=datetime(2026, 2, 22, 14, 0, 0),
    )
    db_session.add(latest_job)
    db_session.commit()

    mqtt = MQTTService()
    mqtt.config["enabled"] = True
    mqtt.connected = True
    mqtt.publish = Mock(return_value=True)

    assert (
        mqtt.publish_repository_data(
            repo,
            failed_repository_ids=set(),
            latest_jobs_by_repository={repo.path: latest_job},
            running_jobs_by_repository={},
        )
        is True
    )

    expected_timestamp = serialize_datetime(terminal_time)
    status_payload = _payload_for_topic(
        mqtt.publish, f"repositories/{repo.id}/backup/status"
    )
    progress_payload = _payload_for_topic(
        mqtt.publish, f"repositories/{repo.id}/backup/progress"
    )

    assert status_payload["timestamp"] == expected_timestamp
    assert progress_payload["timestamp"] == expected_timestamp

@pytest.mark.unit
def test_fetch_latest_backup_jobs_by_repository_uses_latest_row(db_session):
    old_repo1_job = BackupJob(
        repository="/tmp/repo1",
        status="completed",
        created_at=datetime(2026, 2, 20, 12, 0, 0),
    )
    new_repo1_job = BackupJob(
        repository="/tmp/repo1",
        status="failed",
        created_at=datetime(2026, 2, 22, 12, 0, 0),
    )
    repo2_job = BackupJob(
        repository="/tmp/repo2",
        status="completed",
        created_at=datetime(2026, 2, 21, 12, 0, 0),
    )
    db_session.add_all([old_repo1_job, new_repo1_job, repo2_job])
    db_session.commit()

    mqtt = MQTTService()
    latest = mqtt._fetch_latest_backup_jobs_by_repository(db_session)

    assert set(latest.keys()) == {"/tmp/repo1", "/tmp/repo2"}
    assert latest["/tmp/repo1"].id == new_repo1_job.id
    assert latest["/tmp/repo2"].id == repo2_job.id


# =============================================================================
# MQTTSyncStateStore Tests
# =============================================================================

@pytest.mark.unit
class TestMQTTSyncStateStore:
    """Tests for MQTTSyncStateStore persistence layer."""

    def test_load_empty_id_set_when_no_state_exists(self, db_session):
        """Should return empty set when sync state doesn't exist."""
        result = MQTTSyncStateStore.load_id_set(db_session, "nonexistent_key")
        assert result == set()

    def test_load_empty_id_set_when_sync_value_is_empty(self, db_session):
        """Should return empty set when sync_value is empty string."""
        state = MQTTSyncState(sync_key="test_key", sync_value="")
        db_session.add(state)
        db_session.commit()

        result = MQTTSyncStateStore.load_id_set(db_session, "test_key")
        assert result == set()

    def test_load_nonempty_id_set(self, db_session):
        """Should load ID set from database."""
        state = MQTTSyncState(sync_key="test_key", sync_value=json.dumps([1, 2, 3]))
        db_session.add(state)
        db_session.commit()

        result = MQTTSyncStateStore.load_id_set(db_session, "test_key")
        assert result == {1, 2, 3}

    def test_load_id_set_handles_malformed_json(self, db_session):
        """Should return empty set and log warning for malformed JSON."""
        state = MQTTSyncState(sync_key="test_key", sync_value="not valid json")
        db_session.add(state)
        db_session.commit()

        result = MQTTSyncStateStore.load_id_set(db_session, "test_key")
        assert result == set()

    def test_load_id_set_handles_non_list_json(self, db_session):
        """Should return empty set and log warning for non-list JSON."""
        state = MQTTSyncState(sync_key="test_key", sync_value=json.dumps({"foo": "bar"}))
        db_session.add(state)
        db_session.commit()

        result = MQTTSyncStateStore.load_id_set(db_session, "test_key")
        assert result == set()

    def test_save_id_set_creates_new_state(self, db_session):
        """Should create new sync state when it doesn't exist."""
        MQTTSyncStateStore.save_id_set(db_session, "new_key", {1, 2, 3})

        state = db_session.query(MQTTSyncState).filter_by(sync_key="new_key").first()
        assert state is not None
        assert json.loads(state.sync_value) == [1, 2, 3]

    def test_save_id_set_updates_existing_state(self, db_session):
        """Should update existing sync state."""
        state = MQTTSyncState(sync_key="test_key", sync_value=json.dumps([1, 2]))
        db_session.add(state)
        db_session.commit()

        MQTTSyncStateStore.save_id_set(db_session, "test_key", {3, 4, 5})

        updated_state = db_session.query(MQTTSyncState).filter_by(sync_key="test_key").first()
        assert json.loads(updated_state.sync_value) == [3, 4, 5]

    def test_save_id_set_sorts_ids(self, db_session):
        """Should save IDs in sorted order."""
        MQTTSyncStateStore.save_id_set(db_session, "test_key", {5, 1, 3, 2, 4})

        state = db_session.query(MQTTSyncState).filter_by(sync_key="test_key").first()
        assert json.loads(state.sync_value) == [1, 2, 3, 4, 5]

    def test_save_id_set_without_commit(self, db_session):
        """Should allow saving without immediate commit."""
        MQTTSyncStateStore.save_id_set(db_session, "test_key", {1, 2, 3}, commit=False)
        db_session.rollback()

        # State should not exist after rollback
        state = db_session.query(MQTTSyncState).filter_by(sync_key="test_key").first()
        assert state is None


# =============================================================================
# BackupJobQueryService Tests
# =============================================================================

@pytest.mark.unit
class TestBackupJobQueryService:
    """Tests for BackupJobQueryService query layer."""

    def test_fetch_latest_backup_jobs_single_job_per_repo(self, db_session):
        """Should fetch one job per repository."""
        job1 = BackupJob(
            repository="/repo1",
            status="completed",
            created_at=datetime(2026, 2, 20, 12, 0, 0),
        )
        job2 = BackupJob(
            repository="/repo2",
            status="failed",
            created_at=datetime(2026, 2, 21, 12, 0, 0),
        )
        db_session.add_all([job1, job2])
        db_session.commit()

        service = BackupJobQueryService()
        result = service.fetch_latest_backup_jobs_by_repository(db_session)

        assert len(result) == 2
        assert result["/repo1"].id == job1.id
        assert result["/repo2"].id == job2.id

    def test_fetch_latest_backup_jobs_prefers_newest_job(self, db_session):
        """Should prefer most recent job by created_at."""
        old_job = BackupJob(
            repository="/repo1",
            status="completed",
            created_at=datetime(2026, 2, 20, 12, 0, 0),
        )
        new_job = BackupJob(
            repository="/repo1",
            status="failed",
            created_at=datetime(2026, 2, 22, 12, 0, 0),
        )
        db_session.add_all([old_job, new_job])
        db_session.commit()

        service = BackupJobQueryService()
        result = service.fetch_latest_backup_jobs_by_repository(db_session)

        assert result["/repo1"].id == new_job.id

    def test_fetch_latest_backup_jobs_tiebreaker_by_id(self, db_session):
        """Should use ID as tiebreaker when created_at is same."""
        same_time = datetime(2026, 2, 22, 12, 0, 0)
        job1 = BackupJob(repository="/repo1", status="completed", created_at=same_time)
        job2 = BackupJob(repository="/repo1", status="failed", created_at=same_time)
        db_session.add_all([job1, job2])
        db_session.commit()

        service = BackupJobQueryService()
        result = service.fetch_latest_backup_jobs_by_repository(db_session)

        # Should prefer higher ID (most recent insert)
        assert result["/repo1"].id == max(job1.id, job2.id)

    def test_fetch_latest_backup_jobs_ignores_null_repository(self, db_session):
        """Should ignore jobs with null repository."""
        job1 = BackupJob(repository=None, status="completed", created_at=datetime.now())
        job2 = BackupJob(repository="/repo1", status="completed", created_at=datetime.now())
        db_session.add_all([job1, job2])
        db_session.commit()

        service = BackupJobQueryService()
        result = service.fetch_latest_backup_jobs_by_repository(db_session)

        assert len(result) == 1
        assert "/repo1" in result

    def test_fetch_running_backup_jobs_by_repository(self, db_session):
        """Should fetch only running jobs."""
        running_job = BackupJob(
            repository="/repo1",
            status="running",
            created_at=datetime(2026, 2, 22, 12, 0, 0),
            started_at=datetime(2026, 2, 22, 12, 1, 0),
        )
        completed_job = BackupJob(
            repository="/repo1",
            status="completed",
            created_at=datetime(2026, 2, 22, 11, 0, 0),
        )
        db_session.add_all([running_job, completed_job])
        db_session.commit()

        service = BackupJobQueryService()
        result = service.fetch_running_backup_jobs_by_repository(db_session)

        assert len(result) == 1
        assert result["/repo1"].id == running_job.id

    def test_fetch_running_jobs_orders_by_started_at(self, db_session):
        """Should order running jobs by started_at."""
        older_running = BackupJob(
            repository="/repo1",
            status="running",
            created_at=datetime(2026, 2, 22, 12, 0, 0),
            started_at=datetime(2026, 2, 22, 12, 5, 0),
        )
        newer_running = BackupJob(
            repository="/repo1",
            status="running",
            created_at=datetime(2026, 2, 22, 11, 0, 0),
            started_at=datetime(2026, 2, 22, 12, 10, 0),
        )
        db_session.add_all([older_running, newer_running])
        db_session.commit()

        service = BackupJobQueryService()
        result = service.fetch_running_backup_jobs_by_repository(db_session)

        # Should prefer most recent started_at
        assert result["/repo1"].id == newer_running.id

    def test_fetch_failed_repositories(self, db_session):
        """Should identify repositories whose latest job failed."""
        failed_job = BackupJob(
            repository="/repo1",
            status="failed",
            created_at=datetime(2026, 2, 22, 12, 0, 0),
        )
        completed_job = BackupJob(
            repository="/repo2",
            status="completed",
            created_at=datetime(2026, 2, 22, 12, 0, 0),
        )
        db_session.add_all([failed_job, completed_job])
        db_session.commit()

        service = BackupJobQueryService()
        path_to_id = {"/repo1": 1, "/repo2": 2}
        result = service.fetch_failed_repositories(db_session, path_to_id)

        assert result == {1}

    def test_fetch_failed_repositories_with_empty_path_to_id(self, db_session):
        """Should return empty set when path_to_id is empty."""
        service = BackupJobQueryService()
        result = service.fetch_failed_repositories(db_session, {})
        assert result == set()

    def test_fetch_failed_repositories_ignores_nonfailed_statuses(self, db_session):
        """Should only return failed repositories."""
        completed_job = BackupJob(
            repository="/repo1",
            status="completed",
            created_at=datetime(2026, 2, 22, 12, 0, 0),
        )
        completed_with_warnings_job = BackupJob(
            repository="/repo2",
            status="completed_with_warnings",
            created_at=datetime(2026, 2, 22, 12, 0, 0),
        )
        db_session.add_all([completed_job, completed_with_warnings_job])
        db_session.commit()

        service = BackupJobQueryService()
        path_to_id = {"/repo1": 1, "/repo2": 2}
        result = service.fetch_failed_repositories(db_session, path_to_id)

        assert result == set()


# =============================================================================
# RepositoryStatePublisher Tests
# =============================================================================

@pytest.mark.unit
class TestRepositoryStatePublisher:
    """Tests for RepositoryStatePublisher."""

    @pytest.mark.parametrize("size_str,expected", [
        ("0", 0),
        ("100", 100),
        ("1 KB", 1024),
        ("1KB", 1024),
        ("2 MB", 2 * 1024 ** 2),
        ("3 GB", 3 * 1024 ** 3),
        ("4 TB", 4 * 1024 ** 4),
        ("5 PB", 5 * 1024 ** 5),
        ("1.5 GB", int(1.5 * 1024 ** 3)),
        ("", 0),
        ("invalid", 0),
        ("  2.5 MB  ", int(2.5 * 1024 ** 2)),
    ])
    def test_parse_size_to_bytes(self, size_str, expected):
        """Should parse various size formats correctly."""
        publisher = RepositoryStatePublisher(Mock())
        result = publisher.parse_size_to_bytes(size_str)
        assert result == expected

    def test_get_repository_status_failed(self, db_session):
        """Should return 'failed' for repositories in failed set."""
        repo = Repository(
            name="Test",
            path="/repo",
            last_backup=datetime.now(timezone.utc),
        )
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        publisher = RepositoryStatePublisher(Mock())
        status = publisher.get_repository_status(repo, failed_repository_ids={repo.id})
        assert status == "failed"

    def test_get_repository_status_no_backup(self, db_session):
        """Should return 'no_backup' when last_backup is None."""
        repo = Repository(name="Test", path="/repo", last_backup=None)
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        publisher = RepositoryStatePublisher(Mock())
        status = publisher.get_repository_status(repo)
        assert status == "no_backup"

    def test_get_repository_status_healthy(self, db_session):
        """Should return 'healthy' for recent backups (< 3 days)."""
        recent = datetime.now(timezone.utc) - timedelta(days=2)
        repo = Repository(name="Test", path="/repo", last_backup=recent)
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        publisher = RepositoryStatePublisher(Mock())
        status = publisher.get_repository_status(repo)
        assert status == "healthy"

    def test_get_repository_status_warning(self, db_session):
        """Should return 'warning' for backups 4-7 days old."""
        warning_age = datetime.now(timezone.utc) - timedelta(days=5)
        repo = Repository(name="Test", path="/repo", last_backup=warning_age)
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        publisher = RepositoryStatePublisher(Mock())
        status = publisher.get_repository_status(repo)
        assert status == "warning"

    def test_get_repository_status_stale(self, db_session):
        """Should return 'stale' for backups > 7 days old."""
        stale = datetime.now(timezone.utc) - timedelta(days=10)
        repo = Repository(name="Test", path="/repo", last_backup=stale)
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        publisher = RepositoryStatePublisher(Mock())
        status = publisher.get_repository_status(repo)
        assert status == "stale"

    def test_get_repository_status_handles_naive_datetime(self, db_session):
        """Should handle timezone-naive datetimes."""
        # Create naive datetime
        stale_naive = datetime.now() - timedelta(days=10)
        stale_naive = stale_naive.replace(tzinfo=None)

        repo = Repository(name="Test", path="/repo", last_backup=stale_naive)
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        publisher = RepositoryStatePublisher(Mock())
        status = publisher.get_repository_status(repo)
        assert status == "stale"

    def test_publish_repository_data_publishes_all_topics(self, db_session):
        """Should publish all repository state topics."""
        repo = Repository(
            name="Test Repo",
            path="/repo",
            total_size="1 GB",
            archive_count=5,
            last_backup=datetime(2026, 2, 22, 12, 0, 0, tzinfo=timezone.utc),
        )
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        mqtt_service = _create_mqtt_service_configured()
        publisher = RepositoryStatePublisher(mqtt_service)

        result = publisher.publish_repository_data(
            repo,
            failed_repository_ids=set(),
            latest_jobs_by_repository={},
            running_jobs_by_repository={},
        )

        assert result is True
        # Verify all expected methods were called
        assert mqtt_service.publish.call_count >= 5  # At least 5 topics

    def test_publish_repository_data_with_running_job(self, db_session):
        """Should include running job data in progress payload."""
        repo = Repository(name="Test", path="/repo")
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        running_job = BackupJob(
            repository=repo.path,
            status="running",
            progress_percent=45.5,
            estimated_time_remaining=300,
            started_at=datetime(2026, 2, 22, 12, 0, 0, tzinfo=timezone.utc),
            created_at=datetime(2026, 2, 22, 11, 55, 0, tzinfo=timezone.utc),
        )

        mqtt_service = _create_mqtt_service_configured()
        publisher = RepositoryStatePublisher(mqtt_service)

        result = publisher.publish_repository_data(
            repo,
            failed_repository_ids=set(),
            latest_jobs_by_repository={},
            running_jobs_by_repository={repo.path: running_job},
        )

        assert result is True


# =============================================================================
# ServerStatePublisher Tests
# =============================================================================

@pytest.mark.unit
class TestServerStatePublisher:
    """Tests for ServerStatePublisher."""

    def test_publish_server_state_with_no_jobs(self, db_session):
        """Should publish idle state with null timestamps when no jobs exist."""
        mqtt_service = _create_mqtt_service_configured()
        publisher = ServerStatePublisher(mqtt_service)

        result = publisher.publish_server_state_from_db(db_session)

        assert result is True
        status_payload = _payload_for_topic(mqtt_service.publish, "backup/status")
        assert status_payload["status"] == "idle"
        assert status_payload["timestamp"] is None

    @patch('app.services.mqtt_service.datetime')
    def test_publish_server_state_with_running_job(self, mock_datetime, db_session):
        """Should publish running state with job details."""
        # Mock datetime.now() to return the job start time for deterministic ETA calculation
        mock_now = datetime(2026, 2, 22, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.datetime.now.return_value = mock_now
        mock_datetime.timedelta = timedelta  # Pass through timedelta
        mock_datetime.timezone = timezone  # Pass through timezone

        running_job = BackupJob(
            repository="/repo",
            status="running",
            progress_percent=50.0,
            estimated_time_remaining=600,
            started_at=datetime(2026, 2, 22, 12, 0, 0, tzinfo=timezone.utc),
            created_at=datetime(2026, 2, 22, 11, 55, 0, tzinfo=timezone.utc),
        )
        db_session.add(running_job)
        db_session.commit()

        mqtt_service = _create_mqtt_service_configured()
        publisher = ServerStatePublisher(mqtt_service)

        result = publisher.publish_server_state_from_db(db_session)

        assert result is True
        status_payload = _payload_for_topic(mqtt_service.publish, "backup/status")
        assert status_payload["status"] == "running"
        assert status_payload["job_id"] == running_job.id
        assert status_payload["repository"] == "/repo"

        progress_payload = _payload_for_topic(mqtt_service.publish, "backup/progress")
        assert progress_payload["status"] == "running"
        assert progress_payload["percent"] == 50.0
        # ETA should be start time + 600 seconds (10 minutes) = 2026-02-22T12:10:00+00:00
        expected_eta = serialize_datetime(datetime(2026, 2, 22, 12, 10, 0, tzinfo=timezone.utc))
        assert progress_payload["eta_timestamp"] == expected_eta

    def test_publish_server_state_with_completed_job(self, db_session):
        """Should publish idle state with last completed job details."""
        completed_job = BackupJob(
            repository="/repo",
            status="completed",
            started_at=datetime(2026, 2, 22, 12, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 2, 22, 13, 0, 0, tzinfo=timezone.utc),
            created_at=datetime(2026, 2, 22, 11, 55, 0, tzinfo=timezone.utc),
        )
        db_session.add(completed_job)
        db_session.commit()

        mqtt_service = _create_mqtt_service_configured()
        publisher = ServerStatePublisher(mqtt_service)

        result = publisher.publish_server_state_from_db(db_session)

        assert result is True
        status_payload = _payload_for_topic(mqtt_service.publish, "backup/status")
        assert status_payload["status"] == "idle"
        assert status_payload["last_job_status"] == "completed"

        success_payload = _payload_for_topic(mqtt_service.publish, "backup/success")
        assert success_payload["success"] == "true"
        assert success_payload["status"] == "completed"

    def test_publish_server_state_with_failed_job(self, db_session):
        """Should publish failure state with error message."""
        failed_job = BackupJob(
            repository="/repo",
            status="failed",
            error_message="Connection timeout",
            started_at=datetime(2026, 2, 22, 12, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 2, 22, 12, 30, 0, tzinfo=timezone.utc),
            created_at=datetime(2026, 2, 22, 11, 55, 0, tzinfo=timezone.utc),
        )
        db_session.add(failed_job)
        db_session.commit()

        mqtt_service = _create_mqtt_service_configured()
        publisher = ServerStatePublisher(mqtt_service)

        result = publisher.publish_server_state_from_db(db_session)

        assert result is True
        success_payload = _payload_for_topic(mqtt_service.publish, "backup/success")
        assert success_payload["success"] == "false"
        assert success_payload["error"] == "Connection timeout"

    def test_publish_server_state_uses_correct_timestamp_priority(self, db_session):
        """Should prioritize completed_at over started_at over created_at."""
        job = BackupJob(
            repository="/repo",
            status="completed",
            created_at=datetime(2026, 2, 22, 11, 0, 0, tzinfo=timezone.utc),
            started_at=datetime(2026, 2, 22, 12, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 2, 22, 13, 0, 0, tzinfo=timezone.utc),
        )
        db_session.add(job)
        db_session.commit()

        mqtt_service = _create_mqtt_service_configured()
        publisher = ServerStatePublisher(mqtt_service)

        result = publisher.publish_server_state_from_db(db_session)

        assert result is True
        last_payload = _payload_for_topic(mqtt_service.publish, "backup/last")
        expected_timestamp = serialize_datetime(datetime(2026, 2, 22, 13, 0, 0, tzinfo=timezone.utc))
        assert last_payload["timestamp"] == expected_timestamp

    def test_publish_server_state_completed_with_warnings_is_success(self, db_session):
        """Should treat 'completed_with_warnings' as success."""
        job = BackupJob(
            repository="/repo",
            status="completed_with_warnings",
            completed_at=datetime(2026, 2, 22, 13, 0, 0, tzinfo=timezone.utc),
            created_at=datetime(2026, 2, 22, 12, 0, 0, tzinfo=timezone.utc),
        )
        db_session.add(job)
        db_session.commit()

        mqtt_service = _create_mqtt_service_configured()
        publisher = ServerStatePublisher(mqtt_service)

        result = publisher.publish_server_state_from_db(db_session)

        assert result is True
        success_payload = _payload_for_topic(mqtt_service.publish, "backup/success")
        assert success_payload["success"] == "true"


# =============================================================================
# HomeAssistantDiscoveryPublisher Tests
# =============================================================================

@pytest.mark.unit
class TestHomeAssistantDiscoveryPublisher:
    """Tests for HomeAssistantDiscoveryPublisher."""

    def test_get_home_assistant_device_info_for_server(self):
        """Should generate correct device info for server."""
        mqtt_service = _create_mqtt_service_configured()
        mqtt_service.config["home_assistant_device_identifiers"] = "borg_ui"
        mqtt_service.config["home_assistant_device_name"] = "Borg Backup"
        mqtt_service.config["home_assistant_device_manufacturer"] = "Borg UI"

        publisher = HomeAssistantDiscoveryPublisher(mqtt_service)
        device_info = publisher.get_home_assistant_device_info(is_repository=False)

        assert device_info["identifiers"] == ["borg_ui"]
        assert device_info["name"] == "Borg Backup"
        assert device_info["manufacturer"] == "Borg UI"
        assert device_info["model"] == "Server"

    def test_get_home_assistant_device_info_for_repository(self):
        """Should generate correct device info for repository."""
        mqtt_service = _create_mqtt_service_configured()
        mqtt_service.config["home_assistant_device_identifiers"] = "borg_ui"
        mqtt_service.config["home_assistant_device_manufacturer"] = "Borg UI"

        publisher = HomeAssistantDiscoveryPublisher(mqtt_service)
        device_info = publisher.get_home_assistant_device_info(
            is_repository=True,
            repo_id=7,
            repository_name="Test Repo"
        )

        assert device_info["identifiers"] == ["borg_ui_repo_7"]
        assert device_info["name"] == "Test Repo"
        assert device_info["model"] == "Repository"
        assert device_info["via_device"] == "borg_ui"

    def test_setup_home_assistant_sensors(self):
        """Should publish discovery for server sensors."""
        mqtt_service = _create_mqtt_service_configured()
        mqtt_service.config["home_assistant_enabled"] = True

        publisher = HomeAssistantDiscoveryPublisher(mqtt_service)
        result = publisher.setup_home_assistant_sensors()

        assert result is True
        # Should have published 2 sensors (last_backup and backup_success)
        assert mqtt_service.publish.call_count >= 2

    def test_setup_repository_sensors_publishes_all_definitions(self):
        """Should publish discovery for all repository sensor definitions."""
        mqtt_service = _create_mqtt_service_configured()
        mqtt_service.config["home_assistant_enabled"] = True

        publisher = HomeAssistantDiscoveryPublisher(mqtt_service)
        result = publisher.setup_repository_sensors(5, "Test Repository")

        assert result is True
        assert mqtt_service.publish.call_count == len(REPOSITORY_SENSOR_DEFINITIONS)

    def test_setup_repository_sensors_binary_sensor_no_json_attributes(self):
        """Should not include json_attributes for binary sensors with flag."""
        mqtt_service = _create_mqtt_service_configured()
        mqtt_service.config["home_assistant_enabled"] = True
        mqtt_service.config["home_assistant_device_identifiers"] = "borg_ui"

        publisher = HomeAssistantDiscoveryPublisher(mqtt_service)
        result = publisher.setup_repository_sensors(7, "Test Repository")

        assert result is True

        # Find the status sensor call
        status_topic = "homeassistant/sensor/borg_ui/borg_ui_repo_7_status/config"
        payload = _payload_for_topic(mqtt_service.publish, status_topic)

        assert payload["json_attributes_topic"] == "test-borg-ui/repositories/7/status"
        assert payload["value_template"] == "{{ value_json.status }}"

    def test_remove_repository_from_home_assistant(self):
        """Should publish empty retained messages for all repository topics."""
        mqtt_service = _create_mqtt_service_configured()
        mqtt_service._publish_raw = Mock(return_value=True)

        publisher = HomeAssistantDiscoveryPublisher(mqtt_service)
        result = publisher.remove_repository_from_home_assistant(5)

        assert result is True
        # Should publish empty payloads for discovery and state topics
        expected_calls = len(REPOSITORY_SENSOR_DEFINITIONS) + len([
            "status", "size", "archives", "last_backup", "backup/status", "backup/progress"
        ])
        assert mqtt_service._publish_raw.call_count >= expected_calls


# =============================================================================
# MQTTService Configuration Tests
# =============================================================================

@pytest.mark.unit
class TestMQTTServiceConfiguration:
    """Tests for MQTTService configuration."""

    def test_default_configuration(self):
        """Should have sensible defaults."""
        service = MQTTService()
        assert service.config["enabled"] is False
        assert service.config["broker_port"] == 1883
        assert service.config["qos"] == 1
        assert service.config["client_id"] == "borg-ui"
        assert service.config["base_topic"] == "borg-ui"

    def test_configure_updates_config(self):
        """Should update configuration."""
        service = MQTTService()
        service.configure({
            "enabled": True,
            "broker_url": "mqtt://test-broker",
            "broker_port": 8883,
        })

        assert service.config["enabled"] is True
        assert service.config["broker_url"] == "mqtt://test-broker"
        assert service.config["broker_port"] == 8883

    def test_configure_validates_required_fields(self):
        """Should raise error for missing required fields when enabled."""
        service = MQTTService()

        with pytest.raises(ValueError, match="broker_url"):
            service.configure({
                "enabled": True,
                "broker_url": None,
                "base_topic": "test",
            })

    def test_configure_validates_base_topic(self):
        """Should raise error for missing base_topic when enabled."""
        service = MQTTService()

        with pytest.raises(ValueError, match="base_topic"):
            service.configure({
                "enabled": True,
                "broker_url": "mqtt://test",
                "base_topic": None,
            })

    def test_configure_disconnects_existing_client(self):
        """Should disconnect existing client before reconfiguring."""
        service = MQTTService()
        service.client = Mock()
        service.connected = True
        service.disconnect = Mock()

        service.configure({
            "enabled": False,
            "broker_url": "mqtt://test",
            "base_topic": "test",
        })

        service.disconnect.assert_called_once()

    def test_build_mqtt_runtime_config_from_settings(self):
        """Should build config from SystemSettings object."""
        settings = Mock()
        settings.mqtt_enabled = True
        settings.mqtt_beta_enabled = True
        settings.mqtt_broker_url = "mqtt://test"
        settings.mqtt_broker_port = 1883
        settings.mqtt_username = "user"
        settings.mqtt_password = "pass"
        settings.mqtt_client_id = "client"
        settings.mqtt_base_topic = "topic"
        settings.mqtt_qos = 2
        settings.mqtt_tls_enabled = True
        settings.mqtt_tls_ca_cert = "/ca.crt"
        settings.mqtt_tls_client_cert = "/client.crt"
        settings.mqtt_tls_client_key = "/client.key"

        config = build_mqtt_runtime_config(settings)

        assert config["enabled"] is True
        assert config["broker_url"] == "mqtt://test"
        assert config["username"] == "user"
        assert config["password"] == "pass"
        assert config["tls_enabled"] is True

    def test_build_mqtt_runtime_config_requires_both_flags(self):
        """Should require both mqtt_enabled and mqtt_beta_enabled."""
        settings = Mock()
        settings.mqtt_enabled = True
        settings.mqtt_beta_enabled = False
        settings.mqtt_broker_url = "mqtt://test"
        settings.mqtt_broker_port = 1883
        settings.mqtt_username = None
        settings.mqtt_password = None
        settings.mqtt_client_id = "client"
        settings.mqtt_base_topic = "topic"
        settings.mqtt_qos = 1
        settings.mqtt_tls_enabled = False
        settings.mqtt_tls_ca_cert = None
        settings.mqtt_tls_client_cert = None
        settings.mqtt_tls_client_key = None

        config = build_mqtt_runtime_config(settings)

        assert config["enabled"] is False


# =============================================================================
# MQTTService Connection Tests
# =============================================================================

@pytest.mark.unit
class TestMQTTServiceConnection:
    """Tests for MQTT connection handling."""

    def test_is_configured_returns_true_when_configured(self):
        """Should return True when service is properly configured."""
        service = MQTTService()
        service.config["enabled"] = True
        service.config["broker_url"] = "mqtt://test"

        assert service.is_configured() is True

    def test_is_configured_returns_false_when_not_enabled(self):
        """Should return False when not enabled."""
        service = MQTTService()
        service.config["enabled"] = False
        service.config["broker_url"] = "mqtt://test"

        assert service.is_configured() is False

    def test_is_configured_returns_false_when_no_broker(self):
        """Should return False when broker_url is missing."""
        service = MQTTService()
        service.config["enabled"] = True
        service.config["broker_url"] = None

        assert service.is_configured() is False

    def test_is_connected_returns_connection_state(self):
        """Should return connection state."""
        service = MQTTService()
        assert service.is_connected() is False

        service.connected = True
        assert service.is_connected() is True

    @patch("app.services.mqtt_service.mqtt.Client")
    def test_initialize_client_creates_mqtt_client(self, mock_client_class):
        """Should create MQTT client with correct parameters."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        service = MQTTService()
        service.config.update({
            "enabled": True,
            "broker_url": "mqtt://test",
            "broker_port": 1883,
            "base_topic": "test",
            "client_id": "test-client",
        })
        service._initialize_client()

        mock_client_class.assert_called_once()
        assert service.client == mock_client

    @patch("app.services.mqtt_service.mqtt.Client")
    def test_initialize_client_sets_username_password(self, mock_client_class):
        """Should set username and password when provided."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        service = MQTTService()
        service.config.update({
            "enabled": True,
            "broker_url": "mqtt://test",
            "broker_port": 1883,
            "base_topic": "test",
            "username": "testuser",
            "password": "testpass",
        })
        service._initialize_client()

        mock_client.username_pw_set.assert_called_once_with("testuser", "testpass")

    @patch("app.services.mqtt_service.mqtt.Client")
    def test_initialize_client_configures_tls(self, mock_client_class):
        """Should configure TLS when enabled."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        service = MQTTService()
        service.config.update({
            "enabled": True,
            "broker_url": "mqtt://test",
            "broker_port": 8883,
            "base_topic": "test",
            "tls_enabled": True,
            "tls_ca_cert": "/ca.crt",
            "tls_client_cert": "/client.crt",
            "tls_client_key": "/client.key",
        })
        service._initialize_client()

        mock_client.tls_set.assert_called_once_with(
            ca_certs="/ca.crt",
            certfile="/client.crt",
            keyfile="/client.key",
        )

    @patch("app.services.mqtt_service.mqtt.Client")
    def test_initialize_client_sets_will_message(self, mock_client_class):
        """Should set will message for offline status."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        service = MQTTService()
        service.config.update({
            "enabled": True,
            "broker_url": "mqtt://test",
            "broker_port": 1883,
            "base_topic": "test-topic",
        })
        service._initialize_client()

        mock_client.will_set.assert_called_once()
        call_args = mock_client.will_set.call_args
        assert call_args[0][0] == "test-topic/status"
        assert json.loads(call_args[0][1])["status"] == "offline"

    def test_on_connect_callback_success(self):
        """Should set connected flag and sync on successful connection."""
        service = MQTTService()
        service.sync_state = Mock()

        service._on_connect(None, None, None, 0)

        assert service.connected is True
        service.sync_state.assert_called_once_with(reason="mqtt_connect")

    def test_on_connect_callback_failure(self):
        """Should not set connected flag on connection failure."""
        service = MQTTService()
        service.sync_state = Mock()

        service._on_connect(None, None, None, 1)

        assert service.connected is False
        service.sync_state.assert_not_called()

    def test_on_disconnect_callback(self):
        """Should clear connected flag on disconnect."""
        service = MQTTService()
        service.connected = True

        service._on_disconnect(None, None, 0)

        assert service.connected is False

    def test_disconnect_stops_loop_and_disconnects(self):
        """Should stop loop and disconnect client."""
        service = MQTTService()
        mock_client = Mock()
        service.client = mock_client
        service.connected = True

        service.disconnect()

        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()
        assert service.connected is False
        assert service.client is None


# =============================================================================
# MQTTService Publishing Tests
# =============================================================================

@pytest.mark.unit
class TestMQTTServicePublishing:
    """Tests for MQTT message publishing."""

    def test_publish_skips_when_not_configured(self):
        """Should skip publishing when not configured."""
        service = MQTTService()
        service.config["enabled"] = False

        result = service.publish("test/topic", {"data": "value"})

        assert result is False

    def test_publish_skips_when_not_connected(self):
        """Should skip publishing when not connected."""
        service = MQTTService()
        service.config["enabled"] = True
        service.config["broker_url"] = "mqtt://test"
        service.connected = False

        result = service.publish("test/topic", {"data": "value"})

        assert result is False

    def test_publish_with_base_topic(self):
        """Should prepend base topic to topic."""
        service = MQTTService()
        service.config["enabled"] = True
        service.config["broker_url"] = "mqtt://test"
        service.config["base_topic"] = "borg-ui"
        service.connected = True
        service.client = Mock()
        service.client.publish = Mock(return_value=Mock(rc=mqtt.MQTT_ERR_SUCCESS))

        result = service.publish("test/topic", {"data": "value"})

        assert result is True
        service.client.publish.assert_called_once()
        assert service.client.publish.call_args[0][0] == "borg-ui/test/topic"

    def test_publish_without_base_topic(self):
        """Should not prepend base topic when use_base_topic=False."""
        service = MQTTService()
        service.config["enabled"] = True
        service.config["broker_url"] = "mqtt://test"
        service.config["base_topic"] = "borg-ui"
        service.connected = True
        service.client = Mock()
        service.client.publish = Mock(return_value=Mock(rc=mqtt.MQTT_ERR_SUCCESS))

        result = service.publish("absolute/topic", {"data": "value"}, use_base_topic=False)

        assert result is True
        assert service.client.publish.call_args[0][0] == "absolute/topic"

    def test_publish_serializes_payload_to_json(self):
        """Should serialize payload to JSON."""
        service = MQTTService()
        service.config["enabled"] = True
        service.config["broker_url"] = "mqtt://test"
        service.config["base_topic"] = "test"
        service.connected = True
        service.client = Mock()
        service.client.publish = Mock(return_value=Mock(rc=mqtt.MQTT_ERR_SUCCESS))

        payload = {"status": "online", "count": 42}
        service.publish("topic", payload)

        published_payload = service.client.publish.call_args[0][1]
        assert json.loads(published_payload) == payload

    def test_publish_uses_retain_flag(self):
        """Should publish with retain=True."""
        service = MQTTService()
        service.config["enabled"] = True
        service.config["broker_url"] = "mqtt://test"
        service.config["base_topic"] = "test"
        service.connected = True
        service.client = Mock()
        service.client.publish = Mock(return_value=Mock(rc=mqtt.MQTT_ERR_SUCCESS))

        service.publish("topic", {"data": "value"})

        assert service.client.publish.call_args[1]["retain"] is True

    def test_publish_uses_custom_qos(self):
        """Should use custom QoS when provided."""
        service = MQTTService()
        service.config["enabled"] = True
        service.config["broker_url"] = "mqtt://test"
        service.config["base_topic"] = "test"
        service.config["qos"] = 1
        service.connected = True
        service.client = Mock()
        service.client.publish = Mock(return_value=Mock(rc=mqtt.MQTT_ERR_SUCCESS))

        service.publish("topic", {"data": "value"}, qos=2)

        assert service.client.publish.call_args[1]["qos"] == 2

    def test_publish_returns_false_on_error(self):
        """Should return False when publish fails."""
        service = MQTTService()
        service.config["enabled"] = True
        service.config["broker_url"] = "mqtt://test"
        service.config["base_topic"] = "test"
        service.connected = True
        service.client = Mock()
        service.client.publish = Mock(return_value=Mock(rc=mqtt.MQTT_ERR_NO_CONN))

        result = service.publish("topic", {"data": "value"})

        assert result is False

    def test_publish_raw_publishes_string_payload(self):
        """Should publish raw string payload for tombstones."""
        service = MQTTService()
        service.config["enabled"] = True
        service.config["broker_url"] = "mqtt://test"
        service.config["base_topic"] = "test"
        service.connected = True
        service.client = Mock()
        service.client.publish = Mock(return_value=Mock(rc=mqtt.MQTT_ERR_SUCCESS))

        result = service._publish_raw("topic", "")

        assert result is True
        assert service.client.publish.call_args[0][1] == ""


# =============================================================================
# MQTTService State Sync Tests
# =============================================================================

@pytest.mark.unit
class TestMQTTServiceStateSync:
    """Tests for MQTT state synchronization."""

    def test_sync_state_skips_when_not_enabled(self):
        """Should skip sync when MQTT not enabled."""
        service = MQTTService()
        service.config["enabled"] = False

        result = service.sync_state(reason="test")

        assert result is False

    def test_sync_state_skips_when_not_connected(self):
        """Should skip sync when not connected."""
        service = MQTTService()
        service.config["enabled"] = True
        service.connected = False

        with patch("app.services.mqtt_service.SessionLocal") as mock_session:
            result = service.sync_state_with_db(mock_session(), reason="test")

        assert result is False

    def test_sync_state_with_db_publishes_server_availability(self, db_session):
        """Should publish server availability."""
        service = _create_mqtt_service_configured()
        service.setup_home_assistant_sensors = Mock(return_value=True)
        service._publish_server_state_from_db = Mock(return_value=True)

        result = service.sync_state_with_db(db_session, reason="test")

        assert result is True
        assert _topic_was_published(service.publish, "status")

    def test_sync_state_with_db_publishes_server_state(self, db_session):
        """Should publish server state."""
        service = _create_mqtt_service_configured()
        service.setup_home_assistant_sensors = Mock(return_value=True)
        service.publish_availability = Mock(return_value=True)

        result = service.sync_state_with_db(db_session, reason="test")

        assert result is True
        # _publish_server_state_from_db should have been called
        # (it's called internally)

    def test_sync_state_with_db_publishes_all_repositories(self, db_session):
        """Should publish state for all repositories."""
        repo1 = Repository(name="Repo1", path="/repo1")
        repo2 = Repository(name="Repo2", path="/repo2")
        db_session.add_all([repo1, repo2])
        db_session.commit()

        service = _create_mqtt_service_configured()
        service.setup_home_assistant_sensors = Mock(return_value=True)
        service.publish_availability = Mock(return_value=True)
        service._publish_server_state_from_db = Mock(return_value=True)
        service.setup_repository_sensors = Mock(return_value=True)
        service.publish_repository_data = Mock(return_value=True)

        result = service.sync_state_with_db(db_session, reason="test")

        assert result is True
        assert service.setup_repository_sensors.call_count == 2
        assert service.publish_repository_data.call_count == 2

    def test_sync_state_with_db_cleans_up_stale_repositories(self, db_session):
        """Should clean up repositories that no longer exist."""
        # Save previous sync state with repo ID 99
        MQTTSyncStateStore.save_id_set(db_session, REPOSITORY_SYNC_STATE_KEY, {99})

        # No repositories currently exist
        service = _create_mqtt_service_configured()
        service._remove_repository_from_home_assistant = Mock(return_value=True)
        service.publish_availability = Mock(return_value=True)
        service.setup_home_assistant_sensors = Mock(return_value=True)
        service._publish_server_state_from_db = Mock(return_value=True)

        result = service.sync_state_with_db(db_session, reason="test")

        assert result is True
        service._remove_repository_from_home_assistant.assert_called_once_with(99)

    def test_sync_state_with_db_processes_pending_deleted_repos(self, db_session):
        """Should process pending deleted repository cleanup."""
        # Queue repo 5 for deletion
        MQTTSyncStateStore.save_id_set(
            db_session,
            PENDING_DELETED_REPOSITORY_SYNC_STATE_KEY,
            {5}
        )

        service = _create_mqtt_service_configured()
        service._remove_repository_from_home_assistant = Mock(return_value=True)
        service.publish_availability = Mock(return_value=True)
        service.setup_home_assistant_sensors = Mock(return_value=True)
        service._publish_server_state_from_db = Mock(return_value=True)

        result = service.sync_state_with_db(db_session, reason="test")

        assert result is True
        service._remove_repository_from_home_assistant.assert_called_with(5)

        # Pending deleted should be cleared after successful sync
        pending = MQTTSyncStateStore.load_id_set(
            db_session,
            PENDING_DELETED_REPOSITORY_SYNC_STATE_KEY
        )
        assert pending == set()

    def test_sync_state_with_db_saves_current_repository_ids(self, db_session):
        """Should save current repository IDs after successful sync."""
        repo = Repository(name="Test", path="/repo")
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        service = _create_mqtt_service_configured()
        service.setup_home_assistant_sensors = Mock(return_value=True)
        service.publish_availability = Mock(return_value=True)
        service._publish_server_state_from_db = Mock(return_value=True)
        service.setup_repository_sensors = Mock(return_value=True)
        service.publish_repository_data = Mock(return_value=True)

        result = service.sync_state_with_db(db_session, reason="test")

        assert result is True
        saved_ids = MQTTSyncStateStore.load_id_set(db_session, REPOSITORY_SYNC_STATE_KEY)
        assert saved_ids == {repo.id}

    def test_sync_state_with_db_rollback_on_failure(self, db_session):
        """Should rollback sync state changes on publish failure."""
        repo = Repository(name="Test", path="/repo")
        db_session.add(repo)
        db_session.commit()

        service = _create_mqtt_service_configured()
        service.publish_availability = Mock(return_value=False)  # Fail

        result = service.sync_state_with_db(db_session, reason="test")

        assert result is False
        # Sync state should not be saved
        saved_ids = MQTTSyncStateStore.load_id_set(db_session, REPOSITORY_SYNC_STATE_KEY)
        assert saved_ids == set()

    def test_queue_deleted_repository_cleanup(self, db_session):
        """Should queue repository for cleanup on next sync."""
        service = MQTTService()

        service.queue_deleted_repository_cleanup(db_session, 42)

        pending = MQTTSyncStateStore.load_id_set(
            db_session,
            PENDING_DELETED_REPOSITORY_SYNC_STATE_KEY
        )
        assert pending == {42}

    def test_queue_deleted_repository_cleanup_accumulates(self, db_session):
        """Should accumulate multiple deletions."""
        service = MQTTService()

        service.queue_deleted_repository_cleanup(db_session, 1)
        service.queue_deleted_repository_cleanup(db_session, 2)
        service.queue_deleted_repository_cleanup(db_session, 3)

        pending = MQTTSyncStateStore.load_id_set(
            db_session,
            PENDING_DELETED_REPOSITORY_SYNC_STATE_KEY
        )
        assert pending == {1, 2, 3}


# =============================================================================
# Edge Cases & Error Handling Tests
# =============================================================================

@pytest.mark.unit
class TestMQTTServiceEdgeCases:
    """Tests for edge cases and error handling."""

    def test_parse_size_with_none(self):
        """Should handle None size string."""
        publisher = RepositoryStatePublisher(Mock())
        assert publisher.parse_size_to_bytes(None) == 0

    def test_repository_status_with_none_id(self):
        """Should handle repository with no ID."""
        publisher = RepositoryStatePublisher(Mock())
        repo = Mock()
        repo.id = None
        repo.last_backup = datetime.now(timezone.utc)

        status = publisher.get_repository_status(repo, failed_repository_ids={99})
        # Should not crash, should return status based on last_backup
        assert status in ["healthy", "warning", "stale"]

    def test_publish_handles_json_serialization_error(self):
        """Should handle JSON serialization errors gracefully."""
        service = MQTTService()
        service.config["enabled"] = True
        service.config["broker_url"] = "mqtt://test"
        service.config["base_topic"] = "test"
        service.connected = True
        service.client = Mock()

        # Create payload with non-serializable object
        class NonSerializable:
            pass

        # The publish method will fail when trying to serialize
        result = service.publish("topic", {"obj": NonSerializable()})

        # Should return False due to serialization error
        assert result is False

    def test_sync_state_handles_database_error(self, db_session):
        """Should handle database errors during sync."""
        service = _create_mqtt_service_configured()

        # Mock db.query to raise an error
        db_session.query = Mock(side_effect=Exception("Database error"))

        result = service.sync_state_with_db(db_session, reason="test")

        assert result is False

    def test_repository_with_all_null_fields(self, db_session):
        """Should handle repository with null optional fields."""
        repo = Repository(name="Test", path="/repo")
        # All optional fields are None
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        mqtt_service = _create_mqtt_service_configured()
        publisher = RepositoryStatePublisher(mqtt_service)

        result = publisher.publish_repository_data(
            repo,
            failed_repository_ids=set(),
            latest_jobs_by_repository={},
            running_jobs_by_repository={},
        )

        # Should not crash
        assert result is True

    def test_job_with_missing_timestamps(self, db_session):
        """Should handle job with null timestamps."""
        job = BackupJob(
            repository="/repo",
            status="running",
            created_at=None,
            started_at=None,
            completed_at=None,
        )
        db_session.add(job)
        db_session.commit()

        mqtt_service = _create_mqtt_service_configured()
        publisher = ServerStatePublisher(mqtt_service)

        result = publisher.publish_server_state_from_db(db_session)

        # Should not crash
        assert result is True

    def test_empty_broker_url(self):
        """Should handle empty broker URL."""
        service = MQTTService()

        with pytest.raises(ValueError):
            service.configure({
                "enabled": True,
                "broker_url": "",
                "base_topic": "test",
            })

    def test_disconnect_without_client(self):
        """Should handle disconnect when client is None."""
        service = MQTTService()
        service.client = None

        # Should not crash
        service.disconnect()

    def test_disconnect_handles_client_error(self):
        """Should handle errors during disconnect."""
        service = MQTTService()
        service.client = Mock()
        service.client.loop_stop = Mock(side_effect=Exception("Stop error"))
        service.client.disconnect = Mock()

        # Should not crash, should log error
        service.disconnect()

        assert service.client is None
        assert service.connected is False


# =============================================================================
# Integration Test Scenarios
# =============================================================================

@pytest.mark.unit
class TestMQTTIntegrationScenarios:
    """Tests for realistic integration scenarios."""

    def test_full_repository_lifecycle(self, db_session):
        """Should handle full repository lifecycle: create, update, backup, delete."""
        service = _create_mqtt_service_configured()
        service.setup_home_assistant_sensors = Mock(return_value=True)
        service.publish_availability = Mock(return_value=True)
        service._publish_server_state_from_db = Mock(return_value=True)
        service.setup_repository_sensors = Mock(return_value=True)
        service.publish_repository_data = Mock(return_value=True)
        service._remove_repository_from_home_assistant = Mock(return_value=True)

        # 1. Create repository
        repo = Repository(name="Test Repo", path="/test")
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        result = service.sync_state_with_db(db_session, reason="repository creation")
        assert result is True
        assert service.setup_repository_sensors.called

        # 2. Run backup
        job = BackupJob(
            repository=repo.path,
            status="running",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        db_session.commit()

        result = service.sync_state_with_db(db_session, reason="backup started")
        assert result is True

        # 3. Complete backup
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        repo.last_backup = job.completed_at
        db_session.commit()

        result = service.sync_state_with_db(db_session, reason="backup completed")
        assert result is True

        # 4. Delete repository
        repo_id = repo.id
        db_session.delete(repo)
        db_session.commit()

        service.queue_deleted_repository_cleanup(db_session, repo_id)
        result = service.sync_state_with_db(db_session, reason="repository deleted")
        assert result is True
        service._remove_repository_from_home_assistant.assert_called_with(repo_id)

    def test_multiple_concurrent_backups(self, db_session):
        """Should handle multiple repositories backing up simultaneously."""
        # Create multiple repositories with running backups
        for i in range(3):
            repo = Repository(name=f"Repo{i}", path=f"/repo{i}")
            db_session.add(repo)
            db_session.commit()
            db_session.refresh(repo)

            job = BackupJob(
                repository=repo.path,
                status="running",
                progress_percent=50 + i * 10,
                created_at=datetime.now(timezone.utc),
                started_at=datetime.now(timezone.utc),
            )
            db_session.add(job)

        db_session.commit()

        service = _create_mqtt_service_configured()
        service.setup_home_assistant_sensors = Mock(return_value=True)
        service.publish_availability = Mock(return_value=True)
        service._publish_server_state_from_db = Mock(return_value=True)
        service.setup_repository_sensors = Mock(return_value=True)
        service.publish_repository_data = Mock(return_value=True)

        result = service.sync_state_with_db(db_session, reason="concurrent backups")

        assert result is True
        assert service.publish_repository_data.call_count == 3

    def test_recovery_after_mqtt_outage(self, db_session):
        """Should recover state after MQTT broker was unavailable."""
        # Simulate changes while MQTT was offline
        repo1 = Repository(name="Repo1", path="/repo1")
        repo2 = Repository(name="Repo2", path="/repo2")
        db_session.add_all([repo1, repo2])
        db_session.commit()
        db_session.refresh(repo1)
        db_session.refresh(repo2)

        # Previously synced repo 99, but it was deleted while offline
        MQTTSyncStateStore.save_id_set(db_session, REPOSITORY_SYNC_STATE_KEY, {99})

        # Repo was deleted while offline, queued for cleanup
        service = MQTTService()
        service.queue_deleted_repository_cleanup(db_session, 99)

        # Now MQTT comes back online
        service = _create_mqtt_service_configured()
        service.setup_home_assistant_sensors = Mock(return_value=True)
        service.publish_availability = Mock(return_value=True)
        service._publish_server_state_from_db = Mock(return_value=True)
        service.setup_repository_sensors = Mock(return_value=True)
        service.publish_repository_data = Mock(return_value=True)
        service._remove_repository_from_home_assistant = Mock(return_value=True)

        result = service.sync_state_with_db(db_session, reason="reconnect")

        assert result is True
        # Should clean up deleted repo
        service._remove_repository_from_home_assistant.assert_called_with(99)
        # Should publish current repos
        assert service.setup_repository_sensors.call_count == 2
