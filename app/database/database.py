from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from app.config import settings
import os
from pathlib import Path

# Ensure database directory exists before creating engine
if settings.database_url.startswith("sqlite:///"):
    # Extract database file path from URL
    # Format: sqlite:////absolute/path/to/db.db
    db_path = settings.database_url.replace("sqlite:///", "")
    db_dir = os.path.dirname(db_path)

    # Create directory if it doesn't exist
    if db_dir and not os.path.exists(db_dir):
        Path(db_dir).mkdir(parents=True, exist_ok=True)
        print(f"Created database directory: {db_dir}")

# Create database engine with connection pooling
# Note: echo=False disables SQL query logging for performance
# Use LOG_LEVEL=DEBUG environment variable if you need to debug SQL queries
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False  # Always disable SQL logging for performance (creates massive log spam)
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()

def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 