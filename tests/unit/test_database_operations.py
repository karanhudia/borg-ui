"""
Unit tests for database CRUD operations
"""
import pytest
from sqlalchemy.orm import Session

from app.database.models import Repository, User
from app.core.security import get_password_hash, verify_password


@pytest.mark.unit
class TestRepositoryCRUD:
    """Test repository database operations"""

    def test_create_repository(self, db_session: Session):
        """Test creating a repository"""
        repo = Repository(
            name="Test Repo",
            path="/tmp/test-repo",
            encryption="repokey",
            compression="lz4",
            repository_type="local"
        )
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        assert repo.id is not None
        assert repo.name == "Test Repo"
        assert repo.path == "/tmp/test-repo"

    def test_read_repository(self, db_session: Session, sample_repository):
        """Test reading a repository"""
        repo = db_session.query(Repository).filter_by(id=sample_repository.id).first()

        assert repo is not None
        assert repo.name == sample_repository.name
        assert repo.path == sample_repository.path

    def test_update_repository(self, db_session: Session, sample_repository):
        """Test updating a repository"""
        sample_repository.name = "Updated Name"
        sample_repository.compression = "zstd"
        db_session.commit()
        db_session.refresh(sample_repository)

        assert sample_repository.name == "Updated Name"
        assert sample_repository.compression == "zstd"

    def test_delete_repository(self, db_session: Session, sample_repository):
        """Test deleting a repository"""
        repo_id = sample_repository.id
        db_session.delete(sample_repository)
        db_session.commit()

        deleted = db_session.query(Repository).filter_by(id=repo_id).first()
        assert deleted is None

    def test_list_repositories(self, db_session: Session, multiple_repositories):
        """Test listing all repositories"""
        repos = db_session.query(Repository).all()

        assert len(repos) == 3
        assert all(isinstance(repo, Repository) for repo in repos)

    def test_filter_repositories_by_encryption(self, db_session: Session, multiple_repositories):
        """Test filtering repositories by encryption type"""
        encrypted_repos = db_session.query(Repository).filter_by(encryption="repokey").all()

        assert len(encrypted_repos) > 0
        assert all(repo.encryption == "repokey" for repo in encrypted_repos)


@pytest.mark.unit
class TestUserCRUD:
    """Test user database operations"""

    def test_create_user(self, db_session: Session):
        """Test creating a user"""
        password_hash = get_password_hash("testpassword")
        user = User(
            username="newuser",
            password_hash=password_hash,
            is_active=True
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.id is not None
        assert user.username == "newuser"
        assert verify_password("testpassword", user.password_hash)

    def test_read_user(self, db_session: Session, sample_user):
        """Test reading a user"""
        user = db_session.query(User).filter_by(id=sample_user.id).first()

        assert user is not None
        assert user.username == sample_user.username
        assert user.is_active == sample_user.is_active

    def test_update_user(self, db_session: Session, sample_user):
        """Test updating a user"""
        sample_user.is_active = False
        db_session.commit()
        db_session.refresh(sample_user)

        assert sample_user.is_active is False

    def test_delete_user(self, db_session: Session, sample_user):
        """Test deleting a user"""
        user_id = sample_user.id
        db_session.delete(sample_user)
        db_session.commit()

        deleted = db_session.query(User).filter_by(id=user_id).first()
        assert deleted is None

    def test_find_user_by_username(self, db_session: Session, sample_user):
        """Test finding a user by username"""
        user = db_session.query(User).filter_by(username=sample_user.username).first()

        assert user is not None
        assert user.id == sample_user.id

    def test_unique_username_constraint(self, db_session: Session, sample_user):
        """Test that usernames must be unique"""
        duplicate_user = User(
            username=sample_user.username,  # Same username
            password_hash="different_hash",
            is_active=True
        )
        db_session.add(duplicate_user)

        with pytest.raises(Exception):  # Will raise IntegrityError
            db_session.commit()
