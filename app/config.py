import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings"""
    
    # Application settings
    app_name: str = "Borgmatic Web UI"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Security settings
    secret_key: str = "your-secret-key-change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # Database settings
    database_url: str = "sqlite:///./borgmatic.db"
    
    # Borgmatic settings
    borgmatic_config_path: str = "/app/config/borgmatic.yaml"
    borgmatic_backup_path: str = "/backups"

    # SSH keys directory (persistent storage for key files)
    ssh_keys_dir: str = "/app/data/ssh_keys"
    
    # Logging settings
    log_level: str = "INFO"
    log_file: str = "/app/logs/borgmatic-ui.log"
    
    # CORS settings
    cors_origins: List[str] = ["http://localhost:7879", "http://localhost:8000"]
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
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

# Create settings instance
settings = Settings()

# Environment-specific overrides
if os.getenv("ENVIRONMENT") == "production":
    settings.debug = False
    # Handle CORS_ORIGINS as comma-separated string
    cors_origins_env = os.getenv("CORS_ORIGINS", "")
    if cors_origins_env:
        settings.cors_origins = [origin.strip() for origin in cors_origins_env.split(",")]
elif os.getenv("ENVIRONMENT") == "development":
    settings.debug = True
    settings.log_level = "DEBUG"

# Override with environment variables if present
settings.secret_key = os.getenv("SECRET_KEY", settings.secret_key)
settings.borgmatic_config_path = os.getenv("BORGMATIC_CONFIG_PATH", settings.borgmatic_config_path)
settings.borgmatic_backup_path = os.getenv("BORGMATIC_BACKUP_PATH", settings.borgmatic_backup_path)
settings.log_level = os.getenv("LOG_LEVEL", settings.log_level)
settings.database_url = os.getenv("DATABASE_URL", settings.database_url) 