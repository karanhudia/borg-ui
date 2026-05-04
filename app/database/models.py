from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Float,
    BigInteger,
    Table,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database.database import Base


# Helper function for timezone-aware UTC timestamps
def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    full_name = Column(String, nullable=True)
    password_hash = Column(String)
    email = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    auth_source = Column(String, default="local", nullable=False)
    oidc_subject = Column(String, nullable=True, index=True)
    oidc_last_id_token_encrypted = Column(Text, nullable=True)
    role = Column(String, default="viewer", nullable=False)
    all_repositories_role = Column(String, nullable=True)

    @property
    def is_admin(self) -> bool:
        """Backward-compat property — all existing guards continue to work."""
        return self.role == "admin"

    must_change_password = Column(
        Boolean, default=False
    )  # Force password change on next login
    totp_secret_encrypted = Column(String, nullable=True)
    totp_enabled = Column(Boolean, default=False, nullable=False)
    totp_enabled_at = Column(DateTime, nullable=True)
    totp_recovery_codes_hashes = Column(Text, nullable=True)
    analytics_enabled = Column(Boolean, default=True)  # User's analytics preference
    analytics_consent_given = Column(
        Boolean, default=False
    )  # Whether user has responded to consent banner
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    passkeys = relationship(
        "PasskeyCredential", back_populates="user", cascade="all, delete-orphan"
    )


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String, nullable=False)
    token_hash = Column(String, nullable=False)
    prefix = Column(String(12), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    last_used_at = Column(DateTime, nullable=True)


class PasskeyCredential(Base):
    __tablename__ = "passkey_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String, nullable=False)
    credential_id = Column(String, nullable=False, unique=True, index=True)
    public_key = Column(Text, nullable=False)
    sign_count = Column(Integer, default=0, nullable=False)
    transports = Column(Text, nullable=True)
    device_type = Column(String, nullable=True)
    backed_up = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    last_used_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="passkeys")


class UserRepositoryPermission(Base):
    __tablename__ = "user_repository_permissions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    repository_id = Column(
        Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "repository_id"),)


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    path = Column(String, unique=True, index=True)
    encryption = Column(String, default="repokey")
    compression = Column(String, default="lz4")
    passphrase = Column(
        String, nullable=True
    )  # Borg repository passphrase (for encrypted repos)
    has_keyfile = Column(
        Boolean, default=False
    )  # Whether repository has a keyfile (keyfile/keyfile-blake2 encryption)
    source_directories = Column(
        Text, nullable=True
    )  # JSON array of directories to backup
    exclude_patterns = Column(
        Text, nullable=True
    )  # JSON array of exclude patterns (e.g., ["*.log", "*.tmp"])
    last_backup = Column(DateTime, nullable=True)
    last_check = Column(DateTime, nullable=True)  # Last successful check completion
    last_compact = Column(DateTime, nullable=True)  # Last successful compact completion
    total_size = Column(String, nullable=True)
    archive_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # New fields for remote repositories
    repository_type = Column(String, default="local")  # local, ssh, sftp
    host = Column(String, nullable=True)  # For SSH repositories
    port = Column(Integer, default=22)  # SSH port
    username = Column(String, nullable=True)  # SSH username
    ssh_key_id = Column(
        Integer, ForeignKey("ssh_keys.id"), nullable=True
    )  # Associated SSH key
    connection_id = Column(
        Integer, ForeignKey("ssh_connections.id"), nullable=True
    )  # Associated SSH connection (preferred over host/port/username)
    remote_path = Column(
        String, nullable=True
    )  # Path to borg binary on remote server (e.g., /usr/local/bin/borg)

    # New fields for authentication status
    auth_status = Column(
        String, default="unknown"
    )  # connected, failed, testing, unknown
    last_auth_test = Column(DateTime, nullable=True)
    auth_error_message = Column(Text, nullable=True)

    # Backup hooks
    pre_backup_script = Column(Text, nullable=True)  # Shell script to run before backup
    post_backup_script = Column(Text, nullable=True)  # Shell script to run after backup
    pre_backup_script_parameters = Column(
        JSON, nullable=True
    )  # Parameters for pre-backup inline script (JSON dict)
    post_backup_script_parameters = Column(
        JSON, nullable=True
    )  # Parameters for post-backup inline script (JSON dict)
    hook_timeout = Column(
        Integer, default=300
    )  # Hook timeout in seconds (legacy, kept for compatibility)
    pre_hook_timeout = Column(
        Integer, default=300
    )  # Pre-backup hook timeout in seconds
    post_hook_timeout = Column(
        Integer, default=300
    )  # Post-backup hook timeout in seconds
    continue_on_hook_failure = Column(
        Boolean, default=False
    )  # Whether to continue backup if pre-hook fails
    skip_on_hook_failure = Column(
        Boolean, default=False
    )  # Whether to skip backup gracefully if pre-hook fails (not a failure)

    # Repository mode (for observability-only repos)
    mode = Column(
        String, default="full"
    )  # full: backups + observability, observe: observability-only
    bypass_lock = Column(
        Boolean, default=False
    )  # Use --bypass-lock for read-only storage access (observe-only repos)

    # Borg version this repository was created with (1 or 2)
    # Controls which binary and /api/v2/ routes are used for all operations
    borg_version = Column(Integer, default=1, nullable=False)

    # Custom flags for borg create command (advanced users)
    custom_flags = Column(
        Text, nullable=True
    )  # Custom command-line flags for borg create (e.g., "--stats --progress")

    # Data source location (for pull-based backups)
    source_ssh_connection_id = Column(
        Integer, ForeignKey("ssh_connections.id"), nullable=True
    )  # SSH connection for remote data source

    # Scheduled checks
    check_cron_expression = Column(
        String, nullable=True
    )  # NULL = disabled, cron expression for schedule
    check_timezone = Column(
        String, default="UTC", nullable=False
    )  # IANA timezone used to interpret check_cron_expression
    last_scheduled_check = Column(
        DateTime, nullable=True
    )  # Last scheduled check execution time
    next_scheduled_check = Column(DateTime, nullable=True)  # Next scheduled check time
    check_max_duration = Column(
        Integer, default=3600
    )  # Max check duration in seconds (for partial checks)
    notify_on_check_success = Column(
        Boolean, default=False, nullable=False
    )  # Per-repository override
    notify_on_check_failure = Column(
        Boolean, default=True, nullable=False
    )  # Per-repository override
    restore_check_cron_expression = Column(
        String, nullable=True
    )  # NULL = disabled, cron expression for restore verification
    restore_check_timezone = Column(
        String, default="UTC", nullable=False
    )  # IANA timezone used to interpret restore_check_cron_expression
    restore_check_paths = Column(
        Text, nullable=True
    )  # JSON array of paths to restore into a disposable temp directory
    restore_check_full_archive = Column(
        Boolean, default=False, nullable=False
    )  # Explicit opt-in to verify by extracting the full latest archive
    last_restore_check = Column(
        DateTime, nullable=True
    )  # Last successful restore verification completion
    last_scheduled_restore_check = Column(
        DateTime, nullable=True
    )  # Last scheduled restore verification execution time
    next_scheduled_restore_check = Column(
        DateTime, nullable=True
    )  # Next scheduled restore verification time
    notify_on_restore_check_success = Column(
        Boolean, default=False, nullable=False
    )  # Per-repository override
    notify_on_restore_check_failure = Column(
        Boolean, default=True, nullable=False
    )  # Per-repository override

    # Relationships
    ssh_key = relationship("SSHKey", back_populates="repositories")


class SSHKey(Base):
    __tablename__ = "ssh_keys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(Text, nullable=True)
    public_key = Column(Text)
    private_key = Column(Text)  # Encrypted
    key_type = Column(String, default="rsa")  # rsa, ed25519, ecdsa
    is_active = Column(Boolean, default=True)
    is_system_key = Column(
        Boolean, default=False, index=True
    )  # Identifies the system SSH key
    fingerprint = Column(String, nullable=True)  # SSH key fingerprint
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    repositories = relationship("Repository", back_populates="ssh_key")
    connections = relationship("SSHConnection", back_populates="ssh_key")


class SSHConnection(Base):
    __tablename__ = "ssh_connections"

    id = Column(Integer, primary_key=True, index=True)
    ssh_key_id = Column(Integer, ForeignKey("ssh_keys.id"), nullable=True)
    host = Column(String)
    username = Column(String)
    port = Column(Integer, default=22)
    default_path = Column(
        String, nullable=True
    )  # Default starting path for SSH browsing (e.g., /home for Hetzner Storage Box)
    ssh_path_prefix = Column(
        String, nullable=True
    )  # Path prefix for SSH commands (e.g., /volume1 for Synology). SFTP uses path as-is, SSH prepends this prefix.
    mount_point = Column(
        String, nullable=True
    )  # Logical mount point (e.g., /hetzner, /homeserver)
    status = Column(String, default="unknown")  # connected, failed, testing, unknown
    last_test = Column(DateTime, nullable=True)
    last_success = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    # Storage information
    storage_total = Column(BigInteger, nullable=True)  # Total storage in bytes
    storage_used = Column(BigInteger, nullable=True)  # Used storage in bytes
    storage_available = Column(BigInteger, nullable=True)  # Available storage in bytes
    storage_percent_used = Column(Float, nullable=True)  # Percentage of storage used
    last_storage_check = Column(
        DateTime, nullable=True
    )  # Last time storage was checked

    # Remote backup source configuration
    is_backup_source = Column(
        Boolean, default=False
    )  # Mark this connection as a backup source
    borg_binary_path = Column(
        String, default="/usr/bin/borg"
    )  # Path to borg on remote host
    borg_version = Column(String, nullable=True)  # Detected borg version
    last_borg_check = Column(DateTime, nullable=True)  # Last time borg was verified

    # SSH key deployment options
    use_sftp_mode = Column(
        Boolean, default=True, nullable=False
    )  # Use SFTP mode (-s flag) for ssh-copy-id (required by Hetzner, breaks Synology)
    use_sudo = Column(
        Boolean, default=False
    )  # Prepend sudo when running borg on remote host

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    ssh_key = relationship("SSHKey", back_populates="connections")


class Configuration(Base):
    __tablename__ = "configurations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(Text, nullable=True)
    content = Column(Text)  # YAML content
    is_default = Column(Boolean, default=False, index=True)
    is_valid = Column(Boolean, default=False)  # Validation status
    validation_errors = Column(Text, nullable=True)  # JSON string of errors
    validation_warnings = Column(Text, nullable=True)  # JSON string of warnings
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class BackupJob(Base):
    __tablename__ = "backup_jobs"

    id = Column(Integer, primary_key=True, index=True)
    repository = Column(String)  # Repository path/name
    status = Column(
        String, default="pending"
    )  # pending, running, completed, completed_with_warnings, failed
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)  # Full logs (stored after completion)
    log_file_path = Column(String, nullable=True)  # Path to streaming log file
    scheduled_job_id = Column(
        Integer, ForeignKey("scheduled_jobs.id"), nullable=True
    )  # NULL for manual backups

    # Detailed progress fields from Borg JSON output
    original_size = Column(BigInteger, default=0)  # Original uncompressed size in bytes
    compressed_size = Column(BigInteger, default=0)  # Compressed size in bytes
    deduplicated_size = Column(BigInteger, default=0)  # Deduplicated size in bytes
    nfiles = Column(Integer, default=0)  # Number of files processed
    current_file = Column(Text, nullable=True)  # Current file being processed
    progress_percent = Column(Float, default=0.0)  # Progress percentage
    backup_speed = Column(Float, default=0.0)  # Current backup speed in MB/s
    total_expected_size = Column(
        BigInteger, default=0
    )  # Total size of source directories (calculated before backup)
    estimated_time_remaining = Column(Integer, default=0)  # Estimated seconds remaining

    # Archive name created by this backup
    archive_name = Column(
        String, nullable=True
    )  # Name of the archive created (e.g., "manual-backup-2024-04-13T10:30:00")

    # Maintenance status tracking
    maintenance_status = Column(
        String, nullable=True
    )  # null, "running_prune", "prune_completed", "prune_failed", "running_compact", "compact_completed", "compact_failed", "maintenance_completed"

    # Remote backup execution
    execution_mode = Column(String, default="local")  # "local" or "remote_ssh"
    source_ssh_connection_id = Column(
        Integer, ForeignKey("ssh_connections.id"), nullable=True
    )  # SSH connection for remote execution
    remote_process_pid = Column(Integer, nullable=True)  # PID on remote host
    remote_hostname = Column(String, nullable=True)  # Remote hostname for reference

    created_at = Column(DateTime, default=utc_now)


class RestoreJob(Base):
    __tablename__ = "restore_jobs"

    id = Column(Integer, primary_key=True, index=True)
    repository = Column(String)  # Repository path
    archive = Column(String)  # Archive name
    destination = Column(String)  # Restore destination path
    status = Column(
        String, default="pending"
    )  # pending, running, completed, failed, cancelled
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)  # Full logs (stored after completion)

    # Progress tracking fields
    nfiles = Column(Integer, default=0)  # Number of files restored
    current_file = Column(Text, nullable=True)  # Current file being restored
    progress_percent = Column(Float, default=0.0)  # Progress percentage

    # Speed and ETA tracking (similar to backup jobs)
    original_size = Column(BigInteger, default=0)  # Total bytes to restore
    restored_size = Column(BigInteger, default=0)  # Bytes restored so far
    restore_speed = Column(Float, default=0.0)  # Current restore speed in MB/s
    estimated_time_remaining = Column(Integer, default=0)  # Estimated seconds remaining

    # Remote restore fields
    destination_type = Column(String(50), default="local")  # 'local' or 'ssh'
    destination_connection_id = Column(
        Integer, ForeignKey("ssh_connections.id"), nullable=True
    )
    destination_connection = relationship(
        "SSHConnection", foreign_keys=[destination_connection_id]
    )
    execution_mode = Column(
        String(50), default="local_to_local"
    )  # 'local_to_local', 'ssh_to_local', 'local_to_ssh'
    temp_extraction_path = Column(
        String(255), nullable=True
    )  # For local→SSH two-phase restore
    destination_hostname = Column(String(255), nullable=True)  # For display purposes
    repository_type = Column(String(50), default="local")  # 'local' or 'ssh'

    created_at = Column(DateTime, default=utc_now)


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    cron_expression = Column(
        String, nullable=False
    )  # e.g., "0 2 * * *" for daily at 2 AM
    timezone = Column(
        String, default="UTC", nullable=False
    )  # IANA timezone used to interpret cron_expression
    repository = Column(
        String, nullable=True
    )  # Repository path/ID to backup (legacy, for single-repo schedules)
    repository_id = Column(
        Integer, ForeignKey("repositories.id"), nullable=True
    )  # For single-repo schedules (nullable for multi-repo)
    enabled = Column(Boolean, default=True)  # Whether the job is active
    last_run = Column(DateTime, nullable=True)  # Last execution time
    next_run = Column(DateTime, nullable=True)  # Next scheduled execution time
    description = Column(Text, nullable=True)  # User description of the job
    archive_name_template = Column(
        String, nullable=True
    )  # Template for archive names (e.g., "{job_name}-{now}")

    # Multi-repository schedule settings
    run_repository_scripts = Column(
        Boolean, default=False, nullable=False
    )  # Whether to run per-repository pre/post scripts
    pre_backup_script_id = Column(
        Integer, ForeignKey("scripts.id"), nullable=True
    )  # Schedule-level pre-backup script (runs once)
    post_backup_script_id = Column(
        Integer, ForeignKey("scripts.id"), nullable=True
    )  # Schedule-level post-backup script (runs once)
    pre_backup_script_parameters = Column(
        JSON, nullable=True
    )  # Parameters for pre-backup script (JSON dict)
    post_backup_script_parameters = Column(
        JSON, nullable=True
    )  # Parameters for post-backup script (JSON dict)

    # Prune and compact settings
    run_prune_after = Column(Boolean, default=False)  # Run prune after backup
    run_compact_after = Column(Boolean, default=False)  # Run compact after prune
    prune_keep_hourly = Column(
        Integer, default=0
    )  # Keep N hourly backups (0 = disabled)
    prune_keep_daily = Column(Integer, default=7)  # Keep N daily backups
    prune_keep_weekly = Column(Integer, default=4)  # Keep N weekly backups
    prune_keep_monthly = Column(Integer, default=6)  # Keep N monthly backups
    prune_keep_quarterly = Column(
        Integer, default=0
    )  # Keep N quarterly backups (0 = disabled)
    prune_keep_yearly = Column(Integer, default=1)  # Keep N yearly backups
    last_prune = Column(DateTime, nullable=True)  # Last prune execution time
    last_compact = Column(DateTime, nullable=True)  # Last compact execution time

    # Remote backup execution
    execution_mode = Column(String, default="local")  # "local" or "remote_ssh"
    source_ssh_connection_id = Column(
        Integer, ForeignKey("ssh_connections.id"), nullable=True
    )  # SSH connection for remote execution

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, nullable=True)


class ScheduledJobRepository(Base):
    """Junction table for multi-repository scheduled jobs"""

    __tablename__ = "scheduled_job_repositories"
    __table_args__ = (
        UniqueConstraint(
            "scheduled_job_id", "repository_id", name="uq_schedule_repository"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    scheduled_job_id = Column(
        Integer,
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id = Column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    execution_order = Column(
        Integer, nullable=False
    )  # Order in which repositories should be backed up

    created_at = Column(DateTime, default=utc_now)

    def __repr__(self):
        return f"<ScheduledJobRepository(schedule_id={self.scheduled_job_id}, repo_id={self.repository_id}, order={self.execution_order})>"


class CheckJob(Base):
    __tablename__ = "check_jobs"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    repository_path = Column(
        String, nullable=True
    )  # Captured at job creation for display even if repo is deleted
    status = Column(
        String, default="pending"
    )  # pending, running, completed, failed, cancelled
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)  # 0-100 percentage
    progress_message = Column(
        String, nullable=True
    )  # Current progress message (e.g., "Checking segments 25%")
    error_message = Column(Text, nullable=True)
    logs = Column(
        Text, nullable=True
    )  # Deprecated: kept for backwards compatibility, use log_file_path instead
    log_file_path = Column(String, nullable=True)  # Path to log file on disk
    has_logs = Column(Boolean, default=False)  # Flag indicating if logs are available
    max_duration = Column(
        Integer, nullable=True
    )  # Maximum duration in seconds (for partial checks)
    process_pid = Column(Integer, nullable=True)  # Container PID for orphan detection
    process_start_time = Column(
        BigInteger, nullable=True
    )  # Process start time in jiffies for PID uniqueness
    scheduled_check = Column(
        Boolean, default=False, nullable=False
    )  # True if triggered by scheduler, False if manual
    created_at = Column(DateTime, default=utc_now)


class RestoreCheckJob(Base):
    __tablename__ = "restore_check_jobs"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    repository_path = Column(
        String, nullable=True
    )  # Captured at job creation for display even if repo is deleted
    archive_name = Column(
        String, nullable=True
    )  # Archive selected for verification, usually the latest archive
    status = Column(
        String, default="pending"
    )  # pending, running, completed, completed_with_warnings, failed, cancelled
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)  # 0-100 percentage
    progress_message = Column(
        String, nullable=True
    )  # Current progress message (e.g., "Restoring archive to temp dir")
    error_message = Column(Text, nullable=True)
    logs = Column(
        Text, nullable=True
    )  # Deprecated: kept for backwards compatibility, use log_file_path instead
    log_file_path = Column(String, nullable=True)  # Path to log file on disk
    has_logs = Column(Boolean, default=False)  # Flag indicating if logs are available
    probe_paths = Column(
        Text, nullable=True
    )  # JSON array of paths restored for verification
    full_archive = Column(
        Boolean, default=False, nullable=False
    )  # Whether the verification extracted the full archive
    process_pid = Column(Integer, nullable=True)  # Container PID for orphan detection
    process_start_time = Column(
        BigInteger, nullable=True
    )  # Process start time in jiffies for PID uniqueness
    scheduled_restore_check = Column(
        Boolean, default=False, nullable=False
    )  # True if triggered by scheduler, False if manual
    created_at = Column(DateTime, default=utc_now)


class CompactJob(Base):
    __tablename__ = "compact_jobs"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    repository_path = Column(
        String, nullable=True
    )  # Captured at job creation for display even if repo is deleted
    status = Column(
        String, default="pending"
    )  # pending, running, completed, failed, cancelled
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)  # 0-100 percentage
    progress_message = Column(
        String, nullable=True
    )  # Current progress message (e.g., "Compacting segments 50%")
    error_message = Column(Text, nullable=True)
    logs = Column(
        Text, nullable=True
    )  # Deprecated: kept for backwards compatibility, use log_file_path instead
    log_file_path = Column(String, nullable=True)  # Path to log file on disk
    has_logs = Column(Boolean, default=False)  # Flag indicating if logs are available
    scheduled_compact = Column(
        Boolean, default=False, nullable=False
    )  # True if triggered by scheduler, False if manual
    process_pid = Column(Integer, nullable=True)  # Container PID for orphan detection
    process_start_time = Column(
        BigInteger, nullable=True
    )  # Process start time in jiffies for PID uniqueness
    created_at = Column(DateTime, default=utc_now)


class PruneJob(Base):
    __tablename__ = "prune_jobs"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    repository_path = Column(
        String, nullable=True
    )  # Captured at job creation for display even if repo is deleted
    status = Column(
        String, default="pending"
    )  # pending, running, completed, failed, cancelled
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    logs = Column(
        Text, nullable=True
    )  # Deprecated: kept for backwards compatibility, use log_file_path instead
    log_file_path = Column(String, nullable=True)  # Path to log file on disk
    has_logs = Column(Boolean, default=False)  # Flag indicating if logs are available
    scheduled_prune = Column(
        Boolean, default=False, nullable=False
    )  # True if triggered by scheduler, False if manual
    created_at = Column(DateTime, default=utc_now)


class DeleteArchiveJob(Base):
    __tablename__ = "delete_archive_jobs"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(
        Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    repository_path = Column(
        String, nullable=True
    )  # Captured at job creation for display even if repo is deleted
    archive_name = Column(String, nullable=False)  # Name of the archive being deleted
    status = Column(
        String, default="pending"
    )  # pending, running, completed, failed, cancelled
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)  # 0-100 percentage
    progress_message = Column(String, nullable=True)  # Current progress message
    error_message = Column(Text, nullable=True)
    logs = Column(
        Text, nullable=True
    )  # Deprecated: kept for backwards compatibility, use log_file_path instead
    log_file_path = Column(String, nullable=True)  # Path to log file on disk
    has_logs = Column(Boolean, default=False)  # Flag indicating if logs are available
    process_pid = Column(Integer, nullable=True)  # Container PID for orphan detection
    process_start_time = Column(
        BigInteger, nullable=True
    )  # Process start time in jiffies for PID uniqueness
    created_at = Column(DateTime, default=utc_now)


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    # Operation timeouts (in seconds)

    backup_timeout = Column(Integer, default=3600)  # Default 1 hour for backup/restore
    mount_timeout = Column(Integer, default=120)  # Default 2 minutes for borg mount
    info_timeout = Column(Integer, default=600)  # Default 10 minutes for borg info
    list_timeout = Column(Integer, default=600)  # Default 10 minutes for borg list
    init_timeout = Column(Integer, default=300)  # Default 5 minutes for borg init
    source_size_timeout = Column(
        Integer, nullable=True
    )  # Default 1 hour for du-based source size calculation

    max_concurrent_backups = Column(Integer, default=1)
    max_concurrent_scheduled_backups = Column(Integer, default=2)
    max_concurrent_scheduled_checks = Column(Integer, default=4)
    log_retention_days = Column(Integer, default=30)
    log_save_policy = Column(
        String, default="failed_and_warnings"
    )  # Options: "failed_only", "failed_and_warnings", "all_jobs"
    log_max_total_size_mb = Column(
        Integer, default=500
    )  # Maximum total size of all log files in MB
    log_cleanup_on_startup = Column(
        Boolean, default=True
    )  # Run log cleanup on application startup
    cache_ttl_minutes = Column(
        Integer, default=120
    )  # Cache TTL in minutes (2 hours default)
    cache_max_size_mb = Column(
        Integer, default=2048
    )  # Maximum cache size in MB (2GB default)
    redis_url = Column(
        String, nullable=True
    )  # External Redis URL (e.g., redis://host:6379/0)
    browse_max_items = Column(
        Integer, default=1_000_000
    )  # Maximum items to load when browsing archives
    browse_max_memory_mb = Column(
        Integer, default=1024
    )  # Maximum memory (MB) for archive browsing
    stats_refresh_interval_minutes = Column(
        Integer, default=60
    )  # How often to refresh repository stats (0 = disabled)
    last_stats_refresh = Column(
        DateTime, nullable=True
    )  # Last time stats were refreshed
    email_notifications = Column(Boolean, default=False)
    webhook_url = Column(String, nullable=True)
    auto_cleanup = Column(Boolean, default=False)
    cleanup_retention_days = Column(Integer, default=90)

    # Borg binary paths — both versions can coexist in the Docker image
    borg1_binary_path = Column(String, default="borg", nullable=False)
    borg2_binary_path = Column(String, default="borg2", nullable=False)

    # Beta features
    use_new_wizard = Column(
        Boolean, default=False, nullable=False
    )  # Enable new repository wizard (beta)
    bypass_lock_on_info = Column(
        Boolean, default=False, nullable=False
    )  # Use --bypass-lock for all borg info commands (beta fix for SSH lock issues)
    bypass_lock_on_list = Column(
        Boolean, default=False, nullable=False
    )  # Use --bypass-lock for all borg list commands (beta fix for concurrent operation lock issues)
    show_restore_tab = Column(
        Boolean, default=False, nullable=False
    )  # Show legacy Restore tab in navigation (beta feature)
    borg2_fast_browse_beta_enabled = Column(
        Boolean, default=False, nullable=False
    )  # Use depth-limited Borg 2 archive browse and hide directory sizes
    mqtt_beta_enabled = Column(
        Boolean, default=False, nullable=False
    )  # Expose MQTT under beta features

    # MQTT settings
    mqtt_enabled = Column(
        Boolean, default=False, nullable=False
    )  # Enable MQTT publishing
    mqtt_broker_url = Column(
        String, nullable=True
    )  # MQTT broker URL (e.g., mqtt://broker.example.com)
    mqtt_broker_port = Column(Integer, default=1883, nullable=False)  # MQTT broker port
    mqtt_username = Column(String, nullable=True)  # MQTT username
    mqtt_password = Column(String, nullable=True)  # MQTT password
    mqtt_client_id = Column(String, default="borg-ui", nullable=False)  # MQTT client ID
    mqtt_qos = Column(
        Integer, default=1, nullable=False
    )  # Quality of Service (0, 1, or 2)
    mqtt_retain = Column(Boolean, default=False, nullable=False)  # Retain messages
    mqtt_tls_enabled = Column(Boolean, default=False, nullable=False)  # Enable TLS
    mqtt_tls_ca_cert = Column(String, nullable=True)  # Path to CA certificate file
    mqtt_tls_client_cert = Column(
        String, nullable=True
    )  # Path to client certificate file
    mqtt_tls_client_key = Column(String, nullable=True)  # Path to client key file

    # Prometheus metrics settings
    metrics_enabled = Column(Boolean, default=False, nullable=False)
    metrics_require_auth = Column(Boolean, default=False, nullable=False)
    metrics_token = Column(String, nullable=True)

    # Built-in OIDC / SSO settings
    oidc_enabled = Column(Boolean, default=False, nullable=False)
    oidc_disable_local_auth = Column(Boolean, default=False, nullable=False)
    oidc_provider_name = Column(String, nullable=True)
    oidc_discovery_url = Column(String, nullable=True)
    oidc_client_id = Column(String, nullable=True)
    oidc_client_secret_encrypted = Column(String, nullable=True)
    oidc_token_auth_method = Column(
        String, default="client_secret_post", nullable=False
    )
    oidc_scopes = Column(String, default="openid profile email", nullable=False)
    oidc_redirect_uri_override = Column(String, nullable=True)
    oidc_end_session_endpoint_override = Column(String, nullable=True)
    oidc_claim_username = Column(String, default="preferred_username", nullable=False)
    oidc_claim_email = Column(String, default="email", nullable=False)
    oidc_claim_full_name = Column(String, default="name", nullable=False)
    oidc_group_claim = Column(String, nullable=True)
    oidc_role_claim = Column(String, nullable=True)
    oidc_admin_groups = Column(Text, nullable=True)
    oidc_all_repositories_role_claim = Column(String, nullable=True)
    oidc_new_user_mode = Column(String, default="viewer", nullable=False)
    oidc_new_user_template_username = Column(String, nullable=True)
    oidc_default_role = Column(String, default="viewer", nullable=False)
    oidc_default_all_repositories_role = Column(
        String, default="viewer", nullable=False
    )

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Deployment profile
    deployment_type = Column(String, default="individual", nullable=False)
    enterprise_name = Column(String, nullable=True)


class OidcLoginState(Base):
    __tablename__ = "oidc_login_states"

    id = Column(Integer, primary_key=True, index=True)
    state_id = Column(String, unique=True, nullable=False, index=True)
    nonce = Column(String, nullable=False)
    code_verifier = Column(Text, nullable=False)
    return_to = Column(Text, nullable=False)
    flow = Column(String, default="login", nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class AuthEvent(Base):
    __tablename__ = "auth_events"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    auth_source = Column(String, nullable=False, index=True)
    username = Column(String, nullable=True, index=True)
    email = Column(String, nullable=True)
    success = Column(Boolean, default=True, nullable=False, index=True)
    detail = Column(Text, nullable=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False, index=True)


class OidcExchangeGrant(Base):
    __tablename__ = "oidc_exchange_grants"

    id = Column(Integer, primary_key=True, index=True)
    grant_id = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, nullable=False, index=True)
    oidc_subject = Column(String, nullable=True, index=True)
    email = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    groups_json = Column(Text, nullable=True)
    role = Column(String, nullable=True)
    all_repositories_role = Column(String, nullable=True)
    id_token_hint_encrypted = Column(Text, nullable=True)
    used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class AuthRateLimitBucket(Base):
    __tablename__ = "auth_rate_limit_buckets"

    id = Column(Integer, primary_key=True, index=True)
    bucket_key = Column(String, nullable=False, unique=True, index=True)
    scope = Column(String, nullable=False, index=True)
    subject = Column(String, nullable=False)
    client_ip = Column(String, nullable=False, index=True)
    failure_count = Column(Integer, default=0, nullable=False)
    window_started_at = Column(DateTime, default=utc_now, nullable=False)
    last_attempt_at = Column(DateTime, default=utc_now, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class LicensingState(Base):
    __tablename__ = "licensing_state"

    id = Column(Integer, primary_key=True, index=True)
    instance_id = Column(String, unique=True, nullable=False, index=True)
    plan = Column(String, default="community", nullable=False)
    status = Column(
        String, default="none", nullable=False
    )  # none, active, expired, invalid
    is_trial = Column(Boolean, default=False, nullable=False)
    trial_consumed = Column(Boolean, default=False, nullable=False)
    entitlement_id = Column(String, nullable=True, unique=True)
    key_id = Column(String, nullable=True)
    customer_id = Column(String, nullable=True)
    license_id = Column(String, nullable=True)
    max_users = Column(Integer, nullable=True)
    issued_at = Column(DateTime, nullable=True)
    starts_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    last_refresh_at = Column(DateTime, nullable=True)
    last_refresh_error = Column(Text, nullable=True)
    payload_json = Column(JSON, nullable=True)
    signature = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class MQTTSyncState(Base):
    """
    Persistent MQTT synchronization metadata.

    Stores compact sync markers so cleanup can be derived from DB state
    even if MQTT/Home Assistant were unavailable when a change happened.
    """

    __tablename__ = "mqtt_sync_state"

    id = Column(Integer, primary_key=True, index=True)
    sync_key = Column(String, unique=True, nullable=False, index=True)
    sync_value = Column(Text, nullable=False)  # JSON payload
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


# Association table for repository notification filters
repository_notifications = Table(
    "repository_notifications",
    Base.metadata,
    Column(
        "notification_setting_id",
        Integer,
        ForeignKey("notification_settings.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "repository_id",
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class NotificationSettings(Base):
    """
    Notification settings model.

    Stores Apprise-compatible notification URLs and configuration.
    """

    __tablename__ = "notification_settings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(
        String(255), nullable=False
    )  # User-friendly name (e.g., "Slack - DevOps Channel")
    service_url = Column(
        Text, nullable=False
    )  # Apprise URL (e.g., "slack://TokenA/TokenB/TokenC/")
    enabled = Column(Boolean, default=True, nullable=False)

    # Customization
    title_prefix = Column(
        String(100), nullable=True
    )  # Optional custom prefix for notification titles (e.g., "[Production]")
    include_job_name_in_title = Column(
        Boolean, default=False, nullable=False
    )  # Include job/schedule name in notification title
    # Note: JSON data is automatically sent for json:// and jsons:// webhook URLs (no field needed)

    # Event triggers
    notify_on_backup_start = Column(Boolean, default=False, nullable=False)
    notify_on_backup_success = Column(Boolean, default=False, nullable=False)
    notify_on_backup_warning = Column(Boolean, default=False, nullable=False)
    notify_on_backup_failure = Column(Boolean, default=True, nullable=False)
    notify_on_restore_success = Column(Boolean, default=False, nullable=False)
    notify_on_restore_failure = Column(Boolean, default=True, nullable=False)
    notify_on_schedule_failure = Column(Boolean, default=True, nullable=False)
    notify_on_check_success = Column(Boolean, default=False, nullable=False)
    notify_on_check_failure = Column(Boolean, default=True, nullable=False)

    # Repository filtering
    monitor_all_repositories = Column(
        Boolean, default=True, nullable=False
    )  # If True, applies to all repos

    # Relationships
    repositories = relationship(
        "Repository",
        secondary=repository_notifications,
        backref="notification_settings",
    )

    # Timestamps
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    last_used_at = Column(DateTime, nullable=True)  # Last successful notification sent

    def __repr__(self):
        return f"<NotificationSettings(id={self.id}, name='{self.name}', enabled={self.enabled})>"


class InstalledPackage(Base):
    __tablename__ = "installed_packages"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(
        String, unique=True, index=True, nullable=False
    )  # Package name (e.g., "wakeonlan")
    install_command = Column(
        String, nullable=False
    )  # Command to install (e.g., "apt-get install -y wakeonlan")
    description = Column(String, nullable=True)  # Optional description
    status = Column(
        String, default="pending", nullable=False
    )  # pending, installed, failed
    install_log = Column(Text, nullable=True)  # Installation output/logs
    installed_at = Column(DateTime, nullable=True)  # When successfully installed
    last_check = Column(DateTime, nullable=True)  # Last time we verified it exists
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Cascade delete install jobs when package is deleted
    install_jobs = relationship(
        "PackageInstallJob", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self):
        return f"<InstalledPackage(id={self.id}, name='{self.name}', status='{self.status}')>"


class PackageInstallJob(Base):
    __tablename__ = "package_install_jobs"

    id = Column(Integer, primary_key=True, index=True)
    package_id = Column(
        Integer, ForeignKey("installed_packages.id", ondelete="CASCADE"), nullable=False
    )
    status = Column(
        String, default="pending", nullable=False
    )  # pending, installing, completed, failed
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    exit_code = Column(Integer, nullable=True)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    process_pid = Column(Integer, nullable=True)  # Container PID for orphan detection
    process_start_time = Column(
        BigInteger, nullable=True
    )  # Process start time in jiffies for PID uniqueness
    created_at = Column(DateTime, default=utc_now, nullable=False)

    def __repr__(self):
        return f"<PackageInstallJob(id={self.id}, package_id={self.package_id}, status='{self.status}')>"


class Script(Base):
    """Script library - reusable scripts for backup hooks and maintenance"""

    __tablename__ = "scripts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(
        String(255), unique=True, nullable=False, index=True
    )  # "Docker Container Stop"
    description = Column(Text, nullable=True)  # User-friendly description
    file_path = Column(
        String(500), nullable=False
    )  # Relative to /data/scripts/, e.g., "library/docker-stop.sh"
    category = Column(
        String(50), default="custom", nullable=False
    )  # 'template', 'custom', 'system'

    # Execution settings
    timeout = Column(Integer, default=300, nullable=False)  # Default timeout in seconds
    shell = Column(String(50), default="/bin/bash", nullable=False)  # Shell to use

    # Run conditions
    run_on = Column(
        String(50), default="always"
    )  # 'success', 'failure', 'always', 'warning'

    # Metadata
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    created_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Template info
    is_template = Column(
        Boolean, default=False, nullable=False
    )  # Is this a built-in template?
    template_version = Column(String(20), nullable=True)  # For template updates

    # Usage tracking
    usage_count = Column(Integer, default=0, nullable=False)  # How many repos use this?
    last_used_at = Column(DateTime, nullable=True)

    # Script parameters
    parameters = Column(
        Text, nullable=True
    )  # JSON array of parameter definitions: [{'name': 'PARAM', 'type': 'text'|'password', 'default': '', 'description': '', 'required': bool}]

    # Relationships
    repository_scripts = relationship(
        "RepositoryScript", back_populates="script", cascade="all, delete-orphan"
    )
    executions = relationship(
        "ScriptExecution", back_populates="script", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Script(id={self.id}, name='{self.name}', category='{self.category}')>"


class RepositoryScript(Base):
    """Link table between repositories and scripts (many-to-many)"""

    __tablename__ = "repository_scripts"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    script_id = Column(
        Integer,
        ForeignKey("scripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Hook configuration
    hook_type = Column(String(50), nullable=False)  # 'pre-backup', 'post-backup'
    execution_order = Column(
        Float, default=1, nullable=False
    )  # Order in chain (supports decimals for reordering)
    enabled = Column(Boolean, default=True, nullable=False)

    # Per-repository overrides
    custom_timeout = Column(Integer, nullable=True)  # Override script's default timeout
    custom_run_on = Column(
        String(50), nullable=True
    )  # Override script's run_on condition
    continue_on_error = Column(
        Boolean, default=True
    )  # Override script's continue_on_error
    skip_on_failure = Column(
        Boolean, default=False
    )  # Skip backup gracefully if this script fails (not a failure)

    # Script parameter values
    parameter_values = Column(
        Text, nullable=True
    )  # JSON dict of parameter values: {'PARAM': 'value'}. Password-type values are encrypted.

    # Configuration
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    repository = relationship("Repository")
    script = relationship("Script", back_populates="repository_scripts")

    def __repr__(self):
        return f"<RepositoryScript(repo_id={self.repository_id}, script_id={self.script_id}, hook={self.hook_type})>"


class ScriptExecution(Base):
    """Execution history for scripts (for activity feed)"""

    __tablename__ = "script_executions"

    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(
        Integer,
        ForeignKey("scripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id = Column(
        Integer,
        ForeignKey("repositories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )  # NULL for standalone runs
    backup_job_id = Column(
        Integer,
        ForeignKey("backup_jobs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )  # NULL for standalone runs

    # Execution details
    hook_type = Column(
        String(50), nullable=True
    )  # 'pre-backup', 'post-backup', 'standalone', 'maintenance'
    status = Column(
        String(50), nullable=False
    )  # 'pending', 'running', 'completed', 'failed'
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    execution_time = Column(Float, nullable=True)  # Seconds

    # Results
    exit_code = Column(Integer, nullable=True)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    # Context
    triggered_by = Column(
        String(50), nullable=True
    )  # 'scheduled', 'manual', 'backup', 'api'
    triggered_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    script = relationship("Script", back_populates="executions")
    repository = relationship("Repository")
    backup_job = relationship("BackupJob")

    def __repr__(self):
        return f"<ScriptExecution(id={self.id}, script_id={self.script_id}, status='{self.status}')>"
