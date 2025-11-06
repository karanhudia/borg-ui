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
    """Create a test database"""
    # Import app FIRST, before doing anything else
    from app.main import app as application

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()

    # Override BEFORE yielding the session
    application.dependency_overrides[get_db] = override_get_db

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
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
        is_active=True
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
