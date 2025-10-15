from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    email = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    path = Column(String, unique=True, index=True)
    encryption = Column(String, default="repokey")
    compression = Column(String, default="lz4")
    passphrase = Column(String, nullable=True)  # Borg repository passphrase (for encrypted repos)
    is_active = Column(Boolean, default=True)
    last_backup = Column(DateTime, nullable=True)
    total_size = Column(String, nullable=True)
    archive_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # New fields for remote repositories
    repository_type = Column(String, default="local")  # local, ssh, sftp
    host = Column(String, nullable=True)  # For SSH repositories
    port = Column(Integer, default=22)  # SSH port
    username = Column(String, nullable=True)  # SSH username
    ssh_key_id = Column(Integer, ForeignKey("ssh_keys.id"), nullable=True)  # Associated SSH key

    # New fields for authentication status
    auth_status = Column(String, default="unknown")  # connected, failed, testing, unknown
    last_auth_test = Column(DateTime, nullable=True)
    auth_error_message = Column(Text, nullable=True)

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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow) 