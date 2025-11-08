from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float, BigInteger
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
    source_directories = Column(Text, nullable=True)  # JSON array of directories to backup
    exclude_patterns = Column(Text, nullable=True)  # JSON array of exclude patterns (e.g., ["*.log", "*.tmp"])
    last_backup = Column(DateTime, nullable=True)
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
    remote_path = Column(String, nullable=True)  # Path to borg binary on remote server (e.g., /usr/local/bin/borg)

    # New fields for authentication status
    auth_status = Column(String, default="unknown")  # connected, failed, testing, unknown
    last_auth_test = Column(DateTime, nullable=True)
    auth_error_message = Column(Text, nullable=True)

    # Backup hooks
    pre_backup_script = Column(Text, nullable=True)  # Shell script to run before backup
    post_backup_script = Column(Text, nullable=True)  # Shell script to run after backup
    hook_timeout = Column(Integer, default=300)  # Hook timeout in seconds (default 5 minutes)
    continue_on_hook_failure = Column(Boolean, default=False)  # Whether to continue backup if pre-hook fails

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
    connections = relationship("SSHConnection", back_populates="ssh_key", cascade="all, delete-orphan")

class SSHConnection(Base):
    __tablename__ = "ssh_connections"
    
    id = Column(Integer, primary_key=True, index=True)
    ssh_key_id = Column(Integer, ForeignKey("ssh_keys.id"))
    host = Column(String)
    username = Column(String)
    port = Column(Integer, default=22)
    status = Column(String, default="unknown")  # connected, failed, testing, unknown
    last_test = Column(DateTime, nullable=True)
    last_success = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
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
    status = Column(String, default="pending")  # pending, running, completed, failed
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
    repository = Column(String, nullable=True)  # Repository path/ID to backup
    config_file = Column(String, nullable=True)  # Optional config file path
    enabled = Column(Boolean, default=True)  # Whether the job is active
    last_run = Column(DateTime, nullable=True)  # Last execution time
    next_run = Column(DateTime, nullable=True)  # Next scheduled execution time
    description = Column(Text, nullable=True)  # User description of the job

    # Prune and compact settings
    run_prune_after = Column(Boolean, default=False)  # Run prune after backup
    run_compact_after = Column(Boolean, default=False)  # Run compact after prune
    prune_keep_daily = Column(Integer, default=7)  # Keep N daily backups
    prune_keep_weekly = Column(Integer, default=4)  # Keep N weekly backups
    prune_keep_monthly = Column(Integer, default=6)  # Keep N monthly backups
    prune_keep_yearly = Column(Integer, default=1)  # Keep N yearly backups
    last_prune = Column(DateTime, nullable=True)  # Last prune execution time
    last_compact = Column(DateTime, nullable=True)  # Last compact execution time

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, nullable=True) 