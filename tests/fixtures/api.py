"""
API fixtures for testing
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Import app lazily to avoid initialization issues
from app.database.database import Base, get_db
from app.database.models import User
from app.core.security import get_password_hash, create_access_token


@pytest.fixture(scope="function")
def test_db():
    """Create a test database with shared session"""
    # Import app FIRST, before doing anything else
    from app.main import app as application

    import os
    
    # Use the file-based DB from environment if available (set in conftest.py)
    db_url = os.environ.get("DATABASE_URL", "sqlite:///:memory:")
    print(f"DEBUG: test_db using URL: {db_url}")
    
    from sqlalchemy.pool import StaticPool, NullPool
    
    from sqlalchemy import event
    
    # Use StaticPool for memory (persists data across sessions), NullPool for file (concurrency safety)
    pool_class = StaticPool if ":memory:" in db_url else NullPool
    
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        poolclass=pool_class,
    )
    
    # Enable WAL mode for file-based SQLite to allow concurrent readers/writers
    # This prevents the background task from hanging on commit() while the test is polling
    if ":memory:" not in db_url:
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
            
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create a single session that will be shared
    shared_session = TestingSessionLocal()

    def override_get_db():
        """Return the same session for all requests in this test"""
        try:
            yield shared_session
        except Exception:
            shared_session.rollback()
            raise

    # Override BEFORE yielding the session
    application.dependency_overrides[get_db] = override_get_db
    
    # PATCHING SERVICES: Ensure background tasks use the same engine/session factory
    from unittest.mock import patch
    
    # We patch the SessionLocal imported in these modules to use our TestingSessionLocal
    # This ensures background tasks (which create their own sessions) connect to the same DB file
    patches = [
        patch("app.services.backup_service.SessionLocal", TestingSessionLocal),
        patch("app.services.restore_service.SessionLocal", TestingSessionLocal),
        patch("app.services.check_service.SessionLocal", TestingSessionLocal),
    ]
    
    for p in patches:
        p.start()

    try:
        yield shared_session
    finally:
        for p in patches:
            p.stop()
            
        shared_session.close()
        # Clean up database tables
        Base.metadata.drop_all(bind=engine)
        application.dependency_overrides.clear()


@pytest.fixture
def test_client(test_db):
    """Create a test client for API testing"""
    # Import app here to avoid initialization on module load
    from app.main import app
    return TestClient(app)


@pytest.fixture
def test_user(test_db):
    """Create a test user in the database"""
    user = User(
        username="testuser",
        password_hash=get_password_hash("testpass123"),
        is_active=True
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def admin_user(test_db):
    """Create an admin user in the database"""
    user = User(
        username="admin",
        password_hash=get_password_hash("admin123"),
        is_active=True,
        is_admin=True  # CRITICAL: Admin user must have admin privileges!
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def auth_token(test_user):
    """Generate an auth token for test user"""
    return create_access_token(data={"sub": test_user.username})


@pytest.fixture
def admin_token(admin_user):
    """Generate an auth token for admin user"""
    return create_access_token(data={"sub": admin_user.username})


@pytest.fixture
def auth_headers(auth_token):
    """Create authorization headers with test user token"""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def admin_headers(admin_token):
    """Create authorization headers with admin token"""
    return {"Authorization": f"Bearer {admin_token}"}
