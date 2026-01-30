from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float, BigInteger, Table
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
    password_hash = Column(String)
    email = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    must_change_password = Column(Boolean, default=False)  # Force password change on next login
    analytics_enabled = Column(Boolean, default=True)  # User's analytics preference
    analytics_consent_given = Column(Boolean, default=False)  # Whether user has responded to consent banner
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    path = Column(String, unique=True, index=True)
    encryption = Column(String, default="repokey")
    compression = Column(String, default="lz4")
    passphrase = Column(String, nullable=True)  # Borg repository passphrase (for encrypted repos)
    has_keyfile = Column(Boolean, default=False)  # Whether repository has a keyfile (keyfile/keyfile-blake2 encryption)
    source_directories = Column(Text, nullable=True)  # JSON array of directories to backup
    exclude_patterns = Column(Text, nullable=True)  # JSON array of exclude patterns (e.g., ["*.log", "*.tmp"])
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
    ssh_key_id = Column(Integer, ForeignKey("ssh_keys.id"), nullable=True)  # Associated SSH key
    connection_id = Column(Integer, ForeignKey("ssh_connections.id"), nullable=True)  # Associated SSH connection (preferred over host/port/username)
    remote_path = Column(String, nullable=True)  # Path to borg binary on remote server (e.g., /usr/local/bin/borg)

    # New fields for authentication status
    auth_status = Column(String, default="unknown")  # connected, failed, testing, unknown
    last_auth_test = Column(DateTime, nullable=True)
    auth_error_message = Column(Text, nullable=True)

    # Backup hooks
    pre_backup_script = Column(Text, nullable=True)  # Shell script to run before backup
    post_backup_script = Column(Text, nullable=True)  # Shell script to run after backup
    hook_timeout = Column(Integer, default=300)  # Hook timeout in seconds (legacy, kept for compatibility)
    pre_hook_timeout = Column(Integer, default=300)  # Pre-backup hook timeout in seconds
    post_hook_timeout = Column(Integer, default=300)  # Post-backup hook timeout in seconds
    continue_on_hook_failure = Column(Boolean, default=False)  # Whether to continue backup if pre-hook fails

    # Repository mode (for observability-only repos)
    mode = Column(String, default="full")  # full: backups + observability, observe: observability-only
    bypass_lock = Column(Boolean, default=False)  # Use --bypass-lock for read-only storage access (observe-only repos)

    # Custom flags for borg create command (advanced users)
    custom_flags = Column(Text, nullable=True)  # Custom command-line flags for borg create (e.g., "--stats --progress")

    # Data source location (for pull-based backups)
    source_ssh_connection_id = Column(Integer, ForeignKey("ssh_connections.id"), nullable=True)  # SSH connection for remote data source

    # Scheduled checks
    check_cron_expression = Column(String, nullable=True)  # NULL = disabled, cron expression for schedule
    last_scheduled_check = Column(DateTime, nullable=True)  # Last scheduled check execution time
    next_scheduled_check = Column(DateTime, nullable=True)  # Next scheduled check time
    check_max_duration = Column(Integer, default=3600)  # Max check duration in seconds (for partial checks)
    notify_on_check_success = Column(Boolean, default=False, nullable=False)  # Per-repository override
    notify_on_check_failure = Column(Boolean, default=True, nullable=False)  # Per-repository override

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
    is_system_key = Column(Boolean, default=False, index=True)  # Identifies the system SSH key
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
    default_path = Column(String, nullable=True)  # Default starting path for SSH browsing (e.g., /home for Hetzner Storage Box)
    mount_point = Column(String, nullable=True)  # Logical mount point (e.g., /hetzner, /homeserver)
    status = Column(String, default="unknown")  # connected, failed, testing, unknown
    last_test = Column(DateTime, nullable=True)
    last_success = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    # Storage information
    storage_total = Column(BigInteger, nullable=True)  # Total storage in bytes
    storage_used = Column(BigInteger, nullable=True)  # Used storage in bytes
    storage_available = Column(BigInteger, nullable=True)  # Available storage in bytes
    storage_percent_used = Column(Float, nullable=True)  # Percentage of storage used
    last_storage_check = Column(DateTime, nullable=True)  # Last time storage was checked

    # Remote backup source configuration
    is_backup_source = Column(Boolean, default=False)  # Mark this connection as a backup source
    borg_binary_path = Column(String, default="/usr/bin/borg")  # Path to borg on remote host
    borg_version = Column(String, nullable=True)  # Detected borg version
    last_borg_check = Column(DateTime, nullable=True)  # Last time borg was verified

    # SSH key deployment options
    use_sftp_mode = Column(Boolean, default=True, nullable=False)  # Use SFTP mode (-s flag) for ssh-copy-id (required by Hetzner, breaks Synology)

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
    status = Column(String, default="pending")  # pending, running, completed, completed_with_warnings, failed
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)  # Full logs (stored after completion)
    log_file_path = Column(String, nullable=True)  # Path to streaming log file
    scheduled_job_id = Column(Integer, ForeignKey("scheduled_jobs.id"), nullable=True)  # NULL for manual backups

    # Detailed progress fields from Borg JSON output
    original_size = Column(BigInteger, default=0)  # Original uncompressed size in bytes
    compressed_size = Column(BigInteger, default=0)  # Compressed size in bytes
    deduplicated_size = Column(BigInteger, default=0)  # Deduplicated size in bytes
    nfiles = Column(Integer, default=0)  # Number of files processed
    current_file = Column(Text, nullable=True)  # Current file being processed
    progress_percent = Column(Float, default=0.0)  # Progress percentage
    backup_speed = Column(Float, default=0.0)  # Current backup speed in MB/s
    total_expected_size = Column(BigInteger, default=0)  # Total size of source directories (calculated before backup)
    estimated_time_remaining = Column(Integer, default=0)  # Estimated seconds remaining

    # Maintenance status tracking
    maintenance_status = Column(String, nullable=True)  # null, "running_prune", "prune_completed", "prune_failed", "running_compact", "compact_completed", "compact_failed", "maintenance_completed"

    # Remote backup execution
    execution_mode = Column(String, default="local")  # "local" or "remote_ssh"
    source_ssh_connection_id = Column(Integer, ForeignKey("ssh_connections.id"), nullable=True)  # SSH connection for remote execution
    remote_process_pid = Column(Integer, nullable=True)  # PID on remote host
    remote_hostname = Column(String, nullable=True)  # Remote hostname for reference

    created_at = Column(DateTime, default=utc_now)

class RestoreJob(Base):
    __tablename__ = "restore_jobs"

    id = Column(Integer, primary_key=True, index=True)
    repository = Column(String)  # Repository path
    archive = Column(String)  # Archive name
    destination = Column(String)  # Restore destination path
    status = Column(String, default="pending")  # pending, running, completed, failed, cancelled
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)  # Full logs (stored after completion)

    # Progress tracking fields
    nfiles = Column(Integer, default=0)  # Number of files restored
    current_file = Column(Text, nullable=True)  # Current file being restored
    progress_percent = Column(Float, default=0.0)  # Progress percentage

    created_at = Column(DateTime, default=utc_now)

class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    cron_expression = Column(String, nullable=False)  # e.g., "0 2 * * *" for daily at 2 AM
    repository = Column(String, nullable=True)  # Repository path/ID to backup (legacy, for single-repo schedules)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=True)  # For single-repo schedules (nullable for multi-repo)
    enabled = Column(Boolean, default=True)  # Whether the job is active
    last_run = Column(DateTime, nullable=True)  # Last execution time
    next_run = Column(DateTime, nullable=True)  # Next scheduled execution time
    description = Column(Text, nullable=True)  # User description of the job
    archive_name_template = Column(String, nullable=True)  # Template for archive names (e.g., "{job_name}-{now}")

    # Multi-repository schedule settings
    run_repository_scripts = Column(Boolean, default=False, nullable=False)  # Whether to run per-repository pre/post scripts
    pre_backup_script_id = Column(Integer, ForeignKey("scripts.id"), nullable=True)  # Schedule-level pre-backup script (runs once)
    post_backup_script_id = Column(Integer, ForeignKey("scripts.id"), nullable=True)  # Schedule-level post-backup script (runs once)

    # Prune and compact settings
    run_prune_after = Column(Boolean, default=False)  # Run prune after backup
    run_compact_after = Column(Boolean, default=False)  # Run compact after prune
    prune_keep_hourly = Column(Integer, default=0)  # Keep N hourly backups (0 = disabled)
    prune_keep_daily = Column(Integer, default=7)  # Keep N daily backups
    prune_keep_weekly = Column(Integer, default=4)  # Keep N weekly backups
    prune_keep_monthly = Column(Integer, default=6)  # Keep N monthly backups
    prune_keep_quarterly = Column(Integer, default=0)  # Keep N quarterly backups (0 = disabled)
    prune_keep_yearly = Column(Integer, default=1)  # Keep N yearly backups
    last_prune = Column(DateTime, nullable=True)  # Last prune execution time
    last_compact = Column(DateTime, nullable=True)  # Last compact execution time

    # Remote backup execution
    execution_mode = Column(String, default="local")  # "local" or "remote_ssh"
    source_ssh_connection_id = Column(Integer, ForeignKey("ssh_connections.id"), nullable=True)  # SSH connection for remote execution

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, nullable=True)

class ScheduledJobRepository(Base):
    """Junction table for multi-repository scheduled jobs"""
    __tablename__ = "scheduled_job_repositories"

    id = Column(Integer, primary_key=True, index=True)
    scheduled_job_id = Column(Integer, ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    execution_order = Column(Integer, nullable=False)  # Order in which repositories should be backed up

    created_at = Column(DateTime, default=utc_now)

    def __repr__(self):
        return f"<ScheduledJobRepository(schedule_id={self.scheduled_job_id}, repo_id={self.repository_id}, order={self.execution_order})>"

class CheckJob(Base):
    __tablename__ = "check_jobs"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    repository_path = Column(String, nullable=True)  # Captured at job creation for display even if repo is deleted
    status = Column(String, default="pending")  # pending, running, completed, failed, cancelled
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)  # 0-100 percentage
    progress_message = Column(String, nullable=True)  # Current progress message (e.g., "Checking segments 25%")
    error_message = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)  # Deprecated: kept for backwards compatibility, use log_file_path instead
    log_file_path = Column(String, nullable=True)  # Path to log file on disk
    has_logs = Column(Boolean, default=False)  # Flag indicating if logs are available
    max_duration = Column(Integer, nullable=True)  # Maximum duration in seconds (for partial checks)
    process_pid = Column(Integer, nullable=True)  # Container PID for orphan detection
    process_start_time = Column(BigInteger, nullable=True)  # Process start time in jiffies for PID uniqueness
    scheduled_check = Column(Boolean, default=False, nullable=False)  # True if triggered by scheduler, False if manual
    created_at = Column(DateTime, default=utc_now)

class CompactJob(Base):
    __tablename__ = "compact_jobs"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    repository_path = Column(String, nullable=True)  # Captured at job creation for display even if repo is deleted
    status = Column(String, default="pending")  # pending, running, completed, failed, cancelled
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)  # 0-100 percentage
    progress_message = Column(String, nullable=True)  # Current progress message (e.g., "Compacting segments 50%")
    error_message = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)  # Deprecated: kept for backwards compatibility, use log_file_path instead
    log_file_path = Column(String, nullable=True)  # Path to log file on disk
    has_logs = Column(Boolean, default=False)  # Flag indicating if logs are available
    scheduled_compact = Column(Boolean, default=False, nullable=False)  # True if triggered by scheduler, False if manual
    process_pid = Column(Integer, nullable=True)  # Container PID for orphan detection
    process_start_time = Column(BigInteger, nullable=True)  # Process start time in jiffies for PID uniqueness
    created_at = Column(DateTime, default=utc_now)

class PruneJob(Base):
    __tablename__ = "prune_jobs"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    repository_path = Column(String, nullable=True)  # Captured at job creation for display even if repo is deleted
    status = Column(String, default="pending")  # pending, running, completed, failed, cancelled
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)  # Deprecated: kept for backwards compatibility, use log_file_path instead
    log_file_path = Column(String, nullable=True)  # Path to log file on disk
    has_logs = Column(Boolean, default=False)  # Flag indicating if logs are available
    scheduled_prune = Column(Boolean, default=False, nullable=False)  # True if triggered by scheduler, False if manual
    created_at = Column(DateTime, default=utc_now)

class DeleteArchiveJob(Base):
    __tablename__ = "delete_archive_jobs"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    repository_path = Column(String, nullable=True)  # Captured at job creation for display even if repo is deleted
    archive_name = Column(String, nullable=False)  # Name of the archive being deleted
    status = Column(String, default="pending")  # pending, running, completed, failed, cancelled
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)  # 0-100 percentage
    progress_message = Column(String, nullable=True)  # Current progress message
    error_message = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)  # Deprecated: kept for backwards compatibility, use log_file_path instead
    log_file_path = Column(String, nullable=True)  # Path to log file on disk
    has_logs = Column(Boolean, default=False)  # Flag indicating if logs are available
    process_pid = Column(Integer, nullable=True)  # Container PID for orphan detection
    process_start_time = Column(BigInteger, nullable=True)  # Process start time in jiffies for PID uniqueness
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

    max_concurrent_backups = Column(Integer, default=1)
    log_retention_days = Column(Integer, default=30)
    log_save_policy = Column(String, default="failed_and_warnings")  # Options: "failed_only", "failed_and_warnings", "all_jobs"
    log_max_total_size_mb = Column(Integer, default=500)  # Maximum total size of all log files in MB
    log_cleanup_on_startup = Column(Boolean, default=True)  # Run log cleanup on application startup
    cache_ttl_minutes = Column(Integer, default=120)  # Cache TTL in minutes (2 hours default)
    cache_max_size_mb = Column(Integer, default=2048)  # Maximum cache size in MB (2GB default)
    redis_url = Column(String, nullable=True)  # External Redis URL (e.g., redis://host:6379/0)
    browse_max_items = Column(Integer, default=1_000_000)  # Maximum items to load when browsing archives
    browse_max_memory_mb = Column(Integer, default=1024)  # Maximum memory (MB) for archive browsing
    stats_refresh_interval_minutes = Column(Integer, default=60)  # How often to refresh repository stats (0 = disabled)
    last_stats_refresh = Column(DateTime, nullable=True)  # Last time stats were refreshed
    email_notifications = Column(Boolean, default=False)
    webhook_url = Column(String, nullable=True)
    auto_cleanup = Column(Boolean, default=False)
    cleanup_retention_days = Column(Integer, default=90)

    # Beta features
    use_new_wizard = Column(Boolean, default=False, nullable=False)  # Enable new repository wizard (beta)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


# Association table for repository notification filters
repository_notifications = Table(
    'repository_notifications',
    Base.metadata,
    Column('notification_setting_id', Integer, ForeignKey('notification_settings.id', ondelete='CASCADE'), primary_key=True),
    Column('repository_id', Integer, ForeignKey('repositories.id', ondelete='CASCADE'), primary_key=True)
)


class NotificationSettings(Base):
    """
    Notification settings model.

    Stores Apprise-compatible notification URLs and configuration.
    """
    __tablename__ = "notification_settings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)  # User-friendly name (e.g., "Slack - DevOps Channel")
    service_url = Column(Text, nullable=False)  # Apprise URL (e.g., "slack://TokenA/TokenB/TokenC/")
    enabled = Column(Boolean, default=True, nullable=False)

    # Customization
    title_prefix = Column(String(100), nullable=True)  # Optional custom prefix for notification titles (e.g., "[Production]")
    include_job_name_in_title = Column(Boolean, default=False, nullable=False)  # Include job/schedule name in notification title
    # Note: JSON data is automatically sent for json:// and jsons:// webhook URLs (no field needed)

    # Event triggers
    notify_on_backup_start = Column(Boolean, default=False, nullable=False)
    notify_on_backup_success = Column(Boolean, default=False, nullable=False)
    notify_on_backup_failure = Column(Boolean, default=True, nullable=False)
    notify_on_restore_success = Column(Boolean, default=False, nullable=False)
    notify_on_restore_failure = Column(Boolean, default=True, nullable=False)
    notify_on_schedule_failure = Column(Boolean, default=True, nullable=False)
    notify_on_check_success = Column(Boolean, default=False, nullable=False)
    notify_on_check_failure = Column(Boolean, default=True, nullable=False)

    # Repository filtering
    monitor_all_repositories = Column(Boolean, default=True, nullable=False)  # If True, applies to all repos

    # Relationships
    repositories = relationship('Repository', secondary=repository_notifications, backref='notification_settings')

    # Timestamps
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    last_used_at = Column(DateTime, nullable=True)  # Last successful notification sent

    def __repr__(self):
        return f"<NotificationSettings(id={self.id}, name='{self.name}', enabled={self.enabled})>"

class InstalledPackage(Base):
    __tablename__ = "installed_packages"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)  # Package name (e.g., "wakeonlan")
    install_command = Column(String, nullable=False)  # Command to install (e.g., "apt-get install -y wakeonlan")
    description = Column(String, nullable=True)  # Optional description
    status = Column(String, default="pending", nullable=False)  # pending, installed, failed
    install_log = Column(Text, nullable=True)  # Installation output/logs
    installed_at = Column(DateTime, nullable=True)  # When successfully installed
    last_check = Column(DateTime, nullable=True)  # Last time we verified it exists
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    def __repr__(self):
        return f"<InstalledPackage(id={self.id}, name='{self.name}', status='{self.status}')>"

class PackageInstallJob(Base):
    __tablename__ = "package_install_jobs"

    id = Column(Integer, primary_key=True, index=True)
    package_id = Column(Integer, ForeignKey("installed_packages.id"), nullable=False)
    status = Column(String, default="pending", nullable=False)  # pending, installing, completed, failed
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    exit_code = Column(Integer, nullable=True)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    process_pid = Column(Integer, nullable=True)  # Container PID for orphan detection
    process_start_time = Column(BigInteger, nullable=True)  # Process start time in jiffies for PID uniqueness
    created_at = Column(DateTime, default=utc_now, nullable=False)

    def __repr__(self):
        return f"<PackageInstallJob(id={self.id}, package_id={self.package_id}, status='{self.status}')>"

class Script(Base):
    """Script library - reusable scripts for backup hooks and maintenance"""
    __tablename__ = "scripts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)  # "Docker Container Stop"
    description = Column(Text, nullable=True)  # User-friendly description
    file_path = Column(String(500), nullable=False)  # Relative to /data/scripts/, e.g., "library/docker-stop.sh"
    category = Column(String(50), default='custom', nullable=False)  # 'template', 'custom', 'system'

    # Execution settings
    timeout = Column(Integer, default=300, nullable=False)  # Default timeout in seconds
    shell = Column(String(50), default='/bin/bash', nullable=False)  # Shell to use

    # Run conditions
    run_on = Column(String(50), default='always')  # 'success', 'failure', 'always', 'warning'

    # Metadata
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Template info
    is_template = Column(Boolean, default=False, nullable=False)  # Is this a built-in template?
    template_version = Column(String(20), nullable=True)  # For template updates

    # Usage tracking
    usage_count = Column(Integer, default=0, nullable=False)  # How many repos use this?
    last_used_at = Column(DateTime, nullable=True)

    # Relationships
    repository_scripts = relationship("RepositoryScript", back_populates="script", cascade="all, delete-orphan")
    executions = relationship("ScriptExecution", back_populates="script", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Script(id={self.id}, name='{self.name}', category='{self.category}')>"

class RepositoryScript(Base):
    """Link table between repositories and scripts (many-to-many)"""
    __tablename__ = "repository_scripts"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    script_id = Column(Integer, ForeignKey("scripts.id", ondelete="CASCADE"), nullable=False, index=True)

    # Hook configuration
    hook_type = Column(String(50), nullable=False)  # 'pre-backup', 'post-backup'
    execution_order = Column(Float, default=1, nullable=False)  # Order in chain (supports decimals for reordering)
    enabled = Column(Boolean, default=True, nullable=False)

    # Per-repository overrides
    custom_timeout = Column(Integer, nullable=True)  # Override script's default timeout
    custom_run_on = Column(String(50), nullable=True)  # Override script's run_on condition
    continue_on_error = Column(Boolean, default=True)  # Override script's continue_on_error

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
    script_id = Column(Integer, ForeignKey("scripts.id"), nullable=False, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=True, index=True)  # NULL for standalone runs
    backup_job_id = Column(Integer, ForeignKey("backup_jobs.id"), nullable=True, index=True)  # NULL for standalone runs

    # Execution details
    hook_type = Column(String(50), nullable=True)  # 'pre-backup', 'post-backup', 'standalone', 'maintenance'
    status = Column(String(50), nullable=False)  # 'pending', 'running', 'completed', 'failed'
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    execution_time = Column(Float, nullable=True)  # Seconds

    # Results
    exit_code = Column(Integer, nullable=True)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    # Context
    triggered_by = Column(String(50), nullable=True)  # 'scheduled', 'manual', 'backup', 'api'
    triggered_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    script = relationship("Script", back_populates="executions")
    repository = relationship("Repository")
    backup_job = relationship("BackupJob")

    def __repr__(self):
        return f"<ScriptExecution(id={self.id}, script_id={self.script_id}, status='{self.status}')>"
