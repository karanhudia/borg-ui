import os
import secrets
from typing import List, Union
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings"""

    # Application settings
    app_name: str = "Borg Web UI"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # Data directory (for all persistent data) - this is the ONLY path users need to configure
    data_dir: str = "/data"

    # Security settings - auto-generated if not provided
    secret_key: str = ""  # Will be auto-generated on first run
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Database settings - auto-derived from data_dir
    database_url: str = ""  # Will be auto-derived from data_dir

    # Backup settings - auto-derived from data_dir
    borgmatic_backup_path: str = ""  # Deprecated - not needed anymore

    # SSH keys directory - auto-derived from data_dir
    ssh_keys_dir: str = ""  # Will be auto-derived from data_dir

    # Logging settings
    log_level: str = "INFO"
    log_file: str = ""  # Will be auto-derived from data_dir

    # CORS settings - comma-separated string that gets parsed to list
    _cors_origins_str: str = "http://localhost:7879,http://localhost:8000"

    @property
    def cors_origins(self) -> List[str]:
        """Get CORS origins as list"""
        return [origin.strip() for origin in self._cors_origins_str.split(",") if origin.strip()]

    @cors_origins.setter
    def cors_origins(self, value: Union[str, List[str]]):
        """Set CORS origins from string or list"""
        if isinstance(value, list):
            self._cors_origins_str = ",".join(value)
        else:
            self._cors_origins_str = value
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8081
    workers: int = 2
    
    # Cache settings
    cache_enabled: bool = True
    cache_ttl: int = 300  # 5 minutes
    
    # Backup settings
    max_backup_jobs: int = 5
    backup_timeout: int = 3600  # 1 hour
    
    # Health check settings
    health_check_interval: int = 30
    health_check_timeout: int = 10
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"
        # Map CORS_ORIGINS env var to _cors_origins_str field
        fields = {
            "_cors_origins_str": {
                "env": "CORS_ORIGINS"
            }
        }

# Create settings instance
settings = Settings()

# Override data_dir from environment if provided
settings.data_dir = os.getenv("DATA_DIR", settings.data_dir)

# AUTO-DERIVE all paths from data_dir
# Users only need to configure data_dir (via volume mount), everything else is automatic

# 1. Database URL - always derived from data_dir
env_database_url = os.getenv("DATABASE_URL")
if env_database_url:
    settings.database_url = env_database_url
else:
    # Auto-derive: sqlite:////data/borg.db
    settings.database_url = f"sqlite:///{settings.data_dir}/borg.db"

# 2. SSH keys directory - always derived from data_dir
settings.ssh_keys_dir = f"{settings.data_dir}/ssh_keys"

# 3. Log file - always derived from data_dir
settings.log_file = f"{settings.data_dir}/logs/borg-ui.log"

# 4. SECRET_KEY - auto-generate on first run if not provided
secret_key_file = Path(settings.data_dir) / ".secret_key"
env_secret_key = os.getenv("SECRET_KEY")

if env_secret_key:
    # Use environment variable if provided
    settings.secret_key = env_secret_key
elif secret_key_file.exists():
    # Load from persistent file
    settings.secret_key = secret_key_file.read_text().strip()
else:
    # Auto-generate and persist
    settings.secret_key = secrets.token_urlsafe(32)
    # Create data directory if it doesn't exist
    secret_key_file.parent.mkdir(parents=True, exist_ok=True)
    secret_key_file.write_text(settings.secret_key)
    secret_key_file.chmod(0o600)  # Secure permissions
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Auto-generated SECRET_KEY and saved to {secret_key_file}")

# Other environment overrides
settings.environment = os.getenv("ENVIRONMENT", settings.environment)
settings.log_level = os.getenv("LOG_LEVEL", settings.log_level)
settings.port = int(os.getenv("PORT", settings.port))

# Environment-specific overrides
if settings.environment == "production":
    settings.debug = False
elif settings.environment == "development":
    settings.debug = True
    settings.log_level = os.getenv("LOG_LEVEL", "DEBUG")

# Security validation
def validate_security_settings():
    """Validate critical security settings"""
    issues = []

    # Minimal validation - most security concerns are now auto-handled
    if settings.environment == "production":
        if len(settings.secret_key) < 32:
            issues.append(
                "WARNING: SECRET_KEY is too short (< 32 characters). "
                "Auto-generation failed or manual override is weak."
            )

        if settings.debug:
            issues.append(
                "WARNING: Debug mode is enabled in production. "
                "Set DEBUG=false or ENVIRONMENT=production to disable."
            )

    # Log warnings
    if issues:
        import logging
        logger = logging.getLogger(__name__)
        for issue in issues:
            logger.warning(issue)

# Run validation
validate_security_settings() 