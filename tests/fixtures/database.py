"""
Database fixtures for testing
"""

import pytest
from types import MappingProxyType
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.database.models import Repository, User  # noqa: F401 — ensures all models register with Base.metadata


@pytest.fixture(scope="session")
def fixture_password_hashes():
    """Reuse immutable fixed credentials hashed at the real production cost."""
    from app.core.security import get_password_hash

    return MappingProxyType(
        {
            "testpass123": get_password_hash("testpass123"),
            "admin123": get_password_hash("admin123"),
        }
    )


@pytest.fixture(scope="function")
def db_engine():
    """Create an in-memory SQLite database engine for testing"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a new database session for a test with rollback"""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def db_session_commit(db_engine):
    """Create a new database session that commits changes (for background task tests)"""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        # We don't rollback here because we want the background task to see the changes
        # But we do close the session
        session.close()


@pytest.fixture
def sample_user(db_session: Session, fixture_password_hashes):
    """Create a sample user for testing"""
    user = User(
        username="testuser",
        password_hash=fixture_password_hashes["testpass123"],
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def sample_repository(db_session: Session):
    """Create a sample repository for testing"""
    import json

    repo = Repository(
        name="Test Repository",
        path="/tmp/test-repo",
        encryption="repokey",
        passphrase="testpassword",  # Added passphrase
        compression="lz4",
        repository_type="local",
        source_directories=json.dumps(["/home/user/documents"]),
        exclude_patterns=json.dumps(["*.tmp", "*.cache"]),
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


@pytest.fixture
def multiple_repositories(db_session: Session):
    """Create multiple repositories for testing"""
    import json

    repos = [
        Repository(
            name=f"Repo {i}",
            path=f"/tmp/repo-{i}",
            encryption="none" if i % 2 == 0 else "repokey",
            passphrase="testpassword"
            if i % 2 != 0
            else None,  # Added passphrase for encrypted repos
            compression="lz4",
            repository_type="local",
            source_directories=json.dumps([f"/home/user/repo{i}"]),
            exclude_patterns=json.dumps(["*.tmp"]),
        )
        for i in range(3)
    ]
    for repo in repos:
        db_session.add(repo)
    db_session.commit()
    return repos
